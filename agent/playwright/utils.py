#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright Utility Functions

This module provides utility functions for Playwright initialization,
environment setup, and status checking.
"""

import sys
import os

from utils.logger_helper import logger_helper as logger

# PyInstaller environment auto-setup state
_auto_setup_completed = False


def auto_setup_pyinstaller_environment():
    """
    Auto-setup Playwright in PyInstaller environment.
    
    This function is called automatically on module import to ensure
    Playwright is properly configured in packaged applications.
    
    Returns:
        bool: True if setup completed successfully, False otherwise
    """
    global _auto_setup_completed

    if _auto_setup_completed:
        logger.debug("PyInstaller auto-setup already completed, skipping")
        return True

    try:
        # Auto-setup only in PyInstaller environment
        if getattr(sys, 'frozen', False):
            logger.info("Detected PyInstaller environment, starting auto-setup")
            from .core.setup import ensure_playwright_browsers_ready

            # Try to setup Playwright environment
            try:
                browsers_path = ensure_playwright_browsers_ready()
                logger.info(f"✅ PyInstaller auto-setup completed successfully")
                logger.debug(f"Browsers path: {browsers_path}")
                print(f"[PLAYWRIGHT] PyInstaller auto-setup completed: {browsers_path}")
                _auto_setup_completed = True
                return True
            except Exception as e:
                logger.error(f"❌ PyInstaller auto-setup failed: {e}", exc_info=True)
                print(f"[PLAYWRIGHT] PyInstaller auto-setup failed: {e}")
                # Don't block app startup, just log the error
                return False
        
        logger.debug("Not in PyInstaller environment, skipping auto-setup")
        _auto_setup_completed = True
        return True

    except Exception as e:
        logger.error(f"❌ PyInstaller auto-setup error: {e}", exc_info=True)
        print(f"[PLAYWRIGHT] PyInstaller auto-setup error: {e}")
        # Don't block app startup
        return False


def check_and_init_playwright():
    """
    Check and initialize Playwright if needed (simplified convenience function).
    
    This function checks if Playwright is initialized and attempts to
    initialize it if necessary.
    
    Returns:
        bool: True if Playwright is initialized, False otherwise
        
    Examples:
        >>> if check_and_init_playwright():
        ...     # Playwright is ready
        ...     pass
    """
    logger.debug("Checking Playwright initialization status")
    try:
        from .manager import get_playwright_manager
        from .core.helpers import smart_init_prompt, friendly_error_message
        
        manager = get_playwright_manager()
        if not manager.is_initialized():
            logger.info("Playwright not initialized, attempting to initialize")
            smart_init_prompt()
            result = manager.lazy_init()
            if result:
                logger.info("✅ Playwright initialized successfully")
            else:
                logger.warning("⚠️ Playwright initialization returned False")
            return result
        
        logger.debug("Playwright already initialized")
        return True
    except Exception as e:
        from .core.helpers import friendly_error_message
        error_msg = friendly_error_message(e, "ensure_initialized")
        logger.error(f"❌ Failed to check/initialize Playwright: {e}", exc_info=True)
        print(error_msg)
        return False


def get_playwright_browsers_path():
    """
    Get Playwright browsers path.
    
    Returns the path where Playwright browsers are installed.
    
    Returns:
        str or None: Path to Playwright browsers directory, or None if not found
        
    Examples:
        >>> path = get_playwright_browsers_path()
        >>> if path:
        ...     print(f"Browsers at: {path}")
    """
    logger.debug("Getting Playwright browsers path")
    try:
        from .core.setup import get_playwright_browsers_path as _get_path
        path = _get_path()
        if path:
            logger.debug(f"Found browsers path: {path}")
        else:
            logger.debug("Browsers path not found via core.setup")
        return path
    except ImportError as e:
        logger.debug(f"Failed to import core.setup, falling back to environment variable: {e}")
        path = os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
        if path:
            logger.debug(f"Found browsers path from environment: {path}")
        else:
            logger.debug("PLAYWRIGHT_BROWSERS_PATH environment variable not set")
        return path


def is_playwright_ready():
    """
    Check if Playwright is ready to use.
    
    Returns:
        bool: True if Playwright is ready, False otherwise
        
    Examples:
        >>> if is_playwright_ready():
        ...     # Safe to use Playwright
        ...     pass
        ... else:
        ...     print("Please install Playwright browsers")
    """
    logger.debug("Checking if Playwright is ready")
    try:
        from .core.setup import is_playwright_ready as _is_ready
        ready = _is_ready()
        if ready:
            logger.debug("✅ Playwright is ready")
        else:
            logger.debug("⚠️ Playwright is not ready")
        return ready
    except ImportError as e:
        logger.debug(f"Failed to import core.setup, using fallback check: {e}")
        # Simple check of environment variables as fallback
        path = os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
        ready = path is not None and os.path.exists(path)
        if ready:
            logger.debug(f"✅ Playwright browsers found at: {path}")
        else:
            logger.debug("⚠️ Playwright browsers not found (fallback check)")
        return ready


def is_pyinstaller_environment():
    """
    Check if running in PyInstaller environment.
    
    Returns:
        bool: True if running in PyInstaller, False otherwise
        
    Examples:
        >>> if is_pyinstaller_environment():
        ...     print("Running in packaged app")
    """
    is_frozen = getattr(sys, 'frozen', False)
    logger.debug(f"PyInstaller environment check: {'Yes' if is_frozen else 'No'}")
    return is_frozen


def get_environment_info():
    """
    Get information about the current Playwright environment.
    
    Returns:
        dict: Dictionary containing environment information
        
    Examples:
        >>> info = get_environment_info()
        >>> print(f"PyInstaller: {info['is_pyinstaller']}")
        >>> print(f"Ready: {info['is_ready']}")
    """
    logger.debug("Gathering Playwright environment information")
    
    info = {
        'is_pyinstaller': is_pyinstaller_environment(),
        'is_ready': is_playwright_ready(),
        'browsers_path': get_playwright_browsers_path(),
        'auto_setup_completed': _auto_setup_completed
    }
    
    logger.info(
        f"Environment info - PyInstaller: {info['is_pyinstaller']}, "
        f"Ready: {info['is_ready']}, "
        f"Auto-setup: {info['auto_setup_completed']}"
    )
    logger.debug(f"Browsers path: {info['browsers_path']}")
    
    return info

