#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ECBot 跨平台构建系统入口 v6.0
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
🚀 ECBot 跨平台构建系统 v6.0
当前平台: {platform_name}

用法:
  python build.py [模式] [选项]

构建模式:
  dev        开发模式 (显示控制台，跳过前端构建，快速构建)
  dev-debug  调试模式 (显示控制台，包含调试信息)
  prod       生产模式 (无控制台，完整构建，优化) [默认]

选项:
  --force           强制重新构建
  --skip-frontend   跳过前端构建
  --build-frontend  强制构建前端 (覆盖 dev 模式默认)
  --help            显示此帮助信息

示例:
  python build.py                      # 生产模式构建 (包含前端)
  python build.py dev                  # 开发模式构建 (跳过前端)
  python build.py dev --build-frontend # 开发模式但构建前端
  python build.py prod --force         # 强制生产模式构建

输出:
  - macOS: dist/ECBot.app
  - Windows: dist/ECBot.exe
  - 构建信息: dist/build_info.json
""")


def main():
    """主函数 - 调用跨平台构建器"""
    # 检查帮助参数
    if "--help" in sys.argv or "-h" in sys.argv:
        show_help()
        sys.exit(0)

    # 构建器路径
    builder_path = Path(__file__).parent / "build_system" / "ecbot_build.py"

    if not builder_path.exists():
        print("❌ 构建器不存在，请检查文件路径")
        print(f"   期望路径: {builder_path}")
        sys.exit(1)

    # 直接传递所有参数给构建器
    cmd = [sys.executable, str(builder_path)] + sys.argv[1:]

    try:
        result = subprocess.run(cmd)
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        print("\n⚠️  构建被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 构建出错: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()