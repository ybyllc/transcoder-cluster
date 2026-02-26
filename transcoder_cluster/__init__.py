"""
Transcoder Cluster - 分布式 FFmpeg 视频转码集群系统

一个用于在局域网内实现多节点并行视频转码的分布式系统。
"""

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def _read_version_from_pyproject() -> str:
    """开发环境兜底：从 pyproject.toml 的 [project] 读取 version。"""
    pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if not pyproject_path.exists():
        return "0.0.0-dev"

    in_project_section = False
    for raw_line in pyproject_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_project_section = line == "[project]"
            continue
        if in_project_section and line.startswith("version"):
            _, value = line.split("=", 1)
            return value.strip().strip('"').strip("'")

    return "0.0.0-dev"


def _resolve_version() -> str:
    """优先读取安装包元数据，失败时回退到 pyproject.toml。"""
    try:
        return version("transcoder-cluster")
    except PackageNotFoundError:
        return _read_version_from_pyproject()
    except Exception:
        return _read_version_from_pyproject()


__version__ = _resolve_version()
__author__ = "一杯原谅绿茶"
__email__ = "your.email@example.com"

from transcoder_cluster.core.controller import Controller
from transcoder_cluster.core.discovery import DiscoveryService
from transcoder_cluster.core.worker import Worker

__all__ = [
    "Worker",
    "Controller",
    "DiscoveryService",
    "__version__",
]
