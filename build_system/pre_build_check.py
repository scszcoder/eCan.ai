#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构建前检查脚本
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

def handle_macos_chromium_symlinks():
    """处理 macOS 上的 Chromium 符号链接冲突"""
    if sys.platform != 'darwin':
        return
    
    print("[FIX] 检查 macOS Chromium 符号链接冲突...")
    
    # 检查是否存在 Chromium Framework 符号链接冲突
    dist_path = Path("dist")
    if dist_path.exists():
        chromium_framework = dist_path / "eCan" / "_internal" / "Chromium Framework.framework"
        if chromium_framework.exists():
            print(f"[WARN] 发现已存在的 Chromium Framework: {chromium_framework}")
            
            # 尝试清理可能导致冲突的符号链接
            versions_path = chromium_framework / "Versions"
            if versions_path.exists():
                current_link = versions_path / "Current"
                if current_link.exists() and current_link.is_symlink():
                    try:
                        current_link.unlink()
                        print("[SUCCESS] 已清理 Current 符号链接")
                    except Exception as e:
                        print(f"[WARN] 清理 Current 符号链接失败: {e}")
    
    # 设置环境变量，告诉 PyInstaller 跳过符号链接
    os.environ['PYINSTALLER_SKIP_SYMLINKS'] = '1'
    print("[SUCCESS] 已设置 PYINSTALLER_SKIP_SYMLINKS=1")

def run_pre_build_check():
    """运行构建前检查"""
    print("[CHECK] 开始构建前检查...")
    
    # 检查 Python 版本
    python_version = sys.version_info
    print(f"[SUCCESS] Python 版本: {python_version.major}.{python_version.minor}.{python_version.micro}")
    
    # 检查必要的目录
    required_dirs = ["gui", "agent", "utils", "build_system"]
    for dir_name in required_dirs:
        if os.path.exists(dir_name):
            print(f"[SUCCESS] 目录存在: {dir_name}")
        else:
            print(f"[ERROR] 目录缺失: {dir_name}")
            return False
    
    # 检查必要的文件
    required_files = ["main.py", "build.py", "eCan_prod.spec"]
    for file_name in required_files:
        if os.path.exists(file_name):
            print(f"[SUCCESS] 文件存在: {file_name}")
        else:
            print(f"[ERROR] 文件缺失: {file_name}")
            return False
    
    # 处理 macOS 特定的问题
    handle_macos_chromium_symlinks()
    
    print("[SUCCESS] 构建前检查完成")
    return True

if __name__ == "__main__":
    success = run_pre_build_check()
    sys.exit(0 if success else 1)
