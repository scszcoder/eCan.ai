#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright 浏览器管理包
提供延迟初始化的 Playwright 浏览器管理功能
"""

from .manager import PlaywrightManager, get_playwright_manager
from .decorators import ensure_playwright_initialized, with_playwright_context, browser_use_ready, safe_playwright
from .core import core_utils, setup_playwright

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
    'ensure_playwright_initialized',
    'create_browser_use_llm'
]
