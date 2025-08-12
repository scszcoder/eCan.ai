#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright 浏览器管理器
实现延迟初始化和浏览器生命周期管理
"""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from threading import Lock

from .core import setup_playwright, core_utils
from app_context import AppContext

from utils.logger_helper import logger_helper as logger


class PlaywrightManager:
    """
    Playwright 浏览器管理器
    
    特性：
    - 延迟初始化：只在需要时初始化
    - 线程安全：支持多线程环境
    - 状态管理：提供完整的状态信息
    - 错误处理：优雅的错误处理和恢复
    """
    
    def __init__(self):
        self._initialized = False
        self._browsers_path: Optional[str] = None
        self._lock = Lock()
        self.ctx = AppContext()
        self._initialization_error: Optional[str] = None
        
        # 延迟初始化标志
        self._lazy_init_done = False
    
    def _ensure_initialized(self) -> bool:
        """
        确保 Playwright 已初始化（线程安全）
        
        Returns:
            bool: 初始化是否成功
        """
        with self._lock:
            if self._initialized:
                return True
            
            if self._initialization_error:
                logger.warning(f"Playwright initialization previously failed: {self._initialization_error}")
                return False
            
            try:
                logger.info("Initializing Playwright browsers...")
                
                # 设置 Playwright 浏览器环境
                browsers_path = setup_playwright()
                
                if browsers_path and browsers_path.exists():
                    self._browsers_path = str(browsers_path)
                    
                    # 设置环境变量
                    core_utils.set_environment_variables(browsers_path)
                    
                    # 将 Playwright 路径保存到 AppContext 中
                    self.ctx.set_playwright_browsers_path(self._browsers_path)
                    
                    self._initialized = True
                    logger.info(f"Playwright browsers initialized at: {browsers_path}")
                    return True
                else:
                    error_msg = "Invalid Playwright browsers path"
                    self._initialization_error = error_msg
                    logger.error(error_msg)
                    return False
                    
            except Exception as e:
                error_msg = f"Playwright initialization failed: {e}"
                self._initialization_error = error_msg
                logger.error(error_msg)
                return False
    
    def get_browsers_path(self) -> Optional[str]:
        """
        获取 Playwright 浏览器路径
        
        Returns:
            str: 浏览器路径，如果未初始化则返回 None
        """
        if not self._ensure_initialized():
            return None
        return self._browsers_path
    
    def is_initialized(self) -> bool:
        """
        检查是否已初始化
        
        Returns:
            bool: 是否已初始化
        """
        with self._lock:
            return self._initialized
    
    def get_status(self) -> Dict[str, Any]:
        """
        获取当前状态信息
        
        Returns:
            Dict: 包含状态信息的字典
        """
        with self._lock:
            status = {
                "initialized": self._initialized,
                "browsers_path": self._browsers_path,
                "path_exists": Path(self._browsers_path).exists() if self._browsers_path else False,
                "initialization_error": self._initialization_error,
                "lazy_init_done": self._lazy_init_done
            }
            
            # 验证浏览器安装
            if self._browsers_path:
                status["browser_installation_valid"] = core_utils.validate_browser_installation(Path(self._browsers_path))
            else:
                status["browser_installation_valid"] = False
            
            return status
    
    def force_reinitialize(self) -> bool:
        """
        强制重新初始化（用于错误恢复）
        
        Returns:
            bool: 重新初始化是否成功
        """
        with self._lock:
            # 清除之前的状态
            self._initialized = False
            self._browsers_path = None
            self._initialization_error = None
            
            # 重新初始化
            return self._ensure_initialized()
    
    def lazy_init(self) -> bool:
        """
        延迟初始化（在第一次使用时调用）
        
        Returns:
            bool: 初始化是否成功
        """
        if self._lazy_init_done:
            return self._initialized
        
        self._lazy_init_done = True
        return self._ensure_initialized()
    
    def get_environment_info(self) -> Dict[str, Any]:
        """
        获取环境信息
        
        Returns:
            Dict: 环境信息字典
        """
        return {
            "platform": sys.platform,
            "frozen": getattr(sys, 'frozen', False),
            "meipass": getattr(sys, '_MEIPASS', None),
            "bundled_path": str(core_utils.get_bundled_path()) if core_utils.get_bundled_path() else None,
            "default_path": str(core_utils.get_default_browsers_path()),
            "app_data_path": str(core_utils.get_app_data_path()),
            "env_variables": {
                "PLAYWRIGHT_BROWSERS_PATH": os.getenv(core_utils.ENV_BROWSERS_PATH),
                "PLAYWRIGHT_CACHE_DIR": os.getenv(core_utils.ENV_CACHE_DIR),
                "PLAYWRIGHT_BROWSERS_PATH_OVERRIDE": os.getenv(core_utils.ENV_BROWSERS_PATH_OVERRIDE)
            }
        }
    
    def validate_installation(self) -> bool:
        """
        验证当前安装是否有效
        
        Returns:
            bool: 安装是否有效
        """
        if not self._initialized:
            return False
        
        if not self._browsers_path:
            return False
        
        return core_utils.validate_browser_installation(Path(self._browsers_path))
    
    def cleanup(self):
        """
        清理资源（如果需要的话）
        """
        with self._lock:
            # 清除环境变量
            core_utils.clear_environment_variables()
            
            # 重置状态
            self._initialized = False
            self._browsers_path = None
            self._initialization_error = None
            self._lazy_init_done = False
            
            logger.info("Playwright manager cleaned up")


# 全局管理器实例
_manager_instance: Optional[PlaywrightManager] = None
_manager_lock = Lock()


def get_playwright_manager() -> PlaywrightManager:
    """
    获取全局 Playwright 管理器实例（单例模式）
    
    Returns:
        PlaywrightManager: 管理器实例
    """
    global _manager_instance
    
    if _manager_instance is None:
        with _manager_lock:
            if _manager_instance is None:
                _manager_instance = PlaywrightManager()
    
    return _manager_instance


def initialize_playwright_lazy() -> bool:
    """
    便捷函数：延迟初始化 Playwright
    
    Returns:
        bool: 初始化是否成功
    """
    return get_playwright_manager().lazy_init()


def get_playwright_status() -> Dict[str, Any]:
    """
    便捷函数：获取 Playwright 状态
    
    Returns:
        Dict: 状态信息
    """
    return get_playwright_manager().get_status()
