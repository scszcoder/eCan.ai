#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一浏览器资源管理器
解决 crawl4ai、browser_use 和 Playwright 之间的资源冲突问题
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
    """统一的浏览器资源管理器"""
    
    def __init__(self):
        self._lock = Lock()
        self._initialized = False
        self._initialization_error = None
        
        # Playwright 管理器
        self._playwright_manager = None
        
        # 组件实例
        self._async_crawler = None
        self._browser_session = None
        self._browser_use_controller = None
        self._browser_use_file_system = None
        
        # 配置
        self._crawler_config = None
        self._file_system_path = None

        
    def initialize(self, crawler_config: Optional[Dict] = None, file_system_path: Optional[str] = None) -> bool:
        """初始化统一浏览器管理器"""
        with self._lock:
            if self._initialized:
                return True
                
            if self._initialization_error:
                logger.warning(f"Previous initialization failed: {self._initialization_error}")
                
            try:
                logger.info("🔧 开始初始化统一浏览器管理器...")

                if not self._init_playwright_manager():
                    raise RuntimeError("Playwright 管理器初始化失败")

                self._setup_crawler_config(crawler_config)
                self._file_system_path = file_system_path

                self._initialized = True
                self._initialization_error = None
                self.get_browser_session()  # 预热浏览器会话
                logger.info("✅ 统一浏览器管理器初始化成功")
                return True
                
            except Exception as e:
                self._initialization_error = str(e)
                logger.error(f"❌ 统一浏览器管理器初始化失败: {e}")
                return False
    
    def _init_playwright_manager(self) -> bool:
        """初始化 Playwright 管理器"""
        try:
            self._playwright_manager = get_playwright_manager()

            if not self._playwright_manager.is_initialized():
                logger.debug("初始化 Playwright 环境...")
                if not self._playwright_manager.lazy_init():
                    raise RuntimeError("Playwright 环境初始化失败")

            logger.debug("✅ Playwright 管理器就绪")
            return True

        except Exception as e:
            logger.error(f"Playwright 管理器初始化失败: {e}")
            return False


    
    def _setup_crawler_config(self, crawler_config: Optional[Dict]):
        """设置爬虫配置"""
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
        """设置 crawler 运行环境"""
        import os

        # 确保 Playwright 环境变量正确设置，让 crawl4ai 能找到浏览器
        if self._playwright_manager and self._playwright_manager.is_initialized():
            browsers_path = self._playwright_manager.get_browsers_path()
            if browsers_path:
                os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browsers_path
                os.environ["PLAYWRIGHT_CACHE_DIR"] = browsers_path
                logger.debug(f"设置 crawler 环境变量 PLAYWRIGHT_BROWSERS_PATH: {browsers_path}")






    
    def get_async_crawler(self) -> Optional["AsyncWebCrawler"]:
        if not self._initialized:
            logger.warning("管理器未初始化，无法获取 AsyncWebCrawler")
            return None

        if self._async_crawler is None:
            try:
                logger.debug("创建 AsyncWebCrawler 实例...")

                # 确保 Playwright 环境变量正确设置
                self._setup_crawler_environment()

                # 创建 BrowserConfig
                if self._crawler_config:
                    browser_config = BrowserConfig(**self._crawler_config)
                    from crawl4ai import AsyncWebCrawler
                    self._async_crawler = AsyncWebCrawler(config=browser_config)
                    logger.debug("✅ AsyncWebCrawler 创建成功（使用配置）")
                else:
                    from crawl4ai import AsyncWebCrawler
                    self._async_crawler = AsyncWebCrawler()
                    logger.debug("✅ AsyncWebCrawler 创建成功（默认配置）")

            except Exception as e:
                logger.error(f"创建 AsyncWebCrawler 失败: {e}")
                return None

        return self._async_crawler
    
    def get_browser_session(self) -> Optional[BrowserSession]:
        if not self._initialized:
            logger.warning("管理器未初始化，无法获取 BrowserSession")
            return None

        if self._browser_session is None:
            try:
                crawler = self.get_async_crawler()
                if not crawler:
                    logger.warning("无法创建 BrowserSession：爬虫未就绪")
                    return None

                if not hasattr(crawler, 'crawler_strategy') or crawler.crawler_strategy is None:
                    logger.warning("无法创建 BrowserSession：爬虫策略未就绪")
                    return None
                browser = crawler.crawler_strategy.browser_manager.browser
                self._browser_session = BrowserSession(browser=browser)
                logger.debug("✅ BrowserSession 创建成功")

            except Exception as e:
                logger.error(f"创建 BrowserSession 失败: {e}")
                return None

        return self._browser_session
    
    def get_browser_use_controller(self) -> Optional[BrowserUseController]:
        if not self._initialized:
            logger.warning("管理器未初始化，无法获取 BrowserUseController")
            return None

        if self._browser_use_controller is None:
            try:
                logger.debug("创建 BrowserUseController 实例...")
                display_files_in_done_text = True
                self._browser_use_controller = BrowserUseController(
                    display_files_in_done_text=display_files_in_done_text
                )
                logger.debug("✅ BrowserUseController 创建成功")

            except Exception as e:
                logger.error(f"创建 BrowserUseController 失败: {e}")
                return None

        return self._browser_use_controller
    
    def get_browser_use_file_system(self) -> Optional[FileSystem]:
        if not self._initialized:
            logger.warning("管理器未初始化，无法获取 BrowserUse FileSystem")
            return None

        if self._browser_use_file_system is None:
            try:
                if self._file_system_path:
                    self._browser_use_file_system = FileSystem(self._file_system_path)
                    logger.debug(f"✅ BrowserUse FileSystem 创建成功，路径: {self._file_system_path}")
                else:
                    self._browser_use_file_system = FileSystem()
                    logger.debug("✅ BrowserUse FileSystem 创建成功（默认路径）")
            except Exception as e:
                logger.error(f"创建 BrowserUse FileSystem 失败: {e}")
                return None

        return self._browser_use_file_system
    
    def cleanup(self):
        """清理所有资源"""
        with self._lock:
            try:
                # 清理组件实例
                self._async_crawler = None
                self._browser_session = None
                self._browser_use_controller = None
                self._browser_use_file_system = None

                self._initialized = False
                self._initialization_error = None
                logger.debug("统一浏览器管理器资源已清理")
            except Exception as e:
                logger.warning(f"清理资源时出错: {e}")
    
    def is_ready(self) -> bool:
        """检查管理器是否已准备好提供服务"""
        return self._initialized and self._initialization_error is None

    def get_status(self) -> Dict[str, Any]:
        """获取管理器状态"""
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




# 全局管理器实例
_unified_manager_instance: Optional[UnifiedBrowserManager] = None
_unified_manager_lock = Lock()


def get_unified_browser_manager() -> UnifiedBrowserManager:
    """
    获取全局统一浏览器管理器实例（单例模式）
    
    Returns:
        UnifiedBrowserManager: 管理器实例
    """
    global _unified_manager_instance
    
    if _unified_manager_instance is None:
        with _unified_manager_lock:
            if _unified_manager_instance is None:
                _unified_manager_instance = UnifiedBrowserManager()
    
    return _unified_manager_instance
