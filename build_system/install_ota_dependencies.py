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
            return False

        print(f"[CI-OTA] Successfully installed {name} at: {target_path}")
        return True

    def _extract_tar(self, archive_path: Path, target_dir: Path) -> None:
        """Extract TAR file"""
        import tempfile
        
        # Create a temporary directory for extraction
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            
            # Extract the archive to the temporary directory
            if archive_path.suffix == '.xz':
                import lzma
                with lzma.open(archive_path) as f, tarfile.open(fileobj=f) as tar:
                    tar.extractall(path=temp_dir_path)
            else:
                with tarfile.open(archive_path) as tar:
                    tar.extractall(path=temp_dir_path)
            
            # Find the Sparkle.framework in the extracted files
            sparkle_framework = None
            for path in temp_dir_path.rglob('Sparkle.framework'):
                if path.is_dir() and 'Sparkle.framework' in str(path):
                    sparkle_framework = path
                    break
            
            if not sparkle_framework:
                raise FileNotFoundError("Could not find Sparkle.framework in the downloaded archive")
            
            # Remove existing target directory if it exists
            target_framework = target_dir / 'Sparkle.framework'
            if target_framework.exists():
                shutil.rmtree(target_framework)
            
            # Move the framework to the target directory
            shutil.move(str(sparkle_framework), str(target_dir))
            
            # Ensure proper permissions
            sparkle_binary = target_framework / 'Versions' / 'Current' / 'Sparkle'
            if sparkle_binary.exists():
                os.chmod(sparkle_binary, 0o755)
                
            # Set permissions for generate_appcast tool (in Resources directory)
            generate_appcast = target_framework / 'Versions' / 'Current' / 'Resources' / 'generate_appcast'
            if generate_appcast.exists():
                os.chmod(generate_appcast, 0o755)
            
            print(f"[CI-OTA] Successfully extracted Sparkle.framework to {target_framework}")
            
    def _extract_zip(self, archive_path: Path, target_dir: Path) -> None:
        """Extract ZIP file for Windows OTA dependencies"""
        from zipfile import ZipFile
        import tempfile
        
        # Create a temporary directory for extraction
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            
            # Extract the archive to the temporary directory
            print(f"[CI-OTA] Extracting {archive_path.name} to {temp_dir_path}")
            with ZipFile(archive_path, 'r') as zip_ref:
                # List all files in the archive for debugging
                file_list = zip_ref.namelist()
                print(f"[CI-OTA] Archive contains {len(file_list)} files:")
                for file_name in file_list[:10]:  # Show first 10 files
                    print(f"[CI-OTA]   - {file_name}")
                if len(file_list) > 10:
                    print(f"[CI-OTA]   ... and {len(file_list) - 10} more files")
                
                zip_ref.extractall(temp_dir_path)
            
            # List extracted files for debugging
            print(f"[CI-OTA] Extracted files in {temp_dir_path}:")
            for item in temp_dir_path.rglob('*'):
                if item.is_file():
                    print(f"[CI-OTA]   - {item.relative_to(temp_dir_path)}")
            
            # Find the winsparkle files in the extracted files
            winsparkle_files = list(temp_dir_path.rglob('winsparkle.dll'))
            print(f"[CI-OTA] Found {len(winsparkle_files)} winsparkle.dll files")
            
            if not winsparkle_files:
                # Check if the dll is in a subdirectory
                print("[CI-OTA] Searching for winsparkle.dll in subdirectories...")
                for path in temp_dir_path.rglob('*'):
                    if path.is_dir():
                        print(f"[CI-OTA] Checking directory: {path.relative_to(temp_dir_path)}")
                        if 'winsparkle' in path.name.lower():
                            winsparkle_files = list(path.rglob('winsparkle.dll'))
                            print(f"[CI-OTA] Found {len(winsparkle_files)} dll files in {path.name}")
                            if winsparkle_files:
                                break
            
            if not winsparkle_files:
                # Try to find any .dll files for debugging
                all_dll_files = list(temp_dir_path.rglob('*.dll'))
                print(f"[CI-OTA] Found {len(all_dll_files)} .dll files in total:")
                for dll_file in all_dll_files:
                    print(f"[CI-OTA]   - {dll_file.relative_to(temp_dir_path)}")
                
                raise FileNotFoundError("Could not find winsparkle.dll in the downloaded archive")
            
            # Create target directory if it doesn't exist
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy all files from the winsparkle directory to the target directory
            winsparkle_dir = winsparkle_files[0].parent
            print(f"[CI-OTA] Copying files from {winsparkle_dir.relative_to(temp_dir_path)} to {target_dir}")
            
            copied_files = []
            for item in winsparkle_dir.iterdir():
                dest = target_dir / item.name
                if dest.exists():
                    if dest.is_dir():
                        shutil.rmtree(dest)
                    else:
                        dest.unlink()
                
                if item.is_dir():
                    shutil.copytree(item, dest)
                    copied_files.append(f"{item.name}/ (directory)")
                else:
                    shutil.copy2(item, dest)
                    copied_files.append(item.name)
            
            print(f"[CI-OTA] Copied {len(copied_files)} items:")
            for file_name in copied_files:
                print(f"[CI-OTA]   - {file_name}")
            
            print(f"[CI-OTA] Successfully extracted WinSparkle files to {target_dir}")

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
        
        os.chmod(cli_script, 0o755)
        print(f"[CI-OTA] Created Sparkle CLI wrapper: {cli_script}")

    def _create_winsparkle_cli(self):
        """Create winSparkle CLI wrapper"""
        winsparkle_dir = self.third_party_dir / "winsparkle"
        cli_script = winsparkle_dir / "winsparkle-cli.bat"
        
        # Ensure the winsparkle directory exists
        winsparkle_dir.mkdir(parents=True, exist_ok=True)
        
        # Create a more robust batch script with better error handling
        script_content = '''@echo off
:: winSparkle CLI wrapper for eCan OTA (CI-installed)
:: This script is automatically generated - do not modify manually

setlocal enabledelayedexpansion

:: Get the directory where this script is located
set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR%"=="" set "SCRIPT_DIR=.\\"

:: Normalize the path (remove trailing backslash if present)
if "%SCRIPT_DIR:~-1%"=="\\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

:: Set the path to winsparkle.dll
set "DLL_PATH=%SCRIPT_DIR%\\winsparkle.dll"
set "DLL_PATH_EXISTS=0"

:: Check if winsparkle.dll exists
if exist "%DLL_PATH%" (
    set "DLL_PATH_EXISTS=1"
) else (
    echo [ERROR] winsparkle.dll not found at: %DLL_PATH%
    echo Please ensure OTA dependencies are installed via CI
    echo.
    echo Searching for winsparkle.dll in: %~dp0
    dir /s /b "%~dp0winsparkle.dll"
    exit /b 1
)

:: Get the project root (two levels up from third_party/winsparkle)
set "PROJECT_ROOT=%SCRIPT_DIR%\\..\\..\"
set "PROJECT_ROOT=%PROJECT_ROOT:\\=\\%"

:: Handle commands
if "%1"=="" goto usage

if /i "%1"=="check" (
    echo [INFO] Checking for updates via WinSparkle...
    python -c "import sys, os; sys.path.insert(0, r'%PROJECT_ROOT%'); from ota import OTAUpdater; updater = OTAUpdater(); has_update = updater.check_for_updates(silent=True); sys.exit(0 if has_update else 1)"
    set "EXIT_CODE=!ERRORLEVEL!"
    if !EXIT_CODE! EQU 0 (
        echo [INFO] Update available
    ) else (
        echo [INFO] No updates available
    )
    exit /b !EXIT_CODE!
) 

if /i "%1"=="install" (
    echo [INFO] Installing updates via WinSparkle...
    python -c "import sys, os; sys.path.insert(0, r'%PROJECT_ROOT%'); from ota import OTAUpdater; updater = OTAUpdater(); updater.install_update()"
    exit /b !ERRORLEVEL!
)

:usage
echo.
echo WinSparkle CLI for eCan OTA Updates
echo ===================================
echo.
echo Usage: %~nx0 [command]
echo.
echo Commands:
echo   check    Check for available updates
echo   install  Install available updates
echo.
echo Example:
echo   %~nx0 check
echo   %~nx0 install
echo.

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

        # 直接检查每个平台的依赖文件
        all_verified = True
        for name, config in self.dependencies.items():
            if config.get("platform") == self.platform:
                target_dir = self.third_party_dir / config["target_dir"]
                target_path = target_dir / config["target_path"]
                
                print(f"[CI-OTA] Checking {name}:")
                print(f"[CI-OTA]   Target directory: {target_dir}")
                print(f"[CI-OTA]   Target file: {target_path}")
                print(f"[CI-OTA]   Directory exists: {target_dir.exists()}")
                print(f"[CI-OTA]   File exists: {target_path.exists()}")
                
                if target_dir.exists():
                    print(f"[CI-OTA]   Directory contents:")
                    for item in target_dir.iterdir():
                        print(f"[CI-OTA]     - {item.name} ({'dir' if item.is_dir() else 'file'})")
                
                if target_path.exists():
                    print(f"[CI-OTA] [OK] {name} verified at: {target_path}")
                else:
                    print(f"[CI-OTA] [ERROR] {name} not found at: {target_path}")
                    all_verified = False

        # 检查install_info.json文件（如果存在）
        info_file = None
        for name, config in self.dependencies.items():
            if config.get("platform") == self.platform:
                target_dir = self.third_party_dir / config["target_dir"]
                info_file = target_dir / "install_info.json"
                if info_file.exists():
                    print(f"[CI-OTA] Found install info file: {info_file}")
                    try:
                        with open(info_file, 'r') as f:
                            info = json.load(f)
                        print(f"[CI-OTA] Install info: {json.dumps(info, indent=2)}")
                    except Exception as e:
                        print(f"[CI-OTA] Failed to read install info: {e}")
                    break

        if all_verified:
            print("[CI-OTA] [OK] OTA dependencies installed and verified successfully!")
        else:
            print("[CI-OTA] [ERROR] Some OTA dependencies are missing or invalid")
            
        return all_verified


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
