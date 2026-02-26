#!/usr/bin/env python3
"""
GUI 控制端应用（单页流程工作台）
"""

import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import tkinter as tk
import zipfile
from tkinter import filedialog
from typing import Any, Dict, List, Optional

import requests
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.dialogs import Messagebox
from ttkbootstrap.tooltip import ToolTip

from transcoder_cluster import __version__
from transcoder_cluster.core.controller import Controller, Task
from transcoder_cluster.core.discovery import DiscoveryService
from transcoder_cluster.transcode.presets import get_preset, list_presets
from transcoder_cluster.utils.config import config
from transcoder_cluster.utils.logger import get_logger

logger = get_logger(__name__)

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".m4v", ".ts", ".webm"}
CODEC_OPTIONS = ["libx265", "libx264", "hevc_nvenc", "h264_nvenc"]


class ControllerApp:
    """GUI 控制端应用。"""

    def __init__(self, root: ttk.Window):
        self.root = root
        self.controller = Controller()
        self.discovery = DiscoveryService(on_node_discovered=self._on_node_discovered)

        self.selected_files: List[str] = []
        self.file_info_map: Dict[str, str] = {}
        self.current_tasks: List[Task] = []
        self.node_capabilities: Dict[str, Dict[str, Any]] = {}
        self.node_runtime_status: Dict[str, Dict[str, Any]] = {}
        self._capabilities_fetching: set = set()

        self.running = False
        self.dispatch_thread: Optional[threading.Thread] = None
        self.dispatch_stop_event = threading.Event()
        self._last_discovery_time = 0.0

        self.user_config_path = os.path.join(os.getcwd(), "controller_gui_config.json")
        self._load_user_config()

        self._create_ui()
        self._check_local_ffmpeg()
        self._refresh_nodes_tree()

        self.discovery.start()
        self._broadcast_discovery()
        self._schedule_refresh()

    def _create_ui(self):
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=BOTH, expand=YES)

        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=BOTH, expand=YES)

        self.left_panel_frame = ttk.Frame(content_frame, width=460)
        self.left_panel_frame.pack(side=LEFT, fill=Y, padx=(0, 10))
        self.left_panel_frame.pack_propagate(False)

        self.left_scroll_container = ttk.Frame(self.left_panel_frame)
        self.left_scroll_container.pack(side=TOP, fill=BOTH, expand=YES)

        self.left_canvas = tk.Canvas(self.left_scroll_container, highlightthickness=0)
        self.left_scrollbar = ttk.Scrollbar(
            self.left_scroll_container,
            orient=VERTICAL,
            command=self.left_canvas.yview,
        )
        self.left_canvas.configure(yscrollcommand=self.left_scrollbar.set)
        self.left_scrollbar.pack(side=RIGHT, fill=Y)
        self.left_canvas.pack(side=LEFT, fill=BOTH, expand=YES)

        self.left_frame = ttk.Frame(self.left_canvas)
        self.left_canvas_window = self.left_canvas.create_window((0, 0), window=self.left_frame, anchor="nw")
        self.left_frame.bind("<Configure>", self._on_left_content_configure)
        self.left_canvas.bind("<Configure>", self._on_left_canvas_configure)

        self.left_action_frame = ttk.Frame(self.left_panel_frame, padding=(0, 8, 0, 0))
        self.left_action_frame.pack(side=BOTTOM, fill=X)

        self.right_frame = ttk.Frame(content_frame)
        self.right_frame.pack(side=LEFT, fill=BOTH, expand=YES)

        self.bottom_frame = ttk.Frame(main_frame)
        self.bottom_frame.pack(fill=X, pady=(10, 0))

        self._create_left_flow_panel()
        self._create_left_action_panel()
        self._create_right_file_panel()
        self._create_bottom_status_panel()
        self._bind_left_scroll_widgets(self.left_frame)

    def _create_left_flow_panel(self):
        sys_frame = ttk.Labelframe(self.left_frame, text="步骤 1: 环境检查", padding=10)
        sys_frame.pack(fill=X, pady=(0, 8))

        ttk.Label(sys_frame, text=f"软件版本: {__version__}", font=("Arial", 10)).pack(anchor=W)

        self.ffmpeg_version_var = ttk.StringVar(value="FFmpeg: 检测中...")
        ttk.Label(sys_frame, textvariable=self.ffmpeg_version_var, font=("Arial", 10)).pack(anchor=W, pady=(6, 0))

        ffmpeg_btn_frame = ttk.Frame(sys_frame)
        ffmpeg_btn_frame.pack(fill=X, pady=(8, 0))

        self.install_ffmpeg_btn = ttk.Button(
            ffmpeg_btn_frame,
            text="安装 FFmpeg",
            bootstyle="warning",
            command=self._install_ffmpeg,
        )
        ToolTip(self.install_ffmpeg_btn, text="检测不到 FFmpeg 时可自动下载安装")

        files_frame = ttk.Labelframe(self.left_frame, text="步骤 2: 添加文件", padding=10)
        files_frame.pack(fill=X, pady=(0, 8))

        ttk.Button(files_frame, text="添加文件", bootstyle="primary", command=self._add_files).pack(side=LEFT)
        ttk.Button(files_frame, text="添加文件夹", bootstyle="info", command=self._add_folder).pack(side=LEFT, padx=(8, 0))
        ttk.Button(files_frame, text="清空列表", bootstyle="secondary", command=self._clear_files).pack(side=LEFT, padx=(8, 0))

        cfg_frame = ttk.Labelframe(self.left_frame, text="步骤 3: 转码配置", padding=10)
        cfg_frame.pack(fill=X, pady=(0, 8))

        ttk.Label(cfg_frame, text="预设:").grid(row=0, column=0, sticky=W, pady=3)
        self.preset_var = ttk.StringVar()
        self.preset_combo = ttk.Combobox(cfg_frame, textvariable=self.preset_var, values=list_presets(), state="readonly", width=26)
        self.preset_combo.grid(row=0, column=1, sticky=W, pady=3)
        preset_names = list_presets()
        if preset_names:
            self.preset_combo.set(preset_names[0])
        self.preset_combo.bind("<<ComboboxSelected>>", self._on_preset_changed)

        ttk.Label(cfg_frame, text="编码器:").grid(row=1, column=0, sticky=W, pady=3)
        self.codec_var = ttk.StringVar(value="libx265")
        self.codec_combo = ttk.Combobox(cfg_frame, textvariable=self.codec_var, values=CODEC_OPTIONS, state="readonly", width=26)
        self.codec_combo.grid(row=1, column=1, sticky=W, pady=3)
        self.codec_combo.bind("<<ComboboxSelected>>", self._on_codec_changed)

        ttk.Label(cfg_frame, text="CRF/CQ:").grid(row=2, column=0, sticky=W, pady=3)
        self.crf_var = ttk.StringVar(value="28")
        ttk.Entry(cfg_frame, textvariable=self.crf_var, width=10).grid(row=2, column=1, sticky=W, pady=3)

        ttk.Label(cfg_frame, text="最大分辨率:").grid(row=3, column=0, sticky=W, pady=3)
        size_row = ttk.Frame(cfg_frame)
        size_row.grid(row=3, column=1, sticky=W, pady=3)

        ttk.Label(size_row, text="宽").pack(side=LEFT)
        self.max_width_var = ttk.StringVar(value="")
        ttk.Entry(size_row, textvariable=self.max_width_var, width=8).pack(side=LEFT, padx=(4, 10))

        ttk.Label(size_row, text="高").pack(side=LEFT)
        self.max_height_var = ttk.StringVar(value="")
        ttk.Entry(size_row, textvariable=self.max_height_var, width=8).pack(side=LEFT, padx=(4, 0))

        self.codec_support_var = ttk.StringVar(value="编码器支持: 等待节点")
        ttk.Label(
            cfg_frame,
            textvariable=self.codec_support_var,
            bootstyle="info",
        ).grid(row=4, column=0, columnspan=2, sticky=W, pady=(6, 0))

        dispatch_frame = ttk.Labelframe(self.left_frame, text="步骤 4: 派发模式", padding=10)
        dispatch_frame.pack(fill=X, pady=(0, 8))

        self.dispatch_mode_var = ttk.StringVar(value="auto")
        ttk.Radiobutton(dispatch_frame, text="自动派发到所有节点", variable=self.dispatch_mode_var, value="auto", command=self._on_dispatch_mode_changed).pack(anchor=W)

        single_row = ttk.Frame(dispatch_frame)
        single_row.pack(fill=X, pady=(6, 0))

        ttk.Radiobutton(single_row, text="指定节点 IP", variable=self.dispatch_mode_var, value="single", command=self._on_dispatch_mode_changed).pack(side=LEFT)

        self.node_var = ttk.StringVar()
        self.node_combo = ttk.Combobox(single_row, textvariable=self.node_var, state="readonly", width=18)
        self.node_combo.pack(side=LEFT, padx=(8, 0))

        ttk.Button(single_row, text="刷新", width=6, bootstyle="secondary", command=self._broadcast_discovery).pack(side=LEFT, padx=(6, 0))

        self._on_preset_changed()
        self._on_dispatch_mode_changed()

    def _create_left_action_panel(self):
        """左侧固定底部操作区，始终可见。"""
        run_frame = ttk.Labelframe(self.left_action_frame, text="步骤 5: 开始转码", padding=10)
        run_frame.pack(fill=X)

        self.start_btn = ttk.Button(
            run_frame,
            text="开始转码",
            bootstyle="success",
            command=self._start_transcode,
            padding=(8, 10),
        )
        self.start_btn.pack(fill=X)

    def _create_right_file_panel(self):
        files_frame = ttk.Labelframe(self.right_frame, text="文件列表与任务进度", padding=8)
        files_frame.pack(fill=BOTH, expand=YES)

        columns = ("file", "source", "status", "progress", "worker", "output")
        self.files_tree = ttk.Treeview(files_frame, columns=columns, show="headings", bootstyle="primary")

        self.files_tree.heading("file", text="文件")
        self.files_tree.heading("source", text="源分辨率")
        self.files_tree.heading("status", text="状态")
        self.files_tree.heading("progress", text="进度")
        self.files_tree.heading("worker", text="节点")
        self.files_tree.heading("output", text="输出")

        self.files_tree.column("file", width=240)
        self.files_tree.column("source", width=100, anchor=CENTER)
        self.files_tree.column("status", width=100, anchor=CENTER)
        self.files_tree.column("progress", width=80, anchor=CENTER)
        self.files_tree.column("worker", width=120, anchor=CENTER)
        self.files_tree.column("output", width=260)

        self.files_tree.pack(fill=BOTH, expand=YES)

    def _create_bottom_status_panel(self):
        total_frame = ttk.Labelframe(self.bottom_frame, text="总进度", padding=8)
        total_frame.pack(fill=X)

        self.overall_progress_var = ttk.IntVar(value=0)
        self.overall_progress = ttk.Progressbar(total_frame, variable=self.overall_progress_var, maximum=100, bootstyle="success-striped")
        self.overall_progress.pack(fill=X)

        self.overall_label_var = ttk.StringVar(value="总进度: 0% (0/0)")
        ttk.Label(total_frame, textvariable=self.overall_label_var).pack(anchor=W, pady=(4, 0))

        nodes_frame = ttk.Labelframe(self.bottom_frame, text="节点状态", padding=8)
        nodes_frame.pack(fill=X, pady=(8, 0))

        node_columns = ("hostname", "ip", "status", "progress", "ffmpeg", "nvenc")
        self.nodes_tree = ttk.Treeview(nodes_frame, columns=node_columns, show="headings", height=6)

        self.nodes_tree.heading("hostname", text="主机名")
        self.nodes_tree.heading("ip", text="IP")
        self.nodes_tree.heading("status", text="状态")
        self.nodes_tree.heading("progress", text="进度")
        self.nodes_tree.heading("ffmpeg", text="FFmpeg")
        self.nodes_tree.heading("nvenc", text="NVENC")

        self.nodes_tree.column("hostname", width=130)
        self.nodes_tree.column("ip", width=130)
        self.nodes_tree.column("status", width=120, anchor=CENTER)
        self.nodes_tree.column("progress", width=80, anchor=CENTER)
        self.nodes_tree.column("ffmpeg", width=160)
        self.nodes_tree.column("nvenc", width=80, anchor=CENTER)

        self.nodes_tree.pack(fill=X)

    def _on_left_content_configure(self, _event=None):
        """同步左侧滚动区域大小。"""
        self.left_canvas.configure(scrollregion=self.left_canvas.bbox("all"))

    def _on_left_canvas_configure(self, event):
        """让左侧内容宽度跟随画布宽度。"""
        self.left_canvas.itemconfigure(self.left_canvas_window, width=event.width)

    def _on_left_mousewheel(self, event):
        """处理左侧滚动条滚轮滚动。"""
        if event.delta:
            self.left_canvas.yview_scroll(int(-event.delta / 120), "units")
        elif event.num == 4:
            self.left_canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.left_canvas.yview_scroll(1, "units")

    def _bind_left_scroll_widgets(self, widget):
        """递归绑定左栏鼠标滚轮事件。"""
        widget.bind("<MouseWheel>", self._on_left_mousewheel, add="+")
        widget.bind("<Button-4>", self._on_left_mousewheel, add="+")
        widget.bind("<Button-5>", self._on_left_mousewheel, add="+")
        for child in widget.winfo_children():
            self._bind_left_scroll_widgets(child)

    def _on_node_discovered(self, node_info: Dict[str, Any]):
        ip = node_info.get("ip")
        if ip and ip not in self.node_capabilities and ip not in self._capabilities_fetching:
            self._fetch_capabilities_async(ip)
        self.root.after(0, self._refresh_nodes_tree)

    def _broadcast_discovery(self):
        self._last_discovery_time = time.time()
        threading.Thread(target=self.discovery.broadcast_discovery, daemon=True).start()

    def _schedule_refresh(self):
        self._refresh_nodes_tree()
        self._refresh_file_tree()
        self._refresh_overall_progress()
        self._update_codec_support_hint()

        if time.time() - self._last_discovery_time > 8:
            self._broadcast_discovery()

        self.root.after(1000, self._schedule_refresh)

    def _add_files(self):
        paths = filedialog.askopenfilenames(
            title="选择视频文件",
            filetypes=[("视频文件", "*.mp4 *.mkv *.avi *.mov *.flv *.wmv *.m4v *.ts *.webm"), ("所有文件", "*.*")],
        )
        self._add_input_paths(list(paths))

    def _add_folder(self):
        folder = filedialog.askdirectory(title="选择包含视频的文件夹")
        if not folder:
            return

        paths = []
        for root_dir, _, filenames in os.walk(folder):
            for filename in filenames:
                ext = os.path.splitext(filename)[1].lower()
                if ext in VIDEO_EXTENSIONS:
                    paths.append(os.path.join(root_dir, filename))

        self._add_input_paths(paths)

    def _add_input_paths(self, paths: List[str]):
        added = 0
        for path in paths:
            abs_path = os.path.abspath(path)
            if not os.path.isfile(abs_path):
                continue
            if abs_path in self.selected_files:
                continue
            self.selected_files.append(abs_path)
            self.file_info_map[abs_path] = self._probe_resolution(abs_path)
            added += 1

        if added > 0:
            self._refresh_file_tree()
            self._refresh_overall_progress()

    def _clear_files(self):
        if self.running:
            Messagebox.show_warning("任务执行中，暂不允许清空列表", "提示")
            return
        self.selected_files = []
        self.file_info_map = {}
        self.current_tasks = []
        self._refresh_file_tree()
        self._refresh_overall_progress()

    def _probe_resolution(self, file_path: str) -> str:
        try:
            import ffmpeg

            info = ffmpeg.probe(file_path)
            for stream in info.get("streams", []):
                if stream.get("codec_type") == "video":
                    width = stream.get("width")
                    height = stream.get("height")
                    if width and height:
                        return f"{width}x{height}"
        except Exception:
            pass
        return "--"

    def _on_preset_changed(self, _event=None):
        preset_name = self.preset_var.get()
        if not preset_name:
            return

        try:
            preset = get_preset(preset_name)
        except KeyError:
            return

        if preset.codec and preset.codec != "none":
            self.codec_var.set(preset.codec)

        if preset.crf is not None:
            self.crf_var.set(str(preset.crf))

        if preset.resolution and ":" in preset.resolution:
            width, height = preset.resolution.split(":", 1)
            self.max_width_var.set(width)
            self.max_height_var.set(height)

        self._update_codec_support_hint()

    def _on_codec_changed(self, _event=None):
        self._update_codec_support_hint()

    def _on_dispatch_mode_changed(self):
        mode = self.dispatch_mode_var.get()
        if mode == "single":
            self.node_combo.config(state="readonly")
        else:
            self.node_combo.config(state="disabled")

    def _build_scale_filter(self, max_width: Optional[int], max_height: Optional[int]) -> Optional[str]:
        if max_width and max_height:
            return f"scale=w=min(iw\\,{max_width}):h=min(ih\\,{max_height}):force_original_aspect_ratio=decrease"
        if max_width:
            return f"scale=w=min(iw\\,{max_width}):h=-2"
        if max_height:
            return f"scale=w=-2:h=min(ih\\,{max_height})"
        return None

    def _build_ffmpeg_args(self) -> List[str]:
        preset_name = self.preset_var.get()
        preset = get_preset(preset_name) if preset_name else None

        codec = self.codec_var.get().strip() or (preset.codec if preset else "libx265")

        crf_value = None
        crf_text = self.crf_var.get().strip()
        if crf_text:
            crf_value = int(crf_text)
        elif preset and preset.crf is not None:
            crf_value = preset.crf

        max_width = int(self.max_width_var.get()) if self.max_width_var.get().strip() else None
        max_height = int(self.max_height_var.get()) if self.max_height_var.get().strip() else None
        scale_filter = self._build_scale_filter(max_width, max_height)

        args: List[str] = []
        if codec and codec != "none":
            args.extend(["-c:v", codec])

        if scale_filter:
            args.extend(["-vf", scale_filter])

        if crf_value is not None and codec and codec != "none":
            if "_nvenc" in codec:
                args.extend(["-cq", str(crf_value)])
            else:
                args.extend(["-crf", str(crf_value)])
        elif preset and preset.bitrate:
            args.extend(["-b:v", preset.bitrate])

        if preset and preset.preset:
            args.extend(["-preset", preset.preset])

        if preset and preset.audio_codec:
            args.extend(["-c:a", preset.audio_codec])

        if preset and preset.audio_bitrate:
            args.extend(["-b:a", preset.audio_bitrate])

        return args

    def _worker_supports_codec(self, worker_ip: str, codec: str) -> bool:
        if "_nvenc" not in codec:
            return True

        capabilities = self.node_capabilities.get(worker_ip)
        if not capabilities:
            # 硬件编码必须已明确探测到支持再放行
            return False
        encoders = capabilities.get("encoders") or []
        return codec in encoders

    def _update_codec_support_hint(self):
        codec = self.codec_var.get().strip()
        workers = self._get_discovered_worker_ips()
        if not workers:
            self.codec_support_var.set("编码器支持: 无节点")
            return

        if "_nvenc" not in codec:
            self.codec_support_var.set(f"编码器支持: {codec}（软件）")
            return

        support_count = sum(1 for ip in workers if self._worker_supports_codec(ip, codec))
        known_count = sum(1 for ip in workers if ip in self.node_capabilities)
        if known_count < len(workers):
            self.codec_support_var.set(
                f"编码器支持: {codec} {support_count}/{len(workers)}（检测 {known_count}/{len(workers)}）"
            )
        else:
            self.codec_support_var.set(f"编码器支持: {codec} {support_count}/{len(workers)}")

    def _start_transcode(self):
        if self.running:
            Messagebox.show_warning("已有任务正在执行", "提示")
            return

        if not self.selected_files:
            Messagebox.show_error("请先添加文件或文件夹", "错误")
            return

        try:
            ffmpeg_args = self._build_ffmpeg_args()
        except ValueError:
            Messagebox.show_error("CRF、最大宽/高必须是数字", "错误")
            return
        except KeyError as error:
            Messagebox.show_error(str(error), "错误")
            return

        codec = self.codec_var.get().strip()
        workers = self._get_discovered_worker_ips()
        if not workers:
            Messagebox.show_error("未发现可用节点，请先刷新节点", "错误")
            return

        mode = self.dispatch_mode_var.get()
        if mode == "single":
            selected_worker = self.node_var.get().strip()
            if not selected_worker:
                Messagebox.show_error("请选择目标节点 IP", "错误")
                return
            workers = [selected_worker]

        target_workers = workers
        if "_nvenc" in codec:
            supported_workers = [ip for ip in workers if self._worker_supports_codec(ip, codec)]
            known_count = sum(1 for ip in workers if ip in self.node_capabilities)
            if not supported_workers and known_count < len(workers):
                Messagebox.show_warning("NVENC 能力检测中，请稍后再试", "提示")
                return
            if not supported_workers:
                Messagebox.show_error(f"没有节点支持编码器 {codec}", "错误")
                return
            if mode == "auto" and len(supported_workers) < len(workers):
                Messagebox.show_info(f"部分节点不支持 {codec}，将自动使用支持的节点执行", "提示")
            target_workers = supported_workers

        tasks = self.controller.create_tasks_for_files(
            self.selected_files,
            ffmpeg_args,
            max_attempts=2,
        )
        self.current_tasks = tasks

        self.running = True
        self.dispatch_stop_event.clear()
        self.start_btn.config(state=DISABLED)

        self._refresh_file_tree()
        self._refresh_overall_progress()

        def on_task_update(task: Task):
            self.root.after(0, self._on_task_runtime_update, task)

        def on_node_update(worker_ip: str, status: Dict[str, Any]):
            self.root.after(0, self._on_node_runtime_update, worker_ip, status)

        def dispatch_runner():
            try:
                result = self.controller.dispatch_tasks(
                    tasks,
                    target_workers,
                    on_task_update=on_task_update,
                    on_node_update=on_node_update,
                    stop_event=self.dispatch_stop_event,
                )
                self.root.after(0, self._on_dispatch_finished, result)
            except Exception as error:
                logger.exception("批量派发失败")
                self.root.after(0, self._on_dispatch_error, str(error))

        self.dispatch_thread = threading.Thread(target=dispatch_runner, daemon=True)
        self.dispatch_thread.start()

    def _on_task_runtime_update(self, _task: Task):
        self._refresh_file_tree()
        self._refresh_overall_progress()

    def _on_node_runtime_update(self, worker_ip: str, status: Dict[str, Any]):
        self.node_runtime_status[worker_ip] = status
        self._refresh_nodes_tree()

    def _on_dispatch_finished(self, result: Dict[str, Any]):
        self.running = False
        self.start_btn.config(state=NORMAL)
        self._refresh_file_tree()
        self._refresh_overall_progress()

        total = result.get("total", 0)
        completed = result.get("completed", 0)
        failed = result.get("failed", 0)
        Messagebox.show_info(f"批量转码完成\n总计: {total}\n成功: {completed}\n失败: {failed}", "完成")

    def _on_dispatch_error(self, error_message: str):
        self.running = False
        self.start_btn.config(state=NORMAL)
        Messagebox.show_error(f"任务执行异常: {error_message}", "错误")

    def _get_discovered_worker_ips(self) -> List[str]:
        ips = [info.get("ip") for info in self.discovery.discovered_nodes.values() if info.get("ip")]
        seen = set()
        result = []
        for ip in ips:
            if ip not in seen:
                seen.add(ip)
                result.append(ip)
        return result

    def _get_task_by_input(self, input_file: str) -> Optional[Task]:
        for task in self.current_tasks:
            if task.input_file == input_file:
                return task
        return None

    def _format_task_status(self, status: str) -> str:
        mapping = {
            "pending": "等待中",
            "uploading": "上传中",
            "processing": "处理中",
            "completed": "已完成",
            "failed": "失败",
            "error": "错误",
        }
        return mapping.get(status, status)

    def _refresh_file_tree(self):
        for item in self.files_tree.get_children():
            self.files_tree.delete(item)

        for file_path in self.selected_files:
            task = self._get_task_by_input(file_path)
            file_name = os.path.basename(file_path)
            source_resolution = self.file_info_map.get(file_path, "--")

            if task:
                status_text = self._format_task_status(task.status)
                progress_text = f"{int(task.progress)}%"
                worker_text = task.worker or ""
                output_text = os.path.basename(task.output_file)
            else:
                status_text = "待开始"
                progress_text = "0%"
                worker_text = ""
                output_text = os.path.basename(self.controller.build_output_path(file_path))

            self.files_tree.insert(
                "",
                END,
                values=(file_name, source_resolution, status_text, progress_text, worker_text, output_text),
            )

    def _format_node_status(self, status: Any) -> str:
        if isinstance(status, dict):
            state = status.get("status", "unknown")
            progress = int(status.get("progress", 0))
            if state == "processing":
                return f"处理中({progress}%)"
            if state in ("idle", "completed"):
                return "空闲"
            if state == "error":
                return "错误"
            return str(state)

        state = str(status)
        mapping = {
            "processing": "处理中",
            "idle": "空闲",
            "completed": "空闲",
            "error": "错误",
            "unknown": "未知",
        }
        return mapping.get(state, state)

    def _refresh_nodes_tree(self):
        for item in self.nodes_tree.get_children():
            self.nodes_tree.delete(item)

        workers = self._get_discovered_worker_ips()
        self.node_combo["values"] = workers
        if workers and self.node_var.get() not in workers:
            self.node_var.set(workers[0])

        for node_info in self.discovery.discovered_nodes.values():
            ip = node_info.get("ip", "")
            runtime_status = self.node_runtime_status.get(ip)
            status_source = runtime_status if runtime_status else node_info.get("status", "unknown")

            progress = "--"
            if isinstance(status_source, dict):
                progress = f"{int(status_source.get('progress', 0))}%"

            capabilities = self.node_capabilities.get(ip, {})
            ffmpeg_version = capabilities.get("ffmpeg_version") or "--"
            if ffmpeg_version and ffmpeg_version != "--":
                ffmpeg_version = str(ffmpeg_version)[:24]
            nvenc_text = "支持" if capabilities.get("nvenc_supported") else "不支持"
            if not capabilities:
                nvenc_text = "--"

            self.nodes_tree.insert(
                "",
                END,
                values=(
                    node_info.get("hostname", ""),
                    ip,
                    self._format_node_status(status_source),
                    progress,
                    ffmpeg_version,
                    nvenc_text,
                ),
            )

            if ip and ip not in self.node_capabilities and ip not in self._capabilities_fetching:
                self._fetch_capabilities_async(ip)

    def _refresh_overall_progress(self):
        total = len(self.selected_files)
        if total == 0:
            self.overall_progress_var.set(0)
            self.overall_label_var.set("总进度: 0% (0/0)")
            return

        if not self.current_tasks:
            self.overall_progress_var.set(0)
            self.overall_label_var.set(f"总进度: 0% (0/{total})")
            return

        progress_sum = sum(int(task.progress) for task in self.current_tasks)
        overall_percent = int(progress_sum / total)
        completed = sum(1 for task in self.current_tasks if task.status == "completed")

        self.overall_progress_var.set(overall_percent)
        self.overall_label_var.set(f"总进度: {overall_percent}% ({completed}/{total})")

    def _fetch_capabilities_async(self, worker_ip: str):
        self._capabilities_fetching.add(worker_ip)

        def runner():
            try:
                capabilities = self.controller.get_worker_capabilities(worker_ip)
                self.node_capabilities[worker_ip] = capabilities
            finally:
                self._capabilities_fetching.discard(worker_ip)
                self.root.after(0, self._update_codec_support_hint)
                self.root.after(0, self._refresh_nodes_tree)

        threading.Thread(target=runner, daemon=True).start()

    def _check_local_ffmpeg(self):
        try:
            result = subprocess.run(
                [config.ffmpeg_path, "-version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                first_line = result.stdout.splitlines()[0] if result.stdout else ""
                version = first_line.replace("ffmpeg version", "").strip()
                self.ffmpeg_version_var.set(f"FFmpeg: {version}")
                if self.install_ffmpeg_btn.winfo_manager():
                    self.install_ffmpeg_btn.pack_forget()
                return
        except Exception:
            pass

        self.ffmpeg_version_var.set("FFmpeg: 未安装")
        self.install_ffmpeg_btn.config(bootstyle="warning")
        if not self.install_ffmpeg_btn.winfo_manager():
            self.install_ffmpeg_btn.pack(side=LEFT)

    def _install_ffmpeg(self):
        self.install_ffmpeg_btn.config(state=DISABLED)

        def runner():
            try:
                self._install_ffmpeg_windows()
                self.root.after(0, lambda: Messagebox.show_info("FFmpeg 安装完成", "成功"))
            except Exception as error:
                logger.exception("安装 FFmpeg 失败")
                self.root.after(
                    0,
                    lambda: Messagebox.show_error(
                        f"自动安装失败: {error}\n请手动选择本地 ffmpeg.exe。",
                        "安装失败",
                    ),
                )
            finally:
                self.root.after(0, self._check_local_ffmpeg)
                self.root.after(0, lambda: self.install_ffmpeg_btn.config(state=NORMAL))

        threading.Thread(target=runner, daemon=True).start()

    def _install_ffmpeg_windows(self):
        download_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, "ffmpeg.zip")
            extract_dir = os.path.join(temp_dir, "extract")

            response = requests.get(download_url, stream=True, timeout=90)
            response.raise_for_status()
            with open(zip_path, "wb") as file:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        file.write(chunk)

            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)

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

            config.ffmpeg_path = target_ffmpeg
            self._save_user_config()

    def _load_user_config(self):
        if not os.path.exists(self.user_config_path):
            return
        try:
            with open(self.user_config_path, "r", encoding="utf-8") as file:
                data = json.load(file)
            ffmpeg_path = data.get("ffmpeg_path")
            if ffmpeg_path:
                config.ffmpeg_path = ffmpeg_path
        except Exception as error:
            logger.warning(f"读取 GUI 配置失败: {error}")

    def _save_user_config(self):
        try:
            with open(self.user_config_path, "w", encoding="utf-8") as file:
                json.dump({"ffmpeg_path": config.ffmpeg_path}, file, ensure_ascii=False, indent=2)
        except Exception as error:
            logger.warning(f"保存 GUI 配置失败: {error}")

    def run(self):
        self.root.mainloop()

    def close(self):
        self.dispatch_stop_event.set()
        self.discovery.stop()


def main():
    version_tag = __version__ if str(__version__).startswith("v") else f"v{__version__}"
    root = ttk.Window(
        title=f"Transcoder Cluster {version_tag} - 主控端",
        themename="cosmo",
        size=(1700, 1250),
    )
    app = ControllerApp(root)

    def on_close():
        app.close()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    app.run()


if __name__ == "__main__":
    main()
