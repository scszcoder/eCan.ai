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
    ENV_CACHE_DIR = "PLAYWRIGHT_CACHE_DIR"
    ENV_BROWSERS_PATH_OVERRIDE = "PLAYWRIGHT_BROWSERS_PATH_OVERRIDE"
    
    # Application name
    APP_NAME = "eCan"
    
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
    def validate_browser_installation(path: Path) -> bool:
        """Validate if browser installation is valid"""
        logger.info(f"Starting installation validation: {path}")

        if not path or not path.exists():
            logger.error(f"Installation validation failed: {path} - path does not exist")
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
                        logger.info(f"Found valid browsers.json: {path}")
                        return True
                    else:
                        logger.warning(f"browsers.json format invalid, trying other validation methods")
                except Exception as e:
                    logger.warning(f"Failed to read browsers.json: {e}，trying other validation methods")
            else:
                logger.info(f"browsers.json not found, using directory check method")

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
                    logger.error(f"Installation validation failed: {path} - No browser directories found")
                    return False
                all_browser_dirs = browser_dirs

            logger.info(f"Found browser directories: {[d.name for d in all_browser_dirs]}")

            # Check if directory contains actual files (not empty directory)
            valid_browser_found = False
            for browser_dir in all_browser_dirs:
                if browser_dir.is_dir():
                    files = list(browser_dir.rglob("*"))
                    file_count = len(files)

                    # More intelligent validation logic
                    if file_count < 10:
                        logger.warning(f"Browser directory {browser_dir.name} has fewer files: {file_count}")
                        # Check if there are key executable files
                        executables = [f for f in files if f.is_file() and (
                            f.name.lower().startswith('chrome') or
                            f.name.lower().startswith('chromium') or
                            f.name.lower().startswith('firefox') or
                            f.suffix.lower() in ['.exe', '.app', '']
                        )]
                        if not executables:
                            logger.warning(f"in {browser_dir.name} no executable files found")
                            continue
                        else:
                            logger.info(f"in {browser_dir.name} found {len(executables)} executable files")
                    else:
                        logger.info(f"Browser directory {browser_dir.name} contains {file_count} files")

                    valid_browser_found = True
                    break

            if not valid_browser_found:
                logger.error(f"Installation validation failed: {path} - no valid browser installation found")
                return False

            logger.info(f"Installation validation successful: {path}")
            return True

        except Exception as e:
            logger.error(f"Installation validation failed: {path} - validation process error: {e}")
            return False
    
    @staticmethod
    def find_playwright_cache() -> Optional[Path]:
        """Find Playwright cache directory"""
        possible_roots = PlaywrightCoreUtils.get_possible_cache_paths()
        
        # First check paths set in environment variables
        env_path = os.getenv(PlaywrightCoreUtils.ENV_BROWSERS_PATH)
        if env_path:
            env_path_obj = Path(env_path)
            if env_path_obj.exists() and (env_path_obj / "browsers.json").exists():
                return env_path_obj
        
        # Priority check cache in user home directory
        home_cache = Path.home() / ".cache" / "ms-playwright"
        if home_cache.exists() and (home_cache / "browsers.json").exists():
            return home_cache
        
        # Check application data directory
        app_data_cache = PlaywrightCoreUtils.get_app_data_path() / "ms-playwright"
        if app_data_cache.exists() and (app_data_cache / "browsers.json").exists():
            return app_data_cache
        
        # Then search for other possible paths
        for root in possible_roots:
            if root.exists() and (root / "browsers.json").exists():
                return root
        
        # If browsers.json not found, search for directories containing chromium
        for root in possible_roots:
            if root.exists():
                chromium_dirs = list(root.glob("**/chromium*"))
                if chromium_dirs:
                    # Search upward for ms-playwright root directory
                    current = chromium_dirs[0].parent
                    while current.parent != current:  # stop at root directory
                        if current.name == "ms-playwright":
                            return current
                        current = current.parent
        
        # Last resort: search for any ms-playwright directory
        search_paths = [Path.home(), Path.cwd()]
        for search_path in search_paths:
            if search_path.exists():
                for found in search_path.rglob("ms-playwright"):
                    if (found / "browsers.json").exists():
                        return found
        
        return None
    
    @staticmethod
    def install_playwright_browsers(target_path: Path) -> None:
        """Install Playwright browsers to specified path"""
        # Ensure playwright package is installed
        try:
            subprocess.run([sys.executable, "-m", "pip", "show", "playwright"], 
                         check=True, capture_output=True)
        except subprocess.CalledProcessError:
            logger.error("[PLAYWRIGHT] playwright not found; installing...")
            subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)
        
        # Set environment variables for subprocess
        env = os.environ.copy()
        env[PlaywrightCoreUtils.ENV_BROWSERS_PATH] = str(target_path)
        env[PlaywrightCoreUtils.ENV_CACHE_DIR] = str(target_path)
        
        # Install browsers - install chromium and chromium-headless-shell
        logger.info("[PLAYWRIGHT] Installing chromium browsers...")
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium", "chromium-headless-shell"],
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
        """Copy Playwright browser files"""
        if dst_path.exists():
            logger.warning(f"[PLAYWRIGHT] Cleaning existing {dst_path}")
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
