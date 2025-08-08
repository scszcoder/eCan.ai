import os
import platform
import subprocess
import tempfile
import shutil
import zipfile
import sys
from typing import Optional

from utils.logger_helper import logger_helper as logger
from .package_manager import UpdatePackage, package_manager


class SparkleUpdater:
    """macOS Sparkle更新器"""
    
    def __init__(self, ota_manager):
        self.ota_manager = ota_manager
        self.sparkle_framework_path = self._find_sparkle_framework()
        
    def _find_sparkle_framework(self) -> Optional[str]:
        """查找Sparkle框架路径"""
        possible_paths = [
            "/Applications/ECBot.app/Contents/Frameworks/Sparkle.framework",
            os.path.join(self.ota_manager.app_home_path, "Frameworks", "Sparkle.framework"),
            "/Library/Frameworks/Sparkle.framework"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        return None
    
    def check_for_updates(self, silent: bool = False, return_info: bool = False):
        """检查更新，返回(是否有更新, 更新信息)"""
        if not self.sparkle_framework_path:
            logger.error("Sparkle framework not found")
            return (False, None) if return_info else False
        try:
            cmd = [
                os.path.join(self.sparkle_framework_path, "Versions", "Current", "Resources", "sparkle-cli"),
                "check"
            ]
            if silent:
                cmd.append("--silent")
            result = subprocess.run(cmd, capture_output=True, text=True)
            has_update = result.returncode == 0
            update_info = result.stdout if has_update else None
            return (has_update, update_info) if return_info else has_update
        except Exception as e:
            logger.error(f"Sparkle check failed: {e}")
            return (False, None) if return_info else False
    
    def install_update(self, package_manager=None) -> bool:
        """安装更新"""
        try:
            sparkle_path = self._find_sparkle_framework()
            if not sparkle_path:
                return False
            
            cmd = [
                os.path.join(sparkle_path, "Versions", "Current", "Resources", "sparkle-cli"),
                "install"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.returncode == 0
            
        except Exception as e:
            logger.error(f"Sparkle install failed: {e}")
            return False


class WinSparkleUpdater:
    """Windows winSparkle更新器"""
    
    def __init__(self, ota_manager):
        self.ota_manager = ota_manager
        self.winsparkle_dll_path = self._find_winsparkle_dll()
        
    def _find_winsparkle_dll(self) -> Optional[str]:
        """查找winSparkle DLL路径"""
        possible_paths = [
            os.path.join(self.ota_manager.app_home_path, "winsparkle.dll"),
            os.path.join(self.ota_manager.app_home_path, "lib", "winsparkle.dll"),
            "C:\\Program Files\\ECBot\\winsparkle.dll"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        return None
    
    def check_for_updates(self, silent: bool = False, return_info: bool = False):
        """检查更新"""
        if not self.winsparkle_dll_path:
            logger.error("winSparkle DLL not found")
            return (False, None) if return_info else False
        try:
            cmd = ["winsparkle-cli.exe", "check"]
            if silent:
                cmd.append("--silent")
            result = subprocess.run(cmd, capture_output=True, text=True)
            has_update = result.returncode == 0
            update_info = result.stdout if has_update else None
            return (has_update, update_info) if return_info else has_update
        except Exception as e:
            logger.error(f"winSparkle check failed: {e}")
            return (False, None) if return_info else False
    
    def install_update(self, package_manager=None) -> bool:
        """安装更新"""
        try:
            cmd = ["winsparkle-cli.exe", "install"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.returncode == 0
            
        except Exception as e:
            logger.error(f"winSparkle install failed: {e}")
            return False


class GenericUpdater:
    """通用更新器（用于Linux或其他平台）"""
    
    def __init__(self, ota_manager):
        self.ota_manager = ota_manager
    
    def check_for_updates(self, silent: bool = False, return_info: bool = False):
        """检查更新"""
        try:
            import requests
            
            # 检查更新服务器
            update_url = f"{self.ota_manager.update_server_url}/api/check"
            params = {
                "app": "ecbot",
                "version": self.ota_manager.app_version,
                "platform": platform.system().lower(),
                "arch": platform.machine()
            }
            
            # 确保使用HTTPS并验证证书
            if not update_url.startswith('https://'):
                logger.error("Update server must use HTTPS")
                return (False, None) if return_info else False
            
            response = requests.get(update_url, params=params, timeout=10, verify=True)
            
            if response.status_code == 200:
                data = response.json()
                has_update = data.get("update_available", False)
                update_info = data if has_update else None
                return (has_update, update_info) if return_info else has_update
            elif response.status_code == 404:
                logger.info("No update information available on server")
                return (False, None) if return_info else False
            else:
                logger.error(f"Update check failed with status {response.status_code}: {response.text}")
                return (False, None) if return_info else False
                
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error during update check: {e}")
            return (False, None) if return_info else False
        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout during update check: {e}")
            return (False, None) if return_info else False
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error during update check: {e}")
            return (False, None) if return_info else False
        except ValueError as e:
            logger.error(f"Invalid JSON response from update server: {e}")
            return (False, None) if return_info else False
        except Exception as e:
            logger.error(f"Unexpected error during update check: {e}")
            return (False, None) if return_info else False
    
    def install_update(self, package_manager=None) -> bool:
        """安装更新"""
        try:
            import requests
            
            # 先获取最新更新信息
            has_update, update_info = self.check_for_updates(silent=True, return_info=True)
            if not has_update or not update_info:
                logger.info("No update available for installation.")
                return False
            # 构建UpdatePackage
            package = UpdatePackage(
                version=update_info.get("latest_version", ""),
                download_url=update_info.get("download_url", ""),
                file_size=update_info.get("file_size", 0),
                signature=update_info.get("signature", ""),
                description=update_info.get("description", "")
            )
            # 下载
            if not package_manager.download_package(package):
                return False
            # 验证
            if not package_manager.verify_package(package):
                return False
            # 安装
            install_dir = self.ota_manager.app_home_path
            return package_manager.install_package(package, install_dir)
        except Exception as e:
            logger.error(f"Generic install failed: {e}")
            return False
    
    def _install_update_file(self, update_file: str) -> bool:
        """安装更新文件"""
        try:
            # 解压更新文件
            extract_dir = os.path.join(tempfile.gettempdir(), "ecbot_update")
            if os.path.exists(extract_dir):
                shutil.rmtree(extract_dir)
            
            with zipfile.ZipFile(update_file, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            # 执行安装脚本
            install_script = os.path.join(extract_dir, "install.py")
            if os.path.exists(install_script):
                result = subprocess.run([sys.executable, install_script], 
                                     cwd=extract_dir, capture_output=True, text=True)
                return result.returncode == 0
            else:
                logger.error("Install script not found in update package")
                return False
                
        except Exception as e:
            logger.error(f"Update file installation failed: {e}")
            return False 