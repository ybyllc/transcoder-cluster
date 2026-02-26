"""Worker 能力探测测试。"""

import subprocess

from transcoder_cluster.core.worker import get_ffmpeg_version, list_ffmpeg_encoders


class DummyResult:
    """模拟 subprocess.run 返回值。"""

    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


def test_get_ffmpeg_version(monkeypatch):
    """应从 version 输出提取版本号。"""

    def fake_run(*args, **kwargs):
        return DummyResult(stdout="ffmpeg version 7.0-full_build-www.gyan.dev\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert get_ffmpeg_version("ffmpeg") == "7.0-full_build-www.gyan.dev"


def test_list_ffmpeg_encoders(monkeypatch):
    """应从 encoders 输出提取编码器列表。"""
    stdout = """
Encoders:
 V..... libx264              H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10
 V..... libx265              H.265 / HEVC
 V..... h264_nvenc           NVIDIA NVENC H.264 encoder
"""

    def fake_run(*args, **kwargs):
        return DummyResult(stdout=stdout)

    monkeypatch.setattr(subprocess, "run", fake_run)
    encoders = list_ffmpeg_encoders("ffmpeg")
    assert "libx264" in encoders
    assert "libx265" in encoders
    assert "h264_nvenc" in encoders
