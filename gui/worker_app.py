#!/usr/bin/env python3
"""
GUI Worker 节点应用

提供图形界面的 Worker 节点状态监控
使用 ttkbootstrap 实现现代化界面
"""

import os
import threading
import logging

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.widgets import ToolTip
from ttkbootstrap.widgets.scrolled import ScrolledText
from datetime import datetime

from gui.tk_compat import ensure_supported_tk, use_native_scrolledtext_on_legacy_macos, use_native_ttk_on_legacy_macos
from transcoder_cluster import __version__
from transcoder_cluster.core.worker import Worker, WorkerHandler
from transcoder_cluster.core.discovery import HeartbeatService, DiscoveryResponder
from transcoder_cluster.utils.config import config
from transcoder_cluster.utils.logger import get_logger

ttk = use_native_ttk_on_legacy_macos(ttk)
ScrolledText = use_native_scrolledtext_on_legacy_macos(ScrolledText)
logger = get_logger(__name__)


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
        
        # Worker 实例
        self.worker: Worker = None
        
        # 发现服务
        self.heartbeat: HeartbeatService = None
        self.responder: DiscoveryResponder = None
        self._runtime_log_handler = None
        self._progress_log_index = None

        # 创建界面
        self._create_ui()
        
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
        
        ttk.Label(status_grid, text="状态:", font=("Arial", 10)).grid(row=0, column=0, sticky=W, padx=5, pady=5)
        self.status_var = ttk.StringVar(value="⚪ 未启动")
        self.status_label = ttk.Label(
            status_grid, 
            textvariable=self.status_var, 
            font=("Arial", 11, "bold"),
            bootstyle="secondary"
        )
        self.status_label.grid(row=0, column=1, sticky=W, padx=5, pady=5)
        
        ttk.Label(status_grid, text="端口:", font=("Arial", 10)).grid(row=1, column=0, sticky=W, padx=5, pady=5)
        self.port_var = ttk.StringVar(value="9000")
        self.port_entry = ttk.Entry(status_grid, textvariable=self.port_var, width=15)
        self.port_entry.grid(row=1, column=1, sticky=W, padx=5, pady=5)
        
        ttk.Label(status_grid, text="工作目录:", font=("Arial", 10)).grid(row=2, column=0, sticky=W, padx=5, pady=5)
        self.work_dir_var = ttk.StringVar(value="./worker_files")
        ttk.Entry(status_grid, textvariable=self.work_dir_var, width=40).grid(row=2, column=1, sticky=W, padx=5, pady=5)
        
        # 当前任务
        task_frame = ttk.Labelframe(self.root, text="🔄 当前任务", padding=15)
        task_frame.pack(fill=X, padx=15, pady=10)
        
        task_grid = ttk.Frame(task_frame)
        task_grid.pack(fill=X)
        
        ttk.Label(task_grid, text="任务:", font=("Arial", 10)).grid(row=0, column=0, sticky=W, padx=5, pady=5)
        self.task_var = ttk.StringVar(value="无")
        ttk.Label(task_grid, textvariable=self.task_var, font=("Arial", 10)).grid(row=0, column=1, sticky=W, padx=5, pady=5)
        
        ttk.Label(task_grid, text="进度:", font=("Arial", 10)).grid(row=1, column=0, sticky=W, padx=5, pady=5)
        
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
            font=("Arial", 10, "bold"),
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
            text="⚪ 未连接", 
            bootstyle="inverse-secondary",
            font=("Arial", 10)
        )
        self.status_indicator.pack(side=LEFT, padx=10, pady=5)
        
        self.uptime_label = ttk.Label(
            self.status_bar, 
            text="运行时间: --", 
            font=("Arial", 10)
        )
        self.uptime_label.pack(side=RIGHT, padx=10, pady=5)
        
        # 记录启动时间
        self.start_time = None
    
    def _log(self, message: str):
        """添加日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._append_log_line(f"[{timestamp}]  {message}")

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
        if self.worker:
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
    
    def close(self, on_complete: callable = None):
        """关闭应用
        
        Args:
            on_complete: 关闭完成后的回调函数
        """
        self._log("正在关闭应用...")
        
        def do_close():
            if self.heartbeat:
                self.heartbeat.stop()
            
            if self.responder:
                self.responder.stop()
            
            if self.worker:
                self.worker.stop()

            self._remove_runtime_log_bridge()

            if on_complete:
                on_complete()
        
        threading.Thread(target=do_close, daemon=True).start()


def main():
    """GUI Worker 入口"""
    ensure_supported_tk()
    os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")
    version_tag = __version__ if str(__version__).startswith("v") else f"v{__version__}"
    root = ttk.Window(
        title=f"Transcoder Cluster {version_tag} - 子节点",
        themename="cosmo",
        iconphoto=None,
        #size=(600, 550)
    )
    app = WorkerApp(root)
    # Native Tk on older macOS may defer pack geometry until an idle pass.
    root.update_idletasks()
    
    # 自动启动 Worker
    root.after(100, app._start_worker)
    
    def on_close():
        app._log("正在关闭窗口...")
        # 先隐藏窗口，然后异步关闭
        root.withdraw()
        
        def do_close():
            if app.heartbeat:
                app.heartbeat.stop()
            
            if app.responder:
                app.responder.stop()
            
            if app.worker:
                app.worker.stop()

            app._remove_runtime_log_bridge()

            # 在主线程中销毁窗口
            root.after(0, root.destroy)
        
        threading.Thread(target=do_close, daemon=True).start()
    
    root.protocol("WM_DELETE_WINDOW", on_close)
    app.run()


if __name__ == "__main__":
    main()
