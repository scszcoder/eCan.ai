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
            # Install browser extensions from bundled resources (first run)
            core_utils.install_browser_extensions()
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

    # Target directory in app data
    target = app_data_root / 'ms-playwright'

    # Determine bundled browsers path
    if getattr(sys, 'frozen', False):
        bundled = Path(sys._MEIPASS) / 'third_party' / 'ms-playwright'
    else:
        bundled = Path.cwd() / 'third_party' / 'ms-playwright'

    # If target already has a valid installation, prefer reusing it but allow version update from bundled
    if not force_refresh and _validate_browser_installation(target):
        if bundled.exists() and _validate_browser_installation(bundled):
            logger.info(f"Checking for Playwright browser updates from bundled path: {bundled}")
            # copy_playwright_browsers() will perform version comparison and only update when needed
            core_utils.copy_playwright_browsers(bundled, target)

        logger.info(f"Browser installation already exists and is valid at: {target}")
        core_utils.set_environment_variables(target)
        return target

    # Copy from bundled if available (target missing or invalid, or force_refresh=True)
    if bundled.exists() and _validate_browser_installation(bundled):
        logger.info(f"Copying browsers from {bundled}")
        core_utils.copy_playwright_browsers(bundled, target)
        core_utils.set_environment_variables(target)
        logger.info(f"Playwright browsers ready at: {target}")
        return target
    
    # Fallback: runtime installation
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
