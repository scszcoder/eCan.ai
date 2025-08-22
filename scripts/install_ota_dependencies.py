#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CI/CD OTA依赖安装脚本
在CI环境中预安装Sparkle/winSparkle依赖，保持build.py脚本的纯净性
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
import ssl
from pathlib import Path

# Force UTF-8 stdout/stderr to avoid UnicodeEncodeError on Windows CI (cp1252)
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


class CIOTAInstaller:
    """CI环境OTA依赖安装器"""

    def __init__(self, project_root: Path = None):
        self.project_root = project_root or Path.cwd()
        self.third_party_dir = self.project_root / "third_party"
        self.third_party_dir.mkdir(parents=True, exist_ok=True)

        self.platform = self.get_current_platform()

        # OTA依赖配置 - 使用新的third_party目录结构
        self.dependencies = {
            "sparkle": {
                "version": "2.6.4",
                "url": "https://github.com/sparkle-project/Sparkle/releases/download/2.6.4/Sparkle-2.6.4.tar.xz",
                "platform": "darwin",
                "extract_path": "Sparkle.framework",
                "target_dir": "sparkle",  # third_party/sparkle/
                "target_path": "Sparkle.framework"
            },
            "winsparkle": {
                "version": "0.8.0",
                "url": "https://github.com/vslavik/winsparkle/releases/download/v0.8.0/winsparkle-0.8.0.zip",
                "platform": "windows",
                "extract_files": ["winsparkle.dll", "winsparkle.lib", "winsparkle.h"],
                "target_dir": "winsparkle",  # third_party/winsparkle/
                "target_path": "winsparkle/winsparkle.dll"  # 指向实际的 DLL 文件
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

    def install_dependencies(self, force: bool = False) -> bool:
        """安装OTA依赖"""
        print(f"[CI-OTA] Installing OTA dependencies for platform: {self.platform}")

        success = True
        installed_count = 0

        for name, config in self.dependencies.items():
            if config.get("platform") == self.platform:
                if self._install_single_dependency(name, config, force):
                    installed_count += 1
                    print(f"[CI-OTA] [OK] {name} installed successfully")
                else:
                    print(f"[CI-OTA] ❌ Failed to install {name}")
                    success = False

        if success and installed_count > 0:
            self._create_cli_wrappers()
            self._create_install_info()
            print(f"[CI-OTA] [OK] Successfully installed {installed_count} dependencies")
        elif installed_count == 0:
            print(f"[CI-OTA] [INFO] No dependencies to install for platform {self.platform}")

        return success

    def _install_single_dependency(self, name: str, config: dict, force: bool = False) -> bool:
        """安装单个依赖"""
        try:
            # 使用新的third_party目录结构
            target_dir = self.third_party_dir / config["target_dir"]
            target_path = target_dir / config["target_path"]

            # 检查是否已存在
            if target_path.exists() and not force:
                print(f"[CI-OTA] {name} already exists at {target_path}, skipping")
                return True

            # 确保目标目录存在
            target_dir.mkdir(parents=True, exist_ok=True)

            # 下载
            archive_path = self._download_dependency(name, config)
            if not archive_path:
                return False

            # 解压安装
            if name == "sparkle":
                return self._install_sparkle(archive_path, config, target_path)
            elif name == "winsparkle":
                return self._install_winsparkle(archive_path, config, target_path)
            else:
                print(f"[CI-OTA] Unknown dependency: {name}")
                return False

        except Exception as e:
            print(f"[CI-OTA] Failed to install {name}: {e}")
            return False

    def _download_dependency(self, name: str, config: dict) -> Path:
        """下载依赖"""
        url = config["url"]
        filename = url.split("/")[-1]
        download_path = self.third_party_dir / filename

        if download_path.exists():
            print(f"[CI-OTA] {filename} already downloaded")
            return download_path

        try:
            print(f"[CI-OTA] Downloading {name} v{config['version']}...")
            print(f"[CI-OTA] URL: {url}")

            # 创建SSL上下文（忽略证书验证，仅用于CI环境）
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            # 下载文件
            request = urllib.request.Request(url)
            with urllib.request.urlopen(request, context=ssl_context) as response:
                with open(download_path, 'wb') as f:
                    shutil.copyfileobj(response, f)

            # 验证下载
            if download_path.exists() and download_path.stat().st_size > 0:
                print(f"[CI-OTA] Downloaded: {download_path} ({download_path.stat().st_size} bytes)")
                return download_path
            else:
                raise Exception("Downloaded file is empty or missing")

        except Exception as e:
            print(f"[CI-OTA] Failed to download {name}: {e}")
            if download_path.exists():
                download_path.unlink()
            return None

    def _install_sparkle(self, archive_path: Path, config: dict, target_path: Path) -> bool:
        """安装Sparkle框架"""
        try:
            print("[CI-OTA] Installing Sparkle framework...")

            extract_dir = self.third_party_dir / "sparkle_temp"
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

            # 安装到目标位置 (使用已经计算好的target_path)
            if target_path.exists():
                shutil.rmtree(target_path)

            # 保留框架内的符号链接，避免 PyInstaller 在 COLLECT 阶段重复创建导致冲突
            shutil.copytree(framework_path, target_path, symlinks=True)
            print(f"[CI-OTA] Installed Sparkle.framework to: {target_path}")

            # 验证安装
            if (target_path / "Versions" / "Current" / "Sparkle").exists():
                print("[CI-OTA] [OK] Sparkle framework installation verified")
            else:
                print("[CI-OTA] [WARN] Sparkle framework structure may be incomplete")

            # 清理临时文件
            shutil.rmtree(extract_dir)

            return True

        except Exception as e:
            print(f"[CI-OTA] Failed to install Sparkle: {e}")
            return False

    def _install_winsparkle(self, archive_path: Path, config: dict, target_path: Path) -> bool:
        """安装winSparkle库"""
        try:
            print("[CI-OTA] Installing winSparkle library...")

            extract_dir = self.third_party_dir / "winsparkle_temp"
            if extract_dir.exists():
                shutil.rmtree(extract_dir)
            extract_dir.mkdir()

            # 解压ZIP文件
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)

            # 使用传入的target_path (应该是 third_party/winsparkle/)
            target_dir = target_path.parent  # third_party/winsparkle/
            if target_dir.exists():
                shutil.rmtree(target_dir)
            target_dir.mkdir(parents=True, exist_ok=True)

            # 查找并复制所需文件（大小写不敏感），并在 lib 目录下标准化文件名为小写
            desired_map = {
                "winsparkle.dll": "winsparkle.dll",
                "winsparkle.lib": "winsparkle.lib",
                "winsparkle.h": "winsparkle.h",
                # 兼容大小写或变体命名
                "winsparkle64.dll": "winsparkle.dll",
                "winsparkle64.lib": "winsparkle.lib",
                "winsparkle-version.h": "winsparkle-version.h",
                "winsparkle.h": "winsparkle.h",
                "winsparkle.dll": "winsparkle.dll"
            }
            files_found = []

            for root, dirs, files in os.walk(extract_dir):
                for file in files:
                    key = file.lower()
                    if key in desired_map:
                        src_path = Path(root) / file
                        # 目标1：原始 target_dir 以保留上游原始命名
                        try:
                            shutil.copy2(src_path, target_dir / file)
                        except Exception:
                            pass
                        # 目标2：统一小写命名到target_dir
                        norm_name = desired_map[key]
                        try:
                            shutil.copy2(src_path, target_dir / norm_name)
                        except Exception:
                            pass
                        files_found.append(file)
                        print(f"[CI-OTA] Installed: {file}")

            if not files_found:
                raise FileNotFoundError("winSparkle files not found in archive")

            # 验证安装
            dll_path = target_dir / "winsparkle.dll"
            if dll_path.exists():
                print(f"[CI-OTA] [OK] winSparkle DLL installation verified: {dll_path}")
            else:
                print("[CI-OTA] [WARN] winSparkle DLL not found")

            # 清理临时文件
            shutil.rmtree(extract_dir)

            print(f"[CI-OTA] Installed winSparkle to: {target_dir}")
            return True

        except Exception as e:
            print(f"[CI-OTA] Failed to install winSparkle: {e}")
            return False

    def _create_cli_wrappers(self):
        """创建CLI包装器"""
        if self.platform == "darwin":
            self._create_sparkle_cli()
        elif self.platform == "windows":
            self._create_winsparkle_cli()

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
