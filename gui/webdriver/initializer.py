#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebDriver Initializer
在应用启动时自动初始化 WebDriver 服务
"""

import asyncio
from typing import Optional, Callable, Any

from utils.logger_helper import logger_helper as logger
from .service import get_webdriver_service, WebDriverStatus


class WebDriverInitializer:
    """WebDriver 初始化器"""
    
    def __init__(self):
        self._service = None
        self._initialization_task: Optional[asyncio.Task] = None
        self._ready_callbacks: list[Callable] = []
        self._error_callbacks: list[Callable] = []
        self._progress_callbacks: list[Callable] = []
        
    async def start_initialization(self) -> bool:
        """Start WebDriver initialization"""
        try:
            logger.info("🚀 Starting WebDriver automatic initialization...")
            
            # Get service instance
            self._service = await get_webdriver_service()
            
            # Set callbacks
            self._service.add_ready_callback(self._on_ready)
            self._service.add_error_callback(self._on_error)
            self._service.add_progress_callback(self._on_progress)
            
            # Start initialization task
            self._initialization_task = asyncio.create_task(self._service.initialize())
            
            logger.info("✅ WebDriver automatic initialization started")
            return True
            
        except Exception as e:
            logger.error(f"❌ WebDriver automatic initialization startup failed: {e}")
            return False
    
    async def wait_for_ready(self, timeout: float = 600) -> bool:
        """Wait for WebDriver to be ready"""
        try:
            if not self._service:
                logger.error("WebDriver service not initialized")
                return False
            
            # Wait for initialization to complete
            if self._initialization_task:
                try:
                    await asyncio.wait_for(self._initialization_task, timeout=timeout)
                except asyncio.TimeoutError:
                    logger.warning(f"WebDriver initialization timeout ({timeout} seconds)")
                    return False
            
            # Wait for service to be ready
            start_time = asyncio.get_event_loop().time()
            while not self._service.is_ready():
                if asyncio.get_event_loop().time() - start_time > timeout:
                    logger.warning(f"WebDriver ready timeout ({timeout} seconds)")
                    return False
                await asyncio.sleep(1)
            
            logger.info("✅ WebDriver ready")
            return True
            
        except Exception as e:
            logger.error(f"Failed to wait for WebDriver ready: {e}")
            return False
    
    def is_ready(self) -> bool:
        """Check if ready"""
        return self._service and self._service.is_ready()
    
    def is_downloading(self) -> bool:
        """Check if downloading"""
        return self._service and self._service.is_downloading()
    
    def get_status(self) -> Optional[WebDriverStatus]:
        """Get status"""
        return self._service.get_status() if self._service else None
    
    def get_download_progress(self) -> Optional[dict]:
        """Get download progress"""
        return self._service.get_download_progress() if self._service else None
    
    async def get_webdriver_path(self) -> Optional[str]:
        """Get WebDriver path"""
        return await self._service.get_webdriver_path() if self._service else None
    
    async def get_webdriver_instance(self) -> Optional[Any]:
        """Get WebDriver instance"""
        return await self._service.get_webdriver_instance() if self._service else None
    
    # Callback management
    def add_ready_callback(self, callback: Callable):
        """Add ready callback"""
        self._ready_callbacks.append(callback)
    
    def add_error_callback(self, callback: Callable):
        """Add error callback"""
        self._error_callbacks.append(callback)
    
    def add_progress_callback(self, callback: Callable):
        """Add progress callback"""
        self._progress_callbacks.append(callback)
    
    async def _on_ready(self, status: WebDriverStatus):
        """Ready callback handling"""
        logger.info("🎯 WebDriver initializer received ready notification")
        for callback in self._ready_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(status)
                else:
                    callback(status)
            except Exception as e:
                logger.error(f"Ready callback execution failed: {e}")
    
    async def _on_error(self, error_msg: str, status: WebDriverStatus):
        """Error callback handling"""
        logger.error(f"❌ WebDriver initializer received error notification: {error_msg}")
        for callback in self._error_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(error_msg, status)
                else:
                    callback(error_msg, status)
            except Exception as e:
                logger.error(f"Error callback execution failed: {e}")
    
    async def _on_progress(self, progress: dict, status: WebDriverStatus):
        """Progress callback handling"""
        for callback in self._progress_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(progress, status)
                else:
                    callback(progress, status)
            except Exception as e:
                logger.error(f"Progress callback execution failed: {e}")
    
    async def cleanup(self):
        """Clean up resources"""
        try:
            if self._initialization_task and not self._initialization_task.done():
                self._initialization_task.cancel()
            
            if self._service:
                await self._service.cleanup()
            
            logger.info("WebDriver initializer cleanup completed")
            
        except Exception as e:
            logger.error(f"WebDriver initializer cleanup failed: {e}")


# 全局初始化器实例
_webdriver_initializer: Optional[WebDriverInitializer] = None
_initializer_lock = asyncio.Lock()


async def get_webdriver_initializer() -> WebDriverInitializer:
    """获取 WebDriver 初始化器实例"""
    global _webdriver_initializer
    
    if _webdriver_initializer is None:
        async with _initializer_lock:
            if _webdriver_initializer is None:
                _webdriver_initializer = WebDriverInitializer()
    
    return _webdriver_initializer


def get_webdriver_initializer_sync() -> WebDriverInitializer:
    """同步获取 WebDriver 初始化器实例"""
    global _webdriver_initializer
    
    if _webdriver_initializer is None:
        _webdriver_initializer = WebDriverInitializer()
    
    return _webdriver_initializer


async def start_webdriver_initialization() -> bool:
    """Start WebDriver automatic initialization (convenience function)"""
    try:
        initializer = await get_webdriver_initializer()
        return await initializer.start_initialization()
    except Exception as e:
        logger.error(f"Failed to start WebDriver automatic initialization: {e}")
        return False
