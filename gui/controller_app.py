#!/usr/bin/env python3
"""
GUI 控制端应用

提供图形界面的任务管理和节点监控
使用 ttkbootstrap 实现现代化界面
"""

import os
import threading
from datetime import datetime

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.scrolled import ScrolledText
from ttkbootstrap.tooltip import ToolTip
from ttkbootstrap.dialogs import Messagebox
from tkinter import filedialog

from transcoder_cluster.core.controller import Controller
from transcoder_cluster.core.discovery import DiscoveryService
from transcoder_cluster.transcode.presets import list_presets, get_preset
from transcoder_cluster.utils.config import config
from transcoder_cluster.utils.logger import get_logger

logger = get_logger(__name__)


class ControllerApp:
    """GUI 控制端应用"""
    
    def __init__(self, root: ttk.Window):
        self.root = root
        
        # 初始化控制器
        self.controller = Controller()
        
        # 发现服务
        self.discovery = DiscoveryService(
            on_node_discovered=self._on_node_discovered
        )
        
        # 创建界面
        self._create_ui()
        
        # 启动发现服务
        self.discovery.start()
        
        # 定时刷新
        self._schedule_refresh()
    
    def _create_ui(self):
        """创建用户界面"""
        # 创建主框架
        self.main_frame = ttk.Frame(self.root, padding=10)
        self.main_frame.pack(fill=BOTH, expand=YES)
        
        # 创建标签页
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.pack(fill=BOTH, expand=YES)
        
        # 节点管理标签页
        self.nodes_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.nodes_tab, text="📡 节点管理")
        self._create_nodes_tab()
        
        # 任务管理标签页
        self.tasks_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tasks_tab, text="📋 任务管理")
        self._create_tasks_tab()
        
        # 转码配置标签页
        self.transcode_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.transcode_tab, text="⚙️ 转码配置")
        self._create_transcode_tab()
        
        # 日志标签页
        self.logs_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.logs_tab, text="📜 日志")
        self._create_logs_tab()
        
        # 底部状态栏
        self._create_status_bar()
    
    def _create_status_bar(self):
        """创建底部状态栏"""
        self.status_frame = ttk.Frame(self.root, bootstyle="secondary")
        self.status_frame.pack(fill=X, padx=10, pady=(0, 10))
        
        self.status_label = ttk.Label(
            self.status_frame, 
            text="🟢 系统状态: 正常运行", 
            bootstyle="inverse-success",
            font=("Arial", 10)
        )
        self.status_label.pack(side=LEFT, padx=10, pady=5)
        
        self.stats_label = ttk.Label(
            self.status_frame, 
            text="节点: 0 | 任务: 0 | 完成: 0", 
            font=("Arial", 10)
        )
        self.stats_label.pack(side=RIGHT, padx=10, pady=5)
    
    def _create_nodes_tab(self):
        """创建节点管理标签页"""
        # 节点列表
        nodes_frame = ttk.Labelframe(self.nodes_tab, text="可用节点", padding=10)
        nodes_frame.pack(fill=BOTH, expand=YES, pady=(0, 10))
        
        columns = ("hostname", "ip", "status", "last_seen")
        self.nodes_tree = ttk.Treeview(
            nodes_frame,
            columns=columns,
            show="headings",
            bootstyle="info"
        )
        
        self.nodes_tree.heading("hostname", text="主机名")
        self.nodes_tree.heading("ip", text="IP 地址")
        self.nodes_tree.heading("status", text="状态")
        self.nodes_tree.heading("last_seen", text="最后更新")
        
        self.nodes_tree.column("hostname", width=80)
        self.nodes_tree.column("ip", width=80)
        self.nodes_tree.column("status", width=300)
        self.nodes_tree.column("last_seen", width=150)
        
        self.nodes_tree.pack(fill=BOTH, expand=YES)
        
        # 按钮
        buttons_frame = ttk.Frame(self.nodes_tab)
        buttons_frame.pack(fill=X)
        
        refresh_btn = ttk.Button(
            buttons_frame,
            text="🔄 刷新节点",
            bootstyle="success",
            command=self._scan_nodes  # 刷新节点 = 扫描节点（原逻辑）
        )
        refresh_btn.pack(side=LEFT, padx=5)
        ToolTip(refresh_btn, text="扫描网络中的节点")
    
    def _create_tasks_tab(self):
        """创建任务管理标签页"""
        # 任务列表
        tasks_frame = ttk.Labelframe(self.tasks_tab, text="任务列表", padding=10)
        tasks_frame.pack(fill=BOTH, expand=YES, pady=(0, 10))
        
        columns = ("id", "input_file", "output_file", "status", "worker", "progress")
        self.tasks_tree = ttk.Treeview(
            tasks_frame,
            columns=columns,
            show="headings",
            bootstyle="primary"
        )
        
        self.tasks_tree.heading("id", text="任务 ID")
        self.tasks_tree.heading("input_file", text="输入文件")
        self.tasks_tree.heading("output_file", text="输出文件")
        self.tasks_tree.heading("status", text="状态")
        self.tasks_tree.heading("worker", text="执行节点")
        self.tasks_tree.heading("progress", text="进度")
        
        self.tasks_tree.column("id", width=100)
        self.tasks_tree.column("input_file", width=200)
        self.tasks_tree.column("output_file", width=200)
        self.tasks_tree.column("status", width=100)
        self.tasks_tree.column("worker", width=120)
        self.tasks_tree.column("progress", width=80)
        
        self.tasks_tree.pack(fill=BOTH, expand=YES)
        
        # 任务详情区域
        details_frame = ttk.Labelframe(self.tasks_tab, text="任务详情", padding=10)
        details_frame.pack(fill=X, pady=(0, 10))
        
        self.task_details_text = ScrolledText(details_frame, height=6, wrap=WORD, autohide=True)
        self.task_details_text.pack(fill=X)
        self.task_details_text.text.config(state=DISABLED)
        
        # 绑定选择事件
        self.tasks_tree.bind("<<TreeviewSelect>>", self._on_task_select)
        
        # 按钮
        buttons_frame = ttk.Frame(self.tasks_tab)
        buttons_frame.pack(fill=X)
        
        refresh_btn = ttk.Button(
            buttons_frame, 
            text="🔄 刷新任务", 
            bootstyle="info",
            command=self._refresh_tasks
        )
        refresh_btn.pack(side=LEFT, padx=5)
        ToolTip(refresh_btn, text="刷新任务列表")
    
    def _create_transcode_tab(self):
        """创建转码配置标签页"""
        # 输入文件
        input_frame = ttk.Labelframe(self.transcode_tab, text="输入文件", padding=10)
        input_frame.pack(fill=X, pady=(0, 10))
        
        self.input_path_var = ttk.StringVar()
        ttk.Entry(input_frame, textvariable=self.input_path_var, width=60).pack(side=LEFT, padx=5)
        browse_input_btn = ttk.Button(
            input_frame, 
            text="📁 浏览...", 
            bootstyle="secondary",
            command=self._browse_input
        )
        browse_input_btn.pack(side=LEFT, padx=5)
        ToolTip(browse_input_btn, text="选择要转码的视频文件")
        
        # 输出文件
        output_frame = ttk.Labelframe(self.transcode_tab, text="输出文件", padding=10)
        output_frame.pack(fill=X, pady=(0, 10))
        
        self.output_path_var = ttk.StringVar()
        ttk.Entry(output_frame, textvariable=self.output_path_var, width=60).pack(side=LEFT, padx=5)
        browse_output_btn = ttk.Button(
            output_frame, 
            text="📁 浏览...", 
            bootstyle="secondary",
            command=self._browse_output
        )
        browse_output_btn.pack(side=LEFT, padx=5)
        ToolTip(browse_output_btn, text="选择输出文件位置")
        
        # 转码预设
        preset_frame = ttk.Labelframe(self.transcode_tab, text="转码预设", padding=10)
        preset_frame.pack(fill=X, pady=(0, 10))
        
        ttk.Label(preset_frame, text="选择预设:").pack(side=LEFT, padx=5)
        
        self.preset_var = ttk.StringVar()
        preset_combo = ttk.Combobox(
            preset_frame, 
            textvariable=self.preset_var, 
            values=list_presets(), 
            state="readonly",
            width=30
        )
        preset_combo.pack(side=LEFT, padx=5)
        preset_combo.set(list_presets()[0] if list_presets() else "")
        
        # 执行节点
        node_frame = ttk.Labelframe(self.transcode_tab, text="执行节点", padding=10)
        node_frame.pack(fill=X, pady=(0, 10))
        
        ttk.Label(node_frame, text="选择节点:").pack(side=LEFT, padx=5)
        
        self.node_var = ttk.StringVar()
        self.node_combo = ttk.Combobox(
            node_frame, 
            textvariable=self.node_var, 
            state="readonly",
            width=30
        )
        self.node_combo.pack(side=LEFT, padx=5)
        
        refresh_node_btn = ttk.Button(
            node_frame, 
            text="🔄", 
            bootstyle="secondary", 
            width=3,
            command=self._refresh_node_combo
        )
        refresh_node_btn.pack(side=LEFT, padx=5)
        ToolTip(refresh_node_btn, text="刷新节点列表")
        
        # 开始按钮
        start_btn = ttk.Button(
            self.transcode_tab, 
            text="🚀 开始转码", 
            bootstyle="primary",
            width=20,
            command=self._start_transcode
        )
        start_btn.pack(pady=20)
        ToolTip(start_btn, text="点击开始转码任务")
    
    def _create_logs_tab(self):
        """创建日志标签页"""
        self.log_text = ScrolledText(self.logs_tab, wrap=WORD, autohide=True)
        self.log_text.pack(fill=BOTH, expand=YES)
        self.log_text.text.config(state=DISABLED)
    
    def _log(self, message: str):
        """添加日志"""
        self.log_text.text.config(state=NORMAL)
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(END, f"[{timestamp}] {message}\n")
        self.log_text.see(END)
        self.log_text.text.config(state=DISABLED)
    
    def _update_stats(self):
        """更新状态栏统计"""
        node_count = len(self.discovery.discovered_nodes)
        task_count = len(self.controller.tasks)
        completed_count = sum(1 for t in self.controller.tasks if t.status == "completed")
        
        self.stats_label.config(
            text=f"节点: {node_count} | 任务: {task_count} | 完成: {completed_count}"
        )
    
    def _on_node_discovered(self, node_info: dict):
        """节点发现回调"""
        self._log(f"发现节点: {node_info.get('hostname')} ({node_info.get('ip')})")
        self._refresh_nodes()
    
    def _refresh_nodes(self):
        """刷新节点列表"""
        for item in self.nodes_tree.get_children():
            self.nodes_tree.delete(item)
        
        for node_key, node_info in self.discovery.discovered_nodes.items():
            # 格式化状态显示
            status_raw = node_info.get("status", "unknown")
            status_display = self._format_node_status(status_raw)
            self.nodes_tree.insert("", END, values=(
                node_info.get("hostname", ""),
                node_info.get("ip", ""),
                status_display,
                node_info.get("last_seen", "")
            ))
        
        self._refresh_node_combo()
        self._update_stats()
    
    def _format_node_status(self, status) -> str:
        """将节点状态转换为友好显示格式"""
        # 如果 status 是字典，提取相关信息
        if isinstance(status, dict):
            node_status = status.get("status", "unknown")
            progress = status.get("progress", 0)
            if node_status == "processing":
                return f"🔄 处理中 ({progress}%)"
            elif node_status == "completed":
                return "✅ 空闲"
            elif node_status == "idle":
                return "✅ 空闲"
            elif node_status == "error":
                return f"⚠️ 错误"
            else:
                return f"📊 {node_status}"
        
        # 如果是字符串
        status_map = {
            "idle": "✅ 空闲",
            "processing": "🔄 处理中",
            "completed": "✅ 空闲",
            "error": "⚠️ 错误",
            "unknown": "❓ 未知"
        }
        return status_map.get(status, str(status))
    
    def _refresh_tasks(self):
        """刷新任务列表"""
        for item in self.tasks_tree.get_children():
            self.tasks_tree.delete(item)
        
        for task in self.controller.tasks:
            # 状态显示友好格式
            status_display = self._format_status(task.status)
            self.tasks_tree.insert("", END, values=(
                task.id,
                os.path.basename(task.input_file),  # 只显示文件名
                os.path.basename(task.output_file),
                status_display,
                task.worker or "",
                f"{task.progress}%"
            ), iid=task.id)  # 使用 task.id 作为 iid方便查找
        
        self._update_stats()
    
    def _format_status(self, status: str) -> str:
        """将状态转换为友好显示格式"""
        status_map = {
            "pending": "⏳ 等待中",
            "uploading": "📤 上传中",
            "processing": "🔄 处理中",
            "completed": "✅ 已完成",
            "failed": "❌ 失败",
            "error": "⚠️ 错误"
        }
        return status_map.get(status, status)
    
    def _on_task_select(self, event):
        """任务选择事件处理"""
        selection = self.tasks_tree.selection()
        if not selection:
            return
        
        task_id = selection[0]
        task = next((t for t in self.controller.tasks if t.id == task_id), None)
        if not task:
            return
        
        # 格式化显示任务详情
        details = f"""任务 ID: {task.id}
状态: {self._format_status(task.status)}
进度: {task.progress}%
输入文件: {task.input_file}
输出文件: {task.output_file}
执行节点: {task.worker or '未分配'}
创建时间: {task.create_time}"""
        
        if task.error:
            details += f"\n错误信息: {task.error}"
        
        self.task_details_text.text.config(state=NORMAL)
        self.task_details_text.delete("1.0", END)
        self.task_details_text.insert(END, details)
        self.task_details_text.text.config(state=DISABLED)
    
    def _refresh_node_combo(self):
        """刷新节点下拉框"""
        nodes = [info.get("ip") for info in self.discovery.discovered_nodes.values()]
        self.node_combo["values"] = nodes
        if nodes and not self.node_var.get():
            self.node_var.set(nodes[0])
    
    def _scan_nodes(self):
        """扫描节点"""
        self._log("正在扫描节点...")
        threading.Thread(target=self._do_scan, daemon=True).start()
    
    def _do_scan(self):
        """执行扫描"""
        self.discovery.broadcast_discovery()
        self.root.after(2000, self._refresh_nodes)
    
    def _browse_input(self):
        """浏览输入文件"""
        path = filedialog.askopenfilename(
            title="选择输入文件",
            filetypes=[
                ("视频文件", "*.mp4 *.avi *.mkv *.mov *.flv *.wmv"),
                ("所有文件", "*.*")
            ]
        )
        if path:
            self.input_path_var.set(path)
            # 自动设置输出路径
            if not self.output_path_var.get():
                base, ext = os.path.splitext(path)
                self.output_path_var.set(f"{base}_output{ext}")
    
    def _browse_output(self):
        """浏览输出文件"""
        path = filedialog.asksaveasfilename(
            title="选择输出文件",
            defaultextension=".mp4",
            filetypes=[
                ("MP4 文件", "*.mp4"),
                ("MKV 文件", "*.mkv"),
                ("所有文件", "*.*")
            ]
        )
        if path:
            self.output_path_var.set(path)
    
    def _start_transcode(self):
        """开始转码"""
        input_path = self.input_path_var.get()
        output_path = self.output_path_var.get()
        preset_name = self.preset_var.get()
        worker_ip = self.node_var.get()
        
        if not input_path:
            Messagebox.show_error("请选择输入文件", "错误")
            return
        
        if not output_path:
            Messagebox.show_error("请选择输出文件", "错误")
            return
        
        if not worker_ip:
            Messagebox.show_error("请选择执行节点", "错误")
            return
        
        # 获取预设参数
        try:
            preset = get_preset(preset_name)
            ffmpeg_args = preset.to_ffmpeg_args()
        except KeyError:
            ffmpeg_args = ["-c:v", "libx265", "-crf", "28"]
        
        # 创建任务
        task = self.controller.create_task(input_path, output_path, ffmpeg_args)
        
        self._log(f"创建任务: {task.id}")
        self._log(f"输入: {input_path}")
        self._log(f"输出: {output_path}")
        self._log(f"节点: {worker_ip}")
        
        # 提交任务
        def submit_task():
            try:
                # 启动一个线程定期更新进度
                stop_progress_update = threading.Event()
                last_worker_status = [None]  # 用于跟踪上一次的 Worker 状态
                
                def update_progress():
                    """定期从 Worker 获取进度并更新任务"""
                    while not stop_progress_update.is_set():
                        try:
                            status = self.controller.get_worker_status(worker_ip)
                            current_status = status.get("status")
                            
                            # 状态变化时更新
                            if current_status == "processing":
                                progress = status.get("progress", 0)
                                task.progress = progress
                                task.status = "processing"
                                self.root.after(0, self._refresh_tasks)
                                last_worker_status[0] = "processing"
                            elif current_status == "completed":
                                # 只有之前是 processing 才认为任务完成
                                if last_worker_status[0] == "processing":
                                    task.progress = 100
                                    task.status = "completed"
                                    self.root.after(0, self._refresh_tasks)
                                    break
                            elif current_status == "idle":
                                # Worker 空闲，说明还没开始或已完成
                                if last_worker_status[0] == "processing":
                                    # 从 processing 变为 idle，说明完成了
                                    task.progress = 100
                                    task.status = "completed"
                                    self.root.after(0, self._refresh_tasks)
                                    break
                        except Exception:
                            pass
                        stop_progress_update.wait(0.5)  # 每0.5秒更新一次
                
                progress_thread = threading.Thread(target=update_progress, daemon=True)
                progress_thread.start()
                
                result = self.controller.submit_task(task, worker_ip)
                stop_progress_update.set()  # 停止进度更新线程
                
                if result.get("status") == "success":
                    task.status = "completed"
                    task.progress = 100
                    self._log(f"任务 {task.id} 完成")
                    # 下载结果
                    output_file = result.get("output_file")
                    if output_file:
                        self.controller.download_result(
                            worker_ip,
                            os.path.basename(output_file),
                            output_path
                        )
                    self.root.after(0, lambda: Messagebox.show_info(
                        f"转码完成: {output_path}", "成功"
                    ))
                else:
                    task.status = "failed"
                    self._log(f"任务 {task.id} 失败: {result.get('error')}")
                    self.root.after(0, lambda: Messagebox.show_error(
                        f"转码失败: {result.get('error')}", "失败"
                    ))
            except Exception as e:
                task.status = "error"
                task.error = str(e)
                self._log(f"任务异常: {e}")
                self.root.after(0, lambda: Messagebox.show_error(str(e), "错误"))
            
            self.root.after(0, self._refresh_tasks)
        
        threading.Thread(target=submit_task, daemon=True).start()
        self._refresh_tasks()
    
    def _schedule_refresh(self):
        """定时刷新"""
        self._refresh_nodes()
        self._refresh_tasks()
        self.root.after(5000, self._schedule_refresh)
    
    def run(self):
        """运行应用"""
        self.root.mainloop()
    
    def close(self):
        """关闭应用"""
        self.discovery.stop()


def main():
    """GUI 控制端入口"""
    root = ttk.Window(
        title="Transcoder Cluster - 控制端",
        themename="cosmo",
        size=(1255, 875)
    )
    app = ControllerApp(root)
    
    def on_close():
        app.close()
        root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_close)
    app.run()


if __name__ == "__main__":
    main()
