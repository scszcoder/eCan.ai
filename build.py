#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ECBot 统一构建系统 v9.0
支持多种构建模式和性能优化
"""

import sys
import os
import platform
import argparse
import subprocess
from pathlib import Path


class BuildEnvironment:
    """构建环境检测和管理"""
    
    def __init__(self):
        self.platform = platform.system()
        self.is_windows = self.platform == "Windows"
        self.is_macos = self.platform == "Darwin"
        self.is_linux = self.platform == "Linux"
        self.is_ci = self._detect_ci_environment()
        
    def _detect_ci_environment(self) -> bool:
        """检测是否在CI环境中运行"""
        ci_vars = ['GITHUB_ACTIONS', 'CI', 'TRAVIS', 'CIRCLECI']
        return any(os.getenv(var) for var in ci_vars)
    
    def validate_environment(self) -> bool:
        """验证构建环境"""
        print(f"[ENV] Platform: {self.platform}")
        print(f"[ENV] Python: {platform.python_version()}")
        print(f"[ENV] Architecture: {platform.architecture()[0]}")
        print(f"[ENV] CI Environment: {self.is_ci}")
        
        # 检查Python版本
        if not self._check_python_version():
            return False
            
        # 检查虚拟环境
        if not self._check_virtual_environment():
            return False
            
        # 检查必要文件
        if not self._check_required_files():
            return False
            
        return True
    
    def _check_python_version(self) -> bool:
        """检查Python版本"""
        version = sys.version_info
        if version.major != 3 or version.minor < 8:
            print(f"[ERROR] Python 3.8+ required, current: {version.major}.{version.minor}")
            return False
        return True
    
    def _check_required_files(self) -> bool:
        """检查必要文件"""
        required_files = [
            "main.py",
            "build_system/ecbot_build.py",
            "build_system/build_config.json"
        ]
        
        for file_path in required_files:
            if not Path(file_path).exists():
                print(f"[ERROR] Required file not found: {file_path}")
                return False
        
        return True
    
    def _check_virtual_environment(self) -> bool:
        """检查虚拟环境"""
        if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
            print("[SUCCESS] Virtual environment detected")
            return True
        else:
            print("[WARNING] Virtual environment directory exists but not activated")
            print("[INFO] Activating virtual environment...")
            return self._activate_virtual_environment()
    
    def _activate_virtual_environment(self) -> bool:
        """激活虚拟环境"""
        venv_path = Path("venv")
        if not venv_path.exists():
            print("[ERROR] Virtual environment not found")
            return False
        
        # 在Windows上激活虚拟环境
        if self.is_windows:
            activate_script = venv_path / "Scripts" / "activate.bat"
            if activate_script.exists():
                os.environ['VIRTUAL_ENV'] = str(venv_path)
                os.environ['PATH'] = str(venv_path / "Scripts") + os.pathsep + os.environ['PATH']
                print("[SUCCESS] Virtual environment activated")
                return True
        else:
            # 在Unix系统上激活虚拟环境
            activate_script = venv_path / "bin" / "activate"
            if activate_script.exists():
                os.environ['VIRTUAL_ENV'] = str(venv_path)
                os.environ['PATH'] = str(venv_path / "bin") + os.pathsep + os.environ['PATH']
                print("[SUCCESS] Virtual environment activated")
                return True
        
        print("[ERROR] Failed to activate virtual environment")
        return False


def print_banner():
    """打印构建横幅"""
    print("=" * 60)
    print("ECBot 统一构建系统 v9.0")
    print("=" * 60)

def print_mode_info(mode: str, fast: bool = False):
    """打印构建模式信息"""
    print(f"构建模式: {mode.upper()}")

    if fast:
        print("🚀 快速构建特性:")
        print("  ✓ 并行编译 (多核CPU加速)")
        print("  ✓ 智能缓存 (增量构建)")
        print("  ✓ 优化依赖 (~280个包)")
        print("  ✓ 调试符号剥离")
        print("  ✓ 预计时间: 2-5分钟")
    elif mode == "dev":
        print("🔧 开发构建特性:")
        print("  ✓ 并行编译 (多核CPU加速)")
        print("  ✓ 启用控制台输出")
        print("  ✓ 保留调试符号")
        print("  ✓ 预计时间: 5-10分钟")
    else:
        print("🏭 生产构建特性:")
        print("  ✓ 并行编译 (多核CPU加速)")
        print("  ✓ 完整优化和清理")
        print("  ✓ 调试符号剥离")
        print("  ✓ LZMA最佳压缩")
        print("  ✓ 预计时间: 15-25分钟")

    print("=" * 60)

def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="ECBot 统一构建系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
构建模式说明:
  fast     快速构建 (并行+缓存，2-5分钟)
  dev      开发构建 (并行+控制台，5-10分钟)
  prod     生产构建 (并行+最佳压缩，15-25分钟)

使用示例:
  python build.py fast              # 快速构建
  python build.py dev --force       # 强制开发构建
  python build.py prod              # 生产构建
  python build.py prod --version 2.1.0  # 指定版本构建
  python build.py fast --skip-frontend  # 跳过前端的快速构建
  python build.py prod --skip-installer # 跳过安装程序创建
        """
    )

    # 位置参数
    parser.add_argument(
        "mode",
        choices=["fast", "dev", "prod"],
        default="fast",
        nargs="?",
        help="构建模式 (默认: fast)"
    )

    # 可选参数
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="强制重新构建 (清理缓存)"
    )

    parser.add_argument(
        "--version", "-V",
        type=str,
        help="指定版本号 (如: 1.0.0, 2.1.3)"
    )

    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="跳过前端构建 (仅构建Python部分)"
    )

    parser.add_argument(
        "--skip-installer",
        action="store_true",
        help="跳过安装程序创建 (仅生成可执行文件)"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="显示详细构建信息"
    )

    args = parser.parse_args()

    # 验证环境
    env = BuildEnvironment()
    if not env.validate_environment():
        sys.exit(1)

    # 打印信息
    print_banner()

    # 使用指定的构建模式
    build_mode = args.mode
    fast_mode = args.mode == "fast"

    print_mode_info(args.mode, fast_mode)

    # 构建命令
    cmd = [sys.executable, "build_system/ecbot_build.py", build_mode]

    # 添加选项参数
    if args.force:
        cmd.append("--force")
    if args.version:
        cmd.extend(["--version", args.version])
    if args.skip_frontend:
        cmd.append("--skip-frontend")
    if args.skip_installer:
        cmd.append("--skip-installer")

    print(f"[EXEC] 执行命令: {' '.join(cmd)}")
    print("=" * 60)

    # 执行构建
    try:
        subprocess.run(cmd, check=True)

        print("\n" + "=" * 60)
        print("🎉 构建完成!")
        print("=" * 60)

        # 根据操作系统确定可执行文件名和安装包信息
        if platform.system() == "Windows":
            exe_name = "ECBot.exe"
            installer_info = f"📦 安装包: {Path.cwd()}/dist/ECBot-Setup.exe"
        elif platform.system() == "Darwin":
            exe_name = "ECBot"  # macOS
            installer_info = f"📦 安装包: {Path.cwd()}/dist/ECBot-1.0.0.pkg"
        else:
            exe_name = "ECBot"  # Linux
            installer_info = "📦 安装包: 暂不支持Linux安装包"

        print(f"📁 可执行文件: {Path.cwd()}/dist/ECBot/{exe_name}")
        if not args.skip_frontend:
            print(f"🌐 前端文件: {Path.cwd()}/gui_v2/dist/")
        if not args.skip_installer:
            print(installer_info)
        print("=" * 60)

        return 0

    except subprocess.CalledProcessError as e:
        print(f"\n❌ 构建失败，退出码: {e.returncode}")
        return e.returncode
    except KeyboardInterrupt:
        print("\n⏹️  构建被用户中断")
        return 1
    except Exception as e:
        print(f"\n❌ 构建失败: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())