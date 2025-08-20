#!/usr/bin/env python3
"""
Simplified Build Optimizer
Basic change detection without complex caching
"""

import time
from pathlib import Path
from typing import Dict, List


class SimpleBuildOptimizer:
    """Simplified build optimizer with basic change detection"""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.cache_dir = Path(".build_cache")
        self.cache_dir.mkdir(exist_ok=True)
        self.timestamps_file = self.cache_dir / "timestamps.txt"
        self.last_build_times = self._load_timestamps()

    def _load_timestamps(self) -> Dict[str, float]:
        """Load last build timestamps"""
        if not self.timestamps_file.exists():
            return {}

        try:
            timestamps = {}
            with open(self.timestamps_file, 'r') as f:
                for line in f:
                    if '=' in line:
                        key, value = line.strip().split('=', 1)
                        timestamps[key] = float(value)
            return timestamps
        except Exception:
            return {}

    def _save_timestamps(self):
        """Save build timestamps"""
        try:
            with open(self.timestamps_file, 'w') as f:
                for key, timestamp in self.last_build_times.items():
                    f.write(f"{key}={timestamp}\n")
        except Exception:
            pass

    def log(self, message: str, level: str = "INFO"):
        """Log message if verbose mode is enabled"""
        if self.verbose:
            print(f"[OPTIMIZER-{level}] {message}")

    def _get_newest_file_time(self, paths: List[Path]) -> float:
        """Get the newest modification time from a list of paths"""
        newest_time = 0.0

        for path in paths:
            if not path.exists():
                continue

            if path.is_file():
                try:
                    mtime = path.stat().st_mtime
                    newest_time = max(newest_time, mtime)
                    self.log(f"Checked file: {path} ({mtime})", "DEBUG")
                except OSError:
                    continue
            elif path.is_dir():
                # Check key file types in directory
                patterns = ["*.py", "*.js", "*.ts", "*.vue", "*.json", "*.txt"]
                file_count = 0
                max_files = 500  # Increased limit for better detection

                for pattern in patterns:
                    for file_path in path.rglob(pattern):
                        if file_count >= max_files:
                            break
                        try:
                            mtime = file_path.stat().st_mtime
                            if mtime > newest_time:
                                newest_time = mtime
                                self.log(f"Newer file found: {file_path} ({mtime})", "DEBUG")
                            file_count += 1
                        except OSError:
                            continue
                    if file_count >= max_files:
                        self.log(f"Hit file limit ({max_files}) for {path}", "DEBUG")
                        break

        return newest_time

    def should_skip_build(self, force: bool = False, build_mode: str = "fast") -> bool:
        """Check if entire build can be skipped"""
        if force:
            self.log("Force rebuild requested")
            return False

        # Dev and prod modes should always rebuild for consistency
        if build_mode in ["dev", "prod"]:
            self.log(f"{build_mode.upper()} mode: forcing full rebuild")
            return False

        # Check if dist directory exists
        dist_dir = Path("dist")
        if not dist_dir.exists():
            self.log("Dist directory missing, rebuild needed")
            return False

        # Comprehensive check: include more critical paths
        core_paths = [
            Path("main.py"),
            Path("bot"),
            Path("gui"),
            Path("gui_v2"),  # Frontend
            Path("utils"),
            Path("common"),
            Path("build_system"),  # All build system files
            Path("requirements.txt"),  # Dependencies
            Path("package.json"),  # Frontend dependencies
        ]

        last_build = self.last_build_times.get("full_build", 0)
        newest_file = self._get_newest_file_time(core_paths)

        if newest_file > last_build:
            self.log("Source files changed, rebuild needed")
            return False

        # Check if main executable exists
        main_exe_paths = [
            dist_dir / "eCan" / "eCan.exe",  # Windows
            dist_dir / "eCan" / "eCan",      # Linux
            dist_dir / "eCan.app",           # macOS
        ]

        if not any(p.exists() for p in main_exe_paths):
            self.log("Main executable missing, rebuild needed")
            return False

        self.log("No changes detected, build can be skipped")
        return True

    def should_rebuild_frontend(self, force: bool = False, build_mode: str = "fast") -> bool:
        """Check if frontend should be rebuilt"""
        if force or build_mode in ["dev", "prod"]:
            return True

        frontend_dir = Path("gui_v2")
        if not frontend_dir.exists():
            return False

        last_build = self.last_build_times.get("frontend", 0)
        newest_file = self._get_newest_file_time([frontend_dir])

        return newest_file > last_build

    def should_rebuild_core(self, force: bool = False, build_mode: str = "fast") -> bool:
        """Check if core application should be rebuilt"""
        if force or build_mode in ["dev", "prod"]:
            return True

        core_paths = [
            Path("main.py"),
            Path("bot"),
            Path("gui"),
            Path("utils"),
            Path("common"),
            Path("build_system/build_config.json")
        ]

        last_build = self.last_build_times.get("core", 0)
        newest_file = self._get_newest_file_time(core_paths)

        return newest_file > last_build

    def mark_frontend_built(self):
        """Mark frontend as built"""
        self.last_build_times["frontend"] = time.time()
        self._save_timestamps()

    def mark_core_built(self):
        """Mark core application as built"""
        current_time = time.time()
        self.last_build_times["core"] = current_time
        self.last_build_times["full_build"] = current_time  # Also mark full build
        self._save_timestamps()
        self.log(f"Marked core build complete at {current_time}")

    def mark_full_build_complete(self):
        """Mark full build as complete (including installer)"""
        current_time = time.time()
        self.last_build_times["full_build"] = current_time
        self._save_timestamps()
        self.log(f"Marked full build complete at {current_time}")

    def get_cache_stats(self) -> Dict[str, any]:
        """Get simple cache statistics"""
        cache_size = 0
        file_count = 0

        if self.cache_dir.exists():
            for file_path in self.cache_dir.rglob("*"):
                if file_path.is_file():
                    try:
                        cache_size += file_path.stat().st_size
                        file_count += 1
                    except OSError:
                        pass

        return {
            "cache_dir": str(self.cache_dir),
            "cache_size_mb": cache_size / (1024 * 1024),
            "file_count": file_count,
            "components_cached": len(self.last_build_times)
        }

    def clear_cache(self):
        """Clear cache data"""
        import shutil

        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir, ignore_errors=True)

        self.cache_dir.mkdir(exist_ok=True)
        self.last_build_times = {}
        self.log("Cache cleared")


# Global optimizer instance
build_optimizer = SimpleBuildOptimizer()

def set_optimizer_verbose(verbose: bool):
    """Set verbose mode for the global optimizer"""
    global build_optimizer
    build_optimizer.verbose = verbose