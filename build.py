#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ECBot Cross-Platform Build System v8.0
统一构建入口 - 简化版本
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


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="ECBot Build System")
    parser.add_argument("mode", choices=["dev", "prod"], default="prod", nargs="?",
                       help="Build mode (default: prod)")
    parser.add_argument("--force", "-f", action="store_true",
                       help="Force rebuild")
    parser.add_argument("--skip-frontend", action="store_true",
                       help="Skip frontend build")
    
    args = parser.parse_args()
    
    # 验证环境
    env = BuildEnvironment()
    if not env.validate_environment():
        sys.exit(1)
    
    print("=" * 60)
    print("ECBot Cross-Platform Build System v8.0")
    print("=" * 60)
    
    # 构建命令
    cmd = [sys.executable, "build_system/ecbot_build.py", args.mode]
    if args.force:
        cmd.append("--force")
    if args.skip_frontend:
        cmd.append("--skip-frontend")
    
    print(f"[EXEC] Running: {' '.join(cmd)}")
    
    # 执行构建
    try:
        result = subprocess.run(cmd, check=True)
        print("[SUCCESS] Build completed successfully")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Build failed with exit code: {e.returncode}")
        return e.returncode
    except Exception as e:
        print(f"[ERROR] Build failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())