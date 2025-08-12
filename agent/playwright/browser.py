#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright 浏览器操作封装
提供高级的浏览器操作接口和错误处理
"""

from typing import Optional, Dict, Any, List
from pathlib import Path

from .manager import get_playwright_manager

from utils.logger_helper import logger_helper as logger


class PlaywrightBrowser:
    """
    Playwright 浏览器操作封装类
    
    提供高级的浏览器操作接口，自动处理初始化
    """
    
    def __init__(self):
        self._manager = get_playwright_manager()
        self._playwright = None
        self._browser = None
        self._context = None
    
    def _ensure_ready(self) -> bool:
        """
        确保浏览器环境已准备就绪
        
        Returns:
            bool: 是否准备就绪
        """
        if not self._manager.is_initialized():
            logger.info("Playwright not initialized, performing lazy initialization...")
            if not self._manager.lazy_init():
                logger.error("Failed to initialize Playwright")
                return False
        
        return True
    
    def launch_browser(self, headless: bool = True, max_retries: int = 2, **kwargs) -> Optional[Any]:
        """
        启动浏览器
        
        Args:
            headless: 是否无头模式
            max_retries: 最大重试次数
            **kwargs: 其他启动参数
            
        Returns:
            浏览器实例，失败时返回 None
        """
        if not self._ensure_ready():
            return None
        
        for attempt in range(max_retries):
            try:
                from playwright.sync_api import sync_playwright
                
                self._playwright = sync_playwright().start()
                
                # 设置启动参数
                launch_args = {
                    'headless': headless,
                    'args': [
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        '--disable-web-security',
                        '--disable-features=VizDisplayCompositor'
                    ]
                }
                
                # 合并用户提供的参数
                launch_args.update(kwargs)
                
                # 启动浏览器
                self._browser = self._playwright.chromium.launch(**launch_args)
                
                logger.info("Browser launched successfully")
                return self._browser
                
            except Exception as e:
                logger.warning(f"Browser launch attempt {attempt + 1} failed: {e}")
                
                # 清理资源
                if self._playwright:
                    try:
                        self._playwright.stop()
                    except:
                        pass
                    self._playwright = None
                
                # 如果不是最后一次尝试，等待后重试
                if attempt < max_retries - 1:
                    import time
                    wait_time = 2 ** attempt  # 指数退避
                    logger.info(f"Retrying browser launch in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed to launch browser after {max_retries} attempts")
                    return None
        
        return None
    
    def create_context(self, **kwargs) -> Optional[Any]:
        """
        创建浏览器上下文
        
        Args:
            **kwargs: 上下文参数
            
        Returns:
            上下文实例，失败时返回 None
        """
        if not self._browser:
            logger.error("Browser not launched")
            return None
        
        try:
            self._context = self._browser.new_context(**kwargs)
            logger.info("Browser context created successfully")
            return self._context
            
        except Exception as e:
            logger.error(f"Failed to create context: {e}")
            return None
    
    def create_page(self) -> Optional[Any]:
        """
        创建新页面
        
        Returns:
            页面实例，失败时返回 None
        """
        if not self._context:
            logger.error("Browser context not created")
            return None
        
        try:
            page = self._context.new_page()
            logger.info("New page created successfully")
            return page
            
        except Exception as e:
            logger.error(f"Failed to create page: {e}")
            return None
    
    def navigate_to(self, url: str, page: Optional[Any] = None) -> bool:
        """
        导航到指定URL
        
        Args:
            url: 目标URL
            page: 页面实例，如果为None则创建新页面
            
        Returns:
            bool: 是否成功
        """
        if not page:
            page = self.create_page()
            if not page:
                return False
        
        try:
            page.goto(url)
            logger.info(f"Navigated to: {url}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to navigate to {url}: {e}")
            return False
    
    def take_screenshot(self, page: Any, path: str, **kwargs) -> bool:
        """
        截图
        
        Args:
            page: 页面实例
            path: 保存路径
            **kwargs: 截图参数
            
        Returns:
            bool: 是否成功
        """
        try:
            page.screenshot(path=path, **kwargs)
            logger.info(f"Screenshot saved to: {path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to take screenshot: {e}")
            return False
    
    def get_page_content(self, page: Any) -> Optional[str]:
        """
        获取页面内容
        
        Args:
            page: 页面实例
            
        Returns:
            str: 页面内容，失败时返回 None
        """
        try:
            content = page.content()
            return content
            
        except Exception as e:
            logger.error(f"Failed to get page content: {e}")
            return None
    
    def close(self):
        """关闭浏览器和相关资源"""
        try:
            if self._context:
                self._context.close()
                self._context = None
                logger.info("Browser context closed")
            
            if self._browser:
                self._browser.close()
                self._browser = None
                logger.info("Browser closed")
            
            if self._playwright:
                self._playwright.stop()
                self._playwright = None
                logger.info("Playwright stopped")
                
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """
        获取当前状态
        
        Returns:
            Dict: 状态信息
        """
        return {
            "manager_initialized": self._manager.is_initialized(),
            "playwright_available": self._playwright is not None,
            "browser_available": self._browser is not None,
            "context_available": self._context is not None,
            "manager_status": self._manager.get_status()
        }
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()


# 便捷函数
def create_browser(headless: bool = True, max_retries: int = 2, **kwargs) -> Optional[PlaywrightBrowser]:
    """
    创建浏览器实例的便捷函数
    
    Args:
        headless: 是否无头模式
        max_retries: 最大重试次数
        **kwargs: 其他参数
        
    Returns:
        PlaywrightBrowser 实例
    """
    browser = PlaywrightBrowser()
    if browser.launch_browser(headless=headless, max_retries=max_retries, **kwargs):
        return browser
    return None


def with_browser(func):
    """
    装饰器：自动管理浏览器生命周期
    
    Usage:
        @with_browser
        def my_function(browser):
            # 使用 browser 进行操作
            pass
    """
    def wrapper(*args, **kwargs):
        browser = create_browser(max_retries=2)
        if not browser:
            raise RuntimeError("Failed to create browser after multiple attempts")
        
        try:
            return func(browser, *args, **kwargs)
        finally:
            browser.close()
    
    return wrapper
