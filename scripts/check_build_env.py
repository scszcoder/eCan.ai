#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build Environment Checker
Simple script to check build environment and required files
"""

import sys
import platform
from pathlib import Path

def check_environment():
    """Check build environment"""
    print(f'Platform: {platform.system()}')
    print(f'Python: {platform.python_version()}')
    print(f'Architecture: {platform.architecture()[0]}')
    
    # Check virtual environment
    is_venv = hasattr(sys, "real_prefix") or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)
    print(f'Virtual Environment: {is_venv}')
    
    print("Checking required files:")
    
    # Check required files
    files_to_check = [
        "main.py",
        "build_system/build_config.json"
    ]
    
    for file_path in files_to_check:
        exists = Path(file_path).exists()
        status = "✅" if exists else "❌"
        print(f'{file_path}: {status}')

if __name__ == "__main__":
    check_environment()
