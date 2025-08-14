#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pre-build check script - simplified
"""

import os
import sys
from pathlib import Path

def run_pre_build_check():
    """Run pre-build checks"""
    print("[CHECK] Starting pre-build checks...")
    
    # Check Python version
    python_version = sys.version_info
    print(f"[SUCCESS] Python version: {python_version.major}.{python_version.minor}.{python_version.micro}")
    
    # Check required directories
    required_dirs = ["gui", "agent", "utils", "build_system"]
    for dir_name in required_dirs:
        if os.path.exists(dir_name):
            print(f"[SUCCESS] Directory exists: {dir_name}")
        else:
            print(f"[ERROR] Missing directory: {dir_name}")
            return False
    
    # Check required files
    required_files = ["main.py", "build.py"]
    for file_name in required_files:
        if os.path.exists(file_name):
            print(f"[SUCCESS] File exists: {file_name}")
        else:
            print(f"[ERROR] Missing file: {file_name}")
            return False
    
    # Check for spec files (any eCan*.spec)
    spec_files = list(Path(".").glob("eCan*.spec"))
    if spec_files:
        print(f"[SUCCESS] Found spec file: {spec_files[0].name}")
    else:
        print("[WARN] No spec file found; not required")
    
    print("[SUCCESS] Pre-build checks complete")
    return True

if __name__ == "__main__":
    success = run_pre_build_check()
    sys.exit(0 if success else 1)
