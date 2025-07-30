#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ECBot 构建系统极简入口 v5.0
单文件解决方案，消除所有重复代码
"""

import sys
import subprocess
from pathlib import Path


def main():
    """主函数 - 直接调用极简构建器"""
    # 构建器路径
    builder_path = Path(__file__).parent / "build_system" / "ecbot_build.py"

    if not builder_path.exists():
        print("❌ 构建器不存在，请检查文件路径")
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