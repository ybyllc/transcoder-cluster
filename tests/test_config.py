"""配置模块测试"""

import os
import pytest
import tempfile
from transcoder_cluster.utils.config import Config, load_config


class TestConfig:
    """配置测试类"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = Config()
        assert config.control_port == 55555
        assert config.worker_port == 9000
        assert config.log_level == "INFO"
    
    def test_config_from_env(self):
        """测试从环境变量加载配置"""
        os.environ["TC_WORKER_PORT"] = "9001"
        os.environ["TC_LOG_LEVEL"] = "DEBUG"
        
        config = Config.from_env()
        assert config.worker_port == 9001
        assert config.log_level == "DEBUG"
        
        # 清理
        del os.environ["TC_WORKER_PORT"]
        del os.environ["TC_LOG_LEVEL"]
    
    def test_config_to_file(self):
        """测试保存配置到文件"""
        config = Config(
            worker_port=9002,
            log_level="WARNING"
        )
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = f.name
        
        try:
            config.to_file(temp_path)
            
            # 验证文件内容
            loaded = Config.from_file(temp_path)
            assert loaded.worker_port == 9002
            assert loaded.log_level == "WARNING"
        finally:
            os.unlink(temp_path)
    
    def test_config_from_file(self):
        """测试从文件加载配置"""
        import json
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "worker_port": 9003,
                "log_level": "ERROR"
            }, f)
            temp_path = f.name
        
        try:
            config = Config.from_file(temp_path)
            assert config.worker_port == 9003
            assert config.log_level == "ERROR"
        finally:
            os.unlink(temp_path)
