#!/usr/bin/env python3
"""
Unified Symlink and Copy Manager
Handles all symlink-related issues across QtWebEngine, Playwright, and other components
"""

import os
import sys
import shutil
import platform
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple
import subprocess


class SymlinkManager:
    """Simplified manager for symlink handling across all build components"""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.is_macos = platform.system() == "Darwin"
        self.copied_paths: Set[str] = set()

    def log(self, message: str, level: str = "INFO") -> None:
        """Log message if verbose mode is enabled"""
        if self.verbose:
            print(f"[SYMLINK-{level}] {message}")

    def safe_copytree(self, src: Path, dst: Path, component: str = "UNKNOWN") -> bool:
        """
        Safe copy tree that handles symlinks properly
        Returns True if successful, False otherwise
        """
        src_str = str(src.resolve())

        # Check for duplicate copies
        if src_str in self.copied_paths:
            self.log(f"Skipping duplicate copy: {src} (already copied)", "SKIP")
            return True

        self.log(f"Starting safe copy: {src} -> {dst} ({component})")

        try:
            # Remove destination if it exists
            if dst.exists():
                self.log(f"Removing existing destination: {dst}")
                self._safe_remove(dst)

            # Create parent directories
            dst.parent.mkdir(parents=True, exist_ok=True)

            # Use unified copy strategy: resolve all symlinks to avoid conflicts
            shutil.copytree(src, dst, symlinks=False, ignore=self._get_ignore_func(component))

            self.copied_paths.add(src_str)
            self.log(f"Successfully copied: {src} -> {dst}")
            return True

        except Exception as e:
            self.log(f"Copy failed: {src} -> {dst}: {e}", "ERROR")
            return False

    def _get_ignore_func(self, component: str):
        """Get ignore function for specific component types"""
        def ignore_func(dir_path, names):
            ignored = []
            dir_path_obj = Path(dir_path)

            for name in names:
                item_path = dir_path_obj / name

                # Skip cache and temp directories
                if name.lower() in ["cache", "tmp", "temp", "logs", "__pycache__"]:
                    ignored.append(name)
                    continue

                # Skip problematic symlinks
                if item_path.is_symlink():
                    try:
                        target = item_path.readlink()
                        # Skip external or problematic symlinks
                        if target.is_absolute() or ".." in str(target):
                            ignored.append(name)
                            self.log(f"Ignoring problematic symlink: {item_path} -> {target}")
                    except Exception:
                        ignored.append(name)
                        self.log(f"Ignoring unreadable symlink: {item_path}")

            return ignored

        return ignore_func

    def _safe_remove(self, path: Path) -> None:
        """Safely remove directory with symlink handling"""
        if not path.exists():
            return

        try:
            if self.is_macos:
                # On macOS, remove symlinks first to avoid conflicts
                for root, dirs, files in os.walk(path, topdown=False):
                    root_path = Path(root)

                    # Remove symlinked files
                    for file in files:
                        file_path = root_path / file
                        if file_path.is_symlink():
                            file_path.unlink()

                    # Remove symlinked directories
                    for dir_name in dirs[:]:  # Copy to avoid modification during iteration
                        dir_path = root_path / dir_name
                        if dir_path.is_symlink():
                            dir_path.unlink()
                            dirs.remove(dir_name)

            # Remove the directory tree
            shutil.rmtree(path, ignore_errors=True)

        except Exception as e:
            self.log(f"Safe remove failed for {path}: {e}", "ERROR")
            # Fallback to standard removal
            shutil.rmtree(path, ignore_errors=True)

    def cleanup_build_artifacts(self, build_paths: List[Path]) -> None:
        """Clean up build artifacts with proper symlink handling"""
        for path in build_paths:
            if path.exists():
                self.log(f"Cleaning build artifacts: {path}")
                self._safe_remove(path)

    def fix_pyinstaller_conflicts(self) -> bool:
        """Fix macOS framework symlinks that cause PyInstaller conflicts"""
        if not self.is_macos:
            return True

        self.log("Fixing framework symlinks to prevent PyInstaller conflicts...")

        try:
            # First, clean up any existing build artifacts
            self._cleanup_build_conflicts()

            # Fix Playwright browser symlinks (main cause of the error)
            self._fix_playwright_browsers()

            # Find QtWebEngineCore.framework
            framework_path = self._find_qtwebengine_framework()
            if framework_path:
                self.log(f"Found QtWebEngineCore.framework at: {framework_path}")
                self._fix_framework_symlinks(framework_path)
            else:
                self.log("QtWebEngineCore.framework not found, skipping Qt fix")

            self.log("All framework symlink fixes completed")
            return True

        except Exception as e:
            self.log(f"Framework symlink fix failed: {e}", "ERROR")
            return False

    def _cleanup_build_conflicts(self):
        """Clean up potential build conflicts before starting"""
        self.log("Cleaning up potential build conflicts...")

        # Clean dist directory completely
        dist_dir = Path("dist")
        if dist_dir.exists():
            self.log("Removing existing dist directory")
            self._safe_remove(dist_dir)

        # Clean build directory
        build_dir = Path("build")
        if build_dir.exists():
            self.log("Removing existing build directory")
            self._safe_remove(build_dir)

        # Clean PyInstaller cache that might contain conflicting symlinks
        import tempfile
        pyinstaller_cache = Path(tempfile.gettempdir()) / "pyinstaller"
        if pyinstaller_cache.exists():
            self.log("Cleaning PyInstaller cache")
            self._safe_remove(pyinstaller_cache)

        # Clean user-specific PyInstaller cache
        user_cache = Path.home() / "Library" / "Application Support" / "pyinstaller"
        if user_cache.exists():
            self.log("Cleaning user PyInstaller cache")
            self._safe_remove(user_cache)

    def _fix_playwright_browsers(self):
        """Fix Playwright browser symlinks that cause PyInstaller conflicts"""
        self.log("Fixing Playwright browser symlinks...")

        # Common Playwright browser locations
        playwright_dirs = [
            Path("third_party") / "ms-playwright",
            Path.home() / "Library" / "Caches" / "ms-playwright",
            Path("~/.cache/ms-playwright").expanduser()
        ]

        for playwright_dir in playwright_dirs:
            if playwright_dir.exists():
                self.log(f"Processing Playwright directory: {playwright_dir}")
                self._process_playwright_directory(playwright_dir)

    def _process_playwright_directory(self, playwright_dir: Path):
        """Process a Playwright directory to fix symlinks"""
        try:
            # Look for Chromium installations
            for chromium_path in playwright_dir.rglob("*chromium*/chrome-mac/Chromium.app"):
                if chromium_path.exists():
                    self.log(f"Found Chromium app: {chromium_path}")

                    # For severe symlink conflicts, remove the entire browser
                    if self._has_problematic_symlinks(chromium_path):
                        self.log(f"Removing problematic Chromium installation: {chromium_path}")
                        self._safe_remove(chromium_path)
                    else:
                        # Fix frameworks in the Chromium app
                        frameworks_dir = chromium_path / "Contents" / "Frameworks"
                        if frameworks_dir.exists():
                            for framework in frameworks_dir.rglob("*.framework"):
                                self._fix_framework_symlinks(framework)

        except Exception as e:
            self.log(f"Warning: Failed to process Playwright directory {playwright_dir}: {e}", "WARNING")

    def _has_problematic_symlinks(self, app_path: Path) -> bool:
        """Check if app has problematic symlinks that cause PyInstaller conflicts"""
        try:
            frameworks_dir = app_path / "Contents" / "Frameworks"
            if not frameworks_dir.exists():
                return False

            # Check for the specific symlink pattern that causes the error
            for framework in frameworks_dir.rglob("*.framework"):
                helpers_link = framework / "Helpers"
                versions_current = framework / "Versions" / "Current"

                if helpers_link.is_symlink() and versions_current.is_symlink():
                    self.log(f"Found problematic symlink pattern in: {framework.name}")
                    return True

            return False

        except Exception:
            return True  # If we can't check, assume it's problematic

    def _fix_framework_symlinks(self, framework_path: Path):
        """Fix symlinks in a specific framework"""
        try:
            self.log(f"Fixing symlinks in framework: {framework_path.name}")

            # Common problematic symlinks in frameworks
            problematic_links = [
                "Resources",
                "Helpers",
                "Versions/Current",
                "Libraries",
                "Headers"
            ]

            for link_name in problematic_links:
                link_path = framework_path / link_name
                if link_path.is_symlink():
                    try:
                        # Test if symlink is broken
                        link_path.resolve(strict=True)
                    except (OSError, FileNotFoundError):
                        self.log(f"Removing broken symlink: {link_path}")
                        link_path.unlink()
                    except Exception:
                        # If we can't resolve it, it might be problematic
                        self.log(f"Removing potentially problematic symlink: {link_path}")
                        link_path.unlink()

        except Exception as e:
            self.log(f"Warning: Failed to fix framework symlinks in {framework_path}: {e}", "WARNING")



    def _find_qtwebengine_framework(self) -> Optional[Path]:
        """Find QtWebEngineCore.framework in the virtual environment"""
        venv_path = Path("venv")
        if not venv_path.exists():
            return None

        # Common paths for QtWebEngineCore.framework
        for python_version in ["python3.11", "python3.12", "python3.10"]:
            framework_path = (venv_path / "lib" / python_version / "site-packages" /
                            "PySide6" / "Qt" / "lib" / "QtWebEngineCore.framework")
            if framework_path.exists():
                return framework_path

        return None

    def get_copy_summary(self) -> Dict[str, int]:
        """Get summary of copy operations"""
        return {"total_copies": len(self.copied_paths)}


# Global instance
symlink_manager = SymlinkManager(verbose=False)


def set_verbose(verbose: bool) -> None:
    """Set verbose mode for the global symlink manager"""
    global symlink_manager
    symlink_manager.verbose = verbose
