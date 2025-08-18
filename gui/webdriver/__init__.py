#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebDriver package for managing Chrome WebDriver instances
"""

from .manager import WebDriverManager, get_webdriver_manager, get_webdriver_manager_sync
from .service import WebDriverService, get_webdriver_service, get_webdriver_service_sync
from .initializer import WebDriverInitializer, get_webdriver_initializer, get_webdriver_initializer_sync, start_webdriver_initialization

__all__ = [
    'WebDriverManager',
    'get_webdriver_manager', 
    'get_webdriver_manager_sync',
    'WebDriverService',
    'get_webdriver_service',
    'get_webdriver_service_sync',
    'WebDriverInitializer',
    'get_webdriver_initializer',
    'get_webdriver_initializer_sync',
    'start_webdriver_initialization'
]

__version__ = '1.0.0'
