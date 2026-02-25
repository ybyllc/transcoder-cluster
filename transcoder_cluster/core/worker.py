"""
Worker 节点模块 - 处理转码任务

提供 HTTP API 接收任务，执行 FFmpeg 转码，返回结果
"""

import os
import subprocess
import json
import re
import base64
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from typing import Optional, Dict, Any, Callable
from datetime import datetime

from transcoder_cluster.utils.config import config
from transcoder_cluster.utils.logger import get_logger

logger = get_logger(__name__)


def parse_ffmpeg_progress(line: str) -> Optional[float]:
    """
    解析 FFmpeg 输出中的进度信息
    
    Args:
        line: FFmpeg 输出的一行文本
        
    Returns:
        当前转码秒数，如果无法解析则返回 None
    """
    match = re.search(r'time=(\d+):(\d+):([\d\.]+)', line)
    if match:
        h, m, s = map(float, match.groups())
        return h * 3600 + m * 60 + s
    return None


class WorkerHandler(BaseHTTPRequestHandler):
    """Worker HTTP 请求处理器"""
    
    # 类级别变量，用于存储状态
    status: Dict[str, Any] = {
        "status": "idle",
        "current_task": None,
        "progress": 0
    }
    on_task_complete: Optional[Callable] = None
    
    def log_message(self, format: str, *args) -> None:
        """重写日志方法，使用自定义 logger"""
        logger.info("%s - %s", self.address_string(), format % args)
    
    def do_POST(self) -> None:
        """处理 POST 请求"""
        if self.path == "/task":
            self._handle_task()
        else:
            self.send_error(404, "Not Found")
    
    def _handle_task(self) -> None:
        """处理转码任务"""
        try:
            # 接收数据
            content_length = int(self.headers['Content-Length'])
            received = 0
            chunks = []
            chunk_size = 1024 * 1024  # 1MB
            
            logger.info(f"开始接收文件，总大小: {content_length/1024/1024:.2f} MB")
            
            while received < content_length:
                to_read = min(chunk_size, content_length - received)
                chunk = self.rfile.read(to_read)
                if not chunk:
                    break
                chunks.append(chunk)
                received += len(chunk)
            
            logger.info("文件接收完成")
            
            # 解析任务数据
            post_data = b"".join(chunks)
            task = json.loads(post_data.decode())
            video_file = task['video_file']
            ffmpeg_args = task['ffmpeg_args']
            
            # 保存上传的视频文件
            file_path = os.path.join(config.work_dir, video_file['name'])
            with open(file_path, 'wb') as f:
                f.write(base64.b64decode(video_file['data']))
            
            # 执行转码
            input_path = file_path
            output_path = os.path.join(config.work_dir, "output_" + video_file['name'])
            
            result = self._execute_ffmpeg(input_path, output_path, ffmpeg_args)
            
            # 返回结果
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
            
        except Exception as e:
            logger.error(f"处理任务失败: {e}")
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "error", "error": str(e)}).encode())
    
    def _execute_ffmpeg(self, input_path: str, output_path: str, ffmpeg_args: list) -> Dict[str, Any]:
        """
        执行 FFmpeg 转码
        
        Args:
            input_path: 输入文件路径
            output_path: 输出文件路径
            ffmpeg_args: FFmpeg 参数列表
            
        Returns:
            包含转码结果的字典
        """
        WorkerHandler.status = {
            "status": "processing",
            "current_task": input_path,
            "progress": 0,
            "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        cmd = [config.ffmpeg_path, "-y", "-i", input_path] + ffmpeg_args + [output_path]
        logger.info(f"开始转码: {' '.join(cmd)}")
        
        try:
            proc = subprocess.Popen(
                cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True
            )
            
            # 获取视频时长
            duration = self._get_video_duration(input_path)
            
            # 实时读取进度
            last_percent = -1
            for line in proc.stderr:
                sec = parse_ffmpeg_progress(line)
                if sec and duration:
                    percent = int(sec / duration * 100)
                    if percent != last_percent:
                        WorkerHandler.status["progress"] = percent
                        logger.debug(f"转码进度: {percent}%")
                        last_percent = percent
            
            proc.wait()
            
            if proc.returncode == 0:
                WorkerHandler.status = {
                    "status": "completed",
                    "current_task": None,
                    "progress": 100,
                    "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                logger.info(f"转码完成: {output_path}")
                return {
                    "status": "success",
                    "output_file": output_path
                }
            else:
                WorkerHandler.status = {
                    "status": "error",
                    "current_task": None,
                    "progress": 0,
                    "error": f"FFmpeg 返回码: {proc.returncode}"
                }
                return {
                    "status": "fail",
                    "error": f"FFmpeg returned code {proc.returncode}"
                }
                
        except Exception as e:
            WorkerHandler.status = {
                "status": "error",
                "current_task": None,
                "progress": 0,
                "error": str(e)
            }
            logger.error(f"转码失败: {e}")
            return {"status": "error", "error": str(e)}
    
    def _get_video_duration(self, video_path: str) -> Optional[float]:
        """获取视频时长"""
        try:
            import ffmpeg
            probe = ffmpeg.probe(video_path)
            return float(probe['format']['duration'])
        except Exception as e:
            logger.warning(f"获取视频时长失败: {e}")
            return None
    
    def do_GET(self) -> None:
        """处理 GET 请求"""
        if self.path.startswith("/download"):
            self._handle_download()
        elif self.path == "/ping":
            self._handle_ping()
        elif self.path == "/status":
            self._handle_status()
        else:
            self.send_error(404, "Not Found")
    
    def _handle_download(self) -> None:
        """处理文件下载请求"""
        query = parse_qs(urlparse(self.path).query)
        filename = query.get("file", [None])[0]
        
        if filename:
            file_path = os.path.join(config.work_dir, filename)
            if os.path.exists(file_path):
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
                self.end_headers()
                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())
                return
        
        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"File not found")
    
    def _handle_ping(self) -> None:
        """处理健康检查请求"""
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"pong")
    
    def _handle_status(self) -> None:
        """处理状态查询请求"""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(WorkerHandler.status).encode())


class Worker:
    """
    Worker 节点类
    
    启动 HTTP 服务器监听任务请求，执行转码任务
    """
    
    def __init__(self, port: int = 9000, work_dir: str = None):
        """
        初始化 Worker
        
        Args:
            port: 监听端口
            work_dir: 工作目录
        """
        self.port = port
        self.work_dir = work_dir or config.work_dir
        self.server: Optional[HTTPServer] = None
        self._server_thread: Optional[threading.Thread] = None
        self._running = False
        
        # 确保工作目录存在
        os.makedirs(self.work_dir, exist_ok=True)
    
    def start(self) -> None:
        """启动 Worker 服务器（阻塞直到收到 KeyboardInterrupt 或 stop() 被调用）"""
        self.server = HTTPServer(('0.0.0.0', self.port), WorkerHandler)
        self._running = True
        
        logger.info(f"Worker 启动于 http://0.0.0.0:{self.port}")
        logger.info(f"工作目录: {self.work_dir}")
        
        # 在主线程中运行 serve_forever
        # KeyboardInterrupt 会被抛出到调用者
        try:
            self.server.serve_forever()
        finally:
            self._running = False
    
    def start_async(self) -> None:
        """异步启动 Worker 服务器（在后台线程中运行，立即返回）"""
        self.server = HTTPServer(('0.0.0.0', self.port), WorkerHandler)
        self._running = True
        
        logger.info(f"Worker 启动于 http://0.0.0.0:{self.port}")
        logger.info(f"工作目录: {self.work_dir}")
        
        # 在单独的线程中运行 serve_forever
        self._server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._server_thread.start()
    
    def stop(self) -> None:
        """停止 Worker 服务器"""
        if self.server:
            was_running = self._running
            self._running = False
            if was_running:
                logger.info("正在停止 Worker...")
                try:
                    self.server.shutdown()
                except Exception as e:
                    logger.debug(f"shutdown() 异常（可忽略）: {e}")
                if self._server_thread:
                    self._server_thread.join(timeout=2)
                logger.info("Worker 已停止")
    
    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        """获取当前状态"""
        return WorkerHandler.status


def main():
    """Worker 命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="启动 Transcoder Cluster Worker 节点")
    parser.add_argument("--port", type=int, default=9000, help="监听端口 (默认: 9000)")
    parser.add_argument("--work-dir", type=str, default=None, help="工作目录")
    
    args = parser.parse_args()
    
    worker = Worker(port=args.port, work_dir=args.work_dir)
    worker.start()


if __name__ == "__main__":
    main()
