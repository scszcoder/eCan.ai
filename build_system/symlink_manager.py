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
    """Unified manager for symlink handling across all build components"""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.is_macos = platform.system() == "Darwin"
        self.copied_paths: Set[str] = set()  # Track copied paths to avoid duplicates
        self.symlink_registry: Dict[str, str] = {}  # Track symlinks for conflict resolution
        
    def log(self, message: str, level: str = "INFO") -> None:
        """Log message if verbose mode is enabled"""
        if self.verbose:
            print(f"[SYMLINK-{level}] {message}")
    
    def safe_copytree(self, src: Path, dst: Path, component: str = "UNKNOWN") -> bool:
        """
        Safe copy tree that handles symlinks properly on macOS
        Returns True if successful, False otherwise
        """
        src_str = str(src.resolve())
        dst_str = str(dst.resolve())
        
        # Check for duplicate copies
        if src_str in self.copied_paths:
            self.log(f"Skipping duplicate copy: {src} (already copied)", "SKIP")
            return True
        
        self.log(f"Starting safe copy: {src} -> {dst} ({component})")
        
        try:
            # Remove destination if it exists
            if dst.exists():
                self.log(f"Removing existing destination: {dst}")
                if self.is_macos:
                    self._safe_remove_macos(dst)
                else:
                    shutil.rmtree(dst, ignore_errors=True)
            
            # Create parent directories
            dst.parent.mkdir(parents=True, exist_ok=True)
            
            if self.is_macos:
                # macOS-specific copy with symlink handling
                success = self._copy_macos_safe(src, dst, component)
            else:
                # Standard copy for other platforms
                shutil.copytree(src, dst, symlinks=False)  # Resolve symlinks
                success = True
            
            if success:
                self.copied_paths.add(src_str)
                self.log(f"Successfully copied: {src} -> {dst}")
            
            return success
            
        except Exception as e:
            self.log(f"Copy failed: {src} -> {dst}: {e}", "ERROR")
            return False
    
    def _safe_remove_macos(self, path: Path) -> None:
        """Safely remove directory on macOS with symlink handling"""
        if not path.exists():
            return
        
        try:
            # First pass: remove symlinks to avoid conflicts
            for root, dirs, files in os.walk(path, topdown=False):
                root_path = Path(root)
                
                # Handle symlinked files
                for file in files:
                    file_path = root_path / file
                    if file_path.is_symlink():
                        file_path.unlink()
                        self.log(f"Removed symlink file: {file_path}")
                
                # Handle symlinked directories
                for dir_name in dirs[:]:  # Copy list to avoid modification during iteration
                    dir_path = root_path / dir_name
                    if dir_path.is_symlink():
                        dir_path.unlink()
                        dirs.remove(dir_name)  # Don't traverse into removed symlink
                        self.log(f"Removed symlink directory: {dir_path}")
            
            # Second pass: remove the directory tree
            shutil.rmtree(path, ignore_errors=True)
            
        except Exception as e:
            self.log(f"Safe remove failed for {path}: {e}", "ERROR")
            # Fallback to standard removal
            shutil.rmtree(path, ignore_errors=True)
    
    def _copy_macos_safe(self, src: Path, dst: Path, component: str) -> bool:
        """macOS-specific safe copy with intelligent symlink handling"""
        try:
            if component.upper() in ["QTWEBENGINE", "WEBKIT"]:
                return self._copy_framework_safe(src, dst)
            elif component.upper() in ["PLAYWRIGHT", "CHROMIUM"]:
                return self._copy_chromium_safe(src, dst)
            else:
                # Generic safe copy
                return self._copy_generic_safe(src, dst)
                
        except Exception as e:
            self.log(f"macOS safe copy failed: {e}", "ERROR")
            return False
    
    def _copy_framework_safe(self, src: Path, dst: Path) -> bool:
        """Safe copy for macOS frameworks (QtWebEngine, etc.)"""
        self.log(f"Copying framework: {src.name}")
        
        # For frameworks, we need to be very careful with symlinks
        def ignore_problematic_symlinks(dir_path, names):
            ignored = []
            dir_path_obj = Path(dir_path)
            
            for name in names:
                item_path = dir_path_obj / name
                if item_path.is_symlink():
                    # Check if this is a problematic symlink
                    if any(problem in name.lower() for problem in ['current', 'helpers']):
                        # Instead of ignoring, we'll handle it specially
                        target = item_path.readlink()
                        if target.is_absolute() or '..' in str(target):
                            ignored.append(name)
                            self.log(f"Ignoring problematic symlink: {item_path} -> {target}")
            
            return ignored
        
        shutil.copytree(src, dst, ignore=ignore_problematic_symlinks, symlinks=False)
        
        # Post-process: create safe symlinks where needed
        self._create_safe_framework_symlinks(dst)
        
        return True
    
    def _copy_chromium_safe(self, src: Path, dst: Path) -> bool:
        """Safe copy for Chromium/Playwright browsers"""
        self.log(f"Copying Chromium browser: {src.name}")
        
        # For Chromium, we want to preserve some symlinks but avoid conflicts
        def chromium_ignore_func(dir_path, names):
            ignored = []
            dir_path_obj = Path(dir_path)
            
            for name in names:
                item_path = dir_path_obj / name
                
                # Skip problematic symlinks in Chromium.app
                if item_path.is_symlink() and '.app' in str(dir_path_obj):
                    target = item_path.readlink()
                    # Skip symlinks that point outside the app bundle
                    if target.is_absolute() or str(target).startswith('../'):
                        ignored.append(name)
                        self.log(f"Ignoring external symlink: {item_path} -> {target}")
                
                # Skip cache and temp directories
                if name.lower() in ['cache', 'tmp', 'temp', 'logs']:
                    ignored.append(name)
            
            return ignored
        
        shutil.copytree(src, dst, ignore=chromium_ignore_func, symlinks=True)
        return True
    
    def _copy_generic_safe(self, src: Path, dst: Path) -> bool:
        """Generic safe copy for other components"""
        # For generic copies, resolve all symlinks to avoid conflicts
        shutil.copytree(src, dst, symlinks=False)
        return True
    
    def _create_safe_framework_symlinks(self, framework_path: Path) -> None:
        """Create safe symlinks for framework structure"""
        # This is where we would recreate essential symlinks that were skipped
        # For now, we'll just log what we're doing
        self.log(f"Post-processing framework symlinks: {framework_path}")
        
        # Example: Create Versions/Current symlink if needed
        versions_dir = framework_path / "Versions"
        if versions_dir.exists():
            current_link = versions_dir / "Current"
            if not current_link.exists():
                # Find the actual version directory
                version_dirs = [d for d in versions_dir.iterdir() if d.is_dir() and d.name != "Current"]
                if version_dirs:
                    try:
                        current_link.symlink_to(version_dirs[0].name)
                        self.log(f"Created safe Current symlink: {current_link}")
                    except Exception as e:
                        self.log(f"Failed to create Current symlink: {e}", "WARNING")
    
    def validate_symlinks(self, path: Path) -> Dict[str, List[str]]:
        """Validate symlinks in a directory and return report"""
        report = {
            "valid_symlinks": [],
            "broken_symlinks": [],
            "external_symlinks": [],
            "problematic_symlinks": []
        }
        
        if not path.exists():
            return report
        
        for root, dirs, files in os.walk(path):
            root_path = Path(root)
            
            # Check file symlinks
            for file in files:
                file_path = root_path / file
                if file_path.is_symlink():
                    self._categorize_symlink(file_path, report)
            
            # Check directory symlinks
            for dir_name in dirs:
                dir_path = root_path / dir_name
                if dir_path.is_symlink():
                    self._categorize_symlink(dir_path, report)
        
        return report
    
    def _categorize_symlink(self, symlink_path: Path, report: Dict[str, List[str]]) -> None:
        """Categorize a symlink into the appropriate report category"""
        try:
            target = symlink_path.readlink()
            symlink_str = str(symlink_path)
            
            if not symlink_path.exists():
                report["broken_symlinks"].append(symlink_str)
            elif target.is_absolute():
                report["external_symlinks"].append(symlink_str)
            elif any(problem in symlink_str.lower() for problem in ['current', 'helpers']):
                report["problematic_symlinks"].append(symlink_str)
            else:
                report["valid_symlinks"].append(symlink_str)
                
        except Exception as e:
            report["broken_symlinks"].append(f"{symlink_path} (error: {e})")
    
    def cleanup_build_artifacts(self, build_paths: List[Path]) -> None:
        """Clean up build artifacts with proper symlink handling"""
        for path in build_paths:
            if path.exists():
                self.log(f"Cleaning build artifacts: {path}")
                if self.is_macos:
                    self._safe_remove_macos(path)
                else:
                    shutil.rmtree(path, ignore_errors=True)
    
    def get_copy_summary(self) -> Dict[str, int]:
        """Get summary of copy operations"""
        return {
            "total_copies": len(self.copied_paths),
            "symlinks_tracked": len(self.symlink_registry)
        }

# Global instance
symlink_manager = SymlinkManager(verbose=False)

def set_verbose(verbose: bool) -> None:
    """Set verbose mode for the global symlink manager"""
    global symlink_manager
    symlink_manager.verbose = verbose
