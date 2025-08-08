import os
import platform
import subprocess
import threading
import time
from typing import Optional, Callable

from config.app_info import app_info
from config.constants import APP_NAME
from utils.logger_helper import logger_helper as logger

from .config import ota_config
from .package_manager import package_manager, UpdatePackage
from .platforms import SparkleUpdater, WinSparkleUpdater, GenericUpdater


class OTAUpdater:
    """OTA更新管理器"""
    
    def __init__(self):
        self.platform = platform.system()
        self.app_version = ota_config.get('app_version', '1.0.0')
        self.update_server_url = ota_config.get_update_server()
        self.is_checking = False
        self.update_callback: Optional[Callable] = None
        self._auto_check_thread = None
        self._stop_auto_check = False
        
        # 获取应用路径
        self.app_home_path = app_info.app_home_path
        
        # 平台特定的更新器
        self.platform_updater = self._create_platform_updater()
        
        logger.info(f"OTA Updater initialized for {self.platform}")
    
    def _create_platform_updater(self):
        """创建平台特定的更新器"""
        if self.platform == "Darwin":
            return SparkleUpdater(self)
        elif self.platform == "Windows":
            return WinSparkleUpdater(self)
        else:
            return GenericUpdater(self)
    
    def check_for_updates(self, silent: bool = False) -> bool:
        """检查更新"""
        if self.is_checking:
            return False
        
        self.is_checking = True
        try:
            logger.info("Checking for updates...")
            
            has_update, update_info = self.platform_updater.check_for_updates(silent, return_info=True)
            
            if has_update and self.update_callback:
                self.update_callback(has_update, update_info)
            
            return has_update
        except Exception as e:
            logger.error(f"Update check failed: {e}")
            return False
        finally:
            self.is_checking = False
    
    def install_update(self) -> bool:
        """安装更新"""
        try:
            return self.platform_updater.install_update(package_manager=package_manager)
        except Exception as e:
            logger.error(f"Update installation failed: {e}")
            return False
    
    def start_auto_check(self):
        """启动自动检查"""
        if self._auto_check_thread and self._auto_check_thread.is_alive():
            logger.info("Auto check already running")
            return
        
        self._stop_auto_check = False
        
        def check_loop():
            check_interval = ota_config.get_check_interval()
            while not self._stop_auto_check:
                try:
                    self.check_for_updates(silent=True)
                    # 分段睡眠，以便能够及时响应停止信号
                    for _ in range(check_interval):
                        if self._stop_auto_check:
                            break
                        time.sleep(1)
                except Exception as e:
                    logger.error(f"Auto check failed: {e}")
                    # 错误时等待较短时间后重试
                    for _ in range(300):  # 5分钟
                        if self._stop_auto_check:
                            break
                        time.sleep(1)
        
        self._auto_check_thread = threading.Thread(target=check_loop, daemon=True)
        self._auto_check_thread.start()
        logger.info("Auto update check started")
    
    def stop_auto_check(self):
        """停止自动检查"""
        if self._auto_check_thread and self._auto_check_thread.is_alive():
            self._stop_auto_check = True
            self._auto_check_thread.join(timeout=5)  # 等待最多5秒
            logger.info("Auto update check stopped")
        else:
            logger.info("Auto check not running")
    
    def set_update_callback(self, callback: Callable):
        """设置更新回调"""
        self.update_callback = callback 