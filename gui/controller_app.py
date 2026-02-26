#!/usr/bin/env python3
"""
GUI 控制端应用

提供图形界面的任务管理和节点监控
"""

import os
import subprocess
import sys
import threading
from datetime import datetime

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog

from transcoder_cluster.core.controller import Controller
from transcoder_cluster.core.discovery import DiscoveryService
from transcoder_cluster.transcode.presets import list_presets, get_preset
from transcoder_cluster.utils.config import config
from transcoder_cluster.utils.logger import get_logger

logger = get_logger(__name__)


def send_system_notification(title: str, message: str):
    """发送系统通知
    
    Args:
        title: 通知标题
        message: 通知内容
    """
    try:
        if sys.platform == 'win32':
            # Windows: 使用 PowerShell 发送 Toast 通知
            ps_script = f'''
            [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
            [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
            $template = @"
            <toast>
                <visual>
                    <binding template="ToastText02">
                        <text id="1">{title}</text>
                        <text id="2">{message}</text>
                    </binding>
                </visual>
            </toast>
"@
            $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
            $xml.LoadXml($template)
            $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
            [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Transcoder Cluster").Show($toast)
            '''
            subprocess.run(['powershell', '-Command', ps_script],
                         capture_output=True, timeout=10)
        elif sys.platform == 'darwin':
            # macOS: 使用 osascript
            subprocess.run(['osascript', '-e',
                          f'display notification "{message}" with title "{title}"'],
                         capture_output=True, timeout=10)
        else:
            # Linux: 使用 notify-send
            subprocess.run(['notify-send', title, message],
                         capture_output=True, timeout=10)
    except Exception as e:
        logger.debug(f"发送系统通知失败: {e}")


class ControllerApp:
    """GUI 控制端应用"""
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Transcoder Cluster - 控制端")
        self.root.geometry("1024x768")
        
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
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建标签页
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # 节点管理标签页
        self.nodes_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.nodes_tab, text="节点管理")
        self._create_nodes_tab()
        
        # 任务管理标签页
        self.tasks_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.tasks_tab, text="任务管理")
        self._create_tasks_tab()
        
        # 转码配置标签页
        self.transcode_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.transcode_tab, text="转码配置")
        self._create_transcode_tab()
        
        # 日志标签页
        self.logs_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.logs_tab, text="日志")
        self._create_logs_tab()
    
    def _create_nodes_tab(self):
        """创建节点管理标签页"""
        # 节点列表
        nodes_frame = ttk.LabelFrame(self.nodes_tab, text="可用节点")
        nodes_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        columns = ("hostname", "ip", "status", "last_seen")
        self.nodes_tree = ttk.Treeview(nodes_frame, columns=columns, show="headings")
        
        self.nodes_tree.heading("hostname", text="主机名")
        self.nodes_tree.heading("ip", text="IP 地址")
        self.nodes_tree.heading("status", text="状态")
        self.nodes_tree.heading("last_seen", text="最后更新")
        
        self.nodes_tree.column("hostname", width=150)
        self.nodes_tree.column("ip", width=150)
        self.nodes_tree.column("status", width=200)
        self.nodes_tree.column("last_seen", width=200)
        
        self.nodes_tree.pack(fill=tk.BOTH, expand=True)
        
        # 按钮
        buttons_frame = ttk.Frame(self.nodes_tab)
        buttons_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(buttons_frame, text="刷新节点", command=self._scan_nodes).pack(side=tk.LEFT, padx=5)
    
    def _create_tasks_tab(self):
        """创建任务管理标签页"""
        # 任务列表
        tasks_frame = ttk.LabelFrame(self.tasks_tab, text="任务列表")
        tasks_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        columns = ("id", "input_file", "output_file", "status", "worker", "progress")
        self.tasks_tree = ttk.Treeview(tasks_frame, columns=columns, show="headings")
        
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
        
        self.tasks_tree.pack(fill=tk.BOTH, expand=True)
        
        # 任务详情区域
        details_frame = ttk.LabelFrame(self.tasks_tab, text="任务详情")
        details_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.task_details_text = scrolledtext.ScrolledText(details_frame, height=6, wrap=tk.WORD)
        self.task_details_text.pack(fill=tk.X, padx=5, pady=5)
        self.task_details_text.config(state=tk.DISABLED)
        
        # 绑定选择事件
        self.tasks_tree.bind("<<TreeviewSelect>>", self._on_task_select)
        
        # 按钮
        buttons_frame = ttk.Frame(self.tasks_tab)
        buttons_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(buttons_frame, text="刷新任务", command=self._refresh_tasks).pack(side=tk.LEFT, padx=5)
    
    def _create_transcode_tab(self):
        """创建转码配置标签页"""
        # 输入文件
        input_frame = ttk.LabelFrame(self.transcode_tab, text="输入文件")
        input_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.input_path_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.input_path_var, width=60).pack(side=tk.LEFT, padx=5)
        ttk.Button(input_frame, text="浏览...", command=self._browse_input).pack(side=tk.LEFT, padx=5)
        
        # 输出文件
        output_frame = ttk.LabelFrame(self.transcode_tab, text="输出文件")
        output_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.output_path_var = tk.StringVar()
        ttk.Entry(output_frame, textvariable=self.output_path_var, width=60).pack(side=tk.LEFT, padx=5)
        ttk.Button(output_frame, text="浏览...", command=self._browse_output).pack(side=tk.LEFT, padx=5)
        
        # 转码预设
        preset_frame = ttk.LabelFrame(self.transcode_tab, text="转码预设")
        preset_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(preset_frame, text="选择预设:").pack(side=tk.LEFT, padx=5)
        
        self.preset_var = tk.StringVar()
        preset_combo = ttk.Combobox(preset_frame, textvariable=self.preset_var, values=list_presets(), state="readonly")
        preset_combo.pack(side=tk.LEFT, padx=5)
        preset_combo.set(list_presets()[0] if list_presets() else "")
        
        # 执行节点
        node_frame = ttk.LabelFrame(self.transcode_tab, text="执行节点")
        node_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(node_frame, text="选择节点:").pack(side=tk.LEFT, padx=5)
        
        self.node_var = tk.StringVar()
        self.node_combo = ttk.Combobox(node_frame, textvariable=self.node_var, state="readonly")
        self.node_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(node_frame, text="刷新", command=self._refresh_node_combo).pack(side=tk.LEFT, padx=5)
        
        # 选项
        options_frame = ttk.LabelFrame(self.transcode_tab, text="选项")
        options_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.delete_original_var = tk.BooleanVar(value=False)
        delete_check = ttk.Checkbutton(
            options_frame,
            text="成功后删除原文件",
            variable=self.delete_original_var
        )
        delete_check.pack(side=tk.LEFT, padx=5)
        
        # 红色警告标签
        warning_label = ttk.Label(
            options_frame,
            text="⚠️ 谨慎选择：删除后无法恢复！",
            foreground="red"
        )
        warning_label.pack(side=tk.LEFT, padx=10)
        
        # 开始按钮
        ttk.Button(self.transcode_tab, text="开始转码", command=self._start_transcode).pack(pady=20)
    
    def _create_logs_tab(self):
        """创建日志标签页"""
        self.log_text = scrolledtext.ScrolledText(self.logs_tab, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.log_text.config(state=tk.DISABLED)
    
    def _log(self, message: str):
        """添加日志"""
        self.log_text.config(state=tk.NORMAL)
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
    
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
            self.nodes_tree.insert("", tk.END, values=(
                node_info.get("hostname", ""),
                node_info.get("ip", ""),
                status_display,
                node_info.get("last_seen", "")
            ))
        
        self._refresh_node_combo()
    
    def _format_node_status(self, status) -> str:
        """将节点状态转换为友好显示格式"""
        # 如果 status 是字典，提取相关信息
        if isinstance(status, dict):
            node_status = status.get("status", "unknown")
            progress = status.get("progress", 0)
            if node_status == "receiving":
                return f"📥 接收中 ({progress}%)"
            elif node_status == "processing":
                return f"🔄 处理中 ({progress}%)"
            elif node_status == "completed":
                return "✅ 空闲"
            elif node_status == "idle":
                return "✅ 空闲"
            elif node_status == "error":
                return f"⚠️ 错误"
            elif node_status == "stopped":
                return "⏹️ 已停止"
            else:
                return f"📊 {node_status}"
        
        # 如果是字符串
        status_map = {
            "idle": "✅ 空闲",
            "receiving": "📥 接收中",
            "processing": "🔄 处理中",
            "completed": "✅ 空闲",
            "error": "⚠️ 错误",
            "stopped": "⏹️ 已停止",
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
            self.tasks_tree.insert("", tk.END, values=(
                task.id,
                os.path.basename(task.input_file),  # 只显示文件名
                os.path.basename(task.output_file),
                status_display,
                task.worker or "",
                f"{task.progress}%"
            ), iid=task.id)  # 使用 task.id 作为 iid方便查找
    
    def _format_status(self, status: str) -> str:
        """将状态转换为友好显示格式"""
        status_map = {
            "pending": "⏳ 等待中",
            "uploading": "📤 上传中",
            "processing": "🔄 处理中",
            "completed": "✅ 已完成",
            "failed": "❌ 失败",
            "error": "⚠️ 错误",
            "stopped": "⏹️ 已停止"
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
        
        self.task_details_text.config(state=tk.NORMAL)
        self.task_details_text.delete(1.0, tk.END)
        self.task_details_text.insert(tk.END, details)
        self.task_details_text.config(state=tk.DISABLED)
    
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
                self.output_path_var.set(f"{base}_transcoded{ext}")
    
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
            messagebox.showerror("错误", "请选择输入文件")
            return
        
        if not output_path:
            messagebox.showerror("错误", "请选择输出文件")
            return
        
        if not worker_ip:
            messagebox.showerror("错误", "请选择执行节点")
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
                # 更新任务状态为上传中
                task.status = "uploading"
                self.root.after(0, self._refresh_all)
                
                # 启动一个线程定期更新进度
                stop_progress_update = threading.Event()
                
                def update_progress():
                    """定期从 Worker 获取进度并更新任务"""
                    while not stop_progress_update.is_set():
                        try:
                            status = self.controller.get_worker_status(worker_ip)
                            current_status = status.get("status")
                            progress = status.get("progress", 0)
                            error_msg = status.get("error", "")
                            
                            # 保存上一次的状态用于判断状态变化
                            old_status = task.status
                            
                            # 状态变化时更新
                            if current_status == "receiving":
                                # Worker 正在接收文件
                                task.status = "uploading"
                                task.progress = progress
                            elif current_status == "processing":
                                task.status = "processing"
                                task.progress = progress
                            elif current_status == "completed":
                                # Worker 报告完成（转码完成，等待响应）
                                task.progress = 100
                                # 不立即设置为 completed，等 submit_task 返回确认
                            elif current_status == "idle":
                                # Worker 空闲，可能还没开始或已完成
                                pass
                            elif current_status == "stopped":
                                # Worker 被停止
                                task.status = "stopped"
                                task.error = "转码被中断"
                                self.root.after(0, self._refresh_all)
                                break
                            elif current_status == "error":
                                # Worker 报告错误
                                task.status = "failed"
                                task.error = error_msg if error_msg else "未知错误"
                                self._log(f"任务 {task.id} 失败: {task.error}")
                                self.root.after(0, self._refresh_all)
                                break
                            
                            # 只有状态或进度变化时才刷新
                            if old_status != task.status or task.progress != progress:
                                self.root.after(0, self._refresh_all)
                                
                        except Exception as e:
                            logger.debug(f"获取 Worker 状态失败: {e}")
                        stop_progress_update.wait(0.5)  # 每0.5秒更新一次
                
                progress_thread = threading.Thread(target=update_progress, daemon=True)
                progress_thread.start()
                
                # 提交任务（这是一个阻塞调用，会等待 Worker 完成）
                result = self.controller.submit_task(task, worker_ip)
                
                # 停止进度更新线程
                stop_progress_update.set()
                
                if result.get("status") == "success":
                    task.status = "completed"
                    task.progress = 100
                    self._log(f"任务 {task.id} 完成")
                    
                    # 下载结果
                    output_file = result.get("output_file")
                    download_success = False
                    
                    if output_file:
                        download_success = self.controller.download_result(
                            worker_ip,
                            os.path.basename(output_file),
                            output_path
                        )
                    
                    # 验证输出文件是否存在且大小大于0
                    if download_success and os.path.exists(output_path):
                        file_size = os.path.getsize(output_path)
                        if file_size > 0:
                            self._log(f"输出文件验证通过: {output_path} ({file_size / 1024 / 1024:.2f} MB)")
                            
                            # 删除原文件（如果选择了该选项）
                            if self.delete_original_var.get():
                                try:
                                    os.remove(input_path)
                                    self._log(f"已删除原文件: {input_path}")
                                except Exception as e:
                                    self._log(f"删除原文件失败: {e}")
                            
                            # 发送系统通知
                            send_system_notification("转码完成", f"任务 {task.id} 已完成\n输出: {os.path.basename(output_path)}")
                            self.root.after(0, lambda: messagebox.showinfo("成功", f"转码完成: {output_path}"))
                        else:
                            # 文件大小为0
                            task.status = "failed"
                            task.error = "输出文件大小为0，转码可能失败"
                            self._log(f"任务 {task.id} 失败: 输出文件大小为0")
                            send_system_notification("转码失败", f"任务 {task.id} 输出文件大小为0")
                            self.root.after(0, lambda: messagebox.showerror("失败", "转码失败：输出文件大小为0"))
                    else:
                        # 下载失败或文件不存在
                        task.status = "failed"
                        task.error = "输出文件下载失败或不存在"
                        self._log(f"任务 {task.id} 失败: 输出文件下载失败")
                        send_system_notification("转码失败", f"任务 {task.id} 输出文件下载失败")
                        self.root.after(0, lambda: messagebox.showerror("失败", "转码失败：输出文件下载失败"))
                elif result.get("status") == "stopped":
                    task.status = "stopped"
                    task.error = "转码被中断"
                    self._log(f"任务 {task.id} 已停止")
                    send_system_notification("转码停止", f"任务 {task.id} 被中断")
                else:
                    task.status = "failed"
                    task.error = result.get("error", "未知错误")
                    self._log(f"任务 {task.id} 失败: {task.error}")
                    # 发送系统通知
                    send_system_notification("转码失败", f"任务 {task.id} 失败\n错误: {task.error}")
                    self.root.after(0, lambda: messagebox.showerror("失败", f"转码失败: {task.error}"))
                    
                # 检查是否所有任务都已完成
                self._check_all_tasks_completed()
            except Exception as e:
                task.status = "error"
                task.error = str(e)
                self._log(f"任务异常: {e}")
                send_system_notification("转码错误", f"任务 {task.id} 发生错误\n{str(e)}")
                self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
            
            # 最终刷新
            self.root.after(0, self._refresh_all)
        
        threading.Thread(target=submit_task, daemon=True).start()
        self._refresh_all()
    
    def _refresh_all(self):
        """同时刷新任务列表和节点列表，保证UI一致性"""
        self._refresh_tasks()
        self._refresh_nodes()
    
    def _check_all_tasks_completed(self):
        """检查是否所有任务都已完成，如果是则发送通知"""
        if not self.controller.tasks:
            return
        
        all_done = all(
            t.status in ("completed", "failed", "error", "stopped")
            for t in self.controller.tasks
        )
        
        if all_done:
            completed = sum(1 for t in self.controller.tasks if t.status == "completed")
            failed = sum(1 for t in self.controller.tasks if t.status in ("failed", "error", "stopped"))
            total = len(self.controller.tasks)
            
            if failed == 0:
                send_system_notification(
                    "所有任务完成",
                    f"全部 {total} 个任务已成功完成"
                )
                self._log(f"✅ 所有 {total} 个任务已成功完成")
            else:
                send_system_notification(
                    "任务执行完毕",
                    f"完成: {completed}, 失败: {failed}, 总计: {total}"
                )
                self._log(f"📊 任务执行完毕 - 完成: {completed}, 失败: {failed}")
    
    def _schedule_refresh(self):
        """定时刷新"""
        self._refresh_all()
        self.root.after(5000, self._schedule_refresh)
    
    def run(self):
        """运行应用"""
        self.root.mainloop()
    
    def close(self):
        """关闭应用"""
        self.discovery.stop()


def main():
    """GUI 控制端入口"""
    root = tk.Tk()
    app = ControllerApp(root)
    
    def on_close():
        # 先隐藏窗口
        root.withdraw()
        
        def do_close():
            app.discovery.stop()
            # 在主线程中销毁窗口
            root.after(0, root.destroy)
        
        # 异步关闭
        threading.Thread(target=do_close, daemon=True).start()
    
    root.protocol("WM_DELETE_WINDOW", on_close)
    app.run()


if __name__ == "__main__":
    main()
