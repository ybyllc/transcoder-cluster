#!/usr/bin/env python3
"""
GUI Worker 节点应用

提供图形界面的 Worker 节点状态监控
"""

import os
import threading

import tkinter as tk
from tkinter import ttk, scrolledtext
from datetime import datetime

from transcoder_cluster.core.worker import Worker, WorkerHandler
from transcoder_cluster.core.discovery import HeartbeatService, DiscoveryResponder
from transcoder_cluster.utils.config import config
from transcoder_cluster.utils.logger import get_logger

logger = get_logger(__name__)


class WorkerApp:
    """GUI Worker 节点应用"""
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Transcoder Cluster - Worker 节点")
        self.root.geometry("600x500")
        
        # Worker 实例
        self.worker: Worker = None
        
        # 发现服务
        self.heartbeat: HeartbeatService = None
        self.responder: DiscoveryResponder = None
        
        # 创建界面
        self._create_ui()
        
        # 定时刷新状态
        self._schedule_refresh()
    
    def _create_ui(self):
        """创建用户界面"""
        # 状态框架
        status_frame = ttk.LabelFrame(self.root, text="节点状态", padding="10")
        status_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # 状态标签
        ttk.Label(status_frame, text="状态:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.status_var = tk.StringVar(value="未启动")
        ttk.Label(status_frame, textvariable=self.status_var, font=("Arial", 10, "bold")).grid(row=0, column=1, sticky=tk.W)
        
        ttk.Label(status_frame, text="端口:").grid(row=1, column=0, sticky=tk.W, padx=5)
        self.port_var = tk.StringVar(value="9000")
        ttk.Entry(status_frame, textvariable=self.port_var, width=10).grid(row=1, column=1, sticky=tk.W)
        
        ttk.Label(status_frame, text="工作目录:").grid(row=2, column=0, sticky=tk.W, padx=5)
        self.work_dir_var = tk.StringVar(value="./worker_files")
        ttk.Entry(status_frame, textvariable=self.work_dir_var, width=40).grid(row=2, column=1, sticky=tk.W)
        
        # 当前任务
        task_frame = ttk.LabelFrame(self.root, text="当前任务", padding="10")
        task_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Label(task_frame, text="任务:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.task_var = tk.StringVar(value="无")
        ttk.Label(task_frame, textvariable=self.task_var).grid(row=0, column=1, sticky=tk.W)
        
        ttk.Label(task_frame, text="进度:").grid(row=1, column=0, sticky=tk.W, padx=5)
        self.progress_var = tk.IntVar(value=0)
        self.progress_bar = ttk.Progressbar(task_frame, variable=self.progress_var, maximum=100, length=300)
        self.progress_bar.grid(row=1, column=1, sticky=tk.W)
        
        self.progress_label = ttk.Label(task_frame, text="0%")
        self.progress_label.grid(row=1, column=2, padx=5)
        
        # 控制按钮
        control_frame = ttk.Frame(self.root, padding="10")
        control_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.start_btn = ttk.Button(control_frame, text="启动", command=self._start_worker)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(control_frame, text="停止", command=self._stop_worker, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        # 日志
        log_frame = ttk.LabelFrame(self.root, text="日志", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=10)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.config(state=tk.DISABLED)
    
    def _log(self, message: str):
        """添加日志"""
        self.log_text.config(state=tk.NORMAL)
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def _start_worker(self):
        """启动 Worker"""
        try:
            port = int(self.port_var.get())
            work_dir = self.work_dir_var.get()
        except ValueError:
            self._log("错误: 端口必须是数字")
            return
        
        # 创建工作目录
        os.makedirs(work_dir, exist_ok=True)
        
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
        
        # 更新 UI
        self.status_var.set("运行中")
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.port_var.trace_add("write", lambda *args: None)  # 禁用修改
        
        self._log(f"Worker 启动于端口 {port}")
        self._log(f"工作目录: {work_dir}")
    
    def _stop_worker(self):
        """停止 Worker"""
        if self.worker:
            self.worker.stop()
        
        if self.heartbeat:
            self.heartbeat.stop()
        
        if self.responder:
            self.responder.stop()
        
        # 更新 UI
        self.status_var.set("已停止")
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        
        self._log("Worker 已停止")
    
    def _schedule_refresh(self):
        """定时刷新状态"""
        if self.worker:
            status = WorkerHandler.status
            
            # 更新状态
            self.status_var.set(status.get("status", "unknown"))
            
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
        
        self.root.after(1000, self._schedule_refresh)
    
    def run(self):
        """运行应用"""
        self.root.mainloop()
    
    def close(self):
        """关闭应用"""
        self._stop_worker()


def main():
    """GUI Worker 入口"""
    root = tk.Tk()
    app = WorkerApp(root)
    
    def on_close():
        app.close()
        root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_close)
    app.run()


if __name__ == "__main__":
    main()
