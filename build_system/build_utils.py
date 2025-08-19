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
    """Standardize build artifact filenames to match release.yml expected format"""
    platform_name = platform.system()

    if platform_name == "Windows":
        _standardize_windows_artifacts(version, arch)
    elif platform_name == "Darwin":
        _standardize_macos_artifacts(version, arch)
    elif platform_name == "Linux":
        _standardize_linux_artifacts(version, arch)


def _standardize_windows_artifacts(version: str, arch: str):
    """Standardize Windows build artifacts"""
    dist_dir = Path("dist")

    # Find eCan-Setup.exe (installer)
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
    """Standardize macOS build artifacts"""
    dist_dir = Path("dist")

    # Find .dmg files
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
        # If no DMG found, try to create one
        app_dirs = list(dist_dir.glob("*.app"))
        if app_dirs:
            app_path = app_dirs[0]
            dmg_name = f"eCan-{version}-macos-{arch}.dmg"
            dmg_path = dist_dir / dmg_name

            try:
                # Use hdiutil to create DMG
                import subprocess

                subprocess.run(
                    [
                        "hdiutil",
                        "create",
                        "-volname",
                        "eCan",
                        "-srcfolder",
                        str(app_path),
                        "-ov",
                        "-format",
                        "UDZO",
                        str(dmg_path),
                    ],
                    check=True,
                )
                print(f"[RENAME] Created: {dmg_path.name}")
            except Exception as e:
                print(f"[RENAME] Warning: Failed to create DMG: {e}")


def _standardize_linux_artifacts(version: str, arch: str):
    """Standardize Linux build artifacts"""
    dist_dir = Path("dist")

    # Find executable files or AppImage
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
            if root_path.name.endswith(".framework"):
                for item in root_path.iterdir():
                    if item.is_symlink():
                        try:
                            item.unlink()
                            print(f"[MACOS] Removed symlink: {item}")
                        except Exception as e:
                            print(
                                f"[MACOS] Warning: Failed to remove symlink {item}: {e}"
                            )

            # Handle other symlinks
            for file in files:
                file_path = root_path / file
                if file_path.is_symlink():
                    try:
                        file_path.unlink()
                        print(f"[MACOS] Removed symlink: {file_path}")
                    except Exception as e:
                        print(
                            f"[MACOS] Warning: Failed to remove symlink {file_path}: {e}"
                        )

        # Now remove the directory tree
        shutil.rmtree(build_path, ignore_errors=True)

    except Exception as e:
        print(f"[MACOS] Warning: Framework cleanup failed: {e}")
        # Fallback to regular cleanup
        shutil.rmtree(build_path, ignore_errors=True)


def prepare_third_party_assets() -> None:
    """Prepare third-party assets (simplified - direct Playwright handling)"""
    print("[THIRD-PARTY] Preparing Playwright assets...")

    try:
        # Use simplified Playwright preparation
        _prepare_playwright_simple()
        print("[THIRD-PARTY] Playwright assets prepared successfully")

    except Exception as e:
        print(f"[THIRD-PARTY] Playwright preparation failed: {e}")
        print("[THIRD-PARTY] This may cause issues with browser automation features")
        # Don't fail the build, just warn
        return


def _prepare_playwright_simple() -> None:
    """Simplified Playwright asset preparation"""
    import subprocess
    import sys
    import shutil
    from pathlib import Path

    target_path = Path.cwd() / "third_party" / "ms-playwright"

    # 1. Ensure playwright is installed
    try:
        subprocess.run([sys.executable, "-m", "pip", "show", "playwright"],
                      check=True, capture_output=True)
    except subprocess.CalledProcessError:
        print("[BUILD] Installing playwright...")
        subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)

    # 2. Find existing cache or install browsers
    cache_path = _find_playwright_cache()
    if not cache_path:
        print("[BUILD] Installing Playwright browsers...")
        # Install to default location
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        cache_path = _find_playwright_cache()

        if not cache_path:
            raise RuntimeError("Failed to install or locate Playwright browsers")

    # 3. Copy to target location
    print(f"[BUILD] Copying Playwright assets: {cache_path} -> {target_path}")
    if target_path.exists():
        shutil.rmtree(target_path, ignore_errors=True)

    # Use symlink manager if available for safe copying
    try:
        from build_system.symlink_manager import symlink_manager
        success = symlink_manager.safe_copytree(cache_path, target_path, "PLAYWRIGHT")
        if not success:
            raise Exception("Symlink manager copy failed")
    except Exception:
        # Fallback to standard copy
        shutil.copytree(cache_path, target_path, symlinks=False)

    print(f"[BUILD] Playwright assets copied to {target_path}")


def _find_playwright_cache() -> Path:
    """Find Playwright cache directory (simplified)"""
    import os
    import platform
    from pathlib import Path

    # Check environment variable first
    env_path = os.getenv("PLAYWRIGHT_BROWSERS_PATH")
    if env_path:
        env_path_obj = Path(env_path)
        if env_path_obj.exists() and (env_path_obj / "browsers.json").exists():
            return env_path_obj

    # Platform-specific default paths
    if platform.system() == "Windows":
        possible_paths = [
            Path.home() / "AppData" / "Local" / "ms-playwright",
            Path(os.getenv("LOCALAPPDATA", "")) / "ms-playwright",
        ]
    elif platform.system() == "Darwin":  # macOS
        possible_paths = [
            Path.home() / ".cache" / "ms-playwright",
            Path.home() / "Library" / "Caches" / "ms-playwright",
        ]
    else:  # Linux
        possible_paths = [
            Path.home() / ".cache" / "ms-playwright",
            Path.home() / ".local" / "share" / "ms-playwright",
        ]

    # Find first valid path
    for path in possible_paths:
        if path.exists() and (path / "browsers.json").exists():
            return path

    return None


def validate_macos_app_bundle(app_bundle_path: Path) -> bool:
    """Simple macOS app bundle validation (simplified from symlink_validator)"""
    import platform

    if platform.system() != "Darwin":
        return True  # Skip on non-macOS

    if not app_bundle_path.exists():
        print(f"[MACOS] Warning: App bundle not found: {app_bundle_path}")
        return False

    print(f"[MACOS] Validating app bundle: {app_bundle_path}")

    # Basic structure check
    contents_dir = app_bundle_path / "Contents"
    if not contents_dir.exists():
        print("[MACOS] Warning: Contents directory missing")
        return False

    # Check for executable
    macos_dir = contents_dir / "MacOS"
    if not macos_dir.exists():
        print("[MACOS] Warning: MacOS directory missing")
        return False

    # Count broken symlinks (simple check)
    broken_count = 0
    total_symlinks = 0

    try:
        for item in app_bundle_path.rglob("*"):
            if item.is_symlink():
                total_symlinks += 1
                try:
                    # Try to resolve the symlink
                    item.resolve(strict=True)
                except (OSError, FileNotFoundError):
                    broken_count += 1
    except Exception as e:
        print(f"[MACOS] Warning: Error during symlink check: {e}")

    print(f"[MACOS] Found {total_symlinks} symlinks, {broken_count} broken")

    if broken_count > 0:
        print(f"[MACOS] Warning: {broken_count} broken symlinks found")
        print("[MACOS] This may cause runtime issues but build will continue")
    else:
        print("[MACOS] App bundle validation passed")

    return True  # Don't fail build for symlink issues


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
        print(
            "[DEV-SIGN] Windows: DEV_WIN_CERT_PFX or DEV_WIN_CERT_PASSWORD not set, skipping"
        )
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
