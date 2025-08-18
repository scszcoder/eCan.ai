#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified Browser Resource Manager
Resolves resource conflicts between crawl4ai, browser_use, and Playwright
"""

from typing import Optional, Any, Dict, TYPE_CHECKING
from threading import Lock

from agent.playwright import get_playwright_manager
from crawl4ai import BrowserConfig
from browser_use.browser import BrowserSession
from browser_use.controller.service import Controller as BrowserUseController
from browser_use.filesystem.file_system import FileSystem

from utils.logger_helper import logger_helper as logger

if TYPE_CHECKING:
    from crawl4ai import AsyncWebCrawler


class UnifiedBrowserManager:
    """Unified browser resource manager"""

    def __init__(self):
        self._lock = Lock()
        self._initialized = False
        self._initialization_error = None

        # Playwright manager
        self._playwright_manager = None

        # Component instances
        self._async_crawler = None
        self._browser_session = None
        self._browser_use_controller = None
        self._browser_use_file_system = None

        # Configuration
        self._crawler_config = None
        self._file_system_path = None

        
    def initialize(self, crawler_config: Optional[Dict] = None, file_system_path: Optional[str] = None) -> bool:
        """Initialize unified browser manager"""
        with self._lock:
            if self._initialized:
                return True

            if self._initialization_error:
                logger.warning(f"Previous initialization failed: {self._initialization_error}")

            try:
                logger.info("🔧 Starting unified browser manager initialization...")

                if not self._init_playwright_manager():
                    raise RuntimeError("Playwright manager initialization failed")

                # Set environment variables immediately to ensure subsequent components can find browsers
                self._setup_crawler_environment()

                self._setup_crawler_config(crawler_config)
                self._file_system_path = file_system_path

                self._initialized = True
                self._initialization_error = None
                logger.info("✅ Unified browser manager initialized successfully")
                return True

            except Exception as e:
                self._initialization_error = str(e)
                logger.error(f"❌ Unified browser manager initialization failed: {e}")
                return False
    
    def _init_playwright_manager(self) -> bool:
        """Initialize Playwright manager"""
        try:
            self._playwright_manager = get_playwright_manager()

            if not self._playwright_manager.is_initialized():
                logger.debug("Initializing Playwright environment...")
                if not self._playwright_manager.lazy_init():
                    raise RuntimeError("Playwright environment initialization failed")

            logger.debug("✅ Playwright manager ready")
            return True

        except Exception as e:
            logger.error(f"Playwright manager initialization failed: {e}")
            return False


    
    def _setup_crawler_config(self, crawler_config: Optional[Dict]):
        """Setup crawler configuration"""
        default_config = {
            'headless': False,
            'verbose': True,
            'viewport_width': 1920,
            'viewport_height': 1080
        }

        if crawler_config:
            default_config.update(crawler_config)

        self._crawler_config = default_config

    def _setup_crawler_environment(self):
        """Setup crawler runtime environment"""
        import os

        # Ensure Playwright environment variables are set correctly so crawl4ai can find browsers
        if self._playwright_manager and self._playwright_manager.is_initialized():
            browsers_path = self._playwright_manager.get_browsers_path()
            if browsers_path:
                os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browsers_path
                os.environ["PLAYWRIGHT_CACHE_DIR"] = browsers_path
                logger.debug(f"Set crawler environment variable PLAYWRIGHT_BROWSERS_PATH: {browsers_path}")
            else:
                logger.warning("Playwright manager is initialized but browser path is empty")
        else:
            logger.warning("Playwright manager is not initialized or not ready")






    
    def get_async_crawler(self) -> Optional["AsyncWebCrawler"]:
        if not self._initialized:
            logger.warning("Manager not initialized, cannot get AsyncWebCrawler")
            return None

        if self._async_crawler is None:
            try:
                logger.debug("Creating AsyncWebCrawler instance...")

                # Ensure Playwright environment variables are set correctly
                self._setup_crawler_environment()

                # Verify environment variables are set successfully
                import os
                browsers_path = os.getenv("PLAYWRIGHT_BROWSERS_PATH")
                if not browsers_path:
                    raise RuntimeError("PLAYWRIGHT_BROWSERS_PATH environment variable not set")

                logger.debug(f"Using browser path: {browsers_path}")

                # Create BrowserConfig
                if self._crawler_config:
                    browser_config = BrowserConfig(**self._crawler_config)
                    from crawl4ai import AsyncWebCrawler
                    self._async_crawler = AsyncWebCrawler(config=browser_config)
                    logger.debug("✅ AsyncWebCrawler created successfully (with config)")
                else:
                    from crawl4ai import AsyncWebCrawler
                    self._async_crawler = AsyncWebCrawler()
                    logger.debug("✅ AsyncWebCrawler created successfully (default config)")

            except Exception as e:
                logger.error(f"Failed to create AsyncWebCrawler: {e}")
                # Output more detailed error information
                import traceback
                logger.error(f"Detailed error info: {traceback.format_exc()}")
                return None

        return self._async_crawler
    
    def get_browser_session(self) -> Optional[BrowserSession]:
        """Get BrowserSession instance (lazy creation)"""
        if not self._initialized:
            logger.warning("Manager not initialized, cannot get BrowserSession")
            return None

        if self._browser_session is None:
            try:
                # Note: BrowserSession needs to be created after AsyncWebCrawler is started
                # This is just preparation, actual creation should be done when needed
                logger.debug("BrowserSession will be created when needed")
                return None

            except Exception as e:
                logger.error(f"Failed to prepare BrowserSession: {e}")
                return None

        return self._browser_session
    
    def get_browser_use_controller(self) -> Optional[BrowserUseController]:
        if not self._initialized:
            logger.warning("Manager not initialized, cannot get BrowserUseController")
            return None

        if self._browser_use_controller is None:
            try:
                logger.debug("Creating BrowserUseController instance...")
                display_files_in_done_text = True
                self._browser_use_controller = BrowserUseController(
                    display_files_in_done_text=display_files_in_done_text
                )
                logger.debug("✅ BrowserUseController created successfully")

            except Exception as e:
                logger.error(f"Failed to create BrowserUseController: {e}")
                return None

        return self._browser_use_controller
    
    def get_browser_use_file_system(self) -> Optional[FileSystem]:
        if not self._initialized:
            logger.warning("Manager not initialized, cannot get BrowserUse FileSystem")
            return None

        if self._browser_use_file_system is None:
            try:
                if self._file_system_path:
                    self._browser_use_file_system = FileSystem(self._file_system_path)
                    logger.debug(f"✅ BrowserUse FileSystem created successfully, path: {self._file_system_path}")
                else:
                    self._browser_use_file_system = FileSystem()
                    logger.debug("✅ BrowserUse FileSystem created successfully (default path)")
            except Exception as e:
                logger.error(f"Failed to create BrowserUse FileSystem: {e}")
                return None

        return self._browser_use_file_system
    
    def cleanup(self):
        """Clean up all resources"""
        with self._lock:
            try:
                # Clean up component instances
                self._async_crawler = None
                self._browser_session = None
                self._browser_use_controller = None
                self._browser_use_file_system = None

                self._initialized = False
                self._initialization_error = None
                logger.debug("Unified browser manager resources cleaned up")
            except Exception as e:
                logger.warning(f"Error during resource cleanup: {e}")

    def is_ready(self) -> bool:
        """Check if manager is ready to provide services"""
        return self._initialized and self._initialization_error is None

    def get_status(self) -> Dict[str, Any]:
        """Get manager status"""
        return {
            'initialized': self._initialized,
            'ready': self.is_ready(),
            'initialization_error': self._initialization_error,
            'async_crawler_ready': self._async_crawler is not None,
            'browser_session_ready': self._browser_session is not None,
            'browser_use_controller_ready': self._browser_use_controller is not None,
            'browser_use_file_system_ready': self._browser_use_file_system is not None,
            'playwright_manager_status': self._playwright_manager.get_status() if self._playwright_manager else None
        }




# Global manager instance
_unified_manager_instance: Optional[UnifiedBrowserManager] = None
_unified_manager_lock = Lock()


def get_unified_browser_manager() -> UnifiedBrowserManager:
    """
    Get global unified browser manager instance (singleton pattern)

    Returns:
        UnifiedBrowserManager: Manager instance
    """
    global _unified_manager_instance

    if _unified_manager_instance is None:
        with _unified_manager_lock:
            if _unified_manager_instance is None:
                _unified_manager_instance = UnifiedBrowserManager()

    return _unified_manager_instance
