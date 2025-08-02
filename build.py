#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ECBot Cross-Platform Build System v6.0
Supports macOS and Windows dual-platform packaging
"""

import sys
import subprocess
import platform
from pathlib import Path


def show_help():
    """Show help information"""
    platform_name = "macOS" if platform.system() == "Darwin" else "Windows" if platform.system() == "Windows" else "Linux"

    print(f"""
[BUILD] ECBot Cross-Platform Build System v6.0
Current platform: {platform_name}

Usage:
  python build.py [mode] [options]

Build mode:
  dev        Development mode (fast build, show console)
  prod       Production mode (optimized build, no console) [default]

Options:
  --force            Force rebuild
  --help             Show this help information

Examples:
  python build.py                      # Production mode build
  python build.py dev                  # Development mode build
  python build.py prod --force         # Force production mode build

Output:
  - macOS: dist/ECBot.app
  - Windows: dist/ECBot.exe + dist/ECBot-Setup.exe
""")


def main():
    """Main function - cross-platform build"""
    # 检查帮助参数
    if "--help" in sys.argv or "-h" in sys.argv:
        show_help()
        sys.exit(0)

    # 获取构建参数
    build_args = sys.argv[1:] if len(sys.argv) > 1 else ["prod"]
    
    # 构建器路径
    builder_path = Path(__file__).parent / "build_system" / "ecbot_build.py"

    if not builder_path.exists():
        print("[ERROR] Builder not found, please check file path")
        print(f"    Expected path: {builder_path}")
        sys.exit(1)

    # 直接传递所有参数给构建器
    cmd = [sys.executable, str(builder_path)] + build_args

    try:
        result = subprocess.run(cmd)
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        print("\n[WARNING] Build interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Build error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()