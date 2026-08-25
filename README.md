# 🎬 Transcoder Cluster

<div align="center">

**分布式 FFmpeg 视频转码集群系统**

通过 FFmpeg 压制来压缩视频体积，并通过多节点集群增加转码速度。

**核心原理**：利用 FFmpeg 的压制命令对视频进行转码压缩，视频文件通过 Base64 编码传输到各个 Worker 节点，实现多节点协同工作。

[![GitHub stars](https://img.shields.io/github/stars/ybyllc/transcoder-cluster?style=for-the-badge&logo=github&color=yellow)](https://github.com/ybyllc/transcoder-cluster/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/ybyllc/transcoder-cluster?style=for-the-badge&logo=github&color=blue)](https://github.com/ybyllc/transcoder-cluster/network/members)
[![GitHub issues](https://img.shields.io/github/issues/ybyllc/transcoder-cluster?style=for-the-badge&logo=github&color=red)](https://github.com/ybyllc/transcoder-cluster/issues)
[![GitHub license](https://img.shields.io/github/license/ybyllc/transcoder-cluster?style=for-the-badge&color=green)](LICENSE)

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-5.0%2B-orange?style=flat-square&logo=ffmpeg&logoColor=white)](https://ffmpeg.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey?style=flat-square)](https://github.com/ybyllc/transcoder-cluster)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg?style=flat-square)](https://github.com/psf/black)

[🚀 快速开始](#-快速开始) • [📖 文档](#-目录) • [🧭 通信流程](transcoder_cluster/core/COMMUNICATION_FLOW.md) • [🤝 贡献](#-贡献指南) • [💬 讨论](https://github.com/ybyllc/transcoder-cluster/discussions)

</div>

---

## 🔥 项目亮点

<div align="center">

| 🚀 性能 | 🖥️ 易用 | 🔧 灵活 |
|:------:|:------:|:------:|
| 多节点并行转码 | GUI + CLI 双模式 | 自定义 FFmpeg 参数 |
| 自动负载均衡 | 一键部署 | 预设配置模板 |
| 实时进度监控 | 自动节点发现 | 可扩展架构 |

</div>

---

## 📖 目录

- [功能特性](#-功能特性)
- [系统架构](#️-系统架构)
- [通信流程笔记（Core）](transcoder_cluster/core/COMMUNICATION_FLOW.md)
- [环境要求](#-环境要求)
- [安装](#-安装)
- [快速开始](#-快速开始)
- [使用指南](#-使用指南)
- [配置说明](#-配置说明)
- [API 文档](#-api-文档)
- [项目结构](#-项目结构)
- [开发指南](#-开发指南)
- [常见问题](#-常见问题)
- [贡献者](#-贡献者)

## ✨ 功能特性

<table>
<tr>
<td width="50%">

### 🎯 核心功能

- 🚀 **分布式转码** - 在局域网内多台机器部署 Worker 节点，实现并行转码
- 🔍 **自动发现** - 通过 UDP 广播自动发现局域网内的 Worker 节点
- 📊 **进度监控** - 实时显示转码进度，支持任务状态追踪
- 📁 **文件传输** - 支持视频文件上传和转码结果下载

</td>
<td width="50%">

### 🛠️ 用户体验

- 🖥️ **双模式运行** - 支持命令行模式和 GUI 图形界面模式
- 💾 **任务持久化** - 任务状态保存到本地，支持断点恢复
- ⚙️ **预设配置** - 内置常用转码预设（1080p/720p/480p, H.264/H.265）
- 🔄 **断点续传** - 网络中断后自动重连

</td>
</tr>
</table>

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                      Control Node (控制端)                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   CLI Mode  │  │   GUI Mode  │  │  Discovery Service  │  │
│  │ tc-control  │  │tc-control-gui│  │    (UDP Broadcast)  │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│   Worker Node   │ │   Worker Node   │ │   Worker Node   │
│   (tc-worker)   │ │   (tc-worker)   │ │   (tc-worker)   │
│  ┌───────────┐  │ │  ┌───────────┐  │ │  ┌───────────┐  │
│  │ HTTP API  │  │ │  │ HTTP API  │  │ │  │ HTTP API  │  │
│  │  :9000    │  │ │  │  :9000    │  │ │  │  :9000    │  │
│  └───────────┘  │ │  └───────────┘  │ │  └───────────┘  │
│  ┌───────────┐  │ │  ┌───────────┐  │ │  ┌───────────┐  │
│  │  FFmpeg   │  │ │  │  FFmpeg   │  │ │  │  FFmpeg   │  │
│  └───────────┘  │ │  └───────────┘  │ │  └───────────┘  │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

## 🔧 环境要求

### 必需软件

| 软件 | 版本要求 | 说明 |
|:------:|:---------:|:------|
| ![Python](https://img.shields.io/badge/Python-3.8%2B-blue?style=flat-square) | 3.8+ | 运行环境 |
| ![FFmpeg](https://img.shields.io/badge/FFmpeg-5.0%2B-orange?style=flat-square) | 5.0+ | 视频转码工具 |

## 📦 安装

### 从 GitHub 的 Release 页面安装（推荐）
https://github.com/ybyllc/transcoder-cluster/releases
一台设备下载`tc-control-gui.exe`
作为运算节点的设备下载 `tc-worker-gui.exe`（主控端也可以同时下载节点）

macOS 用户请下载对应芯片的压缩包：

- `transcoder-cluster-macos-arm64.zip`：Apple Silicon（M1/M2/M3/M4）
- `transcoder-cluster-macos-x86_64.zip`：Intel Mac

解压后双击 `tc-control-gui` 或 `tc-worker-gui` 即可。首次打开若被 Gatekeeper 拦截，
请在“系统设置 → 隐私与安全性”中允许打开，或在终端执行 `xattr -dr com.apple.quarantine <文件路径>`。

### 从源码安装

```bash
git clone https://github.com/ybyllc/transcoder-cluster.git
cd transcoder-cluster
pip install -e .
```

### 安装 FFmpeg

<details>
<summary><b>Windows</b></summary>

```bash
# 使用 winget
winget install ffmpeg

# 或使用 Chocolatey
choco install ffmpeg

# 或下载后添加到 PATH
# 下载地址: https://ffmpeg.org/download.html#build-windows
```
</details>

<details>
<summary><b>macOS</b></summary>

```bash
# 使用 Homebrew
brew install ffmpeg

# 或使用 MacPorts
sudo port install ffmpeg
```
</details>

<details>
<summary><b>Linux (Ubuntu/Debian)</b></summary>

```bash
sudo apt update && sudo apt install ffmpeg

# 或使用 Snap
sudo snap install ffmpeg
```
</details>

## 🚀 快速开始

### 1️⃣ 启动 Worker 节点

在每台作为转码工作站的机器上运行：

```bash
# 命令行模式
tc-worker

# 或 GUI 模式
tc-worker-gui

# 指定端口和工作目录
tc-worker --port 9001 --work-dir /data/transcode
```

Worker 启动后会监听 `http://0.0.0.0:9000`

### 2️⃣ 启动控制端

```bash
# 扫描 Worker 节点
tc-control --scan

# 提交转码任务
tc-control --input video.mp4 --output output.mp4 --preset 1080p_h265_standard

# GUI 模式
tc-control-gui
```

### 3️⃣ 使用 Python API

```python
from transcoder_cluster import Controller, Worker
from transcoder_cluster.transcode.presets import get_preset

# 创建控制器
controller = Controller()

# 扫描节点
workers = controller.scan_workers()
print(f"发现 {len(workers)} 个 Worker 节点")

# 获取预设参数
preset = get_preset("1080p_h265_standard")
ffmpeg_args = preset.to_ffmpeg_args()

# 创建并提交任务
task = controller.create_task("input.mp4", "output.mp4", ffmpeg_args)
result = controller.submit_task(task)

if result["status"] == "success":
    print("转码完成！")
```

## 📚 使用指南

### 转码预设说明

| 预设名称 | 分辨率 | 编码器 | 适用场景 |
|:---------|:------:|:------:|:---------|
| `720p_h265` | 1280x720 | libx265 | 小体积优先，压缩率更高 |
| `1080p_h264_high` | 1920x1080 | libx264 | 高清视频，兼容性好 |
| `1080p_h264_standard` | 1920x1080 | libx264 | 平衡画质与文件大小 |
| `720p_h264` | 1280x720 | libx264 | 适合网络传输 |
| `480p_h264` | 854x480 | libx264 | 小文件，快速传输 |
| `1080p_h265_high` | 1920x1080 | libx265 | 高压缩率 |
| `1080p_h265_standard` | 1920x1080 | libx265 | 节省空间 |
| `4k_h265` | 3840x2160 | libx265 | 超高清 |
| `1080p_nvenc` | 1920x1080 | h264_nvenc | NVIDIA 硬件加速 |
| `audio_mp3` | - | libmp3lame | 提取 MP3 音频 |

### 自定义 FFmpeg 参数

```bash
# 使用自定义参数
tc-control -i video.mp4 -o output.mp4 --args "-c:v libx265 -crf 28 -preset fast"

# 缩放到 640x360
tc-control -i video.mp4 -o output.mp4 --args "-vf scale=640:360 -c:v libx264"

# 提取音频
tc-control -i video.mp4 -o audio.mp3 --args "-vn -c:a libmp3lame -q:a 2"
```

### 批量转码

```python
from transcoder_cluster import Controller
from transcoder_cluster.transcode.presets import get_preset

controller = Controller()
controller.scan_workers()

preset = get_preset("1080p_h265_standard")
videos = ["video1.mp4", "video2.mp4", "video3.mp4"]

for video in videos:
    output = video.replace(".mp4", "_transcoded.mp4")
    task = controller.create_task(video, output, preset.to_ffmpeg_args())
    controller.submit_task(task)
    print(f"完成: {output}")
```

## ⚙️ 配置说明

### 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `TC_CONTROL_PORT` | 55555 | 控制端口 |
| `TC_DATA_PORT` | 55556 | 数据端口 |
| `TC_DISCOVERY_PORT` | 55557 | 发现端口 |
| `TC_WORKER_PORT` | 9000 | Worker 端口 |
| `TC_WORK_DIR` | . | 工作目录 |
| `TC_FFMPEG_PATH` | ffmpeg | FFmpeg 路径 |
| `TC_LOG_LEVEL` | INFO | 日志级别 |

### 配置文件

```json
{
    "control_port": 55555,
    "worker_port": 9000,
    "work_dir": "./worker_files",
    "ffmpeg_path": "/usr/bin/ffmpeg",
    "log_level": "DEBUG"
}
```

使用配置文件：

```bash
tc-worker --config worker.json
tc-control --config controller.json
```

## 📡 API 文档

### Worker API (端口 9000)

#### 提交转码任务
```http
POST /task
Content-Type: application/json

{
    "video_file": {
        "name": "video.mp4",
        "data": "<base64_encoded_data>"
    },
    "ffmpeg_args": ["-c:v", "libx265", "-crf", "28"]
}
```

**响应:**
```json
{
    "status": "success",
    "output_file": "/path/to/output_video.mp4"
}
```

#### 下载转码结果
```http
GET /download?file=output_video.mp4
```

#### 健康检查
```http
GET /ping
```

**响应:** `pong`

#### 获取状态
```http
GET /status
```

**响应:**
```json
{
    "status": "processing",
    "current_task": "video.mp4",
    "progress": 45
}
```

## 📁 项目结构

```
transcoder-cluster/
├── .github/
│   └── workflows/
│       ├── python-tests.yml    # GitHub Actions CI
│       └── release.yml         # Windows/macOS 打包与 Release 发布
├── transcoder_cluster/         # 核心包
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── worker.py           # Worker 节点
│   │   ├── controller.py       # 控制端
│   │   └── discovery.py        # 节点发现
│   ├── transcode/
│   │   ├── __init__.py
│   │   ├── ffmpeg_wrapper.py   # FFmpeg 封装
│   │   └── presets.py          # 转码预设
│   └── utils/
│       ├── __init__.py
│       ├── config.py           # 配置管理
│       └── logger.py           # 日志系统
├── cli/                        # 命令行入口
│   ├── __init__.py
│   ├── worker.py               # tc-worker
│   └── controller.py           # tc-control
├── gui/                        # GUI 应用
│   ├── __init__.py
│   ├── worker_app.py           # Worker GUI
│   └── controller_app.py       # Controller GUI
├── tests/                      # 测试
│   ├── __init__.py
│   ├── test_config.py
│   └── test_presets.py
├── .gitignore
├── LICENSE
├── README.md
├── pyproject.toml              # 项目配置
├── requirements.txt            # 依赖
└── requirements-dev.txt        # 开发依赖
```

## 🔨 开发指南

核心通信链路说明见: [`transcoder_cluster/core/COMMUNICATION_FLOW.md`](transcoder_cluster/core/COMMUNICATION_FLOW.md)

### 设置开发环境

```bash
# 克隆仓库
git clone https://github.com/ybyllc/transcoder-cluster.git
cd transcoder-cluster

# macOS 请使用 Homebrew Python（系统/Command Line Tools Python 的 Tk 8.5 会白屏）
brew install python@3.14 python-tk@3.14

# 创建虚拟环境
"$(brew --prefix)/bin/python3" -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate  # Windows

# 升级 pip
python -m pip install --upgrade pip

# 安装开发依赖
python -m pip install -e ".[dev,build]"
```

### 运行测试

```bash
# 运行所有测试
pytest tests/ -v

# 生成覆盖率报告
pytest tests/ --cov=transcoder_cluster --cov-report=html
```

### 代码风格

```bash
# 格式化代码
black .
isort .

# 代码检查
flake8 transcoder_cluster cli gui

# 类型检查
mypy transcoder_cluster
```

### 添加新的转码预设

在 [`transcoder_cluster/transcode/presets.py`](transcoder_cluster/transcode/presets.py) 中添加：

```python
PRESETS["my_custom_preset"] = TranscodePreset(
    name="我的自定义预设",
    description="自定义转码配置",
    codec="libx265",
    resolution="1920:1080",
    crf=25,
    preset="medium"
)
```

## ❓ 常见问题

<details>
<summary><b>Q: Worker 节点无法被发现？</b></summary>

**A:** 检查以下项目：
1. 确认 Worker 已启动并监听端口 9000
2. 检查防火墙是否允许 UDP 55557 端口
3. 确认控制端和 Worker 在同一局域网
4. 尝试手动 ping Worker IP

</details>

<details>
<summary><b>Q: 转码任务失败？</b></summary>

**A:** 可能原因：
1. FFmpeg 未正确安装或不在 PATH 中
2. 输入文件格式不支持
3. FFmpeg 参数错误
4. 磁盘空间不足

检查 Worker 日志获取详细错误信息。

</details>

<details>
<summary><b>Q: 大文件传输慢？</b></summary>

**A:** 当前版本使用 base64 编码，会增加约 33% 的数据量。建议：
1. 在 Worker 节点本地处理文件
2. 使用更快的网络连接
3. 等待后续版本优化传输协议

</details>

<details>
<summary><b>Q: 如何在多台机器上部署？</b></summary>

**A:** 
1. 在每台机器上安装 Python 和 FFmpeg
2. `pip install transcoder-cluster`
3. 运行 `tc-worker` 启动 Worker
4. 在控制端机器运行 `tc-control`

</details>

## 👥 贡献者

<div align="center">

[![Contributors](https://contrib.rocks/image?repo=ybyllc/transcoder-cluster)](https://github.com/ybyllc/transcoder-cluster/graphs/contributors)

**感谢所有贡献者！**

</div>

## 📝 更新日志

### v0.2.1 (当前版本)

#### 🚀 新增改进
- 主控端流程化单页继续优化，配置与任务操作更直观
- 新增任务列表右键操作，支持空白区操作和选中任务删除
- 输出文件后缀支持可视化配置，默认 `_transcoded`
- CRF/CQ 支持输入 `0` 表示自动（不追加 `-crf/-cq` 参数）
- 左侧流程栏拖拽与宽度约束优化（含最大宽度限制）
- 新增通信流程文档：`transcoder_cluster/core/COMMUNICATION_FLOW.md`
- 发布流程支持版本专属 Release 文案

#### 🐛 修复问题
- 修复主控端任务列表“上传中 0%”不更新的问题
- 修复节点状态偶发 `unknown` 覆盖“处理中”的问题
- Worker 升级为并发 HTTP 服务，任务执行期间状态接口可实时访问
- 修复转码结果校验稳定性，减少无效输出误判成功
- 修复并恢复“成功后删除原文件”流程
- 修复 CLI/GUI 启动告警及相关兼容性问题
- 修复发布流水线问题，支持标签补发发布

### v0.2.0
- ✅ 主控端 GUI 重构为单页流程工作台，操作更直观
- ✅ 支持自动派发到所有节点（节点空闲自动领取新任务）
- ✅ 新增编码器能力检测（重点检测 NVENC 并提示支持情况）
- ✅ 输出文件默认后缀统一为 `_transcoded`（支持在 GUI 中修改）
- ✅ 新增“成功后删除原文件”可选项（仅删除成功任务的源文件）
- ✅ 转码完成前增加输出文件有效性校验（文件存在且大小大于 0）
- ✅ 优化 Worker 停止逻辑与发现服务关闭稳定性，降低卡死风险
- ✅ CLI/GUI 增加版本与 FFmpeg 检测信息展示
- ✅ 修复 Release 打包工作流，可手动补发指定标签发布
#### v0.2.0界面样式：
<p align="center">
  <img src="https://github.com/user-attachments/assets/ecc8c8eb-f431-4933-8b23-687f0d002266" height="406" />
  <img src="https://github.com/user-attachments/assets/009a230b-95b8-4a84-b5d1-3d93f1ffda0e" height="300" />
</p>

### v0.1.0
- ✅ 初版分布式转码框架
- ✅ Worker 节点发现、任务提交与结果下载能力

### 计划功能
- [ ] 支持linux等多平台，让树莓派等端侧设备加入运算
- [ ] 用更轻量更现代化的界面
- [ ] 异步传输优化
- [ ] 任务队列管理
- [ ] Web 管理界面（CLI➕web管理的方案）
- [ ] Docker 部署支持
- [ ] 认证与加密

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

1. 🍴 Fork 本仓库
2. 🌿 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 💾 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 📤 推送到分支 (`git push origin feature/AmazingFeature`)
5. 🎉 提交 Pull Request

## 💬 联系方式

<div align="center">

[![GitHub](https://img.shields.io/badge/GitHub-ybyllc-181717?style=for-the-badge&logo=github)](https://github.com/ybyllc)
[![Email](https://img.shields.io/badge/Email-420752002@qq.com-EA4335?style=for-the-badge&logo=gmail&logoColor=white)](mailto:420752002@qq.com)
[![Discussions](https://img.shields.io/badge/Discussions-加入讨论-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://github.com/ybyllc/transcoder-cluster/discussions)

</div>

---

<div align="center">

**如果这个项目对你有帮助，请给一个 ⭐ Star 支持一下！**

[![Star History Chart](https://api.star-history.com/svg?repos=ybyllc/transcoder-cluster&type=date&legend=top-left)](https://www.star-history.com/#ybyllc/transcoder-cluster&type=date&legend=top-left)

**Made with ❤️ by [一杯原谅绿茶](https://github.com/ybyllc)**

</div>
