"""
Transcoder Cluster - 分布式 FFmpeg 视频转码集群系统

一个用于在局域网内实现多节点并行视频转码的分布式系统。
"""

__version__ = "1.0.0"
__author__ = "一杯原谅绿茶"
__email__ = "your.email@example.com"

from transcoder_cluster.core.controller import Controller
from transcoder_cluster.core.discovery import DiscoveryService
from transcoder_cluster.core.worker import Worker

__all__ = [
    "Worker",
    "Controller",
    "DiscoveryService",
    "__version__",
]
