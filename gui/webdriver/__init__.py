#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebDriver package for managing Chrome WebDriver instances
"""

from .manager import WebDriverManager, get_webdriver_manager, get_webdriver_manager_sync

__all__ = [
    'WebDriverManager',
    'get_webdriver_manager',
    'get_webdriver_manager_sync',
]

__version__ = '1.0.0'
