#!/usr/bin/env python3
"""
Build Optimizer
Provides caching, change detection, and performance optimizations for the build system
"""

import os
import json
import hashlib
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Any
import shutil


class BuildCache:
    """Build cache management for faster incremental builds"""
    
    def __init__(self, cache_dir: Path = None):
        self.cache_dir = cache_dir or Path(".build_cache")
        self.cache_dir.mkdir(exist_ok=True)
        self.hashes_file = self.cache_dir / "file_hashes.json"
        self.build_info_file = self.cache_dir / "build_info.json"
        self.hashes = self._load_hashes()
        self.build_info = self._load_build_info()
    
    def _load_hashes(self) -> Dict[str, str]:
        """Load cached file hashes"""
        if self.hashes_file.exists():
            try:
                with open(self.hashes_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}
    
    def _save_hashes(self):
        """Save file hashes to cache"""
        with open(self.hashes_file, 'w', encoding='utf-8') as f:
            json.dump(self.hashes, f, indent=2)
    
    def _load_build_info(self) -> Dict[str, Any]:
        """Load build information"""
        if self.build_info_file.exists():
            try:
                with open(self.build_info_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}
    
    def _save_build_info(self):
        """Save build information"""
        with open(self.build_info_file, 'w', encoding='utf-8') as f:
            json.dump(self.build_info, f, indent=2)
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate hash based on file metadata for performance"""
        if not file_path.exists() or not file_path.is_file():
            return ""

        try:
            stat = file_path.stat()
            # Use file size and modification time for faster hashing
            hash_input = f"{stat.st_size}:{stat.st_mtime}:{file_path.name}"
            return hashlib.sha256(hash_input.encode('utf-8')).hexdigest()
        except Exception:
            return ""
    
    def _calculate_directory_hash(self, dir_path: Path, patterns: List[str] = None) -> str:
        """Calculate hash of directory contents"""
        if not dir_path.exists() or not dir_path.is_dir():
            return ""

        patterns = patterns or ["*.py", "*.js", "*.ts", "*.vue", "*.json"]
        files = []

        # Limit the number of files to avoid performance issues
        max_files = 1000
        file_count = 0

        for pattern in patterns:
            for file_path in dir_path.rglob(pattern):
                if file_count >= max_files:
                    break
                files.append(file_path)
                file_count += 1
            if file_count >= max_files:
                break

        # Sort files for consistent hashing
        files.sort()

        hash_sha256 = hashlib.sha256()
        for file_path in files:
            if file_path.is_file():
                try:
                    # Include relative path and file modification time for faster hashing
                    rel_path = file_path.relative_to(dir_path)
                    hash_sha256.update(str(rel_path).encode('utf-8'))

                    # Use file size and modification time instead of full content hash for speed
                    stat = file_path.stat()
                    hash_sha256.update(str(stat.st_size).encode('utf-8'))
                    hash_sha256.update(str(stat.st_mtime).encode('utf-8'))
                except (OSError, ValueError):
                    # Skip files that can't be accessed
                    continue

        return hash_sha256.hexdigest()
    
    def has_changed(self, path: Path, patterns: List[str] = None) -> bool:
        """Check if file or directory has changed since last build"""
        path_str = str(path)
        
        if path.is_file():
            current_hash = self._calculate_file_hash(path)
        elif path.is_dir():
            current_hash = self._calculate_directory_hash(path, patterns)
        else:
            return True  # Path doesn't exist, consider it changed
        
        cached_hash = self.hashes.get(path_str, "")
        return current_hash != cached_hash
    
    def update_hash(self, path: Path, patterns: List[str] = None):
        """Update hash for file or directory"""
        path_str = str(path)
        
        if path.is_file():
            current_hash = self._calculate_file_hash(path)
        elif path.is_dir():
            current_hash = self._calculate_directory_hash(path, patterns)
        else:
            return
        
        self.hashes[path_str] = current_hash
        self._save_hashes()
    
    def should_rebuild_component(self, component: str, dependencies: List[Path]) -> bool:
        """Check if a component should be rebuilt based on its dependencies"""
        for dep in dependencies:
            if self.has_changed(dep):
                return True
        return False
    
    def mark_component_built(self, component: str, dependencies: List[Path]):
        """Mark component as built and update dependency hashes"""
        for dep in dependencies:
            self.update_hash(dep)
        
        self.build_info[component] = {
            "last_build": time.time(),
            "dependencies": [str(dep) for dep in dependencies]
        }
        self._save_build_info()
    
    def get_cached_result(self, component: str) -> Optional[Path]:
        """Get cached build result if available"""
        cache_path = self.cache_dir / component
        if cache_path.exists():
            return cache_path
        return None
    
    def cache_result(self, component: str, source_path: Path):
        """Cache build result"""
        cache_path = self.cache_dir / component
        if source_path.exists():
            if source_path.is_dir():
                if cache_path.exists():
                    shutil.rmtree(cache_path)
                shutil.copytree(source_path, cache_path)
            else:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, cache_path)


class ChangeDetector:
    """Detect changes in source files and dependencies"""
    
    def __init__(self, cache: BuildCache):
        self.cache = cache
        self.key_patterns = {
            "python": ["*.py"],
            "frontend": ["*.js", "*.ts", "*.vue", "*.json", "*.css", "*.scss"],
            "config": ["*.json", "*.yaml", "*.yml", "*.toml"],
            "requirements": ["requirements*.txt", "package*.json", "yarn.lock"]
        }
    
    def check_python_changes(self) -> bool:
        """Check if Python source files have changed"""
        python_dirs = [Path("agent"), Path("bot"), Path("gui"), Path("utils"), Path("common")]
        python_files = [Path("main.py")]
        
        for directory in python_dirs:
            if directory.exists() and self.cache.has_changed(directory, self.key_patterns["python"]):
                return True
        
        for file_path in python_files:
            if file_path.exists() and self.cache.has_changed(file_path):
                return True
        
        return False
    
    def check_frontend_changes(self) -> bool:
        """Check if frontend files have changed"""
        frontend_dir = Path("gui_v2")
        if not frontend_dir.exists():
            return False
        
        return self.cache.has_changed(frontend_dir, self.key_patterns["frontend"])
    
    def check_config_changes(self) -> bool:
        """Check if configuration files have changed"""
        config_files = [
            Path("build_system/build_config.json"),
            Path("build_system/third_party_config.json")
        ]
        
        for file_path in config_files:
            if file_path.exists() and self.cache.has_changed(file_path):
                return True
        
        return False
    
    def check_requirements_changes(self) -> bool:
        """Check if dependency files have changed"""
        req_files = list(Path(".").glob("requirements*.txt"))
        req_files.extend(Path(".").glob("package*.json"))
        
        for file_path in req_files:
            if self.cache.has_changed(file_path):
                return True
        
        return False


class BuildOptimizer:
    """Main build optimizer with caching and change detection"""
    
    def __init__(self, cache_dir: Path = None, verbose: bool = False):
        self.cache = BuildCache(cache_dir)
        self.detector = ChangeDetector(self.cache)
        self.verbose = verbose
    
    def log(self, message: str, level: str = "INFO"):
        """Log message if verbose mode is enabled"""
        if self.verbose:
            print(f"[OPTIMIZER-{level}] {message}")
    
    def should_skip_build(self, force: bool = False, build_mode: str = "fast") -> bool:
        """Check if entire build can be skipped"""
        if force:
            return False

        # Dev and prod modes should always rebuild for consistency
        if build_mode in ["dev", "prod"]:
            self.log(f"{build_mode.upper()} mode: forcing full rebuild for consistency")
            return False

        # Check if any source files have changed
        changes = {
            "python": self.detector.check_python_changes(),
            "frontend": self.detector.check_frontend_changes(),
            "config": self.detector.check_config_changes(),
            "requirements": self.detector.check_requirements_changes()
        }

        has_changes = any(changes.values())

        if self.verbose:
            for component, changed in changes.items():
                status = "CHANGED" if changed else "UNCHANGED"
                self.log(f"{component}: {status}")

        if not has_changes:
            self.log("No changes detected, build can be skipped")
            return True

        return False
    
    def should_rebuild_frontend(self, force: bool = False, build_mode: str = "fast") -> bool:
        """Check if frontend should be rebuilt"""
        if force:
            return True

        # Dev and prod modes should always rebuild frontend
        if build_mode in ["dev", "prod"]:
            return True

        return self.detector.check_frontend_changes()

    def should_rebuild_core(self, force: bool = False, build_mode: str = "fast") -> bool:
        """Check if core application should be rebuilt"""
        if force:
            return True

        # Dev and prod modes should always rebuild core
        if build_mode in ["dev", "prod"]:
            return True

        return (self.detector.check_python_changes() or
                self.detector.check_config_changes() or
                self.detector.check_requirements_changes())
    
    def mark_frontend_built(self):
        """Mark frontend as built"""
        frontend_dir = Path("gui_v2")
        if frontend_dir.exists():
            self.cache.mark_component_built("frontend", [frontend_dir])
    
    def mark_core_built(self):
        """Mark core application as built"""
        dependencies = [
            Path("main.py"),
            Path("agent"),
            Path("bot"), 
            Path("gui"),
            Path("utils"),
            Path("common"),
            Path("build_system/build_config.json")
        ]
        
        existing_deps = [dep for dep in dependencies if dep.exists()]
        self.cache.mark_component_built("core", existing_deps)
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        cache_size = 0
        file_count = 0
        
        if self.cache.cache_dir.exists():
            for file_path in self.cache.cache_dir.rglob("*"):
                if file_path.is_file():
                    cache_size += file_path.stat().st_size
                    file_count += 1
        
        return {
            "cache_dir": str(self.cache.cache_dir),
            "cache_size_mb": cache_size / (1024 * 1024),
            "file_count": file_count,
            "components_cached": len(self.cache.build_info)
        }
    
    def clear_cache(self):
        """Clear all cached data"""
        if self.cache.cache_dir.exists():
            shutil.rmtree(self.cache.cache_dir)
        self.cache.cache_dir.mkdir(exist_ok=True)
        self.cache.hashes = {}
        self.cache.build_info = {}
        self.log("Cache cleared")


# Global optimizer instance
build_optimizer = BuildOptimizer()

def set_optimizer_verbose(verbose: bool):
    """Set verbose mode for the global optimizer"""
    global build_optimizer
    build_optimizer.verbose = verbose
