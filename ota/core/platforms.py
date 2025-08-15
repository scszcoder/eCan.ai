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
    """macOS Sparkle更新器"""
    
    def __init__(self, ota_manager):
        self.ota_manager = ota_manager
        self.sparkle_framework_path = self._find_sparkle_framework()
        
    def _find_sparkle_framework(self) -> Optional[str]:
        """查找Sparkle框架路径"""
        # 首先检查打包后的依赖位置
        if hasattr(sys, '_MEIPASS'):
            # PyInstaller打包环境
            bundled_path = os.path.join(sys._MEIPASS, "ota", "dependencies", "Sparkle.framework")
            if os.path.exists(bundled_path):
                logger.info(f"Found bundled Sparkle framework at: {bundled_path}")
                return bundled_path
        
        # 开发环境或手动安装的位置
        possible_paths = [
            # 项目内打包的依赖
            os.path.join(self.ota_manager.app_home_path, "ota", "dependencies", "Sparkle.framework"),
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
        """检查更新，返回(是否有更新, 更新信息)"""
        try:
            if not self.sparkle_framework_path:
                raise PlatformError(
                    UpdateErrorCode.FRAMEWORK_NOT_FOUND,
                    "Sparkle framework not found",
                    {"searched_paths": [
                        "/Applications/ECBot.app/Contents/Frameworks/Sparkle.framework",
                        os.path.join(self.ota_manager.app_home_path, "Frameworks", "Sparkle.framework"),
                        "/Library/Frameworks/Sparkle.framework"
                    ]}
                )
            
            # 首先尝试打包的CLI包装器
            cli_path = None
            if hasattr(sys, '_MEIPASS'):
                bundled_cli = os.path.join(sys._MEIPASS, "ota", "dependencies", "sparkle-cli")
                if os.path.exists(bundled_cli):
                    cli_path = bundled_cli
            
            # 如果没有找到打包的CLI，尝试框架内的CLI
            if not cli_path:
                framework_cli = os.path.join(self.sparkle_framework_path, "Versions", "Current", "Resources", "sparkle-cli")
                if os.path.exists(framework_cli):
                    cli_path = framework_cli
            
            # 最后尝试项目内的CLI包装器
            if not cli_path:
                project_cli = os.path.join(self.ota_manager.app_home_path, "ota", "dependencies", "sparkle-cli")
                if os.path.exists(project_cli):
                    cli_path = project_cli
            
            # 检查CLI工具是否存在
            if not cli_path or not os.path.exists(cli_path):
                raise PlatformError(
                    UpdateErrorCode.CLI_TOOL_NOT_FOUND,
                    f"Sparkle CLI not found. Searched locations: framework, bundled, project",
                    {"framework_path": self.sparkle_framework_path, "searched_paths": [
                        os.path.join(self.sparkle_framework_path, "Versions", "Current", "Resources", "sparkle-cli"),
                        os.path.join(sys._MEIPASS, "ota", "dependencies", "sparkle-cli") if hasattr(sys, '_MEIPASS') else None,
                        os.path.join(self.ota_manager.app_home_path, "ota", "dependencies", "sparkle-cli")
                    ]}
                )
            
            # 检查是否可执行
            if not os.access(cli_path, os.X_OK):
                raise PlatformError(
                    UpdateErrorCode.PERMISSION_DENIED,
                    f"Sparkle CLI not executable: {cli_path}",
                    {"cli_path": cli_path}
                )
            
            cmd = [cli_path, "check"]
            if silent:
                cmd.append("--silent")
                
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            has_update = result.returncode == 0
            update_info = result.stdout if has_update else None
            return (has_update, update_info) if return_info else has_update
            
        except subprocess.TimeoutExpired as e:
            error = UpdateError(
                UpdateErrorCode.CONNECTION_TIMEOUT,
                "Sparkle check timed out",
                {"timeout": 30, "command": cmd}
            )
            logger.error(str(error))
            if return_info:
                return False, error
            return False
            
        except UpdateError:
            # 重新抛出我们的自定义错误
            raise
            
        except Exception as e:
            error = create_error_from_exception(e, "Sparkle update check")
            logger.error(str(error))
            if return_info:
                return False, error
            return False
    
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
        # 首先检查打包后的依赖位置
        if hasattr(sys, '_MEIPASS'):
            # PyInstaller打包环境
            bundled_path = os.path.join(sys._MEIPASS, "ota", "dependencies", "winsparkle", "winsparkle.dll")
            if os.path.exists(bundled_path):
                logger.info(f"Found bundled winSparkle DLL at: {bundled_path}")
                return bundled_path
        
        # 开发环境或手动安装的位置
        possible_paths = [
            # 项目内打包的依赖
            os.path.join(self.ota_manager.app_home_path, "ota", "dependencies", "winsparkle", "winsparkle.dll"),
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
            bundled_cli = os.path.join(sys._MEIPASS, "ota", "dependencies", "winsparkle-cli.bat")
            if os.path.exists(bundled_cli):
                logger.info(f"Found bundled winSparkle CLI at: {bundled_cli}")
                return bundled_cli
        
        possible_names = ["winsparkle-cli.bat", "winsparkle-cli.exe", "winsparkle_cli.exe"]
        possible_dirs = [
            # 项目内打包的依赖
            os.path.join(self.ota_manager.app_home_path, "ota", "dependencies"),
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
        """检查更新"""
        if not self.winsparkle_dll_path:
            logger.error("winSparkle DLL not found")
            return (False, None) if return_info else False
        
        try:
            # 查找CLI工具
            cli_path = self._find_winsparkle_cli()
            if not cli_path:
                logger.error("winSparkle CLI not found")
                return (False, None) if return_info else False
            
            cmd = [cli_path, "check"]
            if silent:
                cmd.append("--silent")
                
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            has_update = result.returncode == 0
            update_info = result.stdout if has_update else None
            return (has_update, update_info) if return_info else has_update
            
        except subprocess.TimeoutExpired:
            logger.error("winSparkle check timed out")
            return (False, None) if return_info else False
        except FileNotFoundError:
            logger.error("winSparkle CLI executable not found")
            return (False, None) if return_info else False
        except Exception as e:
            logger.error(f"winSparkle check failed: {e}")
            return (False, None) if return_info else False
    
    def install_update(self, package_manager=None) -> bool:
        """安装更新"""
        try:
            # 查找CLI工具
            cli_path = self._find_winsparkle_cli()
            if not cli_path:
                logger.error("winSparkle CLI not found for installation")
                return False
            
            cmd = [cli_path, "install"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)  # 5分钟超时
            return result.returncode == 0
            
        except subprocess.TimeoutExpired:
            logger.error("winSparkle install timed out")
            return False
        except FileNotFoundError:
            logger.error("winSparkle CLI executable not found for installation")
            return False
        except Exception as e:
            logger.error(f"winSparkle install failed: {e}")
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