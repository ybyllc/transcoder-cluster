"""
配置管理模块

支持从环境变量、配置文件加载配置
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Config:
    """应用配置"""

    # 网络配置
    control_port: int = 55555
    data_port: int = 55556
    discovery_port: int = 55557
    worker_port: int = 9000

    # 发现配置
    discovery_interval: int = 10
    heartbeat_interval: int = 10

    # 路径配置
    work_dir: str = "."
    ffmpeg_path: str = "ffmpeg"

    # 日志配置
    log_level: str = "INFO"
    log_file: Optional[str] = None

    @classmethod
    def from_env(cls) -> "Config":
        """从环境变量加载配置"""
        return cls(
            control_port=int(os.getenv("TC_CONTROL_PORT", 55555)),
            data_port=int(os.getenv("TC_DATA_PORT", 55556)),
            discovery_port=int(os.getenv("TC_DISCOVERY_PORT", 55557)),
            worker_port=int(os.getenv("TC_WORKER_PORT", 9000)),
            discovery_interval=int(os.getenv("TC_DISCOVERY_INTERVAL", 10)),
            heartbeat_interval=int(os.getenv("TC_HEARTBEAT_INTERVAL", 10)),
            work_dir=os.getenv("TC_WORK_DIR", "."),
            ffmpeg_path=os.getenv("TC_FFMPEG_PATH", "ffmpeg"),
            log_level=os.getenv("TC_LOG_LEVEL", "INFO"),
            log_file=os.getenv("TC_LOG_FILE"),
        )

    @classmethod
    def from_file(cls, path: str) -> "Config":
        """从 JSON 文件加载配置"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(**data)

    def to_file(self, path: str) -> None:
        """保存配置到 JSON 文件"""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.__dict__, f, indent=2)

    def __post_init__(self):
        """后处理：确保工作目录存在"""
        Path(self.work_dir).mkdir(parents=True, exist_ok=True)


# 全局配置实例
config = Config.from_env()


def load_config(config_path: Optional[str] = None) -> Config:
    """
    加载配置

    优先级：配置文件 > 环境变量 > 默认值

    Args:
        config_path: 配置文件路径

    Returns:
        配置实例
    """
    global config

    # 先从环境变量加载
    config = Config.from_env()

    # 如果有配置文件，覆盖配置
    if config_path and os.path.exists(config_path):
        file_config = Config.from_file(config_path)
        # 合并配置
        for key, value in file_config.__dict__.items():
            if value is not None:
                setattr(config, key, value)

    return config
