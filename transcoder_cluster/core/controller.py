"""
Controller 控制端模块 - 管理任务分发和节点调度

提供任务提交、节点发现、文件传输等功能
"""

import os
import json
import base64
import socket
import concurrent.futures
import subprocess
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

import requests

from transcoder_cluster.utils.config import config
from transcoder_cluster.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Task:
    """转码任务数据类"""
    id: str
    input_file: str
    output_file: str
    ffmpeg_args: List[str]
    status: str = "pending"
    worker: Optional[str] = None
    progress: int = 0
    create_time: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    error: Optional[str] = None


class Controller:
    """
    Controller 控制端类
    
    负责发现 Worker 节点、分发任务、监控进度
    """
    
    def __init__(self, port: int = None):
        """
        初始化 Controller
        
        Args:
            port: 服务端口
        """
        self.port = port or config.control_port
        self.workers: List[str] = []
        self.tasks: List[Task] = []
        self._task_counter = 0
    
    def scan_workers(self, subnet: str = None, port: int = 9000) -> List[str]:
        """
        扫描局域网内的 Worker 节点
        
        Args:
            subnet: 网段，如 "192.168.1."
            port: Worker 端口
            
        Returns:
            发现的 Worker IP 列表
        """
        if subnet is None:
            subnet = self._get_local_subnet()
        
        logger.info(f"扫描网段 {subnet}* 的 Worker 节点...")
        
        # 直接并行检查所有 IP 的 Worker 服务（跳过 ping，更快）
        ips = [f"{subnet}{i}" for i in range(1, 255)]
        workers = []
        
        def check_worker(ip: str) -> Optional[str]:
            """检查单个 IP 是否有 Worker 服务"""
            try:
                r = requests.get(f"http://{ip}:{port}/ping", timeout=0.1)
                if r.text == "pong":
                    return ip
            except Exception:
                pass
            return None
        
        # 多线程并行检查
        with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
            results = executor.map(check_worker, ips)
            for result in results:
                if result:
                    workers.append(result)
                    logger.info(f"发现 Worker: {result}")
        
        self.workers = workers
        return workers
    
    def _get_local_subnet(self) -> str:
        """获取本机局域网网段（优先获取真实局域网IP，排除VPN/虚拟网卡）"""
        # 方法1: 通过连接外部地址获取本地IP（最可靠）
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                # 排除 VPN/虚拟网段 (198.18.x.x, 10.x.x.x等)
                parts = local_ip.split('.')
                if len(parts) == 4:
                    first_octet = int(parts[0])
                    second_octet = int(parts[1])
                    # 排除 198.18.x.x (VPN常用) 和 127.x.x.x
                    if not (first_octet == 198 and second_octet == 18) and first_octet != 127:
                        return '.'.join(parts[:3]) + '.'
        except Exception:
            pass
        
        # 方法2: 获取所有网络接口
        try:
            import netifaces
            for interface in netifaces.interfaces():
                addrs = netifaces.ifaddresses(interface)
                if netifaces.AF_INET in addrs:
                    for addr_info in addrs[netifaces.AF_INET]:
                        ip = addr_info['addr']
                        parts = ip.split('.')
                        if len(parts) == 4:
                            first_octet = int(parts[0])
                            second_octet = int(parts[1])
                            # 只接受常见局域网段: 192.168.x.x, 10.x.x.x, 172.16-31.x.x
                            if first_octet == 192 and second_octet == 168:
                                return '.'.join(parts[:3]) + '.'
                            elif first_octet == 10:
                                return '.'.join(parts[:3]) + '.'
                            elif first_octet == 172 and 16 <= second_octet <= 31:
                                return '.'.join(parts[:3]) + '.'
        except ImportError:
            pass
        
        # 方法3: 使用 hostname（可能不准确）
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            parts = local_ip.split('.')
            if len(parts) == 4:
                first_octet = int(parts[0])
                second_octet = int(parts[1])
                if not (first_octet == 198 and second_octet == 18) and first_octet != 127:
                    return '.'.join(parts[:3]) + '.'
        except Exception:
            pass
        
        return "192.168.1."
    
    def _ping_ip(self, ip: str) -> Optional[str]:
        """Ping IP 地址"""
        param = ['ping', '-n', '1', '-w', '100', ip]
        result = subprocess.run(param, stdout=subprocess.DEVNULL)
        return ip if result.returncode == 0 else None
    
    def create_task(self, input_file: str, output_file: str, ffmpeg_args: List[str]) -> Task:
        """
        创建转码任务
        
        Args:
            input_file: 输入文件路径
            output_file: 输出文件路径
            ffmpeg_args: FFmpeg 参数
            
        Returns:
            创建的任务对象
        """
        self._task_counter += 1
        task = Task(
            id=f"task_{self._task_counter}",
            input_file=input_file,
            output_file=output_file,
            ffmpeg_args=ffmpeg_args
        )
        self.tasks.append(task)
        logger.info(f"创建任务: {task.id}")
        return task
    
    def submit_task(self, task: Task, worker_ip: str = None) -> Dict[str, Any]:
        """
        提交任务到 Worker
        
        Args:
            task: 任务对象
            worker_ip: Worker IP，如果为 None 则自动选择
            
        Returns:
            Worker 返回的结果
        """
        if worker_ip is None:
            if not self.workers:
                raise RuntimeError("没有可用的 Worker 节点")
            worker_ip = self.workers[0]
        
        task.worker = worker_ip
        task.status = "uploading"
        
        try:
            # 读取视频文件
            with open(task.input_file, "rb") as f:
                video_data = f.read()
            
            # 构建请求
            payload = {
                "video_file": {
                    "name": os.path.basename(task.input_file),
                    "data": base64.b64encode(video_data).decode("utf-8")
                },
                "ffmpeg_args": task.ffmpeg_args
            }
            
            logger.info(f"提交任务 {task.id} 到 Worker {worker_ip}")
            
            # 发送请求
            r = requests.post(
                f"http://{worker_ip}:9000/task",
                data=json.dumps(payload),
                timeout=3600  # 1小时超时
            )
            
            result = r.json()
            
            if result.get("status") == "success":
                task.status = "completed"
                task.progress = 100
                logger.info(f"任务 {task.id} 完成")
            else:
                task.status = "failed"
                task.error = result.get("error", "Unknown error")
                logger.error(f"任务 {task.id} 失败: {task.error}")
            
            return result
            
        except Exception as e:
            task.status = "error"
            task.error = str(e)
            logger.error(f"提交任务失败: {e}")
            raise
    
    def download_result(self, worker_ip: str, filename: str, save_path: str) -> bool:
        """
        从 Worker 下载转码结果
        
        Args:
            worker_ip: Worker IP
            filename: 远程文件名
            save_path: 本地保存路径
            
        Returns:
            是否下载成功
        """
        try:
            url = f"http://{worker_ip}:9000/download?file={filename}"
            r = requests.get(url)
            
            if r.status_code == 200:
                with open(save_path, "wb") as f:
                    f.write(r.content)
                logger.info(f"下载完成: {save_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"下载失败: {e}")
            return False
    
    def get_worker_status(self, worker_ip: str) -> Dict[str, Any]:
        """获取 Worker 状态"""
        try:
            r = requests.get(f"http://{worker_ip}:9000/status", timeout=5)
            return r.json()
        except Exception as e:
            logger.error(f"获取 Worker 状态失败: {e}")
            return {"status": "unknown", "error": str(e)}


def main():
    """Controller 命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Transcoder Cluster Controller")
    parser.add_argument("--scan", action="store_true", help="扫描 Worker 节点")
    parser.add_argument("--input", type=str, help="输入文件路径")
    parser.add_argument("--output", type=str, help="输出文件路径")
    parser.add_argument("--args", type=str, default="-c:v libx265", help="FFmpeg 参数")
    
    args = parser.parse_args()
    
    controller = Controller()
    
    if args.scan:
        workers = controller.scan_workers()
        print(f"发现 {len(workers)} 个 Worker 节点:")
        for w in workers:
            print(f"  - {w}")
        return
    
    if args.input:
        # 扫描节点
        workers = controller.scan_workers()
        if not workers:
            print("未发现可用的 Worker 节点")
            return
        
        # 创建并提交任务
        ffmpeg_args = args.args.split()
        output = args.output or f"output_{os.path.basename(args.input)}"
        
        task = controller.create_task(args.input, output, ffmpeg_args)
        result = controller.submit_task(task)
        
        if result.get("status") == "success":
            # 下载结果
            output_file = result.get("output_file")
            if output_file:
                controller.download_result(
                    workers[0],
                    os.path.basename(output_file),
                    output
                )
            print(f"转码完成: {output}")
        else:
            print(f"转码失败: {result.get('error')}")


if __name__ == "__main__":
    main()
