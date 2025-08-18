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
from .utils import detect_chrome_version, find_existing_webdriver, find_project_webdriver
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
                
                # Detect Chrome version
                self._chrome_version = detect_chrome_version()
                
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
        """Ensure matching webdriver is available"""
        try:
            # First check existing directories
            existing_driver = self._find_existing_webdriver()
            if existing_driver:
                self._webdriver_path = existing_driver
                logger.info(f"Found existing WebDriver: {self._webdriver_path}")
                return True
            
            # Try to download matching webdriver in background
            logger.info("No existing WebDriver found, starting background download...")
            download_id = self._start_background_download()
            
            # Return True to indicate initialization started, actual result will come later
            return True
            
        except Exception as e:
            logger.error(f"WebDriver acquisition failed: {e}")
            return False
    
    def _start_background_download(self) -> str:
        """Start background download of WebDriver"""
        try:
            if not self._chrome_version:
                logger.error("Chrome version not detected, cannot start download")
                return ""
            
            # Start background download with custom callback
            download_id = self._downloader.start_background_download(
                self._chrome_version,
                self._webdriver_dir,
                self._download_progress_callback
            )
            
            # Save download ID for status checking
            self._current_download_id = download_id
            
            logger.info(f"Background download started with ID: {download_id}")
            return download_id
            
        except Exception as e:
            logger.error(f"Failed to start background download: {e}")
            return ""
    
    def _download_progress_callback(self, progress: int, message: str):
        """Callback for download progress updates"""
        logger.info(f"Download progress: {progress}% - {message}")
        
        # Update status for external monitoring
        self._download_progress = {"progress": progress, "message": message}
        
        # Check if download is complete
        if progress == 100 and "completed" in message.lower():
            # Try to find the downloaded webdriver
            try:
                from .utils import find_existing_webdriver
                downloaded_path = find_existing_webdriver(self._webdriver_dir)
                if downloaded_path:
                    self._webdriver_path = downloaded_path
                    logger.info(f"✅ WebDriver path updated after download: {self._webdriver_path}")
                else:
                    logger.warning("Download completed but WebDriver file not found")
            except Exception as e:
                logger.error(f"Failed to update WebDriver path after download: {e}")
        
        # Also check if we have a result from the downloader
        if hasattr(self, '_current_download_id') and self._current_download_id:
            status = self._downloader.get_download_status(self._current_download_id)
            if status and status.get('status') == 'completed' and status.get('result'):
                self._webdriver_path = status.get('result')
                logger.info(f"✅ WebDriver path updated from download result: {self._webdriver_path}")
    
    def get_download_progress(self) -> Optional[dict]:
        """Get current download progress"""
        return getattr(self, '_download_progress', None)
    
    def is_download_complete(self) -> bool:
        """Check if background download is complete"""
        # This is a simplified check - in a real implementation you'd track the actual download status
        return self._webdriver_path is not None
    
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
            # Check project directory for webdriver
            project_driver = find_project_webdriver()
            if project_driver:
                return project_driver
            
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
