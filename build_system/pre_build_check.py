#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构建前检查脚本 - 简化版
"""

import os
import sys
from pathlib import Path

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
    required_files = ["main.py", "build.py"]
    for file_name in required_files:
        if os.path.exists(file_name):
            print(f"[SUCCESS] 文件存在: {file_name}")
        else:
            print(f"[ERROR] 文件缺失: {file_name}")
            return False
    
    # 检查 spec 文件（允许任何 eCan*.spec 文件）
    spec_files = list(Path(".").glob("eCan*.spec"))
    if spec_files:
        print(f"[SUCCESS] 找到 spec 文件: {spec_files[0].name}")
    else:
        print("[WARN] 未找到 spec 文件，但这不是必需的")
    
    print("[SUCCESS] 构建前检查完成")
    return True

if __name__ == "__main__":
    success = run_pre_build_check()
    sys.exit(0 if success else 1)
