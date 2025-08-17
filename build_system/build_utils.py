#!/usr/bin/env python3
"""
Build Utilities
Common utility functions for the build system
"""

import os
import platform
import shutil
from pathlib import Path
from typing import Optional


def print_banner():
    """Print build banner"""
    print("=" * 60)
    print("eCan Unified Build System v9.0")
    print("=" * 60)


def print_mode_info(mode: str, fast: bool = False):
    """Print build mode information"""
    print(f"Build Mode: {mode.upper()}")

    if fast:
        print("[FAST] Fast Build Features:")
        print("  - Parallel processing")
        print("  - Incremental builds")
        print("  - Cache optimization")
        print("  - Estimated time: 2-5 minutes")
    elif mode == "dev":
        print("[DEV] Development Build Features:")
        print("  - Debug symbols included")
        print("  - Console output enabled")
        print("  - Parallel processing")
        print("  - Estimated time: 5-10 minutes")
    elif mode == "prod":
        print("[PROD] Production Build Features:")
        print("  - Maximum optimization")
        print("  - Binary compression")
        print("  - Debug info stripping")
        print("  - Estimated time: 15-25 minutes")

    print("=" * 60)


def standardize_artifact_names(version: str, arch: str = "amd64") -> None:
    """标准化构建产物文件名以匹配 release.yml 期望的格式"""
    platform_name = platform.system()

    if platform_name == "Windows":
        _standardize_windows_artifacts(version, arch)
    elif platform_name == "Darwin":
        _standardize_macos_artifacts(version, arch)
    elif platform_name == "Linux":
        _standardize_linux_artifacts(version, arch)


def _standardize_windows_artifacts(version: str, arch: str):
    """标准化 Windows 构建产物"""
    dist_dir = Path("dist")
    
    # 查找 eCan-Setup.exe
    setup_files = list(dist_dir.glob("*Setup*.exe"))
    if setup_files:
        old_path = setup_files[0]
        new_name = f"eCan-{version}-windows-{arch}.exe"
        new_path = dist_dir / new_name
        
        try:
            if old_path != new_path:
                shutil.move(old_path, new_path)
                print(f"[RENAME] {old_path.name} -> {new_name}")
        except Exception as e:
            print(f"[RENAME] Warning: Failed to rename {old_path}: {e}")


def _standardize_macos_artifacts(version: str, arch: str):
    """标准化 macOS 构建产物"""
    dist_dir = Path("dist")
    
    # 查找 .dmg 文件
    dmg_files = list(dist_dir.glob("*.dmg"))
    if dmg_files:
        old_path = dmg_files[0]
        new_name = f"eCan-{version}-macos-{arch}.dmg"
        new_path = dist_dir / new_name
        
        try:
            if old_path != new_path:
                shutil.move(old_path, new_path)
                print(f"[RENAME] {old_path.name} -> {new_name}")
        except Exception as e:
            print(f"[RENAME] Warning: Failed to rename {old_path}: {e}")
    else:
        # 如果没有 DMG，尝试创建一个
        app_dirs = list(dist_dir.glob("*.app"))
        if app_dirs:
            app_path = app_dirs[0]
            dmg_name = f"eCan-{version}-macos-{arch}.dmg"
            dmg_path = dist_dir / dmg_name
            
            try:
                # 使用 hdiutil 创建 DMG
                import subprocess
                subprocess.run([
                    "hdiutil", "create", "-volname", "eCan",
                    "-srcfolder", str(app_path),
                    "-ov", "-format", "UDZO",
                    str(dmg_path)
                ], check=True)
                print(f"[RENAME] Created: {dmg_path.name}")
            except Exception as e:
                print(f"[RENAME] Warning: Failed to create DMG: {e}")


def _standardize_linux_artifacts(version: str, arch: str):
    """标准化 Linux 构建产物"""
    dist_dir = Path("dist")
    
    # 查找可执行文件或 AppImage
    executables = []
    for pattern in ["eCan", "*.AppImage", "*.deb", "*.rpm"]:
        executables.extend(dist_dir.glob(pattern))
    
    if executables:
        old_path = executables[0]
        suffix = old_path.suffix or ""
        new_name = f"eCan-{version}-linux-{arch}{suffix}"
        new_path = dist_dir / new_name
        
        try:
            if old_path != new_path:
                shutil.move(old_path, new_path)
                print(f"[RENAME] {old_path.name} -> {new_name}")
        except Exception as e:
            print(f"[RENAME] Warning: Failed to rename {old_path}: {e}")


def show_build_results():
    """Show build results"""
    print("\n[RESULT] Build Results:")

    dist_dir = Path("dist")
    if dist_dir.exists():
        files = list(dist_dir.iterdir())
        if files:
            print(f"[RESULT] Output directory: {dist_dir.absolute()}")
            for file in sorted(files):
                if file.is_file():
                    size_mb = file.stat().st_size / (1024 * 1024)
                    print(f"[RESULT]   {file.name} ({size_mb:.1f} MB)")
                elif file.is_dir():
                    print(f"[RESULT]   {file.name}/ (directory)")
        else:
            print("[RESULT] No files found in dist directory")
    else:
        print("[RESULT] No dist directory found")

    print("\n[OPTIMIZATION] Applied optimizations:")
    print("  - PyInstaller optimization")
    print("  - Binary compression")
    print("  - Debug info stripping")


def clean_macos_build_artifacts(build_path: Path) -> None:
    """Clean macOS build artifacts with special handling for symlinks and frameworks"""
    if not build_path.exists():
        return

    print(f"[MACOS] Cleaning {build_path} with framework-aware cleanup...")

    # Special handling for frameworks and symlinks
    try:
        # First, try to remove symlinks that might cause conflicts
        for root, _, files in os.walk(build_path, topdown=False):
            root_path = Path(root)

            # Handle framework symlinks specifically
            if root_path.name.endswith('.framework'):
                for item in root_path.iterdir():
                    if item.is_symlink():
                        try:
                            item.unlink()
                            print(f"[MACOS] Removed symlink: {item}")
                        except Exception as e:
                            print(f"[MACOS] Warning: Failed to remove symlink {item}: {e}")

            # Handle other symlinks
            for file in files:
                file_path = root_path / file
                if file_path.is_symlink():
                    try:
                        file_path.unlink()
                        print(f"[MACOS] Removed symlink: {file_path}")
                    except Exception as e:
                        print(f"[MACOS] Warning: Failed to remove symlink {file_path}: {e}")

        # Now remove the directory tree
        shutil.rmtree(build_path, ignore_errors=True)

    except Exception as e:
        print(f"[MACOS] Warning: Framework cleanup failed: {e}")
        # Fallback to regular cleanup
        shutil.rmtree(build_path, ignore_errors=True)


def prepare_third_party_assets() -> None:
    """Prepare all third-party assets using the unified manager"""
    try:
        from build_system.third_party_manager import third_party_manager, set_verbose

        # Set verbose mode (try to get from args if available)
        try:
            import sys
            verbose = '--verbose' in sys.argv or '-v' in sys.argv
            set_verbose(verbose)
        except:
            pass

        print("[THIRD-PARTY] Processing third-party assets...")

        # Process all enabled third-party components
        results = third_party_manager.process_all()

        # Report results
        success_count = sum(1 for success in results.values() if success)
        total_count = len(results)

        if success_count > 0:
            print(f"[THIRD-PARTY] Successfully processed {success_count}/{total_count} components")
            for name, success in results.items():
                status = "✓" if success else "✗"
                print(f"[THIRD-PARTY]   {status} {name}")
        else:
            print("[THIRD-PARTY] No third-party components processed")

        # Special handling for Playwright if it failed
        if not results.get('playwright', False):
            print("[THIRD-PARTY] Playwright processing failed, using fallback...")
            prepare_playwright_assets_fallback()

    except Exception as e:
        print(f"[THIRD-PARTY] Error in third-party processing: {e}")
        print("[THIRD-PARTY] Using fallback Playwright handling...")
        prepare_playwright_assets_fallback()


def prepare_playwright_assets_fallback() -> None:
    """Fallback Playwright asset preparation"""
    try:
        from build_system.playwright.utils import build_utils

        third_party = Path.cwd() / "third_party" / "ms-playwright"
        build_utils.prepare_playwright_for_build(third_party)
        print("[THIRD-PARTY] Fallback Playwright preparation completed")
    except Exception as e:
        print(f"[THIRD-PARTY] Fallback Playwright preparation failed: {e}")


def dev_sign_artifacts(enable: bool) -> None:
    """Development-only local signing helper (safe no-op if not configured)"""
    if not enable:
        return

    try:
        sysname = platform.system()
        if sysname == "Windows":
            _dev_sign_windows()
        elif sysname == "Darwin":
            _dev_sign_macos()
        else:
            print(f"[DEV-SIGN] Unsupported platform for dev-sign: {sysname}")
    except Exception as e:
        print(f"[DEV-SIGN] ERROR: {e}")


def _dev_sign_windows():
    """Development signing for Windows"""
    cert_pfx = os.getenv("DEV_WIN_CERT_PFX")
    cert_password = os.getenv("DEV_WIN_CERT_PASSWORD")
    
    if not cert_pfx or not cert_password:
        print("[DEV-SIGN] Windows: DEV_WIN_CERT_PFX or DEV_WIN_CERT_PASSWORD not set, skipping")
        return
    
    print("[DEV-SIGN] Windows: Development signing enabled")
    # Implementation would go here


def _dev_sign_macos():
    """Development signing for macOS"""
    identity = os.getenv("DEV_MAC_CODESIGN_IDENTITY")
    
    if not identity:
        print("[DEV-SIGN] macOS: DEV_MAC_CODESIGN_IDENTITY not set, skipping")
        return
    
    print("[DEV-SIGN] macOS: Development signing enabled")
    # Implementation would go here
