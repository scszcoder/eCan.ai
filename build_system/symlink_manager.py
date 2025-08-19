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
            # Find QtWebEngineCore.framework
            framework_path = self._find_qtwebengine_framework()
            if not framework_path:
                self.log("QtWebEngineCore.framework not found, skipping fix")
                return True

            self.log(f"Found QtWebEngineCore.framework at: {framework_path}")

            # Fix the Resources symlink (main issue)
            resources_symlink = framework_path / "Resources"
            if resources_symlink.exists() and resources_symlink.is_symlink():
                self.log("Fixing problematic Resources symlink")
                try:
                    resources_symlink.unlink()

                    # Try to copy the actual directory
                    versions_resources = framework_path / "Versions" / "Current" / "Resources"
                    if versions_resources.exists():
                        shutil.copytree(versions_resources, resources_symlink, symlinks=False)
                        self.log("Replaced Resources symlink with directory copy")
                    else:
                        resources_symlink.mkdir(exist_ok=True)
                        self.log("Created empty Resources directory")
                except Exception as e:
                    self.log(f"Failed to fix Resources symlink: {e}", "WARNING")

            self.log("Framework symlink fix completed")
            return True

        except Exception as e:
            self.log(f"Framework symlink fix failed: {e}", "ERROR")
            return False

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
