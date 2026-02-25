"""
Discovery 服务模块 - 节点发现和心跳机制

通过 UDP 广播实现局域网节点自动发现
"""

import json
import socket
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from transcoder_cluster.utils.config import config
from transcoder_cluster.utils.logger import get_logger

logger = get_logger(__name__)


class DiscoveryService:
    """
    节点发现服务

    使用 UDP 广播实现节点发现和心跳
    """

    def __init__(
        self,
        discovery_port: int = None,
        heartbeat_interval: int = None,
        on_node_discovered: Optional[Callable] = None,
        on_node_lost: Optional[Callable] = None,
    ):
        """
        初始化发现服务

        Args:
            discovery_port: 发现端口
            heartbeat_interval: 心跳间隔（秒）
            on_node_discovered: 发现节点回调
            on_node_lost: 节点丢失回调
        """
        self.discovery_port = discovery_port or config.discovery_port
        self.heartbeat_interval = heartbeat_interval or config.discovery_interval

        self.on_node_discovered = on_node_discovered
        self.on_node_lost = on_node_lost

        self.discovered_nodes: Dict[str, Dict[str, Any]] = {}
        self._stop_event = threading.Event()
        self._threads: list = []

    def start(self) -> None:
        """启动发现服务"""
        # 启动监听线程
        listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        listener_thread.start()
        self._threads.append(listener_thread)

        logger.info(f"发现服务启动，监听端口 {self.discovery_port}")

    def stop(self) -> None:
        """停止发现服务"""
        self._stop_event.set()
        for thread in self._threads:
            if thread.is_alive():
                thread.join(timeout=2)
        logger.info("发现服务已停止")

    def broadcast_discovery(self) -> None:
        """广播发现消息"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                msg = json.dumps({"type": "discovery"}).encode()
                # 诊断日志：获取广播地址和本机IP
                broadcast_addr = "<broadcast>"
                local_ip = self._get_local_ip()
                s.sendto(msg, (broadcast_addr, self.discovery_port))
                logger.debug(
                    f"[诊断] 广播 discovery 消息: {broadcast_addr}:{self.discovery_port}, 本机IP: {local_ip}"
                )
        except Exception as e:
            logger.error(f"广播发现消息失败: {e}")

    def _get_local_ip(self) -> str:
        """获取本地 IP"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return socket.gethostbyname(socket.gethostname())

    def _listen_loop(self) -> None:
        """监听循环"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

                # 尝试设置 SO_REUSEPORT (Windows 兼容)
                try:
                    s.setsockopt(socket.SOL_SOCKET, 0x0F, 1)  # SO_REUSEPORT
                except Exception:
                    pass

                s.bind(("", self.discovery_port))
                s.settimeout(1)

                while not self._stop_event.is_set():
                    try:
                        data, addr = s.recvfrom(4096)
                        message = json.loads(data.decode())
                        self._handle_message(message, addr[0])
                    except socket.timeout:
                        continue
                    except Exception as e:
                        if not self._stop_event.is_set():
                            logger.error(f"处理消息错误: {e}")

        except OSError as e:
            logger.error(f"绑定端口失败: {e}")

    def _handle_message(self, message: Dict[str, Any], sender_ip: str) -> None:
        """处理接收到的消息"""
        msg_type = message.get("type")

        if msg_type == "discovery_response":
            self._handle_discovery_response(message, sender_ip)
        elif msg_type == "heartbeat":
            self._handle_heartbeat(message, sender_ip)
        elif msg_type == "task_complete":
            self._handle_task_complete(message, sender_ip)

    def _handle_discovery_response(self, message: Dict[str, Any], sender_ip: str) -> None:
        """处理发现响应"""
        node_key = f"{message.get('hostname', 'unknown')}@{sender_ip}"

        self.discovered_nodes[node_key] = {
            "hostname": message.get("hostname"),
            "ip": sender_ip,
            "status": message.get("status", "unknown"),
            "last_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        logger.info(f"发现节点: {node_key}")

        if self.on_node_discovered:
            self.on_node_discovered(self.discovered_nodes[node_key])

    def _handle_heartbeat(self, message: Dict[str, Any], sender_ip: str) -> None:
        """处理心跳"""
        node_key = f"{message.get('hostname', 'unknown')}@{sender_ip}"

        self.discovered_nodes[node_key] = {
            "hostname": message.get("hostname"),
            "ip": sender_ip,
            "status": message.get("status", "unknown"),
            "last_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def _handle_task_complete(self, message: Dict[str, Any], sender_ip: str) -> None:
        """处理任务完成通知"""
        logger.info(
            f"节点 {message.get('hostname')}({sender_ip}) 完成任务 {message.get('task_id')}"
        )


class HeartbeatService:
    """
    心跳服务

    定期广播心跳通知控制端
    """

    def __init__(
        self,
        discovery_port: int = None,
        interval: int = None,
        get_status: Optional[Callable] = None,
    ):
        """
        初始化心跳服务

        Args:
            discovery_port: 发现端口
            interval: 心跳间隔（秒）
            get_status: 获取状态的回调函数
        """
        self.discovery_port = discovery_port or config.discovery_port
        self.interval = interval or config.heartbeat_interval
        self.get_status = get_status or (lambda: {"status": "idle"})

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """启动心跳服务"""
        self._thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._thread.start()
        logger.debug(
            f"[诊断] 心跳服务启动，端口: {self.discovery_port}, 间隔: {self.interval} 秒, 本机IP: {self._get_local_ip()}"
        )

    def stop(self) -> None:
        """停止心跳服务"""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        logger.info("心跳服务已停止")

    def _heartbeat_loop(self) -> None:
        """心跳循环"""
        while not self._stop_event.is_set():
            try:
                self._send_heartbeat()
            except Exception as e:
                logger.error(f"发送心跳失败: {e}")

            time.sleep(self.interval)

    def _send_heartbeat(self) -> None:
        """发送心跳"""
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

            local_ip = self._get_local_ip()
            msg = json.dumps(
                {
                    "type": "heartbeat",
                    "hostname": socket.gethostname(),
                    "ip": local_ip,
                    "status": self.get_status(),
                }
            ).encode()

            s.sendto(msg, ("<broadcast>", self.discovery_port))
            logger.debug(f"[诊断] 发送心跳: <broadcast>:{self.discovery_port}, 本机IP: {local_ip}")

    def _get_local_ip(self) -> str:
        """获取本地 IP"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return socket.gethostbyname(socket.gethostname())


class DiscoveryResponder:
    """
    发现响应器

    响应控制端的发现请求
    """

    def __init__(self, discovery_port: int = None, get_status: Optional[Callable] = None):
        """
        初始化发现响应器

        Args:
            discovery_port: 发现端口
            get_status: 获取状态的回调函数
        """
        self.discovery_port = discovery_port or config.discovery_port
        self.get_status = get_status or (lambda: {"status": "idle"})

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """启动发现响应器"""
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        logger.debug(
            f"[诊断] 发现响应器启动，监听端口: {self.discovery_port}, 本机IP: {self._get_local_ip()}"
        )

    def stop(self) -> None:
        """停止发现响应器"""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        logger.info("发现响应器已停止")

    def _listen_loop(self) -> None:
        """监听循环"""
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("", self.discovery_port))
            s.settimeout(1)

            while not self._stop_event.is_set():
                try:
                    data, addr = s.recvfrom(4096)
                    msg = json.loads(data.decode())
                    logger.debug(f"[诊断] 收到消息: {msg.get('type')} from {addr}")

                    if msg.get("type") == "discovery":
                        local_ip = self._get_local_ip()
                        response = json.dumps(
                            {
                                "type": "discovery_response",
                                "hostname": socket.gethostname(),
                                "ip": local_ip,
                                "status": self.get_status(),
                            }
                        ).encode()
                        s.sendto(response, addr)
                        logger.debug(f"[诊断] 响应 discovery 请求到 {addr}, 本机IP: {local_ip}")

                except socket.timeout:
                    continue
                except Exception as e:
                    if not self._stop_event.is_set():
                        logger.error(f"发现响应器错误: {e}")

    def _get_local_ip(self) -> str:
        """获取本地 IP"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return socket.gethostbyname(socket.gethostname())
