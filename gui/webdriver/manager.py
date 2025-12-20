#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebDriver Manager
Supports async lazy loading, automatic Chrome version detection, and dynamic downloading of matching webdriver
"""

import asyncio
import os
from typing import Optional, Dict, Any

from utils.logger_helper import logger_helper as logger
from .config import get_webdriver_dir
from .utils import detect_chrome_version, find_existing_webdriver
from .downloader import WebDriverDownloader


class WebDriverManager:
    """WebDriver Manager with async lazy loading and automatic download support"""
    
    def __init__(self):
        self._webdriver_path: Optional[str] = None
        self._webdriver_instance: Optional[Any] = None
        self._initialized = False
        self._initialization_lock = asyncio.Lock()
        self._chrome_version: Optional[str] = None
        self._webdriver_version: Optional[str] = None
        
        # Configuration
        self._webdriver_dir = get_webdriver_dir()
        self._downloader = WebDriverDownloader()
        
    async def initialize(self) -> bool:
        """Async initialization of WebDriver Manager"""
        async with self._initialization_lock:
            if self._initialized:
                return True
                
            try:
                logger.info("Starting WebDriver Manager initialization...")
                
                # Ensure webdriver directory exists
                os.makedirs(self._webdriver_dir, exist_ok=True)
                
                # Detect Chrome version in a separate thread to avoid blocking
                logger.info("Detecting Chrome version...")
                self._chrome_version = await asyncio.to_thread(detect_chrome_version)
                # self._chrome_version = detect_chrome_version()
                logger.info(f"Detected Chrome version: {self._chrome_version}")
                
                # Find or download matching webdriver
                if not await self._ensure_webdriver():
                    logger.error("Failed to ensure WebDriver availability")
                    # Don't raise exception, just return False to allow graceful fallback
                    return False
                
                self._initialized = True
                logger.info("WebDriver Manager initialization successful")
                return True
                
            except Exception as e:
                logger.error(f"WebDriver Manager initialization failed: {e}")
                return False
    
    async def _ensure_webdriver(self) -> bool:
        """Ensure matching webdriver is available, downloading if necessary."""
        try:
            # Priority 2: Check for an automatically cached webdriver.
            existing_driver = self._find_existing_webdriver()
            if existing_driver:
                self._webdriver_path = existing_driver
                logger.info(f"Found cached compatible WebDriver: {self._webdriver_path}")
                return True

            # Priority 3: Attempt to download a new webdriver.
            logger.info("No compatible WebDriver found. Attempting to download...")
            if not self._chrome_version:
                logger.error("Chrome version not detected, cannot download WebDriver.")
                return False

            driver_path = await self._downloader.download_webdriver(
                self._chrome_version,
                self._webdriver_dir
            )

            if driver_path:
                self._webdriver_path = driver_path
                logger.info(f"Successfully downloaded WebDriver to: {self._webdriver_path}")
                return True
            else:
                logger.error("Failed to download WebDriver.")
                return False

        except Exception as e:
            logger.error(f"An error occurred during WebDriver acquisition: {e}")
            return False
    
    def _find_fallback_webdriver(self) -> Optional[str]:
        """Find any available webdriver as fallback"""
        try:
            # Check common system paths
            import platform
            system = platform.system()
            
            if system == "Windows":
                # Check Windows common paths
                common_paths = [
                    r"C:\chromedriver.exe",
                    r"C:\Program Files\chromedriver.exe",
                    r"C:\Program Files (x86)\chromedriver.exe"
                ]
            elif system == "Darwin":  # macOS
                common_paths = [
                    "/usr/local/bin/chromedriver",
                    "/usr/bin/chromedriver",
                    "/opt/homebrew/bin/chromedriver"
                ]
            else:  # Linux
                common_paths = [
                    "/usr/local/bin/chromedriver",
                    "/usr/bin/chromedriver",
                    "/opt/chromedriver"
                ]
            
            for path in common_paths:
                if os.path.exists(path) and os.access(path, os.X_OK):
                    logger.info(f"Found fallback WebDriver at: {path}")
                    return path
            
            return None
            
        except Exception as e:
            logger.error(f"Fallback WebDriver search failed: {e}")
            return None
    
    def _find_existing_webdriver(self) -> Optional[str]:
        """Find existing webdriver"""
        try:
            # Check webdriver directory
            return find_existing_webdriver(self._webdriver_dir)
            
        except Exception as e:
            logger.error(f"Failed to find existing WebDriver: {e}")
            return None
    
    async def _download_webdriver(self) -> bool:
        """Download matching webdriver"""
        try:
            if not self._chrome_version:
                logger.error("Chrome version not detected, cannot download WebDriver")
                return False
            
            # Download webdriver using the downloader
            driver_path = await self._downloader.download_webdriver(
                self._chrome_version, 
                self._webdriver_dir
            )
            
            if driver_path:
                self._webdriver_path = driver_path
                return True
            
            return False
                
        except Exception as e:
            logger.error(f"WebDriver download failed: {e}")
            return False
    
    async def get_webdriver_path(self) -> Optional[str]:
        """Get webdriver path"""
        if not self._initialized:
            success = await self.initialize()
            if not success:
                logger.warning("WebDriver Manager initialization failed, returning None")
                return None
        return self._webdriver_path
    
    async def get_webdriver_instance(self) -> Optional[Any]:
        """Get webdriver instance (lazy loading)"""
        if not self._initialized:
            success = await self.initialize()
            if not success:
                logger.warning("WebDriver Manager initialization failed, returning None")
                return None
            
        if not self._webdriver_instance and self._webdriver_path:
            try:
                # Here you can create different types of webdriver instances as needed
                # For example Selenium WebDriver or others
                self._webdriver_instance = self._webdriver_path
                logger.info(f"WebDriver instance created successfully: {self._webdriver_path}")
            except Exception as e:
                logger.error(f"WebDriver instance creation failed: {e}")
                return None
        
        return self._webdriver_instance
    
    def get_status(self) -> Dict[str, Any]:
        """Get manager status"""
        return {
            "initialized": self._initialized,
            "webdriver_path": self._webdriver_path,
            "chrome_version": self._chrome_version,
            "webdriver_version": self._webdriver_version,
            "webdriver_dir": self._webdriver_dir
        }
    
    async def cleanup(self) -> None:
        """Clean up resources"""
        try:
            if self._webdriver_instance:
                # Here you can add logic to clean up webdriver instances
                self._webdriver_instance = None
            
            self._initialized = False
            logger.info("WebDriver Manager cleanup completed")
            
        except Exception as e:
            logger.error(f"WebDriver Manager cleanup failed: {e}")


# Global instance
_webdriver_manager: Optional[WebDriverManager] = None
_manager_lock = asyncio.Lock()


async def get_webdriver_manager() -> WebDriverManager:
    """Get WebDriver Manager instance"""
    global _webdriver_manager
    
    if _webdriver_manager is None:
        async with _manager_lock:
            if _webdriver_manager is None:
                _webdriver_manager = WebDriverManager()
    
    return _webdriver_manager


def get_webdriver_manager_sync() -> WebDriverManager:
    """Synchronously get WebDriver Manager instance (for non-async environments)"""
    global _webdriver_manager
    
    if _webdriver_manager is None:
        _webdriver_manager = WebDriverManager()
    
    return _webdriver_manager
