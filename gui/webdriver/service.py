#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebDriver Service Manager
独立管理 WebDriver 的初始化、下载和状态监控
"""

import asyncio
import os
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass

from utils.logger_helper import logger_helper as logger
from .manager import WebDriverManager, get_webdriver_manager


@dataclass
class WebDriverStatus:
    """WebDriver 状态信息"""
    initialized: bool = False
    webdriver_path: Optional[str] = None
    chrome_version: Optional[str] = None
    download_progress: Optional[Dict[str, Any]] = None
    is_downloading: bool = False
    is_ready: bool = False
    error_message: Optional[str] = None


class WebDriverService:
    """WebDriver 服务管理器"""
    
    def __init__(self):
        self._manager: Optional[WebDriverManager] = None
        self._status = WebDriverStatus()
        self._initialization_task: Optional[asyncio.Task] = None
        self._monitoring_task: Optional[asyncio.Task] = None
        self._ready_callbacks: list[Callable] = []
        self._error_callbacks: list[Callable] = []
        self._progress_callbacks: list[Callable] = []
        
    async def initialize(self) -> bool:
        """初始化 WebDriver 服务"""
        try:
            logger.info("🔄 Starting WebDriver service initialization...")
            
            # Get WebDriver manager
            self._manager = await get_webdriver_manager()
            
            # Start async initialization
            success = await self._manager.initialize()
            
            if success:
                logger.info("✅ WebDriver service initialization started successfully")
                
                # Check if existing WebDriver is available
                if self._manager._webdriver_path:
                    self._status.webdriver_path = self._manager._webdriver_path
                    self._status.initialized = True
                    self._status.is_ready = True
                    logger.info(f"✅ Found existing WebDriver: {self._status.webdriver_path}")
                    await self._notify_ready()
                    return True
                else:
                    # Start background download monitoring
                    logger.info("📥 Starting background WebDriver download monitoring...")
                    self._monitoring_task = asyncio.create_task(self._monitor_download())
                    self._status.is_downloading = True
                    return True
            else:
                logger.error("❌ WebDriver service initialization failed")
                self._status.error_message = "Initialization failed"
                await self._notify_error("Initialization failed")
                return False
                
        except Exception as e:
            logger.error(f"WebDriver service initialization exception: {e}")
            self._status.error_message = str(e)
            await self._notify_error(str(e))
            return False
    
    async def _monitor_download(self):
        """Monitor WebDriver download progress"""
        try:
            logger.info("🔍 Starting WebDriver download progress monitoring...")
            
            # Monitor download progress, wait up to 10 minutes
            max_wait_time = 600  # 10 minutes
            check_interval = 3   # Check every 3 seconds
            elapsed_time = 0
            
            while elapsed_time < max_wait_time:
                # Check download status
                progress = self._manager.get_download_progress()
                is_complete = self._manager.is_download_complete()
                
                # Update status
                self._status.download_progress = progress
                
                if progress:
                    logger.info(f"📊 Download progress: {progress.get('progress', 0)}% - {progress.get('message', '')}")
                    await self._notify_progress(progress)
                
                # Check if completed
                if is_complete and self._manager._webdriver_path:
                    self._status.webdriver_path = self._manager._webdriver_path
                    self._status.initialized = True
                    self._status.is_ready = True
                    self._status.is_downloading = False
                    logger.info(f"🎉 WebDriver download completed: {self._status.webdriver_path}")
                    
                    await self._notify_ready()
                    return
                
                # Wait for next check
                await asyncio.sleep(check_interval)
                elapsed_time += check_interval
            
            # Timeout handling
            logger.warning("⏰ WebDriver download monitoring timeout")
            self._status.error_message = "Download timeout"
            self._status.is_downloading = False
            await self._notify_error("Download timeout")
            
        except Exception as e:
            logger.error(f"WebDriver download monitoring exception: {e}")
            self._status.error_message = str(e)
            self._status.is_downloading = False
            await self._notify_error(str(e))
    
    async def get_webdriver_path(self) -> Optional[str]:
        """获取 WebDriver 路径"""
        if self._manager:
            return await self._manager.get_webdriver_path()
        return None
    
    async def get_webdriver_instance(self) -> Optional[Any]:
        """获取 WebDriver 实例"""
        if self._manager:
            return await self._manager.get_webdriver_instance()
        return None
    
    def get_status(self) -> WebDriverStatus:
        """获取当前状态"""
        if self._manager:
            manager_status = self._manager.get_status()
            self._status.initialized = manager_status.get('initialized', False)
            self._status.webdriver_path = manager_status.get('webdriver_path')
            self._status.chrome_version = manager_status.get('chrome_version')
        
        return self._status
    
    def is_ready(self) -> bool:
        """检查是否准备就绪"""
        return self._status.is_ready
    
    def is_downloading(self) -> bool:
        """检查是否正在下载"""
        return self._status.is_downloading
    
    def get_download_progress(self) -> Optional[Dict[str, Any]]:
        """获取下载进度"""
        return self._status.download_progress
    
    # 回调管理
    def add_ready_callback(self, callback: Callable):
        """添加就绪回调"""
        self._ready_callbacks.append(callback)
    
    def add_error_callback(self, callback: Callable):
        """添加错误回调"""
        self._error_callbacks.append(callback)
    
    def add_progress_callback(self, callback: Callable):
        """添加进度回调"""
        self._progress_callbacks.append(callback)
    
    async def _notify_ready(self):
        """Notify ready status"""
        for callback in self._ready_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(self._status)
                else:
                    callback(self._status)
            except Exception as e:
                logger.error(f"Ready callback execution failed: {e}")
    
    async def _notify_error(self, error_msg: str):
        """Notify error status"""
        for callback in self._error_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(error_msg, self._status)
                else:
                    callback(error_msg, self._status)
            except Exception as e:
                logger.error(f"Error callback execution failed: {e}")
    
    async def _notify_progress(self, progress: Dict[str, Any]):
        """Notify progress update"""
        for callback in self._progress_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(progress, self._status)
                else:
                    callback(progress, self._status)
            except Exception as e:
                logger.error(f"Progress callback execution failed: {e}")
    
    async def cleanup(self):
        """Clean up resources"""
        try:
            if self._monitoring_task and not self._monitoring_task.done():
                self._monitoring_task.cancel()
            
            if self._manager:
                await self._manager.cleanup()
            
            logger.info("WebDriver service cleanup completed")
            
        except Exception as e:
            logger.error(f"WebDriver service cleanup failed: {e}")


# 全局服务实例
_webdriver_service: Optional[WebDriverService] = None
_service_lock = asyncio.Lock()


async def get_webdriver_service() -> WebDriverService:
    """获取 WebDriver 服务实例"""
    global _webdriver_service
    
    if _webdriver_service is None:
        async with _service_lock:
            if _webdriver_service is None:
                _webdriver_service = WebDriverService()
    
    return _webdriver_service


def get_webdriver_service_sync() -> WebDriverService:
    """同步获取 WebDriver 服务实例"""
    global _webdriver_service
    
    if _webdriver_service is None:
        _webdriver_service = WebDriverService()
    
    return _webdriver_service
