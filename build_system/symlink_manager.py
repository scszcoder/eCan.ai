#!/usr/bin/env python3
"""
Framework Symlink Manager
Simple framework symlink handling for macOS builds
"""

import os
import platform
import shutil
from pathlib import Path
from typing import List, Optional


class FrameworkManager:
    """Simple framework symlink manager for macOS"""

    # Common framework symlink names
    COMMON_SYMLINKS = ["Resources", "Headers", "Modules", "Helpers", "Current"]

    # Default search paths
    DEFAULT_SEARCH_PATHS = ["third_party", "venv/lib"]

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.is_macos = platform.system() == "Darwin"

    def log(self, message: str, level: str = "INFO") -> None:
        """Log message if verbose"""
        if self.verbose:
            print(f"[{level}] {message}")

    def fix_prebuild_frameworks(self, search_paths: Optional[List[str]] = None) -> bool:
        """Fix framework symlinks before build"""
        if not self.is_macos:
            return True

        paths = search_paths or self.DEFAULT_SEARCH_PATHS
        self.log("Fixing pre-build frameworks...")

        try:
            for path_str in paths:
                self._process_path(Path(path_str))
            return True
        except Exception as e:
            self.log(f"Pre-build fix failed: {e}", "ERROR")
            return False

    def fix_postbuild_frameworks(self, dist_path: str = "dist") -> bool:
        """Fix frameworks after build"""
        if not self.is_macos:
            return True

        dist_dir = Path(dist_path)
        if not dist_dir.exists():
            return True

        self.log("Optimizing post-build frameworks...")

        try:
            self._process_path(dist_dir)
            # Auto-repair any damaged symlinks in the build
            self._auto_repair_symlinks(dist_dir)
            self.log("Post-build optimization completed successfully")
            return True
        except Exception as e:
            self.log(f"Post-build optimization failed: {e}", "ERROR")
            return False

    def _process_path(self, path: Path) -> None:
        """Process all frameworks in a path"""
        if not path.exists():
            return

        frameworks = list(path.rglob("*.framework"))
        for framework in frameworks:
            self._fix_framework(framework)

    def _fix_framework(self, framework_path: Path) -> None:
        """Fix a single framework (skip Qt frameworks)"""
        if not framework_path.exists():
            return

        name = framework_path.name

        # Skip Qt/PySide6 frameworks - let PyInstaller handle them
        qt_frameworks = ["Qt", "PySide6"]
        if any(qt_name in name for qt_name in qt_frameworks):
            self.log(f"Skipping Qt framework: {name}")
            return

        # Skip frameworks in system locations
        path_str = str(framework_path)
        if any(pattern in path_str for pattern in ["site-packages", "venv/lib", "_internal"]):
            self.log(f"Skipping system framework: {name}")
            return

        self.log(f"Processing custom framework: {name}")

        # Special handling for Sparkle (our own framework)
        if "sparkle" in name.lower():
            self._fix_sparkle_framework(framework_path)

        # Fix common symlinks only for our own frameworks
        for symlink_name in self.COMMON_SYMLINKS:
            symlink_path = framework_path / symlink_name
            if symlink_path.is_symlink():
                self._resolve_symlink(symlink_path)

    def _fix_sparkle_framework(self, framework_path: Path) -> None:
        """Fix Sparkle-specific issues"""
        versions_dir = framework_path / "Versions"
        if versions_dir.exists():
            shutil.rmtree(versions_dir, ignore_errors=True)
            self.log("Removed Sparkle Versions directory")

    def _resolve_symlink(self, symlink_path: Path) -> None:
        """Replace symlink with actual content"""
        try:
            target = symlink_path.readlink()
            if not target.is_absolute():
                target = (symlink_path.parent / target).resolve()

            symlink_path.unlink()

            if target.exists():
                if target.is_dir():
                    shutil.copytree(target, symlink_path, symlinks=False, dirs_exist_ok=True)
                else:
                    shutil.copy2(target, symlink_path)
            else:
                # Create empty directory for common symlinks
                if symlink_path.name in self.COMMON_SYMLINKS:
                    symlink_path.mkdir(exist_ok=True)

        except Exception as e:
            self.log(f"Failed to resolve {symlink_path.name}: {e}", "WARNING")

    def _auto_repair_symlinks(self, dist_dir: Path) -> None:
        """Auto-repair damaged symlinks in the build output"""
        self.log("Checking for damaged symlinks...")

        # Find all broken symlinks that need repair
        damaged_links = []
        for item in dist_dir.rglob("*"):
            if item.is_symlink() and not item.exists():
                # Focus on framework-related symlinks that are critical
                if ".framework" in str(item):
                    damaged_links.append(item)

        if not damaged_links:
            self.log("No damaged symlinks found")
            return

        self.log(f"Found {len(damaged_links)} damaged symlinks, attempting repair")

        for damaged_link in damaged_links:
            self._repair_single_symlink(damaged_link)

    def _repair_single_symlink(self, symlink_path: Path) -> None:
        """Repair a single damaged symlink by finding the correct target"""
        try:
            # Get the symlink target
            target = symlink_path.readlink()
            self.log(f"Repairing symlink: {symlink_path.name} -> {target}")

            # If it's a relative path, resolve it
            if not target.is_absolute():
                target = (symlink_path.parent / target).resolve()

            # Try to find alternative sources for the target
            if not target.exists():
                alternative_target = self._find_alternative_target(symlink_path, target)
                if alternative_target:
                    self.log(f"Found alternative target: {alternative_target}")
                    # Remove damaged symlink and create new one
                    symlink_path.unlink()
                    symlink_path.symlink_to(alternative_target.relative_to(symlink_path.parent))
                    self.log(f"Successfully repaired: {symlink_path.name}")
                    return

            self.log(f"Could not repair symlink: {symlink_path.name}", "WARNING")

        except Exception as e:
            self.log(f"Error repairing symlink {symlink_path.name}: {e}", "WARNING")

    def _find_alternative_target(self, symlink_path: Path, original_target: Path) -> Path:
        """Find alternative target for damaged symlinks"""
        framework_root = None

        # Find the framework root directory
        for parent in symlink_path.parents:
            if parent.name.endswith('.framework'):
                framework_root = parent
                break

        if not framework_root:
            return None

        # Look for alternative versions in the framework
        versions_dir = framework_root / "Versions"
        if not versions_dir.exists():
            return None

        target_name = original_target.name

        # Search in all version directories for the target
        for version_dir in versions_dir.iterdir():
            if version_dir.is_dir() and version_dir.name not in ["Current"]:
                potential_target = version_dir / target_name
                if potential_target.exists():
                    return potential_target

                # For directories, also check if we can find the content elsewhere
                if target_name in ["Helpers", "Resources"]:
                    for subdir in version_dir.iterdir():
                        if subdir.is_dir() and subdir.name == target_name:
                            return subdir

        return None

    def clean_build_artifacts(self, paths: List[str]) -> None:
        """Clean build artifacts"""
        for path_str in paths:
            path = Path(path_str)
            if path.exists():
                self.log(f"Cleaning: {path}")
                shutil.rmtree(path, ignore_errors=True)

    def safe_copy(self, src: Path, dst: Path) -> bool:
        """Safe copy with symlink resolution"""
        try:
            if dst.exists():
                shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(src, dst, symlinks=False, dirs_exist_ok=True)
            return True
        except Exception as e:
            self.log(f"Copy failed: {e}", "ERROR")
            return False


# Legacy compatibility
class SymlinkManager(FrameworkManager):
    """Legacy compatibility wrapper"""

    def fix_pyinstaller_conflicts(self) -> bool:
        """Legacy method name"""
        return self.fix_prebuild_frameworks()

    def fix_frameworks_in_dist(self, dist_path: str = "dist") -> bool:
        """Legacy method name"""
        return self.fix_postbuild_frameworks(dist_path)

    def cleanup_build_artifacts(self, build_paths: List[Path]) -> None:
        """Legacy method signature"""
        paths = [str(p) for p in build_paths]
        self.clean_build_artifacts(paths)

    def safe_copytree(self, src: Path, dst: Path, component: str = "UNKNOWN") -> bool:
        """Legacy method name"""
        return self.safe_copy(src, dst)

    def get_stats(self) -> dict:
        """Legacy method"""
        return {"platform": "macOS" if self.is_macos else "Other"}


# Global instance for backward compatibility
symlink_manager = SymlinkManager(verbose=True)
