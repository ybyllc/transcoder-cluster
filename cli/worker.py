#!/usr/bin/env python3
"""
Worker 节点命令行入口

启动 Worker 节点接收转码任务
"""

import argparse
import sys

from transcoder_cluster.core.worker import Worker
from transcoder_cluster.core.discovery import HeartbeatService, DiscoveryResponder
from transcoder_cluster.utils.config import load_config
from transcoder_cluster.utils.logger import get_logger

logger = get_logger(__name__)


def main():
    """Worker 命令行入口"""
    parser = argparse.ArgumentParser(
        description="启动 Transcoder Cluster Worker 节点",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用默认配置启动
  tc-worker
  
  # 指定端口和工作目录
  tc-worker --port 9001 --work-dir /data/transcode
  
  # 使用配置文件
  tc-worker --config worker.json
        """
    )
    
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=9000,
        help="Worker 监听端口 (默认: 9000)"
    )
    parser.add_argument(
        "--work-dir", "-w",
        type=str,
        default="./worker_files",
        help="工作目录 (默认: ./worker_files)"
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        help="配置文件路径"
    )
    parser.add_argument(
        "--no-discovery",
        action="store_true",
        help="禁用节点发现服务"
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别 (默认: INFO)"
    )
    
    args = parser.parse_args()
    
    # 加载配置
    if args.config:
        load_config(args.config)
    
    # 创建工作目录
    import os
    os.makedirs(args.work_dir, exist_ok=True)
    
    # 初始化服务
    worker = Worker(port=args.port, work_dir=args.work_dir)
    
    # 节点发现服务
    heartbeat = None
    responder = None
    
    if not args.no_discovery:
        # 心跳服务
        heartbeat = HeartbeatService(
            get_status=lambda: Worker.get_status()
        )
        
        # 发现响应器
        responder = DiscoveryResponder(
            get_status=lambda: Worker.get_status()
        )
    
    # 启动发现服务
    if heartbeat:
        heartbeat.start()
    if responder:
        responder.start()
    
    # 显示退出提示
    logger.info(f"按 Ctrl+C 退出")
    
    # 启动 Worker（阻塞，直到收到 KeyboardInterrupt）
    try:
        worker.start()
    except KeyboardInterrupt:
        logger.info("正在关闭 Worker...")
    finally:
        worker.stop()
        if heartbeat:
            heartbeat.stop()
        if responder:
            responder.stop()
        logger.info("Worker 已退出")


if __name__ == "__main__":
    main()
