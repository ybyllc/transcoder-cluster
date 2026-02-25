# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 配置文件
用于打包 Transcoder Cluster GUI 应用（单文件模式）
"""

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

block_cipher = None

# 获取项目根目录（使用绝对路径）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(SPEC)))

# 收集 requests 和 certifi 的数据文件
datas = []
datas.extend(collect_data_files('certifi'))
datas.extend(collect_data_files('requests'))

# 收集所有需要的包
hiddenimports = [
    'transcoder_cluster',
    'transcoder_cluster.core',
    'transcoder_cluster.core.worker',
    'transcoder_cluster.core.controller',
    'transcoder_cluster.core.discovery',
    'transcoder_cluster.transcode',
    'transcoder_cluster.transcode.ffmpeg_wrapper',
    'transcoder_cluster.transcode.presets',
    'transcoder_cluster.utils',
    'transcoder_cluster.utils.config',
    'transcoder_cluster.utils.logger',
    'requests',
    'requests.adapters',
    'requests.auth',
    'requests.compat',
    'requests.cookies',
    'requests.exceptions',
    'requests.hooks',
    'requests.models',
    'requests.packages',
    'requests.sessions',
    'requests.structures',
    'requests.utils',
    'ffmpeg',
    'tkinter',
    'tkinter.ttk',
    'tkinter.scrolledtext',
    'tkinter.messagebox',
    'tkinter.filedialog',
    'certifi',
    'charset_normalizer',
    'urllib3',
    'idna',
]

# Worker GUI 应用（单文件模式）
worker_gui = Analysis(
    [os.path.join(PROJECT_ROOT, 'gui', 'worker_app.py')],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'black', 'flake8', 'mypy', 'isort'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

worker_gui_pyz = PYZ(worker_gui.pure, worker_gui.zipped_data, cipher=block_cipher)

worker_gui_exe = EXE(
    worker_gui_pyz,
    worker_gui.scripts,
    worker_gui.binaries,
    worker_gui.zipfiles,
    worker_gui.datas,
    [],
    name='tc-worker-gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI 模式，不显示控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 可以添加图标: 'assets/icon.ico'
)

# Controller GUI 应用（单文件模式）
controller_gui = Analysis(
    [os.path.join(PROJECT_ROOT, 'gui', 'controller_app.py')],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'black', 'flake8', 'mypy', 'isort'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

controller_gui_pyz = PYZ(controller_gui.pure, controller_gui.zipped_data, cipher=block_cipher)

controller_gui_exe = EXE(
    controller_gui_pyz,
    controller_gui.scripts,
    controller_gui.binaries,
    controller_gui.zipfiles,
    controller_gui.datas,
    [],
    name='tc-control-gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI 模式，不显示控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 可以添加图标: 'assets/icon.ico'
)
