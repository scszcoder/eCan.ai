#!/usr/bin/env python3
"""
Optimized Symlink Manager
Simplified and optimized version for handling macOS framework symlinks
"""

import os
import shutil
import platform
from pathlib import Path
from typing import Set, List
import tempfile


class SymlinkManager:
    """Simplified and optimized symlink manager for macOS builds"""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.is_macos = platform.system() == "Darwin"
        self.processed_frameworks: Set[str] = set()

    def log(self, message: str, level: str = "INFO") -> None:
        """Log message if verbose mode is enabled"""
        if self.verbose:
            print(f"[SYMLINK-{level}] {message}")

    def cleanup_build_artifacts(self, build_paths: List[Path]) -> None:
        """Clean up build artifacts with simple removal"""
        for path in build_paths:
            if path.exists():
                self.log(f"Cleaning: {path}")
                shutil.rmtree(path, ignore_errors=True)

    def fix_pyinstaller_conflicts(self) -> bool:
        """Main entry point: fix macOS framework symlinks"""
        if not self.is_macos:
            return True

        self.log("Starting framework symlink fixes...")

        try:
            # Step 1: Clean build directories
            self._clean_build_dirs()
            
            # Step 2: Fix framework symlinks
            self._fix_framework_symlinks()
            
            self.log("Framework symlink fixes completed")
            return True

        except Exception as e:
            self.log(f"Framework fix failed: {e}", "ERROR")
            return False

    def _clean_build_dirs(self) -> None:
        """Clean build directories and caches"""
        dirs_to_clean = [
            Path("dist"),
            Path("build"),
            Path(tempfile.gettempdir()) / "pyinstaller",
            Path.home() / "Library" / "Application Support" / "pyinstaller"
        ]

        for dir_path in dirs_to_clean:
            if dir_path.exists():
                self.log(f"Cleaning: {dir_path}")
                shutil.rmtree(dir_path, ignore_errors=True)

    def _fix_framework_symlinks(self) -> None:
        """Find and fix framework symlinks in common locations"""
        search_paths = [
            Path("venv") / "lib",  # Virtual environment frameworks
            Path(".") / "third_party",  # Third-party frameworks
            Path("ota") / "dependencies",  # OTA dependencies (Sparkle)
            Path("dependencies")  # General dependencies
        ]

        for search_path in search_paths:
            if search_path.exists():
                self._process_frameworks_in_path(search_path)
        
        # Special handling for Sparkle frameworks
        self._fix_sparkle_frameworks()

    def _process_frameworks_in_path(self, search_path: Path) -> None:
        """Process all frameworks in a given path"""
        try:
            # Find .framework directories
            for framework_path in search_path.rglob("*.framework"):
                if framework_path.is_dir():
                    framework_key = str(framework_path.resolve())
                    
                    # Skip if already processed
                    if framework_key in self.processed_frameworks:
                        continue
                        
                    self._fix_framework(framework_path)
                    self.processed_frameworks.add(framework_key)

        except Exception as e:
            self.log(f"Error processing path {search_path}: {e}", "WARNING")

    def _fix_framework(self, framework_path: Path) -> bool:
        """Fix symlinks in a single framework"""
        try:
            symlinks = []
            
            # Find all symlinks in framework
            for item in framework_path.rglob("*"):
                if item.is_symlink():
                    symlinks.append(item)

            if not symlinks:
                return True

            self.log(f"Fixing {len(symlinks)} symlinks in {framework_path.name}")

            # Fix each symlink
            fixed_count = 0
            for symlink in symlinks:
                if self._resolve_symlink(symlink):
                    fixed_count += 1

            self.log(f"Fixed {fixed_count}/{len(symlinks)} symlinks in {framework_path.name}")
            return fixed_count > 0

        except Exception as e:
            self.log(f"Failed to fix framework {framework_path}: {e}", "WARNING")
            return False

    def _resolve_symlink(self, symlink_path: Path) -> bool:
        """Resolve a single symlink by replacing it with actual content"""
        try:
            # Get target before removing symlink
            try:
                target = symlink_path.readlink()
                if not target.is_absolute():
                    target = (symlink_path.parent / target).resolve()
            except Exception:
                target = None

            # Remove the symlink
            symlink_path.unlink()

            # Replace with actual content if target exists
            if target and target.exists():
                if target.is_dir():
                    shutil.copytree(target, symlink_path, symlinks=False, dirs_exist_ok=True)
                elif target.is_file():
                    shutil.copy2(target, symlink_path)
                return True
            else:
                # Create empty directory as fallback
                symlink_path.mkdir(exist_ok=True)
                return True

        except Exception as e:
            self.log(f"Failed to resolve symlink {symlink_path}: {e}", "WARNING")
            return False

    def _fix_sparkle_frameworks(self) -> None:
        """Special handling for Sparkle.framework symlink issues"""
        sparkle_paths = [
            Path("ota") / "dependencies" / "Sparkle.framework",
            Path("third_party") / "Sparkle.framework", 
            Path("dependencies") / "Sparkle.framework"
        ]
        
        for sparkle_path in sparkle_paths:
            if sparkle_path.exists():
                self.log(f"Found Sparkle framework: {sparkle_path}")
                self._fix_sparkle_framework(sparkle_path)

    def _fix_sparkle_framework(self, framework_path: Path) -> bool:
        """Fix Sparkle.framework specific symlink issues"""
        try:
            self.log(f"Fixing Sparkle framework: {framework_path.name}")
            
            # Check for problematic root-level symlinks
            problematic_symlinks = ["Resources", "Frameworks", "Headers", "Modules", "Sparkle"]
            
            for symlink_name in problematic_symlinks:
                symlink_path = framework_path / symlink_name
                if symlink_path.is_symlink():
                    self.log(f"Fixing Sparkle symlink: {symlink_name}")
                    
                    # Get target before removing
                    try:
                        target = symlink_path.readlink()
                        if not target.is_absolute():
                            target = (symlink_path.parent / target).resolve()
                    except Exception:
                        target = None
                    
                    # Remove symlink
                    symlink_path.unlink()
                    
                    # Replace with actual content
                    if target and target.exists():
                        if target.is_dir():
                            shutil.copytree(target, symlink_path, symlinks=False, dirs_exist_ok=True)
                        else:
                            shutil.copy2(target, symlink_path)
                    else:
                        # Create empty directory for missing targets
                        if symlink_name in ["Resources", "Frameworks", "Headers", "Modules"]:
                            symlink_path.mkdir()
            
            # Remove Versions directory to prevent further conflicts
            versions_dir = framework_path / "Versions"
            if versions_dir.exists():
                self.log("Removing Sparkle Versions directory")
                shutil.rmtree(versions_dir, ignore_errors=True)
            
            return True
            
        except Exception as e:
            self.log(f"Failed to fix Sparkle framework {framework_path}: {e}", "ERROR")
            return False

    def get_stats(self) -> dict:
        """Get processing statistics"""
        return {
            "frameworks_processed": len(self.processed_frameworks),
            "is_macos": self.is_macos
        }

    # Legacy compatibility methods
    def safe_copytree(self, src: Path, dst: Path, component: str = "UNKNOWN") -> bool:
        """Legacy compatibility method for safe copying"""
        try:
            if dst.exists():
                shutil.rmtree(dst, ignore_errors=True)
            
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, dst, symlinks=False, dirs_exist_ok=True)
            return True
        except Exception as e:
            self.log(f"Copy failed: {src} -> {dst}: {e}", "ERROR")
            return False

    def get_copy_summary(self) -> dict:
        """Legacy compatibility method"""
        return {"total_copies": len(self.processed_frameworks)}


# Global instance for backward compatibility
symlink_manager = SymlinkManager(verbose=False)


def set_verbose(verbose: bool) -> None:
    """Set verbose mode for the global symlink manager"""
    global symlink_manager
    symlink_manager.verbose = verbose