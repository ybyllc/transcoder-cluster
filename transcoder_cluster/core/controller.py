"""
Controller 控制端模块 - 管理任务分发和节点调度

提供任务提交、节点发现、文件传输等功能
"""

import base64
import concurrent.futures
import json
import os
import socket
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

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
    attempts: int = 0
    max_attempts: int = 1
    last_worker: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None


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
        self._task_lock = threading.Lock()

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
                parts = local_ip.split(".")
                if len(parts) == 4:
                    first_octet = int(parts[0])
                    second_octet = int(parts[1])
                    # 排除 198.18.x.x (VPN常用) 和 127.x.x.x
                    if not (first_octet == 198 and second_octet == 18) and first_octet != 127:
                        return ".".join(parts[:3]) + "."
        except Exception:
            pass

        # 方法2: 获取所有网络接口
        try:
            import netifaces

            for interface in netifaces.interfaces():
                addrs = netifaces.ifaddresses(interface)
                if netifaces.AF_INET in addrs:
                    for addr_info in addrs[netifaces.AF_INET]:
                        ip = addr_info["addr"]
                        parts = ip.split(".")
                        if len(parts) == 4:
                            first_octet = int(parts[0])
                            second_octet = int(parts[1])
                            # 只接受常见局域网段: 192.168.x.x, 10.x.x.x, 172.16-31.x.x
                            if first_octet == 192 and second_octet == 168:
                                return ".".join(parts[:3]) + "."
                            elif first_octet == 10:
                                return ".".join(parts[:3]) + "."
                            elif first_octet == 172 and 16 <= second_octet <= 31:
                                return ".".join(parts[:3]) + "."
        except ImportError:
            pass

        # 方法3: 使用 hostname（可能不准确）
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            parts = local_ip.split(".")
            if len(parts) == 4:
                first_octet = int(parts[0])
                second_octet = int(parts[1])
                if not (first_octet == 198 and second_octet == 18) and first_octet != 127:
                    return ".".join(parts[:3]) + "."
        except Exception:
            pass

        return "192.168.1."

    def _ping_ip(self, ip: str) -> Optional[str]:
        """Ping IP 地址"""
        param = ["ping", "-n", "1", "-w", "100", ip]
        result = subprocess.run(param, stdout=subprocess.DEVNULL)
        return ip if result.returncode == 0 else None

    def create_task(
        self,
        input_file: str,
        output_file: str,
        ffmpeg_args: List[str],
        max_attempts: int = 1,
    ) -> Task:
        """
        创建转码任务

        Args:
            input_file: 输入文件路径
            output_file: 输出文件路径
            ffmpeg_args: FFmpeg 参数

        Returns:
            创建的任务对象
        """
        with self._task_lock:
            self._task_counter += 1
            task = Task(
                id=f"task_{self._task_counter}",
                input_file=input_file,
                output_file=output_file,
                ffmpeg_args=ffmpeg_args,
                max_attempts=max_attempts,
            )
            self.tasks.append(task)
        logger.info(f"创建任务: {task.id}")
        return task

    def build_output_path(self, input_file: str, suffix: str = "_transcoded") -> str:
        """
        根据输入文件路径生成输出路径（同目录 + 后缀，自动避重名）。
        """
        directory = os.path.dirname(input_file)
        name, ext = os.path.splitext(os.path.basename(input_file))
        output = os.path.join(directory, f"{name}{suffix}{ext}")
        index = 2
        while os.path.exists(output):
            output = os.path.join(directory, f"{name}{suffix}_{index}{ext}")
            index += 1
        return output

    def create_tasks_for_files(
        self,
        input_files: List[str],
        ffmpeg_args: List[str],
        max_attempts: int = 1,
        output_suffix: str = "_transcoded",
    ) -> List[Task]:
        """按文件列表批量创建任务。"""
        tasks = []
        for input_file in input_files:
            output_file = self.build_output_path(input_file, suffix=output_suffix)
            tasks.append(self.create_task(input_file, output_file, ffmpeg_args, max_attempts=max_attempts))
        return tasks

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
        task.last_worker = worker_ip
        task.status = "uploading"
        task.start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            # 读取视频文件
            with open(task.input_file, "rb") as f:
                video_data = f.read()

            # 构建请求
            payload = {
                "task_id": task.id,
                "video_file": {
                    "name": os.path.basename(task.input_file),
                    "data": base64.b64encode(video_data).decode("utf-8"),
                },
                "ffmpeg_args": task.ffmpeg_args,
            }

            logger.info(f"提交任务 {task.id} 到 Worker {worker_ip}")

            # 发送请求
            r = requests.post(
                f"http://{worker_ip}:9000/task", data=json.dumps(payload), timeout=3600  # 1小时超时
            )

            result = r.json()

            if result.get("status") == "success":
                task.status = "completed"
                task.progress = 100
                task.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logger.info(f"任务 {task.id} 完成")
            else:
                task.status = "failed"
                task.error = result.get("error", "Unknown error")
                task.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logger.error(f"任务 {task.id} 失败: {task.error}")

            return result

        except Exception as e:
            task.status = "error"
            task.error = str(e)
            task.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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

    def get_worker_capabilities(self, worker_ip: str) -> Dict[str, Any]:
        """获取 Worker 能力信息。"""
        try:
            r = requests.get(f"http://{worker_ip}:9000/capabilities", timeout=5)
            return r.json()
        except Exception as e:
            logger.error(f"获取 Worker 能力失败: {e}")
            return {
                "ffmpeg_installed": False,
                "ffmpeg_version": None,
                "encoders": [],
                "nvenc_supported": False,
                "error": str(e),
            }

    def dispatch_tasks(
        self,
        tasks: List[Task],
        worker_ips: List[str],
        on_task_update: Optional[Callable[[Task], None]] = None,
        on_node_update: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> Dict[str, Any]:
        """
        批量调度任务到多个节点。

        调度策略：
        - 每个节点并发 1 个任务。
        - 节点空闲后自动领取新任务。
        - 失败任务按 max_attempts 自动重试。
        """
        if not tasks:
            return {"total": 0, "completed": 0, "failed": 0}
        if not worker_ips:
            raise RuntimeError("没有可用的 Worker 节点")

        for task in tasks:
            task.status = "pending"
            task.progress = 0
            task.error = None
            task.worker = None
            task.attempts = 0
            task.start_time = None
            task.end_time = None
            if on_task_update:
                on_task_update(task)

        stop_event = stop_event or threading.Event()
        pending_tasks = list(tasks)
        queue_lock = threading.Lock()
        result = {"total": len(tasks), "completed": 0, "failed": 0}

        def pop_next_task(worker_ip: str) -> Optional[Task]:
            with queue_lock:
                if not pending_tasks:
                    return None
                # 有多个节点时，失败重试尽量避免回到同一节点
                if len(worker_ips) > 1:
                    for idx, candidate in enumerate(pending_tasks):
                        if candidate.last_worker != worker_ip:
                            return pending_tasks.pop(idx)
                return pending_tasks.pop(0)

        def push_retry_task(task: Task) -> None:
            with queue_lock:
                pending_tasks.append(task)

        def worker_loop(worker_ip: str) -> None:
            while not stop_event.is_set():
                task = pop_next_task(worker_ip)
                if task is None:
                    return

                task.worker = worker_ip
                task.last_worker = worker_ip
                task.attempts += 1
                task.error = None
                task.status = "uploading"
                if on_task_update:
                    on_task_update(task)

                ok, error_message = self._submit_with_progress(
                    task,
                    worker_ip,
                    on_task_update=on_task_update,
                    on_node_update=on_node_update,
                    stop_event=stop_event,
                )

                if ok:
                    task.status = "completed"
                    task.progress = 100
                    task.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    with queue_lock:
                        result["completed"] += 1
                else:
                    task.error = error_message or task.error or "Unknown error"
                    if task.attempts < task.max_attempts and not stop_event.is_set():
                        task.status = "pending"
                        task.progress = 0
                        push_retry_task(task)
                    else:
                        task.status = "failed"
                        task.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        with queue_lock:
                            result["failed"] += 1

                if on_task_update:
                    on_task_update(task)

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(worker_ips)) as executor:
            futures = [executor.submit(worker_loop, worker_ip) for worker_ip in worker_ips]
            for future in futures:
                future.result()

        return result

    def _submit_with_progress(
        self,
        task: Task,
        worker_ip: str,
        on_task_update: Optional[Callable[[Task], None]] = None,
        on_node_update: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> Tuple[bool, Optional[str]]:
        """提交任务并轮询进度。"""
        stop_event = stop_event or threading.Event()
        poll_stop = threading.Event()

        def poll_progress() -> None:
            while not poll_stop.is_set() and not stop_event.is_set():
                status = self.get_worker_status(worker_ip)
                if on_node_update:
                    on_node_update(worker_ip, status)
                current_status = status.get("status")
                if current_status in ("receiving", "uploading"):
                    task.status = "uploading"
                    task.progress = int(status.get("progress", 0))
                    if on_task_update:
                        on_task_update(task)
                elif current_status == "processing":
                    task.status = "processing"
                    task.progress = int(status.get("progress", 0))
                    if on_task_update:
                        on_task_update(task)
                poll_stop.wait(1.0)

        poll_thread = threading.Thread(target=poll_progress, daemon=True)
        poll_thread.start()

        try:
            result = self.submit_task(task, worker_ip)
            if result.get("status") != "success":
                return False, result.get("error", "Worker failed")

            output_file = result.get("output_file")
            if not output_file:
                return False, "Worker 未返回输出文件路径"

            ok = self.download_result(worker_ip, os.path.basename(output_file), task.output_file)
            if not ok:
                return False, "下载转码结果失败"

            valid, error_message = self._validate_output_file(task.output_file)
            if not valid:
                return False, error_message
            return True, None
        except Exception as e:
            return False, str(e)
        finally:
            poll_stop.set()
            poll_thread.join(timeout=1)

    def _validate_output_file(self, output_path: str) -> Tuple[bool, str]:
        """校验输出文件存在且大小有效。"""
        if not os.path.exists(output_path):
            return False, "输出文件不存在"

        try:
            file_size = os.path.getsize(output_path)
        except OSError as error:
            return False, f"读取输出文件失败: {error}"

        if file_size <= 0:
            return False, "输出文件大小为 0"

        return True, ""


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
                controller.download_result(workers[0], os.path.basename(output_file), output)
            print(f"转码完成: {output}")
        else:
            print(f"转码失败: {result.get('error')}")


if __name__ == "__main__":
    main()
