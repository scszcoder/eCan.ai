import os
import platform
import subprocess
import tempfile
import shutil
import zipfile
import sys
from typing import Optional
from urllib.parse import urlparse


from utils.logger_helper import logger_helper as logger
from .package_manager import UpdatePackage, package_manager
from .config import ota_config
from .errors import (
    UpdateError, UpdateErrorCode, NetworkError, PlatformError,
    VerificationError, create_error_from_exception
)


class SparkleUpdater:
    """macOS Sparkle updater

    Note: Real Sparkle framework doesn't provide CLI tools, using appcast parsing as alternative
    Should use Sparkle's native Objective-C API in production environment
    """

    def __init__(self, ota_manager):
        self.ota_manager = ota_manager
        self.sparkle_framework_path = self._find_sparkle_framework()
        # Import appcast parsing functionality
        try:
            from .appcast import parse_appcast, select_latest_for_platform, normalize_arch_tag
            self.appcast_parser = True
        except ImportError:
            logger.warning("Appcast parser not available, falling back to generic updater")
            self.appcast_parser = False

    def _find_sparkle_framework(self) -> Optional[str]:
        """Find Sparkle framework path"""
        # First check bundled dependency location
        if hasattr(sys, '_MEIPASS'):
            # PyInstaller bundled environment
            bundled_path = os.path.join(sys._MEIPASS, "third_party", "sparkle", "Sparkle.framework")
            if os.path.exists(bundled_path):
                logger.info(f"Found bundled Sparkle framework at: {bundled_path}")
                return bundled_path

        # Development environment or manually installed locations
        possible_paths = [
            # Project bundled dependencies
            os.path.join(self.ota_manager.app_home_path, "third_party", "sparkle", "Sparkle.framework"),
            # Standard installation locations
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
        """Check for updates by parsing the appcast file."""
        # For unified testing and behavior, we directly use the appcast check method.
        return self._check_via_appcast(silent, return_info)

    def _check_via_appcast(self, silent: bool = False, return_info: bool = False):
        """Check for updates via appcast"""
        try:
            import requests
            from .appcast import parse_appcast, select_latest_for_platform, normalize_arch_tag

            # Get platform configuration
            plat_config = ota_config.get_platform_config()
            arch = normalize_arch_tag(platform.machine())

            # Get appcast URL using new configuration method
            appcast_url = ota_config.get_appcast_url(arch)

            if not appcast_url:
                raise PlatformError(
                    UpdateErrorCode.INVALID_CONFIG,
                    "No appcast URL configured for macOS platform",
                    {"platform_config": plat_config}
                )

            # Get appcast content
            response = requests.get(appcast_url, timeout=10)
            response.raise_for_status()

            # Parse appcast
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


    def install_update(self, package_manager=None) -> bool:
        """Install update"""
        try:
            if not package_manager or not package_manager.current_package:
                logger.error("No package available for installation")
                return False

            package = package_manager.current_package
            if not package.is_downloaded or not package.download_path:
                logger.error("Package not downloaded")
                return False

            # Basic DMG installation logic
            return self._install_dmg(package.download_path)

        except Exception as e:
            logger.error(f"Sparkle install failed: {e}")
            return False

    def _install_dmg(self, dmg_path) -> bool:
        """Basic logic for installing DMG files"""
        try:
            logger.info(f"Installing DMG: {dmg_path}")

            # In dev mode, only log without actual installation
            if ota_config.is_dev_mode():
                logger.info("Development mode: DMG installation simulated")
                return True

            logger.warning("DMG installation not fully implemented - manual installation required")
            return False

        except Exception as e:
            logger.error(f"DMG installation failed: {e}")
            return False


class WinSparkleUpdater:
    """Windows winSparkle updater"""

    def __init__(self, ota_manager):
        self.ota_manager = ota_manager
        self.winsparkle_dll_path = self._find_winsparkle_dll()
        # Import appcast parsing functionality
        try:
            from .appcast import parse_appcast, select_latest_for_platform, normalize_arch_tag
            self.appcast_parser = True
        except ImportError:
            logger.warning("Appcast parser not available, falling back to generic updater")
            self.appcast_parser = False

    def _find_winsparkle_dll(self) -> Optional[str]:
        """Find winSparkle DLL path"""
        # First check bundled dependency location
        if hasattr(sys, '_MEIPASS'):
            # PyInstaller bundled environment
            bundled_path = os.path.join(sys._MEIPASS, "third_party", "winsparkle", "winsparkle.dll")
            if os.path.exists(bundled_path):
                logger.info(f"Found bundled winSparkle DLL at: {bundled_path}")
                return bundled_path

        # Development environment or manually installed locations
        possible_paths = [
            # Project bundled dependencies
            os.path.join(self.ota_manager.app_home_path, "third_party", "winsparkle", "winsparkle.dll"),
            # Standard locations
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

    def check_for_updates(self, silent: bool = False, return_info: bool = False):
        """Check for updates by parsing the appcast file."""
        # For unified testing and behavior, we directly use the appcast check method.
        return self._check_via_appcast(silent, return_info)

    def _check_via_appcast(self, silent: bool = False, return_info: bool = False):
        """Check for updates via appcast"""
        try:
            import requests
            from .appcast import parse_appcast, select_latest_for_platform, normalize_arch_tag

            # Get platform configuration
            plat_config = ota_config.get_platform_config()
            arch = normalize_arch_tag(platform.machine())

            # Get appcast URL using new configuration method
            appcast_url = ota_config.get_appcast_url(arch)

            if not appcast_url:
                raise PlatformError(
                    UpdateErrorCode.INVALID_CONFIG,
                    "No appcast URL configured for Windows platform",
                    {"platform_config": plat_config}
                )

            # Get appcast content
            response = requests.get(appcast_url, timeout=10)
            response.raise_for_status()

            # Parse appcast
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


    def install_update(self, package_manager=None) -> bool:
        """Install update"""
        try:
            if not package_manager or not package_manager.current_package:
                logger.error("No package available for installation")
                return False

            package = package_manager.current_package
            if not package.is_downloaded or not package.download_path:
                logger.error("Package not downloaded")
                return False

            # Basic Windows installation logic
            return self._install_windows_package(package.download_path)

        except Exception as e:
            logger.error(f"WinSparkle install failed: {e}")
            return False

    def _install_windows_package(self, package_path) -> bool:
        """Basic logic for installing Windows update packages"""
        try:
            logger.info(f"Installing Windows package: {package_path}")

            # In dev mode, only log without actual installation
            if ota_config.is_dev_mode():
                logger.info("Development mode: Windows package installation simulated")
                return True

            logger.warning("Windows package installation not fully implemented - manual installation required")
            return False

        except Exception as e:
            logger.error(f"Windows package installation failed: {e}")
            return False


class GenericUpdater:
    """Generic updater (for Linux or other platforms)"""

    def __init__(self, ota_manager):
        self.ota_manager = ota_manager

    def check_for_updates(self, silent: bool = False, return_info: bool = False):
        """Check for updates"""
        # Enforce HTTPS in production unless HTTP is explicitly allowed
        base_url = self.ota_manager.update_server_url or ota_config.get_update_server()
        try:
            scheme = urlparse(base_url).scheme.lower()
        except Exception:
            scheme = ""

        if scheme == "http" and not ota_config.is_http_allowed():
            # In production, plain HTTP endpoints are not allowed
            raise NetworkError(
                "Insecure HTTP update server is not allowed in production",
                {"update_server_url": base_url},
            )

        try:
            import requests

            # Use JSON API for checking
            update_url = f"{base_url.rstrip('/')}/api/check"
            params = {
                "app": "ecbot",
                "version": self.ota_manager.app_version,
                "platform": platform.system().lower(),
                "arch": platform.machine(),
            }

            response = requests.get(update_url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json() or {}
                has_update = data.get("update_available", False)
                update_info = data if has_update else None
                return (has_update, update_info) if return_info else has_update
            else:
                return (False, None) if return_info else False

        except Exception as e:
            logger.error(f"Generic update check failed: {e}")
            return (False, None) if return_info else False

    def install_update(self, package_manager=None) -> bool:
        """Install update"""
        try:
            logger.info("Generic updater: install_update called")

            # In dev mode, only log without actual installation
            if ota_config.is_dev_mode():
                logger.info("Development mode: Generic installation simulated")
                return True

            logger.warning("Generic installation not fully implemented - manual installation required")
            return False

        except Exception as e:
            logger.error(f"Generic install failed: {e}")
            return False


def get_platform_updater(ota_manager):
    """Get updater for current platform"""
    system = platform.system().lower()

    if system == 'darwin':  # macOS
        return SparkleUpdater(ota_manager)
    elif system == 'windows':
        return WinSparkleUpdater(ota_manager)
    else:  # Linux and other platforms
        return GenericUpdater(ota_manager)
