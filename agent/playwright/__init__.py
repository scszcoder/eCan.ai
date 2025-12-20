#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright Browser Management Package

Provides lazy initialization of Playwright browser management functionality.
This module serves as the main entry point for the Playwright package,
importing and exposing all public APIs.
"""

# Core managers and components
from .manager import PlaywrightManager, get_playwright_manager
from .decorators import (
    ensure_playwright_initialized,
    with_playwright_context,
    browser_use_ready,
    safe_playwright
)
from .core import core_utils, setup_playwright

# Helper functions
from .core.helpers import (
    friendly_error_message,
    is_first_time_use,
    auto_install_playwright,
    quick_diagnostics,
    smart_init_prompt
)

# Utility functions
from .utils import (
    auto_setup_pyinstaller_environment,
    check_and_init_playwright,
    get_playwright_browsers_path,
    is_playwright_ready,
    is_pyinstaller_environment,
    get_environment_info
)

# LLM adapter functions (now managed by llm_utils)
from agent.ec_skills.llm_utils.llm_utils import (
    create_browser_use_llm,
    is_provider_browser_use_compatible,
    get_browser_use_supported_providers
)


# Auto-execute PyInstaller environment setup on module import
auto_setup_pyinstaller_environment()


# Export main manager classes, decorators and core functionality
__all__ = [
    # Core managers
    'PlaywrightManager',
    'get_playwright_manager',
    
    # Decorators
    'ensure_playwright_initialized',
    'with_playwright_context',
    'browser_use_ready',
    'safe_playwright',

    # Core tools and setup
    'core_utils',
    'setup_playwright',
    
    # Utility functions
    'check_and_init_playwright',
    'get_playwright_browsers_path',
    'is_playwright_ready',
    'is_pyinstaller_environment',
    'get_environment_info',
    
    # LLM adapter functions
    'create_browser_use_llm',
    'is_provider_browser_use_compatible',
    'get_browser_use_supported_providers',

    # Helper functions
    'friendly_error_message',
    'is_first_time_use',
    'auto_install_playwright',
    'quick_diagnostics',
    'smart_init_prompt'
]
