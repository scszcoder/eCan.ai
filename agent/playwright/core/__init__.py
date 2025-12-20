#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright 核心模块
提供 Playwright 的基础工具、运行时设置和构建工具
"""

from .utils import core_utils, PlaywrightCoreUtils
from .setup import setup_playwright, ensure_playwright_browsers_ready
from .helpers import (
    friendly_error_message,
    is_first_time_use,
    auto_install_playwright,
    quick_diagnostics,
    smart_init_prompt
)

__all__ = [
    # 核心工具
    'core_utils',
    'PlaywrightCoreUtils',
    'setup_playwright',
    'ensure_playwright_browsers_ready',

    # 简化的辅助函数
    'friendly_error_message',
    'is_first_time_use',
    'auto_install_playwright',
    'quick_diagnostics',
    'smart_init_prompt'
]
