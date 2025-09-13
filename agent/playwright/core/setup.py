#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright Runtime Setup Module
Handles Playwright browser initialization and setup at application runtime
"""

import sys
import os
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from .utils import core_utils
from .helpers import friendly_error_message

from utils.logger_helper import logger_helper as logger


def _default_app_data_root() -> Path:
    """Get the default application data root directory for the current platform."""
    return core_utils.get_app_data_path()


def _validate_browser_installation(browsers_path: Path) -> bool:
    """Validate that the browser installation is complete and usable."""
    return core_utils.validate_browser_installation(browsers_path)


def _get_browser_info(browsers_path: Path) -> Dict[str, Any]:
    """Get information about installed browsers."""
    info = {
        'path': str(browsers_path),
        'browsers': [],
        'total_size': 0,
        'last_updated': None
    }
    
    try:
        # Get browser directories
        browser_dirs = [d for d in browsers_path.iterdir() 
                       if d.is_dir() and not d.name.startswith('.')]
        
        for browser_dir in browser_dirs:
            browser_info = {
                'name': browser_dir.name,
                'size': sum(f.stat().st_size for f in browser_dir.rglob('*') if f.is_file()),
                'files': len(list(browser_dir.rglob('*')))
            }
            info['browsers'].append(browser_info)
            info['total_size'] += browser_info['size']
        
        # Get last modification time
        if browsers_path.exists():
            info['last_updated'] = datetime.fromtimestamp(browsers_path.stat().st_mtime).isoformat()
            
    except Exception as e:
        logger.error(f"Failed to get browser information: {e}")

    return info


def _print_setup_environment_info(target_path: Path) -> None:
    """Print environment information during setup"""
    import os
    import platform

    logger.info("📋 Playwright Setup Environment:")
    logger.info(f"  Platform: {platform.system()} {platform.release()}")
    logger.info(f"  Python: {platform.python_version()}")
    logger.info(f"  Target Path: {target_path}")

    # Check various paths
    bundled_path = core_utils.get_bundled_path()
    default_path = core_utils.get_default_browsers_path()
    app_data_path = core_utils.get_app_data_path()
    existing_env_path = core_utils.get_environment_browsers_path()

    logger.info("  Path Information:")
    logger.info(f"    Bundled Path: {bundled_path or 'None'}")
    logger.info(f"    Default Path: {default_path}")
    logger.info(f"    App Data Path: {app_data_path}")
    logger.info(f"    Existing Env Path: {existing_env_path or 'None'}")

    # Check environment variables
    env_vars = {
        "PLAYWRIGHT_BROWSERS_PATH": os.getenv("PLAYWRIGHT_BROWSERS_PATH"),
        "PLAYWRIGHT_CACHE_DIR": os.getenv("PLAYWRIGHT_CACHE_DIR"),
        "PLAYWRIGHT_BROWSERS_PATH_OVERRIDE": os.getenv("PLAYWRIGHT_BROWSERS_PATH_OVERRIDE")
    }

    logger.info("  Environment Variables:")
    for var_name, var_value in env_vars.items():
        if var_value:
            logger.info(f"    {var_name}: {var_value}")
        else:
            logger.info(f"    {var_name}: <not set>")

    # Check existing cache
    existing_cache = core_utils.find_playwright_cache()
    if existing_cache:
        logger.info(f"  Existing Cache Found: {existing_cache}")
        if existing_cache.exists():
            items = list(existing_cache.iterdir())
            browser_dirs = [d for d in items if d.is_dir() and
                           any(browser in d.name.lower() for browser in ['chromium', 'firefox', 'webkit'])]
            if browser_dirs:
                logger.info(f"    Browser directories: {[d.name for d in browser_dirs]}")
    else:
        logger.info("  No existing cache found")


def ensure_playwright_browsers_ready(app_data_root: Optional[Path] = None,
                                   force_refresh: bool = False) -> Path:
    """Ensure Playwright browsers are available at a writable path and set env.

    This function ensures that Playwright browsers are available at a writable
    location and sets the necessary environment variables.

    Args:
        app_data_root: Optional path to app data directory. If None, uses default.
        force_refresh: If True, force refresh the browser installation.

    Returns:
        Path to the directory containing Playwright browsers.

    The function follows this logic:
    - Frozen runtime: <_MEIPASS>/third_party/ms-playwright
    - Dev runtime: <repo>/third_party/ms-playwright
    - If found, copy to <app_data_root>/ms-playwright when missing or incomplete.
    - Finally set PLAYWRIGHT_BROWSERS_PATH to the writable directory and return it.
    """
    # PyInstaller special handling: use bundled browsers directly
    if getattr(sys, 'frozen', False):
        bundled_path = Path(sys._MEIPASS) / 'third_party' / 'ms-playwright'
        if bundled_path.exists() and _validate_browser_installation(bundled_path):
            logger.info(f"Using bundled Playwright browsers in PyInstaller: {bundled_path}")
            core_utils.set_environment_variables(bundled_path)
            return bundled_path
        else:
            logger.warning(f"Bundled browsers not found or invalid at: {bundled_path}")

    # Check if valid environment variables are already set
    existing_path = core_utils.get_environment_browsers_path()
    if existing_path and not force_refresh:
        if _validate_browser_installation(existing_path):
            logger.info(f"Using existing PLAYWRIGHT_BROWSERS_PATH: {existing_path}")
            return existing_path
    
    # Simplified: no longer read paths from config files to avoid over-implementation
    
    if app_data_root is None:
        app_data_root = _default_app_data_root()

    logger.info(f"Setting up Playwright browsers in: {app_data_root}")

    # Target directory in app data
    target = app_data_root / 'ms-playwright'

    # Print setup environment information
    _print_setup_environment_info(target)
    
    # First clean up any incomplete browser directories
    if target.exists():
        core_utils.cleanup_incomplete_browsers(target)

    # Then check if target directory is already valid
    if not force_refresh and _validate_browser_installation(target):
        logger.info("Browser installation already exists and is valid")
        core_utils.set_environment_variables(target)
        logger.info(f"Set PLAYWRIGHT_BROWSERS_PATH to: {target}")
        return target
    
    # Check if there are existing Playwright caches that can be used
    existing_cache = core_utils.find_playwright_cache()
    if existing_cache and existing_cache != target and not force_refresh:
        logger.info(f"Found existing Playwright cache at: {existing_cache}")
        # Clean up incomplete directories in existing cache
        core_utils.cleanup_incomplete_browsers(existing_cache)
        if _validate_browser_installation(existing_cache):
            logger.info("Using existing valid browser installation")
            # Use dedicated copy function
            try:
                core_utils.copy_playwright_browsers(existing_cache, target)
                logger.info(f"Copied existing browsers to: {target}")
                core_utils.set_environment_variables(target)
                logger.info(f"Set PLAYWRIGHT_BROWSERS_PATH to: {target}")
                return target
            except Exception as e:
                logger.warning(f"Failed to copy existing browsers: {e}")
                # Continue using original logic
    
    # In development environment, check if there is a local third_party directory
    if not getattr(sys, 'frozen', False):
        local_third_party = Path.cwd() / 'third_party' / 'ms-playwright'
        if local_third_party.exists() and _validate_browser_installation(local_third_party):
            logger.info(f"Found valid local third_party browsers at: {local_third_party}")
            # Ensure copying to application internal directory, not directly using local directory
            try:
                core_utils.copy_playwright_browsers(local_third_party, target)
                logger.info(f"Copied local third_party browsers to: {target}")
                core_utils.set_environment_variables(target)
                logger.info(f"Set PLAYWRIGHT_BROWSERS_PATH to: {target}")
                return target
            except Exception as e:
                logger.warning(f"Failed to copy local third_party browsers: {e}")
                # Continue using original logic
    
    # Determine base directory for bundled browsers
    if getattr(sys, 'frozen', False):
        # PyInstaller frozen environment
        base_dir = Path(sys._MEIPASS)
        bundled = base_dir / 'third_party' / 'ms-playwright'
    else:
        # Development environment
        bundled = Path.cwd() / 'third_party' / 'ms-playwright'
    
    # Determine if we need to copy browsers
    should_copy = force_refresh or not _validate_browser_installation(target)
    
    if should_copy and bundled.exists():
        logger.info(f"Copying bundled browsers from {bundled} to {target}")
        try:
            core_utils.copy_playwright_browsers(bundled, target)
            logger.info("Successfully copied bundled browsers")
            if _validate_browser_installation(target):
                core_utils.set_environment_variables(target)
                logger.info(f"Set PLAYWRIGHT_BROWSERS_PATH to: {target}")
                return target
        except Exception as e:
            logger.error(f"Failed to copy bundled browsers: {e}")
            # Fall back to runtime installation
            should_copy = True
    
    if should_copy:
        logger.info("No bundled browsers available for copying, attempting runtime installation.")
        try:
            # Use simplified installation method
            logger.info("🚀 Starting runtime installation of Playwright browsers...")
            core_utils.install_playwright_browsers(target)

            if _validate_browser_installation(target):
                logger.info("✅ Runtime installation of Playwright browsers successful")
            else:
                logger.warning("⚠️ Runtime installation did not produce valid installation")

        except Exception as e:
            error_msg = friendly_error_message(e, "runtime_installation")
            logger.error(f"❌ Runtime installation of Playwright browsers failed: {error_msg}")
            raise
    else:
        logger.info("Browser installation already exists and is valid")
    
    # Set environment for Playwright - CRITICAL for custom path
    core_utils.set_environment_variables(target)
    
    logger.info(f"Set PLAYWRIGHT_BROWSERS_PATH to: {target}")
    return target


def cleanup_playwright_browsers(app_data_root: Optional[Path] = None) -> bool:
    """Clean up Playwright browser installation.
    
    Args:
        app_data_root: Optional path to app data directory. If None, uses default.
        
    Returns:
        True if cleanup was successful, False otherwise.
    """
    try:
        if app_data_root is None:
            app_data_root = _default_app_data_root()
        
        browsers_path = app_data_root / 'ms-playwright'
        
        if browsers_path.exists():
            import shutil
            shutil.rmtree(browsers_path)
            logger.info(f"Cleaned up Playwright browsers at: {browsers_path}")
        
        # Clear environment variables
        if 'PLAYWRIGHT_BROWSERS_PATH' in os.environ:
            del os.environ['PLAYWRIGHT_BROWSERS_PATH']
            logger.info("Cleared PLAYWRIGHT_BROWSERS_PATH environment variable")
        
        return True
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        return False


def get_playwright_browsers_path() -> Optional[str]:
    """Get the current PLAYWRIGHT_BROWSERS_PATH environment variable value."""
    return core_utils.get_environment_browsers_path()


def is_playwright_ready() -> bool:
    """Check if Playwright browsers are ready and accessible."""
    browsers_path = get_playwright_browsers_path()
    if not browsers_path:
        return False
    
    return _validate_browser_installation(Path(browsers_path))


# Configuration persistence and path override logic removed to avoid over-implementation and keep initialization process simple and clear


def setup_playwright(app_data_root: Optional[Path] = None) -> Path:
    """Quick setup function that ensures Playwright is ready.
    
    This is a convenience function that calls ensure_playwright_browsers_ready()
    with default settings.
    """
    return ensure_playwright_browsers_ready(app_data_root)
