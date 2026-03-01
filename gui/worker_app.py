#!/usr/bin/env python3
"""
GUI Worker 节点应用

提供图形界面的 Worker 节点状态监控
使用 ttkbootstrap 实现现代化界面
"""

import os
import threading
import logging
import tkinter.messagebox as tk_messagebox
import json
import shutil
import tempfile
import zipfile

import requests
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.dialogs import Messagebox
from ttkbootstrap.widgets import ToolTip
from ttkbootstrap.widgets.scrolled import ScrolledText
from datetime import datetime
from typing import Callable, Optional

from transcoder_cluster import __version__
from transcoder_cluster.core.discovery import DiscoveryResponder, HeartbeatService
from transcoder_cluster.core.worker import (
    Worker,
    WorkerHandler,
    get_ffmpeg_version,
    list_ffmpeg_encoders,
)
from transcoder_cluster.utils.config import config
from transcoder_cluster.utils.logger import get_logger

logger = get_logger(__name__)

FONT_FAMILY = "Microsoft YaHei UI"
FONT_NORMAL = (FONT_FAMILY, 10)
FONT_BOLD = (FONT_FAMILY, 10, "bold")


class WorkerGuiLogHandler(logging.Handler):
    """将运行时日志桥接到 GUI 文本框。"""

    def __init__(self, app: "WorkerApp"):
        super().__init__(level=logging.INFO)
        self.app = app

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.INFO:
            return
        if not str(record.name).startswith("transcoder_cluster"):
            return
        try:
            self.app.root.after(0, self.app._append_runtime_log, record)
        except Exception:
            pass


class WorkerApp:
    """GUI Worker 节点应用"""
    
    def __init__(self, root: ttk.Window):
        self.root = root
        self.root.option_add("*Font", FONT_NORMAL)
        
        # Worker 实例
        self.worker: Optional[Worker] = None
        
        # 发现服务
        self.heartbeat: Optional[HeartbeatService] = None
        self.responder: Optional[DiscoveryResponder] = None
        self._runtime_log_handler = None
        self._progress_log_index = None
        self._is_in_tray = False
        self._is_closing = False
        self._tray_icon = None
        self._tray_warned_unavailable = False
        self._tray_op_in_progress = False
        self._tray_deps_checked = False
        self._pystray = None
        self._pil_image = None
        self._pil_draw = None

        self.user_config_path = os.path.join(os.getcwd(), "worker_gui_config.json")
        self._load_user_config()

        # 创建界面
        self._create_ui()
        self._refresh_ffmpeg_capabilities()

        # 窗口事件：点击 × 时询问；点击 _ 自动最小化到系统托盘
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close_request)
        self.root.bind("<Unmap>", self._on_window_unmap, add="+")
        
        # 定时刷新状态
        self._schedule_refresh()
    
    def _create_ui(self):
        """创建用户界面"""
        # 状态框架
        status_frame = ttk.Labelframe(self.root, text="📊 节点状态", padding=15)
        status_frame.pack(fill=X, padx=15, pady=(15, 10))
        
        # 状态指示器
        status_grid = ttk.Frame(status_frame)
        status_grid.pack(fill=X)
        
        ttk.Label(status_grid, text="FFmpeg:", font=FONT_NORMAL).grid(row=0, column=0, sticky=W, padx=5, pady=5)

        self.ffmpeg_row_frame = ttk.Frame(status_grid)
        self.ffmpeg_row_frame.grid(row=0, column=1, columnspan=4, sticky=W, padx=(5, 0), pady=5)

        self.ffmpeg_installed_var = ttk.StringVar(value="")
        self.ffmpeg_installed_label = ttk.Label(
            self.ffmpeg_row_frame,
            textvariable=self.ffmpeg_installed_var,
            font=FONT_BOLD,
            bootstyle="success",
        )
        self.ffmpeg_installed_label.pack(side=LEFT)

        self.ffmpeg_version_var = ttk.StringVar(value="检测中...")
        self.ffmpeg_version_label = ttk.Label(
            self.ffmpeg_row_frame,
            textvariable=self.ffmpeg_version_var,
            font=FONT_BOLD,
        )
        self.ffmpeg_version_label.pack(side=LEFT, padx=(4, 0))

        self.capabilities_var = ttk.StringVar(value="支持能力：检测中...")
        self.capabilities_label = ttk.Label(
            self.ffmpeg_row_frame,
            textvariable=self.capabilities_var,
            font=FONT_NORMAL,
        )
        self.capabilities_label.pack(side=LEFT, padx=(16, 0))

        self.install_ffmpeg_btn = ttk.Button(
            self.ffmpeg_row_frame,
            text="安装 FFmpeg",
            bootstyle="warning",
            command=self._install_ffmpeg,
            padding=(8, 3),
        )
        self.install_ffmpeg_btn.pack(side=LEFT, padx=(8, 0))
        self.install_ffmpeg_btn.pack_forget()
        ToolTip(self.install_ffmpeg_btn, text="未检测到 FFmpeg 时可自动下载安装")

        ttk.Label(status_grid, text="状态:", font=FONT_NORMAL).grid(row=1, column=0, sticky=W, padx=5, pady=5)
        self.status_var = ttk.StringVar(value="⚪ 未启动")
        self.status_label = ttk.Label(
            status_grid,
            textvariable=self.status_var,
            font=FONT_BOLD,
            bootstyle="secondary",
        )
        self.status_label.grid(row=1, column=1, sticky=W, padx=5, pady=5)

        ttk.Label(status_grid, text="端口:", font=FONT_NORMAL).grid(row=2, column=0, sticky=W, padx=5, pady=5)
        self.port_var = ttk.StringVar(value="9000")
        self.port_entry = ttk.Entry(status_grid, textvariable=self.port_var, width=15)
        self.port_entry.grid(row=2, column=1, sticky=W, padx=5, pady=5)

        ttk.Label(status_grid, text="工作目录:", font=FONT_NORMAL).grid(row=3, column=0, sticky=W, padx=5, pady=5)
        self.work_dir_var = ttk.StringVar(value="./worker_files")
        ttk.Entry(status_grid, textvariable=self.work_dir_var, width=40).grid(row=3, column=1, columnspan=4, sticky=W, padx=5, pady=5)
        
        # 当前任务
        task_frame = ttk.Labelframe(self.root, text="🔄 当前任务", padding=15)
        task_frame.pack(fill=X, padx=15, pady=10)
        
        task_grid = ttk.Frame(task_frame)
        task_grid.pack(fill=X)
        
        ttk.Label(task_grid, text="任务:", font=FONT_NORMAL).grid(row=0, column=0, sticky=W, padx=5, pady=5)
        self.task_var = ttk.StringVar(value="无")
        ttk.Label(task_grid, textvariable=self.task_var, font=FONT_NORMAL).grid(row=0, column=1, sticky=W, padx=5, pady=5)

        ttk.Label(task_grid, text="进度:", font=FONT_NORMAL).grid(row=1, column=0, sticky=W, padx=5, pady=5)
        
        # 进度条框架
        progress_frame = ttk.Frame(task_grid)
        progress_frame.grid(row=1, column=1, sticky=W, padx=5, pady=5)
        
        self.progress_var = ttk.IntVar(value=0)
        self.progress_bar = ttk.Progressbar(
            progress_frame, 
            variable=self.progress_var, 
            maximum=100, 
            length=500,
            bootstyle="striped"
        )
        self.progress_bar.pack(side=LEFT)
        
        self.progress_label = ttk.Label(
            progress_frame, 
            text="0%", 
            font=FONT_BOLD,
            bootstyle="primary"
        )
        self.progress_label.pack(side=LEFT, padx=10)
        
        # 控制按钮
        control_frame = ttk.Frame(self.root, padding=15)
        control_frame.pack(fill=X, padx=15, pady=10)
        
        self.start_btn = ttk.Button(
            control_frame, 
            text="🚀 启动", 
            bootstyle="success",
            width=15,
            command=self._start_worker
        )
        self.start_btn.pack(side=LEFT, padx=10)
        ToolTip(self.start_btn, text="启动 Worker 节点")
        
        self.stop_btn = ttk.Button(
            control_frame, 
            text="⏹️ 停止", 
            bootstyle="danger",
            width=15,
            command=self._stop_worker
        )
        self.stop_btn.pack(side=LEFT, padx=10)
        self.stop_btn.config(state=DISABLED)
        ToolTip(self.stop_btn, text="停止 Worker 节点")
        
        # 日志
        log_frame = ttk.Labelframe(self.root, text="📜 日志", padding=10)
        log_frame.pack(fill=BOTH, expand=YES, padx=15, pady=(10, 15))
        
        self.log_text = ScrolledText(log_frame, wrap=WORD, autohide=True, height=10)
        self.log_text.pack(fill=BOTH, expand=YES)
        self.log_text.text.config(state=DISABLED)
        
        # 底部状态栏
        self._create_status_bar()
    
    def _create_status_bar(self):
        """创建底部状态栏"""
        self.status_bar = ttk.Frame(self.root, bootstyle="secondary")
        self.status_bar.pack(fill=X, padx=15, pady=(0, 10))
        
        self.status_indicator = ttk.Label(
            self.status_bar, 
            text="⚪ 未启动", 
            bootstyle="inverse-secondary",
            font=FONT_NORMAL,
        )
        self.status_indicator.pack(side=LEFT, padx=10, pady=5)

        # 运行时间
        self.uptime_label = ttk.Label(
            self.status_bar, 
            text="运行时间: --", 
            font=FONT_NORMAL,
        )
        self.uptime_label.pack(side=RIGHT, padx=10, pady=5)

        # 记录启动时间
        self.start_time = None

    def _refresh_ffmpeg_capabilities(self):
        """刷新 FFmpeg 与能力展示。"""
        version = get_ffmpeg_version(config.ffmpeg_path)
        if version:
            self.ffmpeg_version_var.set(version)
            self.ffmpeg_installed_var.set("已安装")
            self.ffmpeg_installed_label.config(bootstyle="success")
            self._set_install_button_visible(False)
            self._update_capabilities(ffmpeg_available=True)
            return

        self.ffmpeg_version_var.set("")
        self.ffmpeg_installed_var.set("未安装")
        self.ffmpeg_installed_label.config(bootstyle="danger")
        self._set_install_button_visible(True)
        self._update_capabilities(ffmpeg_available=False)

    def _update_capabilities(self, ffmpeg_available: bool):
        """更新编码能力文案。"""
        if not ffmpeg_available:
            self.capabilities_var.set("支持能力：软解")
            return

        try:
            encoders = list_ffmpeg_encoders(config.ffmpeg_path)
            has_nvenc = "h264_nvenc" in encoders or "hevc_nvenc" in encoders
            if has_nvenc:
                self.capabilities_var.set("支持能力：软解，NVENC")
            else:
                self.capabilities_var.set("支持能力：软解")
        except Exception:
            self.capabilities_var.set("支持能力：软解")

    def _set_install_button_visible(self, visible: bool):
        """根据 FFmpeg 状态切换安装按钮显示。"""
        if visible:
            self.install_ffmpeg_btn.pack(side=LEFT, padx=(8, 0))
        else:
            self.install_ffmpeg_btn.pack_forget()

    def _install_ffmpeg(self):
        """自动安装 FFmpeg（Windows）。"""
        self._log("开始安装 FFmpeg...")
        self.install_ffmpeg_btn.config(state=DISABLED)

        def runner():
            try:
                self._log_threadsafe("[1/5] 正在准备安装环境...")
                self._install_ffmpeg_windows()
                self._log_threadsafe("FFmpeg 安装完成")
                self.root.after(0, lambda: Messagebox.show_info("FFmpeg 安装完成", "成功"))
            except Exception as error:
                logger.exception("安装 FFmpeg 失败")
                self._log_threadsafe(f"FFmpeg 安装失败: {error}")
                self.root.after(
                    0,
                    lambda: Messagebox.show_error(
                        f"自动安装失败: {error}\n请手动安装 FFmpeg 并加入 PATH，或设置 TC_FFMPEG_PATH。",
                        "安装失败",
                    ),
                )
            finally:
                self.root.after(0, self._refresh_ffmpeg_capabilities)
                self.root.after(0, lambda: self.install_ffmpeg_btn.config(state=NORMAL))

        threading.Thread(target=runner, daemon=True).start()

    def _install_ffmpeg_windows(self):
        """下载并安装 FFmpeg 到 tools/ffmpeg/bin。"""
        if os.name != "nt":
            raise RuntimeError("当前仅支持 Windows 自动安装")

        download_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, "ffmpeg.zip")
            extract_dir = os.path.join(temp_dir, "extract")

            self._log_threadsafe("[2/5] 正在下载 FFmpeg 安装包...")
            response = requests.get(download_url, stream=True, timeout=90)
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))
            downloaded_size = 0
            next_progress_mark = 10
            with open(zip_path, "wb") as file:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        file.write(chunk)

                        if total_size > 0:
                            downloaded_size += len(chunk)
                            progress = int(downloaded_size * 100 / total_size)
                            while progress >= next_progress_mark and next_progress_mark <= 100:
                                self._log_threadsafe(f"下载进度: {next_progress_mark}%")
                                next_progress_mark += 10

            if total_size <= 0:
                self._log_threadsafe("下载完成")

            self._log_threadsafe("[3/5] 正在解压安装包...")
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)

            self._log_threadsafe("[4/5] 正在定位并复制 ffmpeg.exe...")
            ffmpeg_exe = None
            ffprobe_exe = None
            for root_dir, _, files in os.walk(extract_dir):
                if "ffmpeg.exe" in files:
                    ffmpeg_exe = os.path.join(root_dir, "ffmpeg.exe")
                if "ffprobe.exe" in files:
                    ffprobe_exe = os.path.join(root_dir, "ffprobe.exe")

            if not ffmpeg_exe:
                raise RuntimeError("安装包中未找到 ffmpeg.exe")

            install_bin = os.path.join(os.getcwd(), "tools", "ffmpeg", "bin")
            os.makedirs(install_bin, exist_ok=True)

            target_ffmpeg = os.path.join(install_bin, "ffmpeg.exe")
            shutil.copy2(ffmpeg_exe, target_ffmpeg)

            if ffprobe_exe:
                target_ffprobe = os.path.join(install_bin, "ffprobe.exe")
                shutil.copy2(ffprobe_exe, target_ffprobe)

            self._log_threadsafe("[5/5] 正在保存配置...")
            config.ffmpeg_path = target_ffmpeg
            self._save_user_config()

    def _load_user_config(self):
        """加载 Worker GUI 本地配置。"""
        if not os.path.exists(self.user_config_path):
            return
        try:
            with open(self.user_config_path, "r", encoding="utf-8") as file:
                data = json.load(file)
            ffmpeg_path = data.get("ffmpeg_path")
            if ffmpeg_path:
                config.ffmpeg_path = ffmpeg_path
        except Exception as error:
            logger.warning(f"读取 Worker GUI 配置失败: {error}")

    def _save_user_config(self):
        """保存 Worker GUI 本地配置。"""
        try:
            with open(self.user_config_path, "w", encoding="utf-8") as file:
                json.dump({"ffmpeg_path": config.ffmpeg_path}, file, ensure_ascii=False, indent=2)
        except Exception as error:
            logger.warning(f"保存 Worker GUI 配置失败: {error}")
    
    def _load_tray_dependencies(self):
        """按需加载托盘依赖，避免影响启动速度。"""
        if self._tray_deps_checked:
            return
        self._tray_deps_checked = True

        try:
            import pystray as pystray_module
            self._pystray = pystray_module
        except Exception:
            self._pystray = None

        try:
            from PIL import Image as pil_image
            from PIL import ImageDraw as pil_draw

            self._pil_image = pil_image
            self._pil_draw = pil_draw
        except Exception:
            self._pil_image = None
            self._pil_draw = None

    def _tray_supported(self) -> bool:
        self._load_tray_dependencies()
        return bool(self._pystray and self._pil_image and self._pil_draw)

    def _create_tray_image(self):
        """创建托盘图标。"""
        # 16x16 简单双色图标，避免依赖外部图片资源。
        img = self._pil_image.new("RGB", (16, 16), "#1F6AA5")
        draw = self._pil_draw.Draw(img)
        draw.rectangle((3, 3, 12, 12), outline="white", width=1)
        draw.rectangle((5, 5, 10, 10), fill="white")
        return img

    def _ensure_tray_icon(self) -> bool:
        """确保系统托盘图标可用。"""
        if self._tray_icon is not None:
            return True
        if not self._tray_supported():
            if not self._tray_warned_unavailable:
                self._tray_warned_unavailable = True
                Messagebox.show_warning("系统托盘依赖缺失（pystray/Pillow），将退化为任务栏最小化。", "提示")
            return False

        # Windows 下 default=True 的菜单项可通过双击托盘图标触发。
        menu = self._pystray.Menu(
            self._pystray.MenuItem(
                "打开窗口",
                lambda _icon, _item: self.root.after(0, self._restore_from_tray),
                default=True,
            ),
            self._pystray.MenuItem("退出子节点", lambda _icon, _item: self.root.after(0, self._exit_application)),
        )
        self._tray_icon = self._pystray.Icon(
            "transcoder_cluster_worker",
            self._create_tray_image(),
            "Transcoder Cluster 子节点",
            menu,
        )
        threading.Thread(target=self._tray_icon.run, daemon=True).start()
        return True

    def _stop_tray_icon(self):
        icon = self._tray_icon
        self._tray_icon = None
        if icon is None:
            return
        try:
            icon.stop()
        except Exception as error:
            logger.debug(f"停止托盘图标失败: {error}")

    def _show_tray_minimize_notification(self, retries: int = 3):
        """最小化到托盘后显示系统通知。"""
        icon = self._tray_icon
        if icon is None:
            return
        notify_func = getattr(icon, "notify", None)
        if not callable(notify_func):
            return
        try:
            notify_func("子节点正在后台运行，双击托盘图标可恢复窗口。", "Transcoder Cluster 子节点")
        except Exception:
            # 托盘线程刚启动时可能短暂不可用，做有限次重试。
            if retries > 0:
                self.root.after(180, lambda: self._show_tray_minimize_notification(retries=retries - 1))

    def _minimize_to_tray(self, show_log: bool = True):
        """最小化到系统托盘并后台运行。"""
        if self._is_in_tray or self._is_closing:
            return
        if self._tray_op_in_progress:
            return
        self._tray_op_in_progress = True
        try:
            if self._ensure_tray_icon():
                self.root.withdraw()
                self._is_in_tray = True
                if show_log:
                    self._log("窗口已最小化到系统托盘，子节点继续后台运行")
                self._show_tray_minimize_notification()
            else:
                # 依赖缺失时回退到任务栏最小化
                self.root.iconify()
                if show_log:
                    self._log("窗口已最小化到任务栏，子节点继续后台运行")
        finally:
            self._tray_op_in_progress = False

    def _restore_from_tray(self):
        """从系统托盘恢复窗口。"""
        if not self._is_in_tray:
            return
        self._is_in_tray = False
        try:
            self.root.deiconify()
            self.root.state("normal")
            self.root.lift()
        except Exception as error:
            logger.debug(f"恢复窗口失败: {error}")
        self._stop_tray_icon()
        self._log("窗口已从系统托盘恢复")

    def _on_window_unmap(self, _event=None):
        """处理标题栏最小化（_）：自动入托盘后台运行。"""
        if self._is_closing or self._is_in_tray:
            return
        try:
            if str(self.root.state()) == "iconic":
                # 用 after 回到主循环再处理，避免窗口状态竞争。
                self.root.after(0, self._minimize_to_tray)
        except Exception:
            pass

    def _on_window_close_request(self):
        """点击窗口 × 时，询问最小化到系统托盘还是退出。"""
        confirm = tk_messagebox.askokcancel(
            title="关闭确认",
            message="确定：最小化到系统托盘并后台运行\n取消：停止子节点并退出",
            parent=self.root,
        )
        if confirm:
            self._minimize_to_tray(show_log=True)
            return
        self._exit_application()

    def _exit_application(self):
        """真正退出程序（停止节点后退出）。"""
        if self._is_closing:
            return
        self._is_closing = True
        self._log("正在关闭窗口...")

        def on_complete() -> None:
            self.root.after(0, self.root.destroy)

        self.close(on_complete=on_complete)
    
    def _log(self, message: str):
        """添加日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._append_log_line(f"[{timestamp}]  {message}")

    def _log_threadsafe(self, message: str):
        """在后台线程中安全写入 GUI 日志。"""
        try:
            self.root.after(0, self._log, message)
        except Exception:
            logger.info(message)

    def _append_log_line(self, line: str):
        """向日志框追加一行文本。"""
        if not getattr(self, "log_text", None):
            return
        if not self.log_text.text.winfo_exists():
            return
        self.log_text.text.config(state=NORMAL)
        self.log_text.insert(END, f"{line}\n")
        self.log_text.see(END)
        self.log_text.text.config(state=DISABLED)

    def _append_runtime_log(self, record: logging.LogRecord):
        """将运行日志按用户可读格式写入 GUI。"""
        if not getattr(self, "log_text", None):
            return
        if not self.log_text.text.winfo_exists():
            return

        message = record.getMessage().strip()
        timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        line = f"[{timestamp}]  {message}"
        is_progress = message.startswith("转码进度:")

        text_widget = self.log_text.text
        text_widget.config(state=NORMAL)
        if is_progress:
            if self._progress_log_index:
                try:
                    text_widget.delete(self._progress_log_index, f"{self._progress_log_index} lineend+1c")
                    text_widget.insert(self._progress_log_index, f"{line}\n")
                except Exception:
                    text_widget.insert(END, f"{line}\n")
                    self._progress_log_index = text_widget.index("end-2l linestart")
            else:
                text_widget.insert(END, f"{line}\n")
                self._progress_log_index = text_widget.index("end-2l linestart")
            text_widget.see(self._progress_log_index)
        else:
            text_widget.insert(END, f"{line}\n")
            text_widget.see(END)
            if self._progress_log_index and (
                message.startswith("转码完成")
                or message.startswith("转码失败")
                or message.startswith("收到停止请求")
                or message.startswith("FFmpeg 进程已终止")
            ):
                self._progress_log_index = None
        text_widget.config(state=DISABLED)

    def _install_runtime_log_bridge(self):
        """安装日志桥接，GUI 中显示与 CLI 一致的 INFO 日志。"""
        if self._runtime_log_handler is not None:
            return
        self._progress_log_index = None
        target_logger = logging.getLogger("transcoder_cluster")
        if target_logger.level > logging.INFO:
            target_logger.setLevel(logging.INFO)
        handler = WorkerGuiLogHandler(self)
        target_logger.addHandler(handler)
        self._runtime_log_handler = handler

    def _remove_runtime_log_bridge(self):
        """卸载日志桥接，避免重复输出。"""
        if self._runtime_log_handler is None:
            self._progress_log_index = None
            return
        target_logger = logging.getLogger("transcoder_cluster")
        try:
            target_logger.removeHandler(self._runtime_log_handler)
            self._runtime_log_handler.close()
        finally:
            self._runtime_log_handler = None
            self._progress_log_index = None
    
    def _update_status_style(self, status: str):
        """根据状态更新样式"""
        if status == "运行中":
            self.status_label.config(bootstyle="success")
            self.status_indicator.config(text="🟢 运行中", bootstyle="inverse-success")
        elif status == "已停止":
            self.status_label.config(bootstyle="danger")
            self.status_indicator.config(text="🔴 已停止", bootstyle="inverse-danger")
        elif status == "处理中":
            self.status_label.config(bootstyle="warning")
            self.status_indicator.config(text="🟡 处理中", bootstyle="inverse-warning")
        else:
            self.status_label.config(bootstyle="secondary")
            self.status_indicator.config(text="⚪ 未启动", bootstyle="inverse-secondary")
    
    def _start_worker(self):
        """启动 Worker"""
        if not get_ffmpeg_version(config.ffmpeg_path):
            self._refresh_ffmpeg_capabilities()
            Messagebox.show_error("未检测到 FFmpeg，请先点击“安装 FFmpeg”完成安装。", "错误")
            return

        try:
            port = int(self.port_var.get())
            work_dir = self.work_dir_var.get()
        except ValueError:
            self._log("❌ 错误: 端口必须是数字")
            return
        
        # 创建工作目录
        os.makedirs(work_dir, exist_ok=True)

        # 启动前安装日志桥接，捕获完整运行日志。
        self._install_runtime_log_bridge()
        
        # 启动 Worker（使用 start_async 在后台线程运行）
        self.worker = Worker(port=port, work_dir=work_dir)
        self.worker.start_async()
        
        # 启动发现服务
        self.heartbeat = HeartbeatService(
            get_status=lambda: WorkerHandler.status
        )
        self.heartbeat.start()
        
        self.responder = DiscoveryResponder(
            get_status=lambda: WorkerHandler.status
        )
        self.responder.start()
        
        # 记录启动时间
        self.start_time = datetime.now()
        
        # 更新 UI
        self.status_var.set("🟢 运行中")
        self._update_status_style("运行中")
        self.start_btn.config(state=DISABLED)
        self.stop_btn.config(state=NORMAL)
        self.port_entry.config(state=DISABLED)
        
        self._log(f"✅ Worker 启动于端口 {port}")
        self._log(f"📁 工作目录: {work_dir}")
    
    def _stop_worker(self):
        """停止 Worker"""
        self._log("正在停止 Worker...")
        
        # 在后台线程中执行停止操作，避免阻塞 UI
        def do_stop():
            if self.heartbeat:
                self.heartbeat.stop()
            
            if self.responder:
                self.responder.stop()
            
            if self.worker:
                self.worker.stop()
            
            # 在主线程中更新 UI
            self.root.after(0, self._on_stop_complete)
        
        threading.Thread(target=do_stop, daemon=True).start()
    
    def _on_stop_complete(self):
        """停止完成后的 UI 更新"""
        self.worker = None
        self.heartbeat = None
        self.responder = None

        self._remove_runtime_log_bridge()
        self._progress_log_index = None
        # 重置启动时间
        self.start_time = None
        self.status_var.set("🔴 已停止")
        self._update_status_style("已停止")
        self.start_btn.config(state=NORMAL)
        self.stop_btn.config(state=DISABLED)
        self.port_entry.config(state=NORMAL)
        self.progress_var.set(0)
        self.progress_label.config(text="0%")
        self.task_var.set("无")
        self._log("⏹️ Worker 已停止")
    
    def _update_uptime(self):
        """更新运行时间显示"""
        if self.start_time:
            elapsed = datetime.now() - self.start_time
            hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            self.uptime_label.config(text=f"运行时间: {hours:02d}:{minutes:02d}:{seconds:02d}")
        else:
            self.uptime_label.config(text="运行时间: --")
    
    def _schedule_refresh(self):
        """定时刷新状态"""
        if self._is_closing:
            return

        if self.worker and getattr(self.worker, "_running", False):
            status = WorkerHandler.status
            
            # 更新状态
            worker_status = status.get("status", "unknown")
            if worker_status == "processing":
                self.status_var.set("🟡 处理中")
                self._update_status_style("处理中")
            else:
                self.status_var.set("🟢 运行中")
                self._update_status_style("运行中")
            
            # 更新任务
            current_task = status.get("current_task")
            if current_task:
                self.task_var.set(os.path.basename(current_task) if current_task else "无")
            else:
                self.task_var.set("无")
            
            # 更新进度
            progress = status.get("progress", 0)
            self.progress_var.set(progress)
            self.progress_label.config(text=f"{progress}%")
            
            # 根据进度更新进度条颜色
            if progress < 30:
                self.progress_bar.config(bootstyle="danger striped")
            elif progress < 70:
                self.progress_bar.config(bootstyle="warning striped")
            else:
                self.progress_bar.config(bootstyle="success striped")
        
        # 更新运行时间
        self._update_uptime()
        
        self.root.after(1000, self._schedule_refresh)
    
    def run(self):
        """运行应用"""
        self.root.mainloop()
    
    def close(self, on_complete: Optional[Callable[[], None]] = None):
        """关闭应用
        
        Args:
            on_complete: 关闭完成后的回调函数
        """
        self._log("正在关闭应用...")
        
        def do_close():
            if self.heartbeat:
                self.heartbeat.stop()
                self.heartbeat = None

            if self.responder:
                self.responder.stop()
                self.responder = None

            if self.worker:
                self.worker.stop()
                self.worker = None

            self._remove_runtime_log_bridge()
            self._stop_tray_icon()

            if on_complete:
                on_complete()
        
        threading.Thread(target=do_close, daemon=True).start()


def main():
    """GUI Worker 入口"""
    version_tag = __version__ if str(__version__).startswith("v") else f"v{__version__}"
    root = ttk.Window(
        title=f"Transcoder Cluster {version_tag} - 子节点",
        themename="cosmo",
        #size=(600, 550)
    )
    app = WorkerApp(root)
    
    # 自动启动 Worker
    root.after(100, app._start_worker)

    app.run()


if __name__ == "__main__":
    main()
