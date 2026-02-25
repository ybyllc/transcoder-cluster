#!/usr/bin/env python3
"""
Controller 控制端命令行入口

管理任务分发和节点调度
"""

import argparse
import os
import sys

from transcoder_cluster.core.controller import Controller
from transcoder_cluster.transcode.presets import get_preset, list_presets
from transcoder_cluster.utils.config import load_config
from transcoder_cluster.utils.logger import get_logger

logger = get_logger(__name__)


def main():
    """Controller 命令行入口"""
    parser = argparse.ArgumentParser(
        description="Transcoder Cluster Controller - 控制端",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 扫描 Worker 节点
  tc-control --scan
  
  # 提交转码任务
  tc-control --input video.mp4 --output output.mp4 --preset 1080p_h265_standard
  
  # 使用自定义参数
  tc-control -i video.mp4 -o output.mp4 --args "-c:v libx265 -crf 28"
  
  # 查看可用预设
  tc-control --list-presets
        """,
    )

    # 操作模式
    parser.add_argument("--scan", "-s", action="store_true", help="扫描局域网内的 Worker 节点")
    parser.add_argument("--list-presets", action="store_true", help="列出所有可用的转码预设")

    # 任务参数
    parser.add_argument("--input", "-i", type=str, help="输入文件路径")
    parser.add_argument("--output", "-o", type=str, help="输出文件路径")
    parser.add_argument("--preset", "-p", type=str, help="转码预设名称")
    parser.add_argument(
        "--args", "-a", type=str, help="自定义 FFmpeg 参数 (如: '-c:v libx265 -crf 28')"
    )
    parser.add_argument("--worker", "-w", type=str, help="指定 Worker IP (默认自动选择)")

    # 配置
    parser.add_argument("--config", "-c", type=str, help="配置文件路径")
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别 (默认: INFO)",
    )

    args = parser.parse_args()

    # 加载配置
    if args.config:
        load_config(args.config)

    controller = Controller()

    # 列出预设
    if args.list_presets:
        print("\n可用的转码预设:")
        print("-" * 50)
        for name in list_presets():
            preset = get_preset(name)
            print(f"  {name:25} - {preset.description}")
        print()
        return

    # 扫描节点
    if args.scan:
        print("\n扫描局域网内的 Worker 节点...")
        workers = controller.scan_workers()

        if workers:
            print(f"\n发现 {len(workers)} 个 Worker 节点:")
            for w in workers:
                status = controller.get_worker_status(w)
                print(f"  - {w}: {status.get('status', 'unknown')}")
        else:
            print("\n未发现可用的 Worker 节点")
        return

    # 提交任务
    if args.input:
        if not os.path.exists(args.input):
            print(f"错误: 输入文件不存在: {args.input}")
            sys.exit(1)

        # 扫描节点
        workers = controller.scan_workers()
        if not workers:
            print("错误: 未发现可用的 Worker 节点")
            sys.exit(1)

        # 确定 Worker
        worker_ip = args.worker or workers[0]

        # 构建参数
        if args.preset:
            preset = get_preset(args.preset)
            ffmpeg_args = preset.to_ffmpeg_args()
        elif args.args:
            ffmpeg_args = args.args.split()
        else:
            # 默认使用 H.265
            ffmpeg_args = ["-c:v", "libx265", "-crf", "28"]

        # 确定输出路径
        output = args.output
        if not output:
            base, ext = os.path.splitext(args.input)
            output = f"{base}_transcode{ext}"

        # 创建任务
        print(f"\n提交转码任务:")
        print(f"  输入: {args.input}")
        print(f"  输出: {output}")
        print(f"  Worker: {worker_ip}")
        print(f"  参数: {' '.join(ffmpeg_args)}")
        print()

        task = controller.create_task(args.input, output, ffmpeg_args)

        try:
            result = controller.submit_task(task, worker_ip)

            if result.get("status") == "success":
                # 下载结果
                output_file = result.get("output_file")
                if output_file:
                    controller.download_result(worker_ip, os.path.basename(output_file), output)
                print(f"\n✓ 转码完成: {output}")
            else:
                print(f"\n✗ 转码失败: {result.get('error')}")
                sys.exit(1)

        except Exception as e:
            print(f"\n✗ 任务失败: {e}")
            sys.exit(1)

        return

    # 没有指定操作，显示帮助
    parser.print_help()


if __name__ == "__main__":
    main()
