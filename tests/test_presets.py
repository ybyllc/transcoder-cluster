"""转码预设测试"""

import pytest
from transcoder_cluster.transcode.presets import (
    PRESETS,
    get_preset,
    list_presets,
    get_preset_descriptions,
    TranscodePreset
)


class TestPresets:
    """预设测试类"""
    
    def test_list_presets(self):
        """测试列出预设"""
        presets = list_presets()
        assert isinstance(presets, list)
        assert len(presets) > 0
        assert "1080p_h264_high" in presets
    
    def test_get_preset(self):
        """测试获取预设"""
        preset = get_preset("1080p_h264_high")
        assert isinstance(preset, TranscodePreset)
        assert preset.codec == "libx264"
        assert preset.resolution == "1920:1080"
    
    def test_get_preset_not_found(self):
        """测试获取不存在的预设"""
        with pytest.raises(KeyError):
            get_preset("nonexistent_preset")
    
    def test_preset_to_ffmpeg_args(self):
        """测试预设转换为 FFmpeg 参数"""
        preset = get_preset("1080p_h264_high")
        args = preset.to_ffmpeg_args()
        
        assert "-c:v" in args
        assert "libx264" in args
        assert "-crf" in args
        assert "-preset" in args
    
    def test_get_preset_descriptions(self):
        """测试获取预设描述"""
        descriptions = get_preset_descriptions()
        assert isinstance(descriptions, dict)
        assert "1080p_h264_high" in descriptions
    
    def test_h265_preset(self):
        """测试 H.265 预设"""
        preset = get_preset("1080p_h265_standard")
        assert preset.codec == "libx265"
        args = preset.to_ffmpeg_args()
        assert "libx265" in args
    
    def test_nvenc_preset(self):
        """测试 NVENC 预设"""
        preset = get_preset("1080p_nvenc")
        assert preset.codec == "h264_nvenc"
        args = preset.to_ffmpeg_args()
        assert "h264_nvenc" in args
    
    def test_audio_preset(self):
        """测试音频预设"""
        preset = get_preset("audio_mp3")
        assert preset.audio_codec == "libmp3lame"
        args = preset.to_ffmpeg_args()
        assert "-c:a" in args
        assert "libmp3lame" in args
