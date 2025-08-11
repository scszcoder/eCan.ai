import os
import platform
import subprocess
import threading
import time
from typing import Optional, Callable
from threading import Lock, Event

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from config.app_info import app_info
    from config.constants import APP_NAME
except ImportError:
    # 如果导入失败，使用默认值
    class DefaultAppInfo:
        def __init__(self):
            self.app_home_path = str(Path.cwd())
    
    app_info = DefaultAppInfo()
    APP_NAME = 'ecbot'
from utils.logger_helper import logger_helper as logger

from .config import ota_config
from .package_manager import package_manager, UpdatePackage
from .platforms import SparkleUpdater, WinSparkleUpdater, GenericUpdater
from .errors import UpdateError, UpdateErrorCode, get_user_friendly_message


class OTAUpdater:
    """OTA更新管理器"""
    
    def __init__(self):
        self.platform = platform.system()
        self.app_version = ota_config.get('app_version', '1.0.0')
        self.update_server_url = ota_config.get_update_server()
        
        # 线程安全相关
        self._check_lock = Lock()  # 检查更新锁
        self._install_lock = Lock()  # 安装更新锁
        self._callback_lock = Lock()  # 回调锁
        self._stop_event = Event()  # 停止事件
        
        self.is_checking = False
        self.is_installing = False
        self.update_callback: Optional[Callable] = None
        self.error_callback: Optional[Callable] = None
        self._auto_check_thread = None
        
        # 获取应用路径
        self.app_home_path = app_info.app_home_path
        
        # 平台特定的更新器
        self.platform_updater = self._create_platform_updater()
        
        logger.info(f"OTA Updater initialized for {self.platform}")
    
    def _create_platform_updater(self):
        """创建平台特定的更新器"""
        # 开发模式可强制使用通用更新器，便于本地无平台依赖的调试
        try:
            if ota_config.is_dev_mode() and ota_config.get("force_generic_updater_in_dev", True):
                return GenericUpdater(self)
        except Exception:
            pass
        if self.platform == "Darwin":
            return SparkleUpdater(self)
        elif self.platform == "Windows":
            return WinSparkleUpdater(self)
        else:
            return GenericUpdater(self)
    
    def check_for_updates(self, silent: bool = False) -> bool:
        """检查更新"""
        with self._check_lock:
            if self.is_checking:
                if not silent:
                    logger.info("Update check already in progress")
                return False
            
            self.is_checking = True
        
        try:
            logger.info("Checking for updates...")
            
            has_update, update_info = self.platform_updater.check_for_updates(silent, return_info=True)
            
            # 检查是否返回了错误信息
            if isinstance(update_info, UpdateError):
                # 线程安全地调用错误回调
                self._safe_error_callback(update_info)
                return False
            
            # 线程安全地调用回调
            if has_update:
                self._safe_callback(has_update, update_info)
            
            return has_update
            
        except UpdateError as e:
            logger.error(f"Update check failed: {e}")
            self._safe_error_callback(e)
            return False
        except Exception as e:
            logger.error(f"Update check failed with unexpected error: {e}")
            error = UpdateError(
                UpdateErrorCode.UNKNOWN_ERROR,
                f"Unexpected error during update check: {str(e)}",
                {"original_error": str(e)}
            )
            self._safe_error_callback(error)
            return False
        finally:
            with self._check_lock:
                self.is_checking = False
    
    def install_update(self) -> bool:
        """安装更新"""
        with self._install_lock:
            if self.is_installing:
                logger.info("Update installation already in progress")
                return False
            
            self.is_installing = True
        
        try:
            logger.info("Installing update...")
            result = self.platform_updater.install_update(package_manager=package_manager)
            return result
        except Exception as e:
            logger.error(f"Update installation failed: {e}")
            return False
        finally:
            with self._install_lock:
                self.is_installing = False
    
    def _safe_callback(self, has_update: bool, update_info: any):
        """线程安全地调用回调"""
        with self._callback_lock:
            if self.update_callback:
                try:
                    self.update_callback(has_update, update_info)
                except Exception as e:
                    logger.error(f"Update callback failed: {e}")
    
    def _safe_error_callback(self, error: UpdateError):
        """线程安全地调用错误回调"""
        with self._callback_lock:
            if self.error_callback:
                try:
                    self.error_callback(error)
                except Exception as e:
                    logger.error(f"Error callback failed: {e}")
            else:
                # 如果没有错误回调，记录用户友好的错误消息
                user_message = get_user_friendly_message(error)
                logger.error(f"Update error: {user_message}")
    
    def start_auto_check(self):
        """启动自动检查"""
        if self._auto_check_thread and self._auto_check_thread.is_alive():
            logger.info("Auto check already running")
            return
        
        # 重置停止事件
        self._stop_event.clear()
        
        def check_loop():
            check_interval = ota_config.get_check_interval()
            while not self._stop_event.is_set():
                try:
                    # 检查是否被要求停止
                    if self._stop_event.is_set():
                        break
                    
                    self.check_for_updates(silent=True)
                    
                    # 使用事件等待，可以被立即中断
                    if self._stop_event.wait(timeout=check_interval):
                        break  # 收到停止信号
                        
                except Exception as e:
                    logger.error(f"Auto check failed: {e}")
                    # 错误时等待较短时间后重试
                    if self._stop_event.wait(timeout=300):  # 5分钟
                        break  # 收到停止信号
        
        self._auto_check_thread = threading.Thread(target=check_loop, daemon=True)
        self._auto_check_thread.start()
        logger.info("Auto update check started")
    
    def stop_auto_check(self):
        """停止自动检查"""
        if self._auto_check_thread and self._auto_check_thread.is_alive():
            # 设置停止事件
            self._stop_event.set()
            
            # 等待线程结束
            self._auto_check_thread.join(timeout=5)  # 等待最多5秒
            
            if self._auto_check_thread.is_alive():
                logger.warning("Auto check thread did not stop gracefully")
            else:
                logger.info("Auto update check stopped")
        else:
            logger.info("Auto check not running")
    
    def set_update_callback(self, callback: Callable):
        """设置更新回调"""
        with self._callback_lock:
            self.update_callback = callback
    
    def set_error_callback(self, callback: Callable):
        """设置错误回调"""
        with self._callback_lock:
            self.error_callback = callback
    
    def is_busy(self) -> bool:
        """检查是否正在执行更新相关操作"""
        return self.is_checking or self.is_installing
    
    def get_status(self) -> dict:
        """获取当前状态"""
        return {
            "is_checking": self.is_checking,
            "is_installing": self.is_installing,
            "auto_check_running": self._auto_check_thread and self._auto_check_thread.is_alive(),
            "platform": self.platform,
            "app_version": self.app_version
        } 