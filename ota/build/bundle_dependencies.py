#!/usr/bin/env python3
"""
OTA依赖库打包脚本（示例/占位）
- 仅用于参考与本地实验，不建议在生产/CI 中直接执行
- 需要本机具备网络访问和相应平台工具链
- 默认处于禁用状态：作为脚本运行时需设置环境变量 ECBOT_ALLOW_BUILD_SCRIPTS=1 才会执行

注意：此脚本已集成到主构建系统中 (build_system/ota_dependency_manager.py)
建议使用: python build.py [mode] 进行构建
"""

import os
import sys
import platform
import subprocess
import urllib.request
import zipfile
import tarfile
import shutil
import json
from pathlib import Path
from typing import Dict, Any


class DependencyBundler:
    """依赖库打包器"""
    
    def __init__(self, project_root: Path = None):
        self.project_root = project_root or Path(__file__).parent.parent.parent
        self.ota_dir = self.project_root / "ota"
        self.deps_dir = self.ota_dir / "dependencies"
        self.deps_dir.mkdir(exist_ok=True)
        
        # 依赖库配置
        self.dependencies = {
            "sparkle": {
                "version": "2.6.4",
                "url": "https://github.com/sparkle-project/Sparkle/releases/download/2.6.4/Sparkle-2.6.4.tar.xz",
                "platform": "darwin",
                "extract_path": "Sparkle.framework",
                "target_path": "Frameworks/Sparkle.framework"
            },
            "winsparkle": {
                "version": "0.8.0",
                "url": "https://github.com/vslavik/winsparkle/releases/download/v0.8.0/winsparkle-0.8.0.zip",
                "platform": "windows",
                "extract_files": ["winsparkle.dll", "winsparkle.lib"],
                "target_path": "lib"
            }
        }
    
    def get_current_platform(self) -> str:
        """获取当前平台"""
        system = platform.system().lower()
        if system == "darwin":
            return "darwin"
        elif system == "windows":
            return "windows"
        else:
            return "linux"
    
    def download_dependency(self, name: str, config: Dict[str, Any]) -> Path:
        """下载依赖库"""
        print(f"Downloading {name} v{config['version']}...")
        
        url = config["url"]
        filename = url.split("/")[-1]
        download_path = self.deps_dir / filename
        
        if download_path.exists():
            print(f"  {filename} already exists, skipping download")
            return download_path
        
        try:
            urllib.request.urlretrieve(url, download_path)
            print(f"  Downloaded: {download_path}")
            return download_path
        except Exception as e:
            print(f"  Failed to download {name}: {e}")
            raise
    
    def extract_sparkle(self, archive_path: Path) -> Path:
        """解压Sparkle框架"""
        print("Extracting Sparkle framework...")
        
        extract_dir = self.deps_dir / "sparkle_extracted"
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        extract_dir.mkdir()
        
        # 解压tar.xz文件
        with tarfile.open(archive_path, 'r:xz') as tar:
            tar.extractall(extract_dir)
        
        # 查找Sparkle.framework
        framework_path = None
        for root, dirs, files in os.walk(extract_dir):
            if "Sparkle.framework" in dirs:
                framework_path = Path(root) / "Sparkle.framework"
                break
        
        if not framework_path:
            raise FileNotFoundError("Sparkle.framework not found in archive")
        
        # 复制到目标位置
        target_path = self.deps_dir / "Sparkle.framework"
        if target_path.exists():
            shutil.rmtree(target_path)
        
        shutil.copytree(framework_path, target_path)
        print(f"  Extracted to: {target_path}")
        
        # 清理临时文件
        shutil.rmtree(extract_dir)
        
        return target_path
    
    def extract_winsparkle(self, archive_path: Path) -> Path:
        """解压winSparkle库"""
        print("Extracting winSparkle library...")
        
        extract_dir = self.deps_dir / "winsparkle_extracted"
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        extract_dir.mkdir()
        
        # 解压ZIP文件
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        
        # 创建目标目录
        target_dir = self.deps_dir / "winsparkle"
        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.mkdir()
        
        # 查找并复制所需文件
        files_found = []
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                if file in ["winsparkle.dll", "winsparkle.lib", "winsparkle.h"]:
                    src_path = Path(root) / file
                    dst_path = target_dir / file
                    shutil.copy2(src_path, dst_path)
                    files_found.append(file)
                    print(f"  Copied: {file}")
        
        if not files_found:
            raise FileNotFoundError("winSparkle files not found in archive")
        
        # 清理临时文件
        shutil.rmtree(extract_dir)
        
        return target_dir
    
    def create_cli_wrapper(self, platform: str):
        """创建CLI包装器"""
        if platform == "darwin":
            self.create_sparkle_cli()
        elif platform == "windows":
            self.create_winsparkle_cli()
    
    def create_sparkle_cli(self):
        """创建Sparkle CLI包装器"""
        cli_script = self.deps_dir / "sparkle-cli"
        
        script_content = '''#!/bin/bash
# Sparkle CLI wrapper for ECBot OTA

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRAMEWORK_PATH="$SCRIPT_DIR/Sparkle.framework"

if [ ! -d "$FRAMEWORK_PATH" ]; then
    echo "Error: Sparkle.framework not found at $FRAMEWORK_PATH"
    exit 1
fi

# Check if native CLI exists
NATIVE_CLI="$FRAMEWORK_PATH/Versions/Current/Resources/sparkle-cli"
if [ -x "$NATIVE_CLI" ]; then
    exec "$NATIVE_CLI" "$@"
fi

# Fallback: simulate CLI behavior
case "$1" in
    "check")
        echo "Checking for updates via Sparkle..."
        # This would integrate with the Python OTA system
        python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR/..')
from ota import OTAUpdater
updater = OTAUpdater()
has_update = updater.check_for_updates(silent=True)
sys.exit(0 if has_update else 1)
"
        ;;
    "install")
        echo "Installing update via Sparkle..."
        python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR/..')
from ota import OTAUpdater
updater = OTAUpdater()
success = updater.install_update()
sys.exit(0 if success else 1)
"
        ;;
    *)
        echo "Usage: sparkle-cli [check|install]"
        exit 1
        ;;
esac
'''
        
        with open(cli_script, 'w') as f:
            f.write(script_content)
        
        # 设置可执行权限
        os.chmod(cli_script, 0o755)
        print(f"  Created Sparkle CLI wrapper: {cli_script}")
    
    def create_winsparkle_cli(self):
        """创建winSparkle CLI包装器"""
        cli_script = self.deps_dir / "winsparkle-cli.bat"
        
        script_content = '''@echo off
REM winSparkle CLI wrapper for ECBot OTA

set SCRIPT_DIR=%~dp0
set DLL_PATH=%SCRIPT_DIR%winsparkle\\winsparkle.dll

if not exist "%DLL_PATH%" (
    echo Error: winsparkle.dll not found at %DLL_PATH%
    exit /b 1
)

REM Simulate CLI behavior using Python OTA system
if "%1"=="check" (
    echo Checking for updates via winSparkle...
    python -c "import sys; sys.path.insert(0, r'%SCRIPT_DIR%..'); from ota import OTAUpdater; updater = OTAUpdater(); has_update = updater.check_for_updates(silent=True); sys.exit(0 if has_update else 1)"
    exit /b %ERRORLEVEL%
)

if "%1"=="install" (
    echo Installing update via winSparkle...
    python -c "import sys; sys.path.insert(0, r'%SCRIPT_DIR%..'); from ota import OTAUpdater; updater = OTAUpdater(); success = updater.install_update(); sys.exit(0 if success else 1)"
    exit /b %ERRORLEVEL%
)

echo Usage: winsparkle-cli.bat [check^|install]
exit /b 1
'''
        
        with open(cli_script, 'w') as f:
            f.write(script_content)
        
        print(f"  Created winSparkle CLI wrapper: {cli_script}")
    
    def bundle_dependency(self, name: str) -> bool:
        """打包单个依赖库"""
        config = self.dependencies[name]
        current_platform = self.get_current_platform()
        
        if config["platform"] != current_platform:
            print(f"Skipping {name} (not for current platform {current_platform})")
            return True
        
        try:
            # 下载
            archive_path = self.download_dependency(name, config)
            
            # 解压
            if name == "sparkle":
                extracted_path = self.extract_sparkle(archive_path)
            elif name == "winsparkle":
                extracted_path = self.extract_winsparkle(archive_path)
            else:
                raise ValueError(f"Unknown dependency: {name}")
            
            # 创建CLI包装器
            self.create_cli_wrapper(current_platform)
            
            print(f"[OK] {name} bundled successfully")
            return True

        except Exception as e:
            print(f"[FAIL] Failed to bundle {name}: {e}")
            return False
    
    def bundle_all(self) -> bool:
        """打包所有依赖库"""
        print("Bundling OTA dependencies...")
        print(f"Project root: {self.project_root}")
        print(f"Dependencies dir: {self.deps_dir}")
        
        current_platform = self.get_current_platform()
        print(f"Current platform: {current_platform}")
        
        success = True
        for name, config in self.dependencies.items():
            if config["platform"] == current_platform:
                if not self.bundle_dependency(name):
                    success = False
        
        if success:
            print("\n🎉 All dependencies bundled successfully!")
            self.create_bundle_info()
        else:
            print("\n❌ Some dependencies failed to bundle")
        
        return success
    
    def create_bundle_info(self):
        """创建打包信息文件"""
        info = {
            "platform": self.get_current_platform(),
            "bundled_dependencies": {},
            "bundle_date": str(Path(__file__).stat().st_mtime)
        }
        
        for name, config in self.dependencies.items():
            if config["platform"] == self.get_current_platform():
                info["bundled_dependencies"][name] = {
                    "version": config["version"],
                    "url": config["url"]
                }
        
        info_file = self.deps_dir / "bundle_info.json"
        with open(info_file, 'w') as f:
            json.dump(info, f, indent=2)
        
        print(f"  Created bundle info: {info_file}")
    
    def clean(self):
        """清理下载的文件"""
        if self.deps_dir.exists():
            shutil.rmtree(self.deps_dir)
            print(f"Cleaned dependencies directory: {self.deps_dir}")


def main():
    """主函数"""
    # 默认禁用：仅在明确允许时执行
    if os.environ.get("ECBOT_ALLOW_BUILD_SCRIPTS", "").lower() not in ("1", "true", "yes", "on"):
        print("[bundle_dependencies] This is an example/placeholder build script and is disabled by default.\n"
              "Set ECBOT_ALLOW_BUILD_SCRIPTS=1 to enable execution.")
        return 0
    
    import argparse
    
    parser = argparse.ArgumentParser(description="Bundle OTA dependencies")
    parser.add_argument("action", choices=["bundle", "clean"], help="Action to perform")
    parser.add_argument("--dependency", help="Specific dependency to bundle")
    
    args = parser.parse_args()
    
    bundler = DependencyBundler()
    
    if args.action == "clean":
        bundler.clean()
        return 0
    
    elif args.action == "bundle":
        if args.dependency:
            success = bundler.bundle_dependency(args.dependency)
        else:
            success = bundler.bundle_all()
        
        return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
