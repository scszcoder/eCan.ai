#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright Browser Management Package
Provides lazy initialization of Playwright browser management functionality
"""

import sys
import os

from .manager import PlaywrightManager, get_playwright_manager
from .decorators import ensure_playwright_initialized, with_playwright_context, browser_use_ready, safe_playwright
from .core import core_utils, setup_playwright
from .core.helpers import (
    friendly_error_message,
    is_first_time_use,
    auto_install_playwright,
    quick_diagnostics,
    smart_init_prompt
)

# PyInstaller environment auto-setup
_auto_setup_completed = False

def _auto_setup_pyinstaller_environment():
    """Auto-setup Playwright in PyInstaller environment"""
    global _auto_setup_completed

    if _auto_setup_completed:
        return

    try:
        # Auto-setup only in PyInstaller environment
        if getattr(sys, 'frozen', False):
            from .core.setup import ensure_playwright_browsers_ready

            # Try to setup Playwright environment
            try:
                browsers_path = ensure_playwright_browsers_ready()
                print(f"[PLAYWRIGHT] PyInstaller auto-setup completed: {browsers_path}")
            except Exception as e:
                print(f"[PLAYWRIGHT] PyInstaller auto-setup failed: {e}")
                # Don't block app startup, just log the error

        _auto_setup_completed = True

    except Exception as e:
        print(f"[PLAYWRIGHT] PyInstaller auto-setup error: {e}")
        # Don't block app startup

# Auto-execute PyInstaller environment setup on module import
_auto_setup_pyinstaller_environment()

def ensure_playwright_initialized():
    """Convenience function to ensure Playwright is initialized (simplified version)"""
    try:
        manager = get_playwright_manager()
        if not manager.is_initialized():
            smart_init_prompt()
            return manager.lazy_init()
        return True
    except Exception as e:
        error_msg = friendly_error_message(e, "ensure_initialized")
        print(error_msg)
        return False


def get_playwright_browsers_path():
    """Convenience function to get Playwright browsers path"""
    try:
        from .core.setup import get_playwright_browsers_path
        return get_playwright_browsers_path()
    except ImportError:
        return os.environ.get('PLAYWRIGHT_BROWSERS_PATH')


def is_playwright_ready():
    """Convenience function to check if Playwright is ready"""
    try:
        from .core.setup import is_playwright_ready
        return is_playwright_ready()
    except ImportError:
        # Simple check of environment variables
        path = os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
        return path is not None and os.path.exists(path)


def create_browser_use_llm(fallback_llm):
    """Convenience function to create BrowserUse LLM

    Args:
        fallback_llm: Fallback LLM to use when Playwright initialization fails

    Returns:
        BrowserUseChatOpenAI or fallback LLM
    """
    try:
        if ensure_playwright_initialized():
            from browser_use.llm import ChatOpenAI as BrowserUseChatOpenAI
            return BrowserUseChatOpenAI(model='gpt-4.1-mini')
        else:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("Playwright initialization failed, using fallback LLM")
            return fallback_llm
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to create BrowserUseChatOpenAI: {e}, using fallback LLM")
        return fallback_llm


# Export main manager classes, decorators and core functionality
__all__ = [
    # Core managers and decorators
    'PlaywrightManager',
    'get_playwright_manager',
    'ensure_playwright_initialized',
    'with_playwright_context',
    'browser_use_ready',
    'safe_playwright',

    # Core tools and setup
    'core_utils',
    'setup_playwright',
    'get_playwright_browsers_path',
    'is_playwright_ready',
    'create_browser_use_llm',

    # Simplified helper functions
    'friendly_error_message',
    'is_first_time_use',
    'auto_install_playwright',
    'quick_diagnostics',
    'smart_init_prompt'
]
