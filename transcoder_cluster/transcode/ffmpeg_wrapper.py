"""
FFmpeg 封装模块

提供视频信息获取、转码执行等功能
"""

import os
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from transcoder_cluster.utils.config import config
from transcoder_cluster.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class VideoInfo:
    """视频信息"""

    duration: float
    width: int
    height: int
    codec: str
    bitrate: int
    fps: float
    format: str

    @property
    def resolution(self) -> str:
        return f"{self.width}x{self.height}"


class FFmpegWrapper:
    """
    FFmpeg 封装类

    提供视频信息获取、转码执行等功能
    """

    def __init__(self, ffmpeg_path: str = None):
        """
        初始化 FFmpeg 封装

        Args:
            ffmpeg_path: FFmpeg 可执行文件路径
        """
        self.ffmpeg_path = ffmpeg_path or config.ffmpeg_path
        self._verify_ffmpeg()

    def _verify_ffmpeg(self) -> None:
        """验证 FFmpeg 是否可用"""
        try:
            result = subprocess.run([self.ffmpeg_path, "-version"], capture_output=True, text=True)
            if result.returncode == 0:
                logger.debug(f"FFmpeg 可用: {result.stdout.split()[2]}")
            else:
                raise RuntimeError("FFmpeg 不可用")
        except FileNotFoundError:
            raise RuntimeError(f"FFmpeg 未找到: {self.ffmpeg_path}")

    def get_video_info(self, video_path: str) -> Optional[VideoInfo]:
        """
        获取视频信息

        Args:
            video_path: 视频文件路径

        Returns:
            视频信息对象
        """
        try:
            import ffmpeg

            probe = ffmpeg.probe(video_path)

            # 获取视频流
            video_stream = None
            for stream in probe["streams"]:
                if stream["codec_type"] == "video":
                    video_stream = stream
                    break

            if not video_stream:
                return None

            # 解析帧率
            fps_str = video_stream.get("r_frame_rate", "0/1")
            if "/" in fps_str:
                num, den = map(int, fps_str.split("/"))
                fps = num / den if den != 0 else 0
            else:
                fps = float(fps_str)

            return VideoInfo(
                duration=float(probe["format"]["duration"]),
                width=int(video_stream.get("width", 0)),
                height=int(video_stream.get("height", 0)),
                codec=video_stream.get("codec_name", "unknown"),
                bitrate=int(probe["format"].get("bit_rate", 0)),
                fps=fps,
                format=probe["format"]["format_name"],
            )

        except Exception as e:
            logger.error(f"获取视频信息失败: {e}")
            return None

    def transcode(
        self,
        input_path: str,
        output_path: str,
        args: List[str],
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> bool:
        """
        执行转码

        Args:
            input_path: 输入文件路径
            output_path: 输出文件路径
            args: FFmpeg 参数列表
            progress_callback: 进度回调函数

        Returns:
            是否成功
        """
        cmd = [self.ffmpeg_path, "-y", "-i", input_path] + args + [output_path]
        logger.info(f"执行转码: {' '.join(cmd)}")

        # 获取视频时长用于计算进度
        video_info = self.get_video_info(input_path)
        duration = video_info.duration if video_info else None

        try:
            proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True)

            # 实时读取进度
            last_percent = -1
            for line in proc.stderr:
                sec = self._parse_progress(line)
                if sec and duration and progress_callback:
                    percent = min(99, int(sec / duration * 100))
                    if percent != last_percent:
                        progress_callback(percent)
                        last_percent = percent

            proc.wait()

            if proc.returncode == 0:
                if progress_callback:
                    progress_callback(100)
                logger.info(f"转码完成: {output_path}")
                return True
            else:
                logger.error(f"转码失败，返回码: {proc.returncode}")
                return False

        except Exception as e:
            logger.error(f"转码异常: {e}")
            return False

    def _parse_progress(self, line: str) -> Optional[float]:
        """解析 FFmpeg 输出中的进度"""
        match = re.search(r"time=(\d+):(\d+):([\d\.]+)", line)
        if match:
            h, m, s = map(float, match.groups())
            return h * 3600 + m * 60 + s
        return None

    @staticmethod
    def build_args(
        codec: str = None,
        resolution: str = None,
        bitrate: str = None,
        crf: int = None,
        preset: str = None,
        audio_codec: str = None,
        audio_bitrate: str = None,
        extra: List[str] = None,
    ) -> List[str]:
        """
        构建 FFmpeg 参数

        Args:
            codec: 视频编码器
            resolution: 分辨率 (如 "1920x1080")
            bitrate: 视频比特率
            crf: CRF 值
            preset: 编码预设
            audio_codec: 音频编码器
            audio_bitrate: 音频比特率
            extra: 额外参数

        Returns:
            参数列表
        """
        args = []

        if codec:
            args.extend(["-c:v", codec])

        if resolution:
            args.extend(["-vf", f"scale={resolution}"])

        if bitrate:
            args.extend(["-b:v", bitrate])
        elif crf is not None:
            args.extend(["-crf", str(crf)])

        if preset:
            args.extend(["-preset", preset])

        if audio_codec:
            args.extend(["-c:a", audio_codec])

        if audio_bitrate:
            args.extend(["-b:a", audio_bitrate])

        if extra:
            args.extend(extra)

        return args
