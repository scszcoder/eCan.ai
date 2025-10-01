#!/usr/bin/env python3
"""
CI/CD OTA Dependencies Installer for eCan.ai

This script installs OTA update framework dependencies for CI/CD environments.
It downloads and sets up Sparkle (macOS) or winSparkle (Windows) frameworks
in the third_party directory structure.

Usage:
    python build_system/install_ota_dependencies.py install [--force] [--platform PLATFORM]
    python build_system/install_ota_dependencies.py clean
    python build_system/install_ota_dependencies.py verify
"""

import os
import sys
import platform
import urllib.request
import zipfile
import tarfile
import shutil
import json
import argparse
from pathlib import Path


class CIOTAInstaller:
    """CI/CD OTA依赖安装器"""

    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.third_party_dir = self.project_root / "third_party"
        self.platform = self._detect_platform()

        # 依赖配置
        self.dependencies = {
            "sparkle": {
                "platform": "darwin",
                "version": "2.6.4",
                "url": "https://github.com/sparkle-project/Sparkle/releases/download/2.6.4/Sparkle-2.6.4.tar.xz",
                "target_dir": "sparkle",
                "target_path": "Sparkle.framework",
                "archive_type": "tar.xz"
            },
            "winsparkle": {
                "platform": "windows",
                "version": "0.8.1",
                "url": "https://github.com/vslavik/winsparkle/releases/download/v0.8.1/WinSparkle-0.8.1.zip",
                "target_dir": "winsparkle",
                "target_path": "winsparkle.dll",
                "archive_type": "zip"
            }
        }

    def _detect_platform(self) -> str:
        """检测当前平台"""
        system = platform.system().lower()
        if system == "darwin":
            return "darwin"
        elif system == "windows":
            return "windows"
        elif system == "linux":
            return "linux"
        else:
            raise RuntimeError(f"Unsupported platform: {system}")

    def install_dependencies(self, force: bool = False) -> bool:
        """安装OTA依赖"""
        print(f"[CI-OTA] Installing OTA dependencies for {self.platform}...")

        # 创建third_party目录
        self.third_party_dir.mkdir(parents=True, exist_ok=True)

        # 获取当前平台的依赖配置
        platform_deps = {
            name: config for name, config in self.dependencies.items()
            if config.get("platform") == self.platform
        }

        if not platform_deps:
            print(f"[CI-OTA] No OTA dependencies needed for {self.platform}")
            return True

        success = True
        for name, config in platform_deps.items():
            try:
                if not self._install_dependency(name, config, force):
                    success = False
            except Exception as e:
                print(f"[CI-OTA] Failed to install {name}: {e}")
                success = False

        if success:
            # 创建CLI包装器
            if self.platform == "darwin":
                self._create_sparkle_cli()
            elif self.platform == "windows":
                self._create_winsparkle_cli()

            # 创建安装信息文件
            self._create_install_info()

        return success

    def _install_dependency(self, name: str, config: dict, force: bool) -> bool:
        """安装单个依赖"""
        target_dir = self.third_party_dir / config["target_dir"]
        target_path = target_dir / config["target_path"]

        # 检查是否已安装
        if target_path.exists() and not force:
            print(f"[CI-OTA] {name} already installed at: {target_path}")
            return True

        print(f"[CI-OTA] Installing {name} {config['version']}...")

        # 创建目标目录
        target_dir.mkdir(parents=True, exist_ok=True)

        # 下载文件
        download_path = target_dir / f"{name}.{config['archive_type']}"
        print(f"[CI-OTA] Downloading from: {config['url']}")

        try:
            urllib.request.urlretrieve(config['url'], download_path)
            print(f"[CI-OTA] Downloaded to: {download_path}")
        except Exception as e:
            print(f"[CI-OTA] Download failed: {e}")
            return False

        # 解压文件
        try:
            if config['archive_type'] == 'zip':
                self._extract_zip(download_path, target_dir)
            elif config['archive_type'] in ['tar.xz', 'tar.gz']:
                self._extract_tar(download_path, target_dir)
            else:
                print(f"[CI-OTA] Unsupported archive type: {config['archive_type']}")
                return False

            print(f"[CI-OTA] Extracted to: {target_dir}")
        except Exception as e:
            print(f"[CI-OTA] Extraction failed: {e}")
            return False
        finally:
            # 清理下载文件
            if download_path.exists():
                download_path.unlink()

        # 验证安装
        if not target_path.exists():
            print(f"[CI-OTA] Installation verification failed: {target_path} not found")
            return False

        print(f"[CI-OTA] Successfully installed {name} at: {target_path}")
        return True

    def _extract_zip(self, archive_path: Path, target_dir: Path):
        """解压ZIP文件"""
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            zip_ref.extractall(target_dir)

    def _extract_tar(self, archive_path: Path, target_dir: Path):
        """解压TAR文件"""
        with tarfile.open(archive_path, 'r:*') as tar_ref:
            tar_ref.extractall(target_dir)

    def _create_sparkle_cli(self):
        """创建Sparkle CLI包装器"""
        cli_script = self.third_party_dir / "sparkle" / "sparkle-cli"

        script_content = '''#!/bin/bash
# Sparkle CLI wrapper for eCan OTA (CI-installed)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRAMEWORK_PATH="$SCRIPT_DIR/Sparkle.framework"

if [ ! -d "$FRAMEWORK_PATH" ]; then
    echo "Error: Sparkle.framework not found at $FRAMEWORK_PATH"
    echo "Please ensure OTA dependencies are installed via CI"
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
        python3 -c "
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname('$SCRIPT_DIR'), '..'))
try:
    from ota import OTAUpdater
    updater = OTAUpdater()
    has_update = updater.check_for_updates(silent=True)
    sys.exit(0 if has_update else 1)
except Exception as e:
    print(f'Error: {e}')
    sys.exit(1)
"
        ;;
    "install")
        echo "Installing update via Sparkle..."
        python3 -c "
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname('$SCRIPT_DIR'), '..'))
try:
    from ota import OTAUpdater
    updater = OTAUpdater()
    success = updater.install_update()
    sys.exit(0 if success else 1)
except Exception as e:
    print(f'Error: {e}')
    sys.exit(1)
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
        print(f"[CI-OTA] Created Sparkle CLI wrapper: {cli_script}")

    def _create_winsparkle_cli(self):
        """创建winSparkle CLI包装器"""
        cli_script = self.third_party_dir / "winsparkle" / "winsparkle-cli.bat"

        script_content = '''@echo off
REM winSparkle CLI wrapper for eCan OTA (CI-installed)

set SCRIPT_DIR=%~dp0
set DLL_PATH=%SCRIPT_DIR%winsparkle\\winsparkle.dll

if not exist "%DLL_PATH%" (
    echo Error: winsparkle.dll not found at %DLL_PATH%
    echo Please ensure OTA dependencies are installed via CI
    exit /b 1
)

REM Simulate CLI behavior using Python OTA system
if "%1"=="check" (
    echo Checking for updates via winSparkle...
    python -c "import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(r'%SCRIPT_DIR%'), '..')); from ota import OTAUpdater; updater = OTAUpdater(); has_update = updater.check_for_updates(silent=True); sys.exit(0 if has_update else 1)"
    exit /b %ERRORLEVEL%
)

if "%1"=="install" (
    echo Installing update via winSparkle...
    python -c "import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(r'%SCRIPT_DIR%'), '..')); from ota import OTAUpdater; updater = OTAUpdater(); success = updater.install_update(); sys.exit(0 if success else 1)"
    exit /b %ERRORLEVEL%
)

echo Usage: winsparkle-cli.bat [check^|install]
exit /b 1
'''

        with open(cli_script, 'w') as f:
            f.write(script_content)

        print(f"[CI-OTA] Created winSparkle CLI wrapper: {cli_script}")

    def _create_install_info(self):
        """创建安装信息文件"""
        info = {
            "platform": self.platform,
            "install_method": "ci",
            "installed_dependencies": {},
            "install_timestamp": str(Path(__file__).stat().st_mtime),
            "installer_version": "1.0.0"
        }

        for name, config in self.dependencies.items():
            if config.get("platform") == self.platform:
                target_dir = self.third_party_dir / config["target_dir"]
                target_path = target_dir / config["target_path"]
                if target_path.exists():
                    info["installed_dependencies"][name] = {
                        "version": config["version"],
                        "url": config["url"],
                        "target_path": str(target_path),
                        "installed": True
                    }

        # 为每个平台的依赖创建安装信息文件
        for name, config in self.dependencies.items():
            if config.get("platform") == self.platform:
                target_dir = self.third_party_dir / config["target_dir"]
                if target_dir.exists():
                    info_file = target_dir / "install_info.json"
                    with open(info_file, 'w') as f:
                        json.dump(info, f, indent=2)
                    print(f"[CI-OTA] Created install info: {info_file}")

    def clean_dependencies(self):
        """清理依赖文件"""
        if self.third_party_dir.exists():
            # 只清理OTA相关的目录
            for name, config in self.dependencies.items():
                target_dir = self.third_party_dir / config["target_dir"]
                if target_dir.exists():
                    shutil.rmtree(target_dir)
                    print(f"[CI-OTA] Cleaned {name} directory: {target_dir}")

    def verify_installation(self) -> bool:
        """验证安装"""
        print(f"[CI-OTA] Verifying OTA dependencies installation...")

        # 检查third_party结构
        info_file = None
        for name, config in self.dependencies.items():
            if config.get("platform") == self.platform:
                target_dir = self.third_party_dir / config["target_dir"]
                info_file = target_dir / "install_info.json"
                if info_file.exists():
                    break

        if not info_file or not info_file.exists():
            print("[CI-OTA] ❌ Install info file not found")
            return False

        try:
            with open(info_file, 'r') as f:
                info = json.load(f)

            installed_deps = info.get("installed_dependencies", {})
            if not installed_deps:
                print("[CI-OTA] [ERROR] No dependencies installed")
                return False

            all_verified = True
            for name, dep_info in installed_deps.items():
                target_path = Path(dep_info["target_path"])
                if target_path.exists():
                    print(f"[CI-OTA] [OK] {name} verified at: {target_path}")
                else:
                    print(f"[CI-OTA] [ERROR] {name} not found at: {target_path}")
                    all_verified = False

            return all_verified

        except Exception as e:
            print(f"[CI-OTA] [ERROR] Failed to verify installation: {e}")
            return False


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="CI/CD OTA Dependencies Installer")
    parser.add_argument("action", choices=["install", "clean", "verify"], help="Action to perform")
    parser.add_argument("--force", action="store_true", help="Force reinstall")
    parser.add_argument("--platform", choices=["windows", "darwin", "linux"], help="Target platform")

    args = parser.parse_args()

    installer = CIOTAInstaller()

    # 覆盖平台检测（如果指定）
    if args.platform:
        installer.platform = args.platform

    print(f"[CI-OTA] CI/CD OTA Dependencies Installer")
    print(f"[CI-OTA] Platform: {installer.platform}")
    print(f"[CI-OTA] Action: {args.action}")
    print("=" * 50)

    if args.action == "clean":
        installer.clean_dependencies()
        return 0

    elif args.action == "verify":
        success = installer.verify_installation()
        return 0 if success else 1

    elif args.action == "install":
        success = installer.install_dependencies(force=args.force)
        if success:
            # 验证安装
            if installer.verify_installation():
                print("\n[CI-OTA] [OK] OTA dependencies installed and verified successfully!")
                return 0
            else:
                print("\n[CI-OTA] [ERROR] Installation verification failed")
                return 1
        else:
            print("\n[CI-OTA] [ERROR] Installation failed")
            return 1


if __name__ == "__main__":
    sys.exit(main())
