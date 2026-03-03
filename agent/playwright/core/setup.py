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

    Strategy (optimized for Windows performance):
    1. Always prefer user data directory over temporary directory
    2. First run: copy from PyInstaller bundle to user directory
    3. Subsequent runs: use cached user directory (fast, no Windows Defender scan)
    4. This avoids Windows Defender scanning temporary directory on every startup
    """
    # Get app data root (user directory, not temporary directory)
    if app_data_root is None:
        app_data_root = _default_app_data_root()
    
    # Target directory in user data (persistent across runs)
    target = app_data_root / 'ms-playwright'
    
    # Check if user directory already has valid browsers (fast path for subsequent runs)
    if not force_refresh and _validate_browser_installation(target):
        logger.info(f"✅ Using cached Playwright browsers from user directory: {target}")
        core_utils.set_environment_variables(target)
        return target
    
    # Determine bundled browsers path
    if getattr(sys, 'frozen', False):
        # PyInstaller: browsers in temporary directory
        bundled = Path(sys._MEIPASS) / 'third_party' / 'ms-playwright'
    else:
        # Development: browsers in repo directory
        bundled = Path.cwd() / 'third_party' / 'ms-playwright'
    
    # First run or force refresh: copy from bundled to user directory
    if bundled.exists() and _validate_browser_installation(bundled):
        if getattr(sys, 'frozen', False):
            logger.info(f"🔄 First run: copying Playwright browsers to user directory...")
            logger.info(f"   From: {bundled} (temporary)")
            logger.info(f"   To:   {target} (persistent)")
            logger.info(f"   This improves startup speed on subsequent runs (Windows Defender optimization)")
        else:
            logger.info(f"Copying browsers from {bundled}")
        
        core_utils.copy_playwright_browsers(bundled, target)
        core_utils.set_environment_variables(target)
        
        # Install browser extensions from bundled resources
        if getattr(sys, 'frozen', False):
            core_utils.install_browser_extensions()
        
        logger.info(f"✅ Playwright browsers ready at: {target}")
        return target
    
    # Fallback: runtime installation (should rarely happen)
    logger.warning("Bundled browsers not found, attempting runtime installation...")
    logger.info("Starting runtime installation of Playwright browsers...")
    core_utils.install_playwright_browsers(target)
    
    if not _validate_browser_installation(target):
        raise RuntimeError("Runtime installation failed to produce valid browser installation")
    
    core_utils.set_environment_variables(target)
    logger.info(f"✅ Playwright browsers ready at: {target}")
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
