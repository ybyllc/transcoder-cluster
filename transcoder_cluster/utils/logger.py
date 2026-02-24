"""
日志模块

提供统一的日志配置
"""

import logging
import sys
from typing import Optional

from transcoder_cluster.utils.config import config


def get_logger(name: str = None) -> logging.Logger:
    """
    获取日志记录器
    
    Args:
        name: 日志记录器名称，通常使用 __name__
        
    Returns:
        配置好的日志记录器
    """
    logger = logging.getLogger(name or "transcoder_cluster")
    
    # 避免重复配置
    if logger.handlers:
        return logger
    
    # 设置日志级别
    level = getattr(logging, config.log_level.upper(), logging.INFO)
    logger.setLevel(level)
    
    # 创建格式器
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 文件处理器（如果配置了日志文件）
    if config.log_file:
        file_handler = logging.FileHandler(config.log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def set_log_level(level: str) -> None:
    """
    设置全局日志级别
    
    Args:
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    logging.getLogger("transcoder_cluster").setLevel(getattr(logging, level.upper()))
