#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright 浏览器管理包
提供延迟初始化的 Playwright 浏览器管理功能
"""

import sys
import os

from .manager import PlaywrightManager, get_playwright_manager
from .decorators import ensure_playwright_initialized, with_playwright_context, browser_use_ready, safe_playwright
from .core import core_utils, setup_playwright

# PyInstaller 环境自动设置
_auto_setup_completed = False

def _auto_setup_pyinstaller_environment():
    """在 PyInstaller 环境中自动设置 Playwright"""
    global _auto_setup_completed

    if _auto_setup_completed:
        return

    try:
        # 只在 PyInstaller 环境中自动设置
        if getattr(sys, 'frozen', False):
            from .core.setup import ensure_playwright_browsers_ready

            # 尝试设置 Playwright 环境
            try:
                browsers_path = ensure_playwright_browsers_ready()
                print(f"[PLAYWRIGHT] PyInstaller auto-setup completed: {browsers_path}")
            except Exception as e:
                print(f"[PLAYWRIGHT] PyInstaller auto-setup failed: {e}")
                # 不阻止应用启动，只是记录错误

        _auto_setup_completed = True

    except Exception as e:
        print(f"[PLAYWRIGHT] PyInstaller auto-setup error: {e}")
        # 不阻止应用启动

# 在模块导入时自动执行 PyInstaller 环境设置
_auto_setup_pyinstaller_environment()

def ensure_playwright_initialized():
    """确保 Playwright 已初始化的便捷函数"""
    try:
        manager = get_playwright_manager()
        if not manager.is_initialized():
            return manager.lazy_init()
        return True
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to initialize Playwright: {e}")
        return False


def get_playwright_browsers_path():
    """获取 Playwright 浏览器路径的便捷函数"""
    try:
        from .core.setup import get_playwright_browsers_path
        return get_playwright_browsers_path()
    except ImportError:
        return os.environ.get('PLAYWRIGHT_BROWSERS_PATH')


def is_playwright_ready():
    """检查 Playwright 是否准备就绪的便捷函数"""
    try:
        from .core.setup import is_playwright_ready
        return is_playwright_ready()
    except ImportError:
        # 简单检查环境变量
        path = os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
        return path is not None and os.path.exists(path)


def create_browser_use_llm(fallback_llm):
    """创建 BrowserUse LLM 的便捷函数

    Args:
        fallback_llm: 备用 LLM，当 Playwright 初始化失败时使用

    Returns:
        BrowserUseChatOpenAI 或备用 LLM
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


# 导出主要的管理器类、装饰器和核心功能
__all__ = [
    'PlaywrightManager',
    'get_playwright_manager',
    'ensure_playwright_initialized',
    'with_playwright_context',
    'browser_use_ready',
    'safe_playwright',
    'core_utils',
    'setup_playwright',
    'get_playwright_browsers_path',
    'is_playwright_ready',
    'create_browser_use_llm'
]
