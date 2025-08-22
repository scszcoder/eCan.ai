#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build Environment Cleaner
Provides comprehensive cleaning utilities for the build system
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
import time


class BuildCleaner:
    """Comprehensive build environment cleaner"""
    
    def __init__(self, project_root: Optional[Path] = None, verbose: bool = False):
        self.project_root = project_root or Path.cwd()
        self.verbose = verbose
        self.cleaned_items = {
            "broken_symlinks": 0,
            "build_artifacts": 0,
            "cache_dirs": 0,
            "temp_files": 0,
            "total_size_mb": 0.0
        }
    
    def log(self, message: str, level: str = "INFO") -> None:
        """Log message if verbose mode is enabled"""
        if self.verbose:
            timestamp = time.strftime("%H:%M:%S")
            print(f"[{timestamp}] [CLEANER] [{level}] {message}")
    
    def clean_all(self) -> Dict[str, Any]:
        """Perform comprehensive cleaning of build environment"""
        self.log("Starting comprehensive build environment cleanup")
        start_time = time.time()
        
        # Step 1: Clean broken symlinks
        self.clean_broken_symlinks()
        
        # Step 2: Clean build artifacts
        self.clean_build_artifacts()
        
        # Step 3: Clean Python cache
        self.clean_python_cache()
        
        # Step 4: Clean temporary files
        self.clean_temp_files()
        
        # Step 5: Clean PyInstaller cache
        self.clean_pyinstaller_cache()



        end_time = time.time()
        self.cleaned_items["cleanup_time"] = round(end_time - start_time, 2)
        
        self.log(f"Cleanup completed in {self.cleaned_items['cleanup_time']}s")
        self.log(f"Summary: {self.get_cleanup_summary()}")
        
        return self.cleaned_items
    
    def clean_broken_symlinks(self) -> int:
        """Remove all broken symlinks in the project"""
        self.log("Cleaning broken symlinks...")
        count = 0
        
        try:
            # Find and remove broken symlinks
            result = subprocess.run([
                "find", str(self.project_root), 
                "-type", "l", 
                "!", "-exec", "test", "-e", "{}", ";", 
                "-delete"
            ], capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                # Count broken symlinks before deletion
                count_result = subprocess.run([
                    "find", str(self.project_root), 
                    "-type", "l", 
                    "!", "-exec", "test", "-e", "{}", ";", 
                    "-print"
                ], capture_output=True, text=True, timeout=60)
                
                if count_result.returncode == 0:
                    count = len([line for line in count_result.stdout.strip().split('\n') if line])
                
                self.log(f"Removed {count} broken symlinks")
            else:
                self.log(f"Failed to clean symlinks: {result.stderr}", "WARNING")
                
        except subprocess.TimeoutExpired:
            self.log("Symlink cleanup timed out", "WARNING")
        except Exception as e:
            self.log(f"Error cleaning symlinks: {e}", "ERROR")
        
        self.cleaned_items["broken_symlinks"] = count
        return count
    
    def clean_build_artifacts(self) -> int:
        """Clean build artifacts (dist, build directories)"""
        self.log("Cleaning build artifacts...")
        count = 0
        size_mb = 0.0
        
        build_dirs = ["dist", "build"]
        
        for dir_name in build_dirs:
            dir_path = self.project_root / dir_name
            if dir_path.exists():
                try:
                    # Calculate size before deletion
                    if self.verbose:
                        size_bytes = sum(f.stat().st_size for f in dir_path.rglob('*') if f.is_file())
                        size_mb += size_bytes / (1024 * 1024)
                    
                    # Force remove with proper permissions
                    self._force_remove_directory(dir_path)
                    count += 1
                    self.log(f"Removed {dir_name}/ directory")
                    
                except Exception as e:
                    self.log(f"Failed to remove {dir_name}/: {e}", "WARNING")
        
        self.cleaned_items["build_artifacts"] = count
        self.cleaned_items["total_size_mb"] += size_mb
        return count
    
    def clean_python_cache(self) -> int:
        """Clean Python __pycache__ directories"""
        self.log("Cleaning Python cache directories...")
        count = 0
        
        try:
            # Find all __pycache__ directories
            cache_dirs = list(self.project_root.rglob("__pycache__"))
            
            for cache_dir in cache_dirs:
                try:
                    shutil.rmtree(cache_dir, ignore_errors=True)
                    count += 1
                    if self.verbose:
                        self.log(f"Removed {cache_dir}")
                except Exception as e:
                    self.log(f"Failed to remove {cache_dir}: {e}", "WARNING")
            
            self.log(f"Removed {count} __pycache__ directories")
            
        except Exception as e:
            self.log(f"Error cleaning Python cache: {e}", "ERROR")
        
        self.cleaned_items["cache_dirs"] = count
        return count
    
    def clean_temp_files(self) -> int:
        """Clean temporary files and directories"""
        self.log("Cleaning temporary files...")
        count = 0
        
        # Patterns for temporary files
        temp_patterns = [
            "*.tmp",
            "*.temp",
            "*.log",
            "*.spec",  # PyInstaller spec files
            ".DS_Store",  # macOS
            "Thumbs.db",  # Windows
            "*.pyc",
            "*.pyo"
        ]

        # Temporary directories
        temp_dirs = [
            "tmp",
            "temp",
            ".pytest_cache",
            ".coverage",
            "htmlcov"
        ]
        
        # Clean temporary files
        for pattern in temp_patterns:
            try:
                files = list(self.project_root.rglob(pattern))
                for file_path in files:
                    if file_path.is_file():
                        try:
                            file_path.unlink()
                            count += 1
                            if self.verbose:
                                self.log(f"Removed {file_path}")
                        except Exception as e:
                            self.log(f"Failed to remove {file_path}: {e}", "WARNING")
            except Exception as e:
                self.log(f"Error cleaning pattern {pattern}: {e}", "WARNING")
        
        # Clean temporary directories
        for dir_name in temp_dirs:
            dir_path = self.project_root / dir_name
            if dir_path.exists() and dir_path.is_dir():
                try:
                    shutil.rmtree(dir_path, ignore_errors=True)
                    count += 1
                    self.log(f"Removed {dir_name}/ directory")
                except Exception as e:
                    self.log(f"Failed to remove {dir_name}/: {e}", "WARNING")



        self.cleaned_items["temp_files"] = count
        return count
    
    def clean_pyinstaller_cache(self) -> bool:
        """Clean PyInstaller cache"""
        self.log("Cleaning PyInstaller cache...")
        
        try:
            # PyInstaller cache locations
            cache_locations = [
                Path.home() / "Library" / "Application Support" / "pyinstaller",  # macOS
                Path.home() / ".cache" / "pyinstaller",  # Linux
                Path.home() / "AppData" / "Local" / "pyinstaller",  # Windows
            ]
            
            for cache_path in cache_locations:
                if cache_path.exists():
                    try:
                        shutil.rmtree(cache_path, ignore_errors=True)
                        self.log(f"Cleaned PyInstaller cache: {cache_path}")
                        return True
                    except Exception as e:
                        self.log(f"Failed to clean PyInstaller cache {cache_path}: {e}", "WARNING")
            
            return True
            
        except Exception as e:
            self.log(f"Error cleaning PyInstaller cache: {e}", "ERROR")
            return False



    def _force_remove_directory(self, dir_path: Path) -> None:
        """Force remove directory with permission fixes"""
        try:
            # First try normal removal
            shutil.rmtree(dir_path, ignore_errors=True)
            
            # If directory still exists, try with permission fixes
            if dir_path.exists():
                # Fix permissions recursively
                for root, dirs, files in os.walk(dir_path):
                    for d in dirs:
                        os.chmod(os.path.join(root, d), 0o755)
                    for f in files:
                        os.chmod(os.path.join(root, f), 0o644)
                
                # Try removal again
                shutil.rmtree(dir_path, ignore_errors=True)
                
                # Last resort: use system command
                if dir_path.exists():
                    subprocess.run(["rm", "-rf", str(dir_path)], 
                                 capture_output=True, timeout=30)
                    
        except Exception as e:
            self.log(f"Force removal failed for {dir_path}: {e}", "WARNING")
    
    def get_cleanup_summary(self) -> str:
        """Get a summary of cleanup results"""
        return (f"Symlinks: {self.cleaned_items['broken_symlinks']}, "
                f"Build artifacts: {self.cleaned_items['build_artifacts']}, "
                f"Cache dirs: {self.cleaned_items['cache_dirs']}, "
                f"Temp files: {self.cleaned_items['temp_files']}, "
                f"Size freed: {self.cleaned_items['total_size_mb']:.1f}MB")


def main():
    """Command line interface for build cleaner"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Clean build environment")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Enable verbose output")
    parser.add_argument("--project-root", type=Path,
                       help="Project root directory (default: current directory)")

    args = parser.parse_args()

    cleaner = BuildCleaner(project_root=args.project_root, verbose=args.verbose)
    results = cleaner.clean_all()
    
    print(f"\nCleanup completed successfully!")
    print(f"Summary: {cleaner.get_cleanup_summary()}")
    print(f"Time taken: {results['cleanup_time']}s")


if __name__ == "__main__":
    main()
