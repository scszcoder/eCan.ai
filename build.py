#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ECBot 构建系统
支持 macOS 和 Windows 双平台打包
"""

import sys
import subprocess
import platform
from pathlib import Path


def show_help():
    """显示帮助信息"""
    platform_name = "macOS" if platform.system() == "Darwin" else "Windows" if platform.system() == "Windows" else "Linux"

    print(f"""
[BUILD] ECBot 构建系统
当前平台: {platform_name}

用法:
  python build.py [模式] [选项]

构建模式:
  dev        开发模式 (快速构建，显示控制台)
  prod       生产模式 (优化构建，无控制台) [默认]

选项:
  --force           强制重新构建
  --help            显示此帮助信息

示例:
  python build.py                      # 生产模式构建
  python build.py dev                  # 开发模式构建
  python build.py prod --force         # 强制生产模式构建

输出:
  - macOS: dist/ECBot.app
  - Windows: dist/ECBot.exe + dist/ECBot-Setup.exe
""")


def main():
    """主函数 - 跨平台构建"""
    # 检查帮助参数
    if "--help" in sys.argv or "-h" in sys.argv:
        show_help()
        sys.exit(0)

    # 获取构建参数
    build_args = sys.argv[1:] if len(sys.argv) > 1 else ["prod"]
    
    # 构建器路径
    builder_path = Path(__file__).parent / "build_system" / "ecbot_build.py"

    if not builder_path.exists():
        print("[ERROR] 构建器不存在，请检查文件路径")
        print(f"   期望路径: {builder_path}")
        sys.exit(1)

    # 直接传递所有参数给构建器
    cmd = [sys.executable, str(builder_path)] + build_args

    try:
        result = subprocess.run(cmd)
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        print("\n[WARNING]  构建被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] 构建出错: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()