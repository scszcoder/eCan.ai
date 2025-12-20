#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright Browser Operations Wrapper
Provides high-level browser operation interfaces and error handling
"""

from typing import Optional, Dict, Any, List
from pathlib import Path

from .manager import get_playwright_manager

from utils.logger_helper import logger_helper as logger


class PlaywrightBrowser:
    """
    Playwright Browser Operations Wrapper Class

    Provides high-level browser operation interfaces with automatic initialization handling
    """
    
    def __init__(self):
        self._manager = get_playwright_manager()
        self._playwright = None
        self._browser = None
        self._context = None
    
    def _ensure_ready(self) -> bool:
        """
        Ensure browser environment is ready

        Returns:
            bool: Whether ready
        """
        if not self._manager.is_initialized():
            logger.info("Playwright not initialized, performing lazy initialization...")
            if not self._manager.lazy_init():
                logger.error("Failed to initialize Playwright")
                return False
        
        return True
    
    def launch_browser(self, headless: bool = True, max_retries: int = 2, **kwargs) -> Optional[Any]:
        """
        Launch browser

        Args:
            headless: Whether to run in headless mode
            max_retries: Maximum retry attempts
            **kwargs: Other launch parameters

        Returns:
            Browser instance, or None if failed
        """
        if not self._ensure_ready():
            return None
        
        for attempt in range(max_retries):
            try:
                from playwright.sync_api import sync_playwright
                
                self._playwright = sync_playwright().start()
                
                # Set launch parameters
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

                # Merge user-provided parameters
                launch_args.update(kwargs)

                # Launch browser
                self._browser = self._playwright.chromium.launch(**launch_args)
                
                logger.info("Browser launched successfully")
                return self._browser
                
            except Exception as e:
                logger.warning(f"Browser launch attempt {attempt + 1} failed: {e}")
                
                # Clean up resources
                if self._playwright:
                    try:
                        self._playwright.stop()
                    except:
                        pass
                    self._playwright = None
                
                # If not the last attempt, wait and retry
                if attempt < max_retries - 1:
                    import time
                    wait_time = 2 ** attempt  # exponential backoff
                    logger.info(f"Retrying browser launch in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed to launch browser after {max_retries} attempts")
                    return None
        
        return None
    
    def create_context(self, **kwargs) -> Optional[Any]:
        """
        Create browser context
        
        Args:
            **kwargs: context parameters
            
        Returns:
            Context instance, or None if failed
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
        Create new page
        
        Returns:
            Page instance, or None if failed
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
        Navigate to specified URL
        
        Args:
            url: target URL
            page: page instance, create new page if None
            
        Returns:
            bool: whether successful
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
        Take screenshot
        
        Args:
            page: page instance
            path: save path
            **kwargs: screenshot parameters
            
        Returns:
            bool: whether successful
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
        Get page content
        
        Args:
            page: page instance
            
        Returns:
            str: page content, or None if failed
        """
        try:
            content = page.content()
            return content
            
        except Exception as e:
            logger.error(f"Failed to get page content: {e}")
            return None
    
    def close(self):
        """Close browser and related resources"""
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
        Get current status
        
        Returns:
            Dict: status information
        """
        return {
            "manager_initialized": self._manager.is_initialized(),
            "playwright_available": self._playwright is not None,
            "browser_available": self._browser is not None,
            "context_available": self._context is not None,
            "manager_status": self._manager.get_status()
        }
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


# Convenience functions
def create_browser(headless: bool = True, max_retries: int = 2, **kwargs) -> Optional[PlaywrightBrowser]:
    """
    Convenience function to create browser instance
    
    Args:
        headless: whether to run in headless mode
        max_retries: maximum retry attempts
        **kwargs: other parameters
        
    Returns:
        PlaywrightBrowser instance
    """
    browser = PlaywrightBrowser()
    if browser.launch_browser(headless=headless, max_retries=max_retries, **kwargs):
        return browser
    return None


def with_browser(func):
    """
    Decorator: automatically manage browser lifecycle
    
    Usage:
        @with_browser
        def my_function(browser):
            # use browser for operations
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
