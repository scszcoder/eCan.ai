#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright Core Tools Module
Provides basic utility functions for Playwright, including path handling, installation, validation, etc.
"""

import os
import sys
import shutil
import subprocess
import platform
import time
from pathlib import Path
from typing import Optional, List
from utils.logger_helper import logger_helper as logger

# Import simplified helper functions
try:
    from .helpers import friendly_error_message
except ImportError:
    # Backward compatibility, if new module is not available
    def friendly_error_message(exception, context=""):
        return str(exception)


class PlaywrightCoreUtils:
    """Playwright Core Tools class"""

    # Browser types
    BROWSER_TYPE = "chromium"

    # Environment variable names
    ENV_BROWSERS_PATH = "PLAYWRIGHT_BROWSERS_PATH"
    # Back-compat alias used by helper/installer code to indicate the base dir
    # for Playwright browser downloads. This should map to PLAYWRIGHT_BROWSERS_PATH.
    ENV_BASE_DIR = ENV_BROWSERS_PATH
    ENV_CACHE_DIR = "PLAYWRIGHT_CACHE_DIR"
    ENV_BROWSERS_PATH_OVERRIDE = "PLAYWRIGHT_BROWSERS_PATH_OVERRIDE"

    # Application name
    APP_NAME = "eCan"

    # Cache search results to avoid repeated expensive operations
    _cache_search_result = None
    _cache_search_timestamp = 0
    _cache_search_ttl = 300  # 5 minutes cache
    
    @staticmethod
    def get_default_browsers_path() -> Path:
        """Get default browser installation path"""
        if sys.platform == "darwin":  # macOS
            return Path.home() / ".cache" / "ms-playwright"
        elif sys.platform == "win32":  # Windows
            return Path.home() / "AppData" / "Local" / "ms-playwright"
        else:  # Linux
            return Path.home() / ".cache" / "ms-playwright"
    
    @staticmethod
    def get_app_data_path() -> Path:
        """Get application data directory"""
        if sys.platform == "darwin":  # macOS
            return Path.home() / "Library" / "Application Support" / PlaywrightCoreUtils.APP_NAME
        elif sys.platform == "win32":  # Windows
            return Path.home() / "AppData" / "Local" / PlaywrightCoreUtils.APP_NAME
        else:  # Linux
            return Path.home() / ".local" / "share" / PlaywrightCoreUtils.APP_NAME
    
    @staticmethod
    def get_bundled_path() -> Optional[Path]:
        """Get bundled browser path (if in PyInstaller environment)"""
        if getattr(sys, 'frozen', False):
            return Path(sys._MEIPASS) / "third_party" / "ms-playwright"
        return None
    
    @staticmethod
    def get_most_likely_cache_paths() -> List[Path]:
        """Get the most likely cache paths in order of probability"""
        paths = []

        if platform.system() == "Darwin":  # macOS
            paths.extend([
                Path.home() / ".cache" / "ms-playwright",
                Path.home() / "Library" / "Caches" / "ms-playwright",
            ])
        elif platform.system() == "Windows":
            paths.extend([
                Path.home() / "AppData" / "Local" / "ms-playwright",
                Path(os.getenv("LOCALAPPDATA", "")) / "ms-playwright",
            ])
        else:  # Linux
            paths.extend([
                Path.home() / ".cache" / "ms-playwright",
                Path.home() / ".local" / "share" / "ms-playwright",
            ])

        return [p for p in paths if p]  # Filter out None values

    @staticmethod
    def get_possible_cache_paths() -> List[Path]:
        """Get all possible cache paths"""
        possible_roots = []
        
        if platform.system() == "Windows":
            possible_roots.extend([
                Path(os.getenv("LOCALAPPDATA", "")) / "ms-playwright",
                Path.home() / "AppData" / "Local" / "ms-playwright",
                Path.home() / "AppData" / "Roaming" / "ms-playwright"
            ])
        elif platform.system() == "Darwin":  # macOS
            possible_roots.extend([
                Path.home() / ".cache" / "ms-playwright",
                Path.home() / "Library" / "Caches" / "ms-playwright",
                Path.home() / "Library" / "Application Support" / "ms-playwright"
            ])
        else:  # Linux and others
            possible_roots.extend([
                Path.home() / ".cache" / "ms-playwright",
                Path.home() / ".local" / "share" / "ms-playwright",
                Path.home() / ".ms-playwright"
            ])
        
        # Also check current working directory
        possible_roots.append(Path.cwd() / ".ms-playwright")
        
        return possible_roots
    
    @staticmethod
    def get_browser_version(path: Path) -> Optional[str]:
        """Get browser version from browsers.json or directory name"""
        try:
            # Try to read version from browsers.json
            browsers_json = path / "browsers.json"
            if browsers_json.exists():
                import json
                with open(browsers_json, 'r') as f:
                    data = json.load(f)
                    # browsers.json may contain version info
                    if isinstance(data, dict) and 'browsers' in data:
                        for browser in data.get('browsers', []):
                            if 'revision' in browser:
                                return browser['revision']
            
            # Fallback: extract version from chromium directory name
            chromium_dirs = list(path.glob("chromium-*"))
            if chromium_dirs:
                # Extract version number from directory name like "chromium-1181"
                dir_name = chromium_dirs[0].name
                version = dir_name.split('-')[-1] if '-' in dir_name else None
                return version
            
            return None
        except Exception as e:
            logger.debug(f"Failed to get browser version from {path}: {e}")
            return None
    
    @staticmethod
    def compare_browser_versions(src_path: Path, dst_path: Path) -> bool:
        """Compare browser versions, return True if source is newer or different
        
        Returns:
            True if source should replace destination (newer or different)
            False if destination is same or newer
        """
        src_version = PlaywrightCoreUtils.get_browser_version(src_path)
        dst_version = PlaywrightCoreUtils.get_browser_version(dst_path)
        
        # If can't determine versions, assume update needed
        if src_version is None:
            logger.debug(f"Cannot determine source version, assuming update needed")
            return True
        
        if dst_version is None:
            logger.debug(f"Cannot determine destination version, assuming update needed")
            return True
        
        # Compare versions
        if src_version != dst_version:
            logger.info(f"Browser version changed: {dst_version} -> {src_version}")
            return True
        
        logger.debug(f"Browser versions match: {src_version}")
        return False
    
    @staticmethod
    def validate_browser_installation(path: Path) -> bool:
        """Validate if browser installation is valid"""
        logger.debug(f"Starting installation validation: {path}")

        if not path or not path.exists():
            logger.debug(f"Installation validation failed: {path} - path does not exist")
            return False

        # Check key files - more practical validation method
        try:
            # Method 1: Check browsers.json file (recommended but not mandatory)
            browsers_json = path / "browsers.json"
            if browsers_json.exists():
                try:
                    import json
                    with open(browsers_json, 'r') as f:
                        browsers_data = json.load(f)
                    if isinstance(browsers_data, dict):
                        logger.debug(f"✅ Found valid browsers.json: {path}")
                        return True
                    else:
                        logger.debug(f"browsers.json format invalid, trying other validation methods")
                except Exception as e:
                    logger.debug(f"Failed to read browsers.json: {e}，trying other validation methods")
            else:
                logger.debug(f"browsers.json not found, using directory check method")

            # Method 2: Check browser directories
            chromium_dirs = list(path.glob("chromium*"))
            firefox_dirs = list(path.glob("firefox*"))
            webkit_dirs = list(path.glob("webkit*"))

            all_browser_dirs = chromium_dirs + firefox_dirs + webkit_dirs

            if not all_browser_dirs:
                # Check if there are other possible browser directories
                browser_dirs = [d for d in path.iterdir()
                              if d.is_dir() and not d.name.startswith('.') and
                              any(browser in d.name.lower() for browser in ['chrome', 'firefox', 'safari', 'edge'])]
                if not browser_dirs:
                    logger.debug(f"Installation validation failed: {path} - No browser directories found")
                    return False
                all_browser_dirs = browser_dirs

            logger.debug(f"Found browser directories: {[d.name for d in all_browser_dirs]}")

            # Check if directory contains actual files (not empty directory)
            valid_browser_found = False
            for browser_dir in all_browser_dirs:
                if browser_dir.is_dir():
                    files = list(browser_dir.rglob("*"))
                    file_count = len(files)

                    # More intelligent validation logic
                    if file_count < 10:
                        logger.debug(f"Browser directory {browser_dir.name} has fewer files: {file_count}")
                        # Check if there are key executable files
                        executables = [f for f in files if f.is_file() and (
                            f.name.lower().startswith('chrome') or
                            f.name.lower().startswith('chromium') or
                            f.name.lower().startswith('firefox') or
                            f.suffix.lower() in ['.exe', '.app', '']
                        )]
                        if not executables:
                            logger.debug(f"in {browser_dir.name} no executable files found")
                            continue
                        else:
                            logger.debug(f"in {browser_dir.name} found {len(executables)} executable files")
                    else:
                        logger.debug(f"Browser directory {browser_dir.name} contains {file_count} files")

                    valid_browser_found = True
                    break

            if not valid_browser_found:
                logger.debug(f"Installation validation failed: {path} - no valid browser installation found")
                return False

            logger.debug(f"✅ Installation validation successful: {path}")
            return True

        except Exception as e:
            logger.debug(f"Installation validation failed: {path} - validation process error: {e}")
            return False
    
    @staticmethod
    def find_playwright_cache() -> Optional[Path]:
        """Find Playwright cache directory with caching and performance optimization"""
        # Check if we have a cached result that's still valid
        current_time = time.time()
        if (PlaywrightCoreUtils._cache_search_result is not None and
            current_time - PlaywrightCoreUtils._cache_search_timestamp < PlaywrightCoreUtils._cache_search_ttl):
            logger.debug(f"Using cached Playwright cache location: {PlaywrightCoreUtils._cache_search_result}")
            return PlaywrightCoreUtils._cache_search_result

        logger.debug("Searching for Playwright cache directory...")
        start_time = time.time()

        # First check most likely locations for quick success
        most_likely_paths = PlaywrightCoreUtils.get_most_likely_cache_paths()
        for path in most_likely_paths:
            if path.exists() and (path / "browsers.json").exists():
                PlaywrightCoreUtils._cache_search_result = path
                PlaywrightCoreUtils._cache_search_timestamp = current_time
                logger.debug(f"Found Playwright cache in likely location: {path}")
                return path

        possible_roots = PlaywrightCoreUtils.get_possible_cache_paths()

        # First check paths set in environment variables
        env_path = os.getenv(PlaywrightCoreUtils.ENV_BROWSERS_PATH)
        if env_path:
            env_path_obj = Path(env_path)
            if env_path_obj.exists() and (env_path_obj / "browsers.json").exists():
                PlaywrightCoreUtils._cache_search_result = env_path_obj
                PlaywrightCoreUtils._cache_search_timestamp = current_time
                logger.debug(f"Found Playwright cache in env var: {env_path_obj}")
                return env_path_obj
        
        # Priority check cache in user home directory
        home_cache = Path.home() / ".cache" / "ms-playwright"
        if home_cache.exists() and (home_cache / "browsers.json").exists():
            PlaywrightCoreUtils._cache_search_result = home_cache
            PlaywrightCoreUtils._cache_search_timestamp = current_time
            logger.debug(f"Found Playwright cache in home directory: {home_cache}")
            return home_cache

        # Check application data directory
        app_data_cache = PlaywrightCoreUtils.get_app_data_path() / "ms-playwright"
        if app_data_cache.exists() and (app_data_cache / "browsers.json").exists():
            PlaywrightCoreUtils._cache_search_result = app_data_cache
            PlaywrightCoreUtils._cache_search_timestamp = current_time
            logger.debug(f"Found Playwright cache in app data: {app_data_cache}")
            return app_data_cache

        # Then search for other possible paths (with timeout protection)
        search_timeout = 10  # 10 seconds timeout
        for root in possible_roots:
            if time.time() - start_time > search_timeout:
                logger.warning(f"Playwright cache search timeout after {search_timeout}s, stopping search")
                break

            if root.exists() and (root / "browsers.json").exists():
                PlaywrightCoreUtils._cache_search_result = root
                PlaywrightCoreUtils._cache_search_timestamp = current_time
                logger.debug(f"Found Playwright cache in possible paths: {root}")
                return root
        
        # If browsers.json not found, search for directories containing chromium (with timeout)
        for root in possible_roots:
            if time.time() - start_time > search_timeout:
                logger.warning(f"Playwright cache search timeout during chromium search, stopping")
                break

            if root.exists():
                try:
                    # Limit search depth to avoid performance issues
                    chromium_dirs = list(root.glob("*/chromium*"))  # Only search 1 level deep
                    if chromium_dirs:
                        # Search upward for ms-playwright root directory
                        current = chromium_dirs[0].parent
                        max_levels = 5  # Limit upward search to 5 levels
                        level = 0
                        while current.parent != current and level < max_levels:
                            if current.name == "ms-playwright":
                                PlaywrightCoreUtils._cache_search_result = current
                                PlaywrightCoreUtils._cache_search_timestamp = current_time
                                logger.debug(f"Found Playwright cache via chromium search: {current}")
                                return current
                            current = current.parent
                            level += 1
                except (PermissionError, OSError) as e:
                    logger.debug(f"Permission error searching {root}: {e}")
                    continue
        
        # Last resort: very limited search for ms-playwright directory
        # Only search in specific cache locations with strict timeout
        if time.time() - start_time < search_timeout:
            limited_search_paths = [
                Path.home() / ".cache",
                Path.home() / ".local",
                Path.home() / "Library" / "Caches" if sys.platform == "darwin" else None,
                Path.home() / "AppData" / "Local" if sys.platform == "win32" else None,
            ]

            for search_path in limited_search_paths:
                if time.time() - start_time > search_timeout:
                    logger.warning(f"Playwright cache search timeout during final search, stopping")
                    break

                if search_path and search_path.exists():
                    try:
                        # Very limited search - only 1 level deep
                        for found in search_path.glob("*/ms-playwright"):
                            if found.is_dir() and (found / "browsers.json").exists():
                                PlaywrightCoreUtils._cache_search_result = found
                                PlaywrightCoreUtils._cache_search_timestamp = current_time
                                logger.debug(f"Found Playwright cache in final search: {found}")
                                return found
                    except (PermissionError, OSError) as e:
                        logger.debug(f"Permission error in final search {search_path}: {e}")
                        continue

        # Cache the "not found" result to avoid repeated expensive searches
        search_duration = time.time() - start_time
        logger.info(f"No existing cache found after {search_duration:.2f}s search")
        PlaywrightCoreUtils._cache_search_result = None
        PlaywrightCoreUtils._cache_search_timestamp = current_time

        return None

    @staticmethod
    def clear_cache_search_result():
        """Clear cached search result to force fresh search"""
        PlaywrightCoreUtils._cache_search_result = None
        PlaywrightCoreUtils._cache_search_timestamp = 0
        logger.debug("Cleared Playwright cache search result")

    @staticmethod
    def install_playwright_browsers(target_path: Path) -> None:
        """Install Playwright browsers to specified path"""
        from utils.subprocess_helper import run_no_window
        # Ensure playwright package is installed
        try:
            run_no_window([sys.executable, "-m", "pip", "show", "playwright"], 
                         check=True, capture_output=True)
        except subprocess.CalledProcessError:
            logger.error("[PLAYWRIGHT] playwright not found; installing...")
            run_no_window([sys.executable, "-m", "pip", "install", "playwright"], check=True)
        
        # Set environment variables for subprocess
        env = os.environ.copy()
        env[core_utils.ENV_BASE_DIR] = str(target_path)
        env[core_utils.ENV_CACHE_DIR] = str(target_path)
        
        # Install browsers - install chromium and chromium-headless-shell
        logger.info("[PLAYWRIGHT] Installing chromium browsers...")
        run_no_window([sys.executable, "-m", "playwright", "install", "chromium", "chromium-headless-shell"],
                      check=True, env=env)
    
    @staticmethod
    def cleanup_incomplete_browsers(path: Path) -> None:
        """Clean up incomplete browser directories"""
        if not path or not path.exists():
            return

        logger.info(f"Starting cleanup of incomplete installations: {path}")
        cleaned_count = 0

        try:
            # Find all chromium directories
            chromium_dirs = list(path.glob("chromium*"))

            for browser_dir in chromium_dirs:
                if browser_dir.is_dir():
                    files = list(browser_dir.rglob("*"))
                    file_count = len(files)

                    # If file count is too low, consider it incomplete installation
                    if file_count < 10:
                        # Check if there are key executable files
                        executables = [f for f in files if f.is_file() and (
                            f.name.lower().startswith('chrome') or
                            f.name.lower().startswith('chromium') or
                            f.suffix.lower() in ['.exe', '.app', '']
                        )]

                        if not executables:
                            logger.info(f"[PLAYWRIGHT] Cleaning incomplete browser directory: {browser_dir} ({file_count} files)")
                            try:
                                shutil.rmtree(browser_dir, ignore_errors=True)
                                cleaned_count += 1
                            except Exception as e:
                                logger.warning(f"[PLAYWRIGHT] Failed to clean {browser_dir}: {e}")
                        else:
                            logger.debug(f"[PLAYWRIGHT] Keeping {browser_dir} (has executables)")

            logger.info(f"Cleanup completed: {path} (cleaned up {cleaned_count} items)")

        except Exception as e:
            friendly_error_message(e, "cleanup_incomplete_browsers")

    @staticmethod
    def copy_playwright_browsers(src_path: Path, dst_path: Path) -> None:
        """Copy Playwright browser files with version checking"""
        # Check if destination exists and is valid
        if dst_path.exists() and PlaywrightCoreUtils.validate_browser_installation(dst_path):
            # Compare versions to decide if update is needed
            if not PlaywrightCoreUtils.compare_browser_versions(src_path, dst_path):
                logger.info(f"[PLAYWRIGHT] ✅ Destination has same or newer version, skipping copy: {dst_path}")
                return
            else:
                logger.info(f"[PLAYWRIGHT] 🔄 Updating browsers to newer version")
        
        if dst_path.exists():
            logger.info(f"[PLAYWRIGHT] Cleaning existing installation: {dst_path}")
            shutil.rmtree(dst_path, ignore_errors=True)

        logger.info(f"[PLAYWRIGHT] Copying {src_path} -> {dst_path}")
        shutil.copytree(src_path, dst_path)
        logger.info(f"[PLAYWRIGHT] Successfully copied browsers to {dst_path}")
    

    
    @staticmethod
    def set_environment_variables(browsers_path: Path) -> None:
        """Set Playwright environment variables"""
        os.environ[PlaywrightCoreUtils.ENV_BROWSERS_PATH] = str(browsers_path)
        os.environ[PlaywrightCoreUtils.ENV_CACHE_DIR] = str(browsers_path)
        os.environ[PlaywrightCoreUtils.ENV_BROWSERS_PATH_OVERRIDE] = str(browsers_path)
    
    @staticmethod
    def get_environment_browsers_path() -> Optional[Path]:
        """Get browser path from environment variables"""
        env_path = os.getenv(PlaywrightCoreUtils.ENV_BROWSERS_PATH)
        if env_path:
            return Path(env_path)
        return None
    
    @staticmethod
    def clear_environment_variables() -> None:
        """Clear Playwright environment variables"""
        for env_var in [
            PlaywrightCoreUtils.ENV_BROWSERS_PATH,
            PlaywrightCoreUtils.ENV_CACHE_DIR,
            PlaywrightCoreUtils.ENV_BROWSERS_PATH_OVERRIDE
        ]:
            if env_var in os.environ:
                del os.environ[env_var]


# Global tool instance
core_utils = PlaywrightCoreUtils()
