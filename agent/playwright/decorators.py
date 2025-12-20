#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright Initialization Decorators
Provides decorator functionality for automatic Playwright initialization
"""

import functools
from typing import Callable, Any

from .manager import get_playwright_manager

from utils.logger_helper import logger_helper as logger


def ensure_playwright_initialized(func: Callable) -> Callable:
    """
    Decorator: ensure Playwright is initialized

    Simplified version, provides basic error messages and first-time installation suggestions

    Usage:
        @ensure_playwright_initialized
        def my_function():
            # Use Playwright functionality here
            pass
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            # Get Playwright manager
            manager = get_playwright_manager()

            # Check if initialization is needed
            if not manager.is_initialized():
                from .core.helpers import is_first_time_use, log_with_emoji

                log_with_emoji("info", f"Initializing for function {func.__name__} initialize Playwright")

                # First-time use prompt
                if is_first_time_use():
                    log_with_emoji("warning", "Detected first-time use of Playwright")
                    print("💡 Recommended: from agent.playwright.core.helpers import auto_install_playwright; auto_install_playwright()")

                if not manager.lazy_init():
                    log_with_emoji("error", f"Playwright initialization failed: {func.__name__}")
                    print("💡 Run quick_diagnostics() to check issues")
                else:
                    log_with_emoji("success", f"Playwright initialization successful: {func.__name__}")

            # Execute original function
            return func(*args, **kwargs)

        except Exception as e:
            from .core.helpers import friendly_error_message
            error_msg = friendly_error_message(e, f"decorator_{func.__name__}")
            logger.error(error_msg)
            print(error_msg)

            # Continue executing function, but may fail
            return func(*args, **kwargs)

    return wrapper


def with_playwright_context(func: Callable) -> Callable:
    """
    Decorator: provide Playwright context
    
    Usage:
        @with_playwright_context
        def my_function(playwright_manager):
            # playwright_manager is an initialized manager
            pass
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            # Get and initialize Playwright manager
            manager = get_playwright_manager()
            
            if not manager.is_initialized():
                logger.info(f"Initializing Playwright for function: {func.__name__}")
                if not manager.lazy_init():
                    logger.error(f"Failed to initialize Playwright for function: {func.__name__}")
                    raise RuntimeError("Playwright initialization failed")
            
            # Pass manager as first parameter to function
            return func(manager, *args, **kwargs)
            
        except Exception as e:
            logger.error(f"Error in Playwright context for function {func.__name__}: {e}")
            raise
    
    return wrapper


def browser_use_ready(func: Callable) -> Callable:
    """
    Decorator: ensure BrowserUse functionality is available

    Decorator specifically designed for BrowserUse-related functions
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            # Get Playwright manager
            manager = get_playwright_manager()
            
            # Check if initialization is needed
            if not manager.is_initialized():
                logger.info(f"Initializing Playwright for BrowserUse function: {func.__name__}")
                if not manager.lazy_init():
                    logger.warning(f"Failed to initialize Playwright for BrowserUse function: {func.__name__}")
                    # BrowserUse may not work properly, but continue execution
            
            # Execute original function
            return func(*args, **kwargs)
            
        except Exception as e:
            logger.error(f"Error in BrowserUse Playwright initialization for function {func.__name__}: {e}")
            # continue executing function
            return func(*args, **kwargs)
    
    return wrapper


def safe_playwright(func: Callable) -> Callable:
    """
    Decorator: safe Playwright operations
    
    If Playwright initialization failed, return None or default value
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            # Get Playwright manager
            manager = get_playwright_manager()
            
            # try to initialize
            if not manager.is_initialized():
                logger.info(f"Attempting to initialize Playwright for function: {func.__name__}")
                if not manager.lazy_init():
                    logger.warning(f"Playwright initialization failed for function: {func.__name__}")
                    return None  # Return None to indicate failure
            
            # Execute original function
            return func(*args, **kwargs)
            
        except Exception as e:
            logger.error(f"Error in safe Playwright operation for function {func.__name__}: {e}")
            return None  # Return None to indicate failure
    
    return wrapper
