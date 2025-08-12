#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright 初始化装饰器
提供自动初始化 Playwright 的装饰器功能
"""

import functools
from typing import Callable, Any

from .manager import get_playwright_manager

from utils.logger_helper import logger_helper as logger


def ensure_playwright_initialized(func: Callable) -> Callable:
    """
    装饰器：确保 Playwright 已初始化
    
    用法：
        @ensure_playwright_initialized
        def my_function():
            # 在这里使用 Playwright 功能
            pass
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            # 获取 Playwright 管理器
            manager = get_playwright_manager()
            
            # 检查是否需要初始化
            if not manager.is_initialized():
                logger.info(f"Auto-initializing Playwright for function: {func.__name__}")
                if not manager.lazy_init():
                    logger.warning(f"Failed to initialize Playwright for function: {func.__name__}")
                    # 继续执行函数，但可能失败
            
            # 执行原函数
            return func(*args, **kwargs)
            
        except Exception as e:
            logger.error(f"Error in Playwright initialization for function {func.__name__}: {e}")
            # 继续执行函数，但可能失败
            return func(*args, **kwargs)
    
    return wrapper


def with_playwright_context(func: Callable) -> Callable:
    """
    装饰器：提供 Playwright 上下文
    
    用法：
        @with_playwright_context
        def my_function(playwright_manager):
            # playwright_manager 是已初始化的管理器
            pass
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            # 获取并初始化 Playwright 管理器
            manager = get_playwright_manager()
            
            if not manager.is_initialized():
                logger.info(f"Initializing Playwright for function: {func.__name__}")
                if not manager.lazy_init():
                    logger.error(f"Failed to initialize Playwright for function: {func.__name__}")
                    raise RuntimeError("Playwright initialization failed")
            
            # 将管理器作为第一个参数传递给函数
            return func(manager, *args, **kwargs)
            
        except Exception as e:
            logger.error(f"Error in Playwright context for function {func.__name__}: {e}")
            raise
    
    return wrapper


def browser_use_ready(func: Callable) -> Callable:
    """
    装饰器：确保 BrowserUse 功能可用
    
    专门为 BrowserUse 相关函数设计的装饰器
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            # 获取 Playwright 管理器
            manager = get_playwright_manager()
            
            # 检查是否需要初始化
            if not manager.is_initialized():
                logger.info(f"Initializing Playwright for BrowserUse function: {func.__name__}")
                if not manager.lazy_init():
                    logger.warning(f"Failed to initialize Playwright for BrowserUse function: {func.__name__}")
                    # BrowserUse 可能无法正常工作，但继续执行
            
            # 执行原函数
            return func(*args, **kwargs)
            
        except Exception as e:
            logger.error(f"Error in BrowserUse Playwright initialization for function {func.__name__}: {e}")
            # 继续执行函数
            return func(*args, **kwargs)
    
    return wrapper


def safe_playwright(func: Callable) -> Callable:
    """
    装饰器：安全的 Playwright 操作
    
    如果 Playwright 初始化失败，返回 None 或默认值
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            # 获取 Playwright 管理器
            manager = get_playwright_manager()
            
            # 尝试初始化
            if not manager.is_initialized():
                logger.info(f"Attempting to initialize Playwright for function: {func.__name__}")
                if not manager.lazy_init():
                    logger.warning(f"Playwright initialization failed for function: {func.__name__}")
                    return None  # 返回 None 表示失败
            
            # 执行原函数
            return func(*args, **kwargs)
            
        except Exception as e:
            logger.error(f"Error in safe Playwright operation for function {func.__name__}: {e}")
            return None  # 返回 None 表示失败
    
    return wrapper
