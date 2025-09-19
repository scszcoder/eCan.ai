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
from .config import ota_config
from .errors import (
    UpdateError, UpdateErrorCode, NetworkError, PlatformError, 
    VerificationError, create_error_from_exception
)


class SparkleUpdater:
    """macOS Sparkle更新器
    
    注意: 真实的Sparkle框架不提供CLI工具，这里使用appcast解析作为替代方案
    在生产环境中应该使用Sparkle的原生Objective-C API
    """
    
    def __init__(self, ota_manager):
        self.ota_manager = ota_manager
        self.sparkle_framework_path = self._find_sparkle_framework()
        # 导入appcast解析功能
        try:
            from .appcast import parse_appcast, select_latest_for_platform, normalize_arch_tag
            self.appcast_parser = True
        except ImportError:
            logger.warning("Appcast parser not available, falling back to generic updater")
            self.appcast_parser = False
        
    def _find_sparkle_framework(self) -> Optional[str]:
        """查找Sparkle框架路径"""
        # 首先检查打包后的依赖位置
        if hasattr(sys, '_MEIPASS'):
            # PyInstaller打包环境
            bundled_path = os.path.join(sys._MEIPASS, "third_party", "sparkle", "Sparkle.framework")
            if os.path.exists(bundled_path):
                logger.info(f"Found bundled Sparkle framework at: {bundled_path}")
                return bundled_path
        
        # 开发环境或手动安装的位置
        possible_paths = [
            # 项目内打包的依赖
            os.path.join(self.ota_manager.app_home_path, "third_party", "sparkle", "Sparkle.framework"),
            # 标准安装位置
            "/Applications/ECBot.app/Contents/Frameworks/Sparkle.framework",
            os.path.join(self.ota_manager.app_home_path, "Frameworks", "Sparkle.framework"),
            "/Library/Frameworks/Sparkle.framework",
            "/opt/homebrew/Frameworks/Sparkle.framework",  # Apple Silicon Homebrew
            "/usr/local/Frameworks/Sparkle.framework",     # Intel Homebrew
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                logger.info(f"Found Sparkle framework at: {path}")
                return path
        
        logger.warning("Sparkle framework not found in any expected location")
        return None
    
    def check_for_updates(self, silent: bool = False, return_info: bool = False):
        """检查更新，返回(是否有更新, 更新信息)
        
        由于真实的Sparkle框架不提供CLI工具，这里使用appcast解析作为替代方案
        """
        try:
            # 如果没有appcast解析器，回退到通用更新器逻辑
            if not self.appcast_parser:
                logger.warning("Sparkle framework found but appcast parser unavailable, using fallback method")
                return self._fallback_check_for_updates(silent, return_info)
            
            # 使用appcast解析进行更新检查
            return self._check_via_appcast(silent, return_info)
            
        except subprocess.TimeoutExpired as e:
            error = UpdateError(
                UpdateErrorCode.CONNECTION_TIMEOUT,
                "Sparkle check timed out",
                {"timeout": 30, "command": ["sparkle-cli", "check"]}
            )
            logger.error(str(error))
            if return_info:
                return False, error
            return False
    
    def _check_via_appcast(self, silent: bool = False, return_info: bool = False):
        """通过appcast检查更新"""
        try:
            import requests
            from .appcast import parse_appcast, select_latest_for_platform, normalize_arch_tag
            
            # 获取平台配置
            plat_config = ota_config.get_platform_config()
            arch = normalize_arch_tag(platform.machine())
            
            # 获取appcast URL
            appcast_urls = plat_config.get('appcast_urls', {})
            appcast_url = appcast_urls.get(arch) or plat_config.get('appcast_url')
            
            if not appcast_url:
                raise PlatformError(
                    UpdateErrorCode.INVALID_CONFIG,
                    "No appcast URL configured for macOS platform",
                    {"platform_config": plat_config}
                )
            
            # 获取appcast内容
            response = requests.get(appcast_url, timeout=10)
            response.raise_for_status()
            
            # 解析appcast
            items = parse_appcast(response.text)
            selected = select_latest_for_platform(
                items, 
                None, 
                self.ota_manager.app_version, 
                arch_tag=arch
            )
            
            if selected:
                update_info = {
                    "update_available": True,
                    "latest_version": selected.version,
                    "download_url": selected.url,
                    "file_size": selected.length or 0,
                    "signature": selected.ed_signature or "",
                    "description": selected.description_html or "",
                    "source": "sparkle_appcast"
                }
                return (True, update_info) if return_info else True
            else:
                return (False, None) if return_info else False
                
        except Exception as e:
            error = create_error_from_exception(e, "Sparkle appcast check")
            logger.error(str(error))
            if return_info:
                return False, error
            return False
    
    def _fallback_check_for_updates(self, silent: bool = False, return_info: bool = False):
        """回退到通用更新检查方法"""
        try:
            # 使用通用更新器的逻辑，避免循环导入
            return self._generic_update_check(silent, return_info)
        except Exception as e:
            error = create_error_from_exception(e, "Sparkle fallback check")
            logger.error(str(error))
            if return_info:
                return False, error
            return False
    
    def _generic_update_check(self, silent: bool = False, return_info: bool = False):
        """通用更新检查逻辑"""
        try:
            import requests
            
            # 使用JSON API进行检查
            update_url = f"{self.ota_manager.update_server_url}/api/check"
            params = {
                "app": "ecbot",
                "version": self.ota_manager.app_version,
                "platform": "darwin",
                "arch": platform.machine()
            }
            
            response = requests.get(update_url, params=params, timeout=10)
            response.raise_for_status()
            
            if response.status_code == 200:
                data = response.json()
                has_update = data.get("update_available", False)
                update_info = data if has_update else None
                return (has_update, update_info) if return_info else has_update
            else:
                return (False, None) if return_info else False
                
        except Exception as e:
            logger.error(f"Generic update check failed: {e}")
            return (False, None) if return_info else False
    
    def install_update(self, package_manager=None) -> bool:
        """安装更新
        
        注意: 真实的Sparkle安装需要使用原生API或手动处理DMG文件
        这里提供基本的DMG安装逻辑
        """
        try:
            if not package_manager or not package_manager.current_package:
                logger.error("No package available for installation")
                return False
            
            package = package_manager.current_package
            if not package.is_downloaded or not package.download_path:
                logger.error("Package not downloaded")
                return False
            
            # 基本的DMG安装逻辑
            return self._install_dmg(package.download_path)
            
        except Exception as e:
            logger.error(f"Sparkle install failed: {e}")
            return False
    
    def _install_dmg(self, dmg_path) -> bool:
        """安装DMG文件的基本逻辑"""
        try:
            logger.info(f"Installing DMG: {dmg_path}")
            
            # 在开发模式下，只记录而不实际安装
            if ota_config.is_dev_mode():
                logger.info("Development mode: DMG installation simulated")
                return True
            
            # 实际的DMG安装需要:
            # 1. 挂载DMG
            # 2. 复制应用到Applications
            # 3. 卸载DMG
            # 4. 重启应用
            
            # 这里提供基本框架，实际实现需要根据具体需求
            logger.warning("DMG installation not fully implemented - manual installation required")
            return False
            
        except Exception as e:
            logger.error(f"DMG installation failed: {e}")
            return False


class WinSparkleUpdater:
    """Windows winSparkle更新器
    
    注意: 真实的winSparkle不提供CLI工具，这里使用appcast解析作为替代方案
    在生产环境中应该使用winSparkle的原生C++ API
    """
    
    def __init__(self, ota_manager):
        self.ota_manager = ota_manager
        self.winsparkle_dll_path = self._find_winsparkle_dll()
        # 导入appcast解析功能
        try:
            from .appcast import parse_appcast, select_latest_for_platform, normalize_arch_tag
            self.appcast_parser = True
        except ImportError:
            logger.warning("Appcast parser not available, falling back to generic updater")
            self.appcast_parser = False
        
    def _find_winsparkle_dll(self) -> Optional[str]:
        """查找winSparkle DLL路径"""
        # 首先检查打包后的依赖位置
        if hasattr(sys, '_MEIPASS'):
            # PyInstaller打包环境
            bundled_path = os.path.join(sys._MEIPASS, "third_party", "winsparkle", "winsparkle.dll")
            if os.path.exists(bundled_path):
                logger.info(f"Found bundled winSparkle DLL at: {bundled_path}")
                return bundled_path
        
        # 开发环境或手动安装的位置
        possible_paths = [
            # 项目内打包的依赖
            os.path.join(self.ota_manager.app_home_path, "third_party", "winsparkle", "winsparkle.dll"),
            # 标准位置
            os.path.join(self.ota_manager.app_home_path, "winsparkle.dll"),
            os.path.join(self.ota_manager.app_home_path, "lib", "winsparkle.dll"),
            os.path.join(self.ota_manager.app_home_path, "bin", "winsparkle.dll"),
            "C:\\Program Files\\ECBot\\winsparkle.dll",
            "C:\\Program Files (x86)\\ECBot\\winsparkle.dll"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                logger.info(f"Found winSparkle DLL at: {path}")
                return path
        
        logger.warning("winSparkle DLL not found in any expected location")
        return None
    
    def _find_winsparkle_cli(self) -> Optional[str]:
        """查找winSparkle CLI工具路径"""
        # 首先检查打包后的依赖位置
        if hasattr(sys, '_MEIPASS'):
            # PyInstaller打包环境
            bundled_cli = os.path.join(sys._MEIPASS, "third_party", "winsparkle", "winsparkle-cli.bat")
            if os.path.exists(bundled_cli):
                logger.info(f"Found bundled winSparkle CLI at: {bundled_cli}")
                return bundled_cli
        
        possible_names = ["winsparkle-cli.bat", "winsparkle-cli.exe", "winsparkle_cli.exe"]
        possible_dirs = [
            # 项目内打包的依赖
            os.path.join(self.ota_manager.app_home_path, "third_party", "winsparkle"),
            # 标准位置
            self.ota_manager.app_home_path,
            os.path.join(self.ota_manager.app_home_path, "bin"),
            os.path.join(self.ota_manager.app_home_path, "tools"),
            "C:\\Program Files\\ECBot",
            "C:\\Program Files (x86)\\ECBot"
        ]
        
        for directory in possible_dirs:
            for name in possible_names:
                cli_path = os.path.join(directory, name)
                if os.path.exists(cli_path):
                    logger.info(f"Found winSparkle CLI at: {cli_path}")
                    return cli_path
        
        # 尝试在PATH中查找
        import shutil
        for name in possible_names:
            cli_path = shutil.which(name)
            if cli_path:
                logger.info(f"Found winSparkle CLI in PATH: {cli_path}")
                return cli_path
        
        logger.warning("winSparkle CLI not found")
        return None
    
    def check_for_updates(self, silent: bool = False, return_info: bool = False):
        """检查更新
        
        由于真实的winSparkle不提供CLI工具，这里使用appcast解析作为替代方案
        """
        try:
            # 如果没有appcast解析器，回退到通用更新器逻辑
            if not self.appcast_parser:
                logger.warning("winSparkle DLL found but appcast parser unavailable, using fallback method")
                return self._fallback_check_for_updates(silent, return_info)
            
            # 使用appcast解析进行更新检查
            return self._check_via_appcast(silent, return_info)
            
        except Exception as e:
            error = create_error_from_exception(e, "WinSparkle update check")
            logger.error(str(error))
            if return_info:
                return False, error
            return False
    
    def _check_via_appcast(self, silent: bool = False, return_info: bool = False):
        """通过appcast检查更新"""
        try:
            import requests
            from .appcast import parse_appcast, select_latest_for_platform, normalize_arch_tag
            
            # 获取平台配置
            plat_config = ota_config.get_platform_config()
            arch = normalize_arch_tag(platform.machine())
            
            # 获取appcast URL
            appcast_urls = plat_config.get('appcast_urls', {})
            appcast_url = appcast_urls.get(arch) or plat_config.get('appcast_url')
            
            if not appcast_url:
                raise PlatformError(
                    UpdateErrorCode.INVALID_CONFIG,
                    "No appcast URL configured for Windows platform",
                    {"platform_config": plat_config}
                )
            
            # 获取appcast内容
            response = requests.get(appcast_url, timeout=10)
            response.raise_for_status()
            
            # 解析appcast
            items = parse_appcast(response.text)
            selected = select_latest_for_platform(
                items, 
                None, 
                self.ota_manager.app_version, 
                arch_tag=arch
            )
            
            if selected:
                update_info = {
                    "update_available": True,
                    "latest_version": selected.version,
                    "download_url": selected.url,
                    "file_size": selected.length or 0,
                    "signature": selected.ed_signature or "",
                    "description": selected.description_html or "",
                    "source": "winsparkle_appcast"
                }
                return (True, update_info) if return_info else True
            else:
                return (False, None) if return_info else False
                
        except Exception as e:
            error = create_error_from_exception(e, "WinSparkle appcast check")
            logger.error(str(error))
            if return_info:
                return False, error
            return False
    
    def _fallback_check_for_updates(self, silent: bool = False, return_info: bool = False):
        """回退到通用更新检查方法"""
        try:
            # 使用通用更新器的逻辑，避免循环导入
            return self._generic_update_check(silent, return_info)
        except Exception as e:
            error = create_error_from_exception(e, "WinSparkle fallback check")
            logger.error(str(error))
            if return_info:
                return False, error
            return False
    
    def _generic_update_check(self, silent: bool = False, return_info: bool = False):
        """通用更新检查逻辑"""
        try:
            import requests
            
            # 使用JSON API进行检查
            update_url = f"{self.ota_manager.update_server_url}/api/check"
            params = {
                "app": "ecbot",
                "version": self.ota_manager.app_version,
                "platform": "windows",
                "arch": platform.machine()
            }
            
            response = requests.get(update_url, params=params, timeout=10)
            response.raise_for_status()
            
            if response.status_code == 200:
                data = response.json()
                has_update = data.get("update_available", False)
                update_info = data if has_update else None
                return (has_update, update_info) if return_info else has_update
            else:
                return (False, None) if return_info else False
                
        except Exception as e:
            logger.error(f"Generic update check failed: {e}")
            return (False, None) if return_info else False
    
    def install_update(self, package_manager=None) -> bool:
        """安装更新
        
        注意: 真实的winSparkle安装需要使用原生API或手动处理EXE/MSI文件
        这里提供基本的Windows安装逻辑
        """
        try:
            if not package_manager or not package_manager.current_package:
                logger.error("No package available for installation")
                return False
            
            package = package_manager.current_package
            if not package.is_downloaded or not package.download_path:
                logger.error("Package not downloaded")
                return False
            
            # 基本的Windows安装逻辑
            return self._install_windows_package(package.download_path)
            
        except Exception as e:
            logger.error(f"WinSparkle install failed: {e}")
            return False
    
    def _install_windows_package(self, package_path) -> bool:
        """安装Windows更新包的基本逻辑"""
        try:
            logger.info(f"Installing Windows package: {package_path}")
            
            # 在开发模式下，只记录而不实际安装
            if ota_config.is_dev_mode():
                logger.info("Development mode: Windows package installation simulated")
                return True
            
            # 实际的Windows安装需要:
            # 1. 检查文件类型(.exe, .msi)
            # 2. 以适当权限运行安装程序
            # 3. 处理UAC提示
            # 4. 重启应用
            
            # 这里提供基本框架，实际实现需要根据具体需求
            logger.warning("Windows package installation not fully implemented - manual installation required")
            return False
            
        except Exception as e:
            logger.error(f"Windows package installation failed: {e}")
            return False


class GenericUpdater:
    """通用更新器（用于Linux或其他平台）"""
    
    def __init__(self, ota_manager):
        self.ota_manager = ota_manager
    
    def check_for_updates(self, silent: bool = False, return_info: bool = False):
        """检查更新
        优先支持配置中的 appcast_url（兼容 GitHub Pages/Release 提供的 Sparkle/winSparkle 协议）。
        若无 appcast_url，则回退到 JSON API /api/check。
        """
        try:
            import requests
            from .appcast import parse_appcast, select_latest_for_platform, normalize_arch_tag

            # 1) 优先读取 appcast_url（支持 GitHub appcast），按平台/架构选择
            plat = platform.system().lower()
            arch = normalize_arch_tag(platform.machine())
            pf_conf = ota_config.get('platforms', {}).get(plat, {})
            # 优先使用显式按架构配置的 feed
            appcast_urls = pf_conf.get('appcast_urls', {})
            appcast_url = appcast_urls.get(arch) if arch else None
            # 其次使用平台级 appcast_url
            if not appcast_url:
                appcast_url = pf_conf.get('appcast_url')
            # 若配置为平台 feed，尝试自动拼接架构后缀
            if appcast_url and arch:
                if appcast_url.endswith('.xml'):
                    base, ext = appcast_url[:-4], '.xml'
                    if ('x86_64' not in base and 'arm64' not in base and 'aarch64' not in base):
                        arch_url = f"{base}-{arch}{ext}"
                        try:
                            resp = requests.get(arch_url, timeout=6)
                            if resp.status_code == 200:
                                appcast_url = arch_url
                        except Exception:
                            pass

            if not appcast_url:
                # 允许全局配置 appcast_url
                appcast_url = ota_config.get('appcast_url')

            if appcast_url:
                # HTTPS check (allow HTTP only in dev)
                if not appcast_url.startswith('https://'):
                    if not ota_config.is_http_allowed():
                        raise NetworkError(
                            "Appcast URL must use HTTPS in production mode",
                            {"appcast_url": appcast_url, "dev_mode": ota_config.is_dev_mode()}
                        )
                    else:
                        logger.warning("Using HTTP appcast in development mode - not secure for production!")

                resp = requests.get(appcast_url, timeout=10)
                if resp.status_code != 200:
                    logger.warning(f"Appcast unavailable: HTTP {resp.status_code}, fallback to JSON API if configured")
                else:
                    items = parse_appcast(resp.text)
                    sel = select_latest_for_platform(items, None, self.ota_manager.app_version, arch_tag=arch)
                    if sel:
                        update_info = {
                            "update_available": True,
                            "latest_version": sel.version,
                            "download_url": sel.url,
                            "file_size": sel.length or 0,
                            "signature": sel.ed_signature or "",
                            "description": sel.description_html or "",
                            "source": "appcast",
                        }
                        return (True, update_info) if return_info else True
                    # No suitable item found; continue to fallback

            # 2) 回退到 JSON API /api/check
            update_url = f"{self.ota_manager.update_server_url}/api/check"
            params = {
                "app": "ecbot",
                "version": self.ota_manager.app_version,
                "platform": platform.system().lower(),
                "arch": platform.machine()
            }

            if not update_url.startswith('https://'):
                if not ota_config.is_http_allowed():
                    raise NetworkError(
                        "Update server must use HTTPS in production mode",
                        {"server_url": update_url, "dev_mode": ota_config.is_dev_mode()}
                    )
                else:
                    logger.warning("Using HTTP in development mode - not secure for production!")

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
                error = UpdateError(
                    UpdateErrorCode.SERVER_UNAVAILABLE,
                    f"Update server returned error: {response.status_code}",
                    {"status_code": response.status_code, "response": response.text[:500]}
                )
                logger.error(str(error))
                if return_info:
                    return False, error
                return False

        except requests.exceptions.ConnectionError as e:
            error = NetworkError(
                "Failed to connect to update source",
                {"original_error": str(e)}
            )
            logger.error(str(error))
            if return_info:
                return False, error
            return False
        except requests.exceptions.Timeout as e:
            error = UpdateError(
                UpdateErrorCode.CONNECTION_TIMEOUT,
                "Update check timed out",
                {"timeout": 10, "original_error": str(e)}
            )
            logger.error(str(error))
            if return_info:
                return False, error
            return False
        except UpdateError:
            # 重新抛出我们的自定义错误
            raise
        except Exception as e:
            error = create_error_from_exception(e, "Generic update check")
            logger.error(str(error))
            if return_info:
                return False, error
            return False
    
    def install_update(self, package_manager=None) -> bool:
        """安装更新（通用安装器）。注意：对 .dmg/.exe/.msi 不提供安装实现。"""
        try:
            import requests
            import os
            from urllib.parse import urlparse
            
            # 先获取最新更新信息
            has_update, update_info = self.check_for_updates(silent=True, return_info=True)
            if not has_update or not update_info:
                logger.info("No update available for installation.")
                return False
            
            download_url = update_info.get("download_url", "")
            # 基于扩展名的预检查，避免无谓下载
            path = urlparse(download_url).path if download_url else ""
            ext = os.path.splitext(path)[1].lower() if path else ""
            unsupported_installer_ext = {".dmg", ".exe", ".msi"}
            if ext in unsupported_installer_ext:
                logger.error(
                    f"Installer format not implemented for GenericUpdater: {ext}. "
                    f"Use platform-specific updater or manual install. URL={download_url}"
                )
                return False
            
            # 构建UpdatePackage
            package = UpdatePackage(
                version=update_info.get("latest_version", ""),
                download_url=download_url,
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