"""
转码预设模块

提供常用的转码配置预设
"""

from typing import Dict, List, Any
from dataclasses import dataclass


@dataclass
class TranscodePreset:
    """转码预设"""
    name: str
    description: str
    codec: str
    resolution: str = None
    crf: int = None
    bitrate: str = None
    preset: str = "medium"
    audio_codec: str = "aac"
    audio_bitrate: str = "128k"
    
    def to_ffmpeg_args(self) -> List[str]:
        """转换为 FFmpeg 参数列表"""
        args = ["-c:v", self.codec]
        
        if self.resolution:
            args.extend(["-vf", f"scale={self.resolution}"])
        
        if self.crf is not None:
            args.extend(["-crf", str(self.crf)])
        elif self.bitrate:
            args.extend(["-b:v", self.bitrate])
        
        if self.preset:
            args.extend(["-preset", self.preset])
        
        if self.audio_codec:
            args.extend(["-c:a", self.audio_codec])
        
        if self.audio_bitrate:
            args.extend(["-b:a", self.audio_bitrate])
        
        return args


# 预设配置
PRESETS: Dict[str, TranscodePreset] = {
    # H.264 预设
    "1080p_h264_high": TranscodePreset(
        name="1080p H.264 高画质",
        description="1920x1080 H.264 编码，高画质，兼容性好",
        codec="libx264",
        resolution="1920:1080",
        crf=18,
        preset="slow"
    ),
    "1080p_h264_standard": TranscodePreset(
        name="1080p H.264 标准",
        description="1920x1080 H.264 编码，平衡画质与文件大小",
        codec="libx264",
        resolution="1920:1080",
        crf=23,
        preset="medium"
    ),
    "720p_h264": TranscodePreset(
        name="720p H.264",
        description="1280x720 H.264 编码，适合网络传输",
        codec="libx264",
        resolution="1280:720",
        crf=23,
        preset="medium"
    ),
    "480p_h264": TranscodePreset(
        name="480p H.264",
        description="854x480 H.264 编码，小文件快速传输",
        codec="libx264",
        resolution="854:480",
        crf=28,
        preset="fast"
    ),
    
    # H.265/HEVC 预设
    "1080p_h265_high": TranscodePreset(
        name="1080p H.265 高画质",
        description="1920x1080 H.265 编码，高压缩率",
        codec="libx265",
        resolution="1920:1080",
        crf=20,
        preset="slow"
    ),
    "1080p_h265_standard": TranscodePreset(
        name="1080p H.265 标准",
        description="1920x1080 H.265 编码，节省空间",
        codec="libx265",
        resolution="1920:1080",
        crf=28,
        preset="medium"
    ),
    "4k_h265": TranscodePreset(
        name="4K H.265",
        description="3840x2160 H.265 编码，超高清",
        codec="libx265",
        resolution="3840:2160",
        crf=24,
        preset="medium"
    ),
    
    # 硬件加速预设 (NVIDIA)
    "1080p_nvenc": TranscodePreset(
        name="1080p NVENC",
        description="1920x1080 NVIDIA 硬件加速编码",
        codec="h264_nvenc",
        resolution="1920:1080",
        bitrate="8M",
        preset="p4"
    ),
    "1080p_hevc_nvenc": TranscodePreset(
        name="1080p HEVC NVENC",
        description="1920x1080 NVIDIA HEVC 硬件加速编码",
        codec="hevc_nvenc",
        resolution="1920:1080",
        bitrate="5M",
        preset="p4"
    ),
    
    # 音频提取预设
    "audio_mp3": TranscodePreset(
        name="提取 MP3 音频",
        description="提取音频并转换为 MP3 格式",
        codec="none",
        audio_codec="libmp3lame",
        audio_bitrate="320k"
    ),
    "audio_aac": TranscodePreset(
        name="提取 AAC 音频",
        description="提取音频并转换为 AAC 格式",
        codec="none",
        audio_codec="aac",
        audio_bitrate="256k"
    ),
}


def get_preset(name: str) -> TranscodePreset:
    """
    获取预设
    
    Args:
        name: 预设名称
        
    Returns:
        预设对象
        
    Raises:
        KeyError: 预设不存在
    """
    if name not in PRESETS:
        available = ", ".join(PRESETS.keys())
        raise KeyError(f"预设 '{name}' 不存在。可用预设: {available}")
    return PRESETS[name]


def list_presets() -> List[str]:
    """获取所有预设名称列表"""
    return list(PRESETS.keys())


def get_preset_descriptions() -> Dict[str, str]:
    """获取预设名称和描述的映射"""
    return {name: preset.description for name, preset in PRESETS.items()}
