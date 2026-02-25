#!/usr/bin/env python3
"""
本地打包脚本
用于在本地构建 EXE 文件

使用方法:
    python scripts/build.py
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"


def clean():
    """清理构建目录"""
    print("🧹 清理构建目录...")
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    print("✓ 清理完成")


def install_dependencies():
    """安装打包依赖"""
    print("📦 安装打包依赖...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "pyinstaller"],
        check=True
    )
    print("✓ 依赖安装完成")


def build():
    """构建 EXE"""
    print("🔨 构建 EXE 文件...")
    os.chdir(PROJECT_ROOT)
    
    # 使用 PyInstaller 构建
    result = subprocess.run(
        [
            sys.executable, "-m", "PyInstaller",
            "scripts/build.spec",
            "--clean",
            "--noconfirm"
        ],
        check=False
    )
    
    if result.returncode != 0:
        print("❌ 构建失败")
        sys.exit(1)
    
    print("✓ 构建完成")


def package():
    """打包发布文件"""
    print("📦 打包发布文件...")
    
    import zipfile
    from datetime import datetime
    
    # 创建发布包
    version = datetime.now().strftime("%Y%m%d")
    zip_name = f"transcoder-cluster-windows-{version}"
    zip_path = DIST_DIR / f"{zip_name}.zip"
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        # 添加 EXE 文件
        for exe_dir in ["tc-worker-gui", "tc-control-gui"]:
            exe_path = DIST_DIR / exe_dir
            if exe_path.exists():
                for file in exe_path.rglob("*"):
                    if file.is_file():
                        arcname = f"{zip_name}/{exe_dir}/{file.relative_to(exe_path)}"
                        zf.write(file, arcname)
        
        # 添加文档
        readme = PROJECT_ROOT / "README.md"
        license_file = PROJECT_ROOT / "LICENSE"
        
        if readme.exists():
            zf.write(readme, f"{zip_name}/README.md")
        if license_file.exists():
            zf.write(license_file, f"{zip_name}/LICENSE")
    
    print(f"✓ 发布包已创建: {zip_path}")


def main():
    """主函数"""
    print("=" * 50)
    print("Transcoder Cluster EXE 打包工具")
    print("=" * 50)
    
    # 清理
    clean()
    
    # 安装依赖
    install_dependencies()
    
    # 构建
    build()
    
    # 打包
    package()
    
    print("\n" + "=" * 50)
    print("✅ 打包完成！")
    print(f"输出目录: {DIST_DIR}")
    print("=" * 50)


if __name__ == "__main__":
    main()
