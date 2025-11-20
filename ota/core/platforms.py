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
from ota.config.loader import ota_config
from .errors import (
    UpdateError, UpdateErrorCode, NetworkError, PlatformError,
    VerificationError, create_error_from_exception
)


class MacOSUpdater:
    """macOS OTA updater using self-contained appcast parser

    Uses industry-standard Sparkle-format appcast.xml but with independent implementation.
    No dependency on Sparkle framework - fully self-contained OTA system.
    """

    def __init__(self, ota_manager):
        self.ota_manager = ota_manager
        # Import appcast parsing functionality
        try:
            from .appcast import parse_appcast, select_latest_for_platform, normalize_arch_tag
            self.appcast_parser = True
        except ImportError:
            logger.warning("Appcast parser not available, falling back to generic updater")
            self.appcast_parser = False

    def check_for_updates(self, silent: bool = False, return_info: bool = False):
        """Check for updates by parsing the appcast file."""
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
                    "source": "macos_appcast"
                }
                return (True, update_info) if return_info else True
            else:
                return (False, None) if return_info else False

        except Exception as e:
            error = create_error_from_exception(e, "macOS appcast check")
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
            logger.error(f"macOS install failed: {e}")
            return False

    def _install_dmg(self, dmg_path) -> bool:
        """Install DMG package (or PKG if it's a PKG file)"""
        try:
            # In dev mode, only log without actual installation
            if ota_config.is_dev_mode():
                logger.info("Development mode: Installation simulated")
                return True

            # Check if it's a PKG file
            if dmg_path.endswith('.pkg'):
                logger.info(f"Installing PKG: {dmg_path}")
                # Use AppleScript (osascript) to run installer with administrator privileges
                # Pass the package path via argv to avoid quoting issues in the script body
                osa_cmd = [
                    '/usr/bin/osascript',
                    '-e',
                    'on run argv',
                    '-e',
                    'set pkgPath to item 1 of argv',
                    '-e',
                    'do shell script "installer -pkg " & quoted form of pkgPath & " -target /" with administrator privileges',
                    '-e',
                    'end run',
                    dmg_path,
                ]

                logger.info("Requesting admin privileges for installation...")
                result = subprocess.run(osa_cmd, capture_output=True, text=True)

                if result.returncode == 0:
                    logger.info("PKG installation started successfully")
                    return True
                else:
                    if "User canceled" in result.stderr:
                        logger.warning("Installation canceled by user")
                    else:
                        logger.error(f"PKG installation failed: {result.stderr}")
                    return False
            else:
                logger.info(f"Installing DMG: {dmg_path}")
                logger.warning("DMG installation not fully implemented - manual installation required")
                # For DMG, we typically just open it
                subprocess.run(['open', dmg_path])
                return False

        except Exception as e:
            logger.error(f"Installation failed: {e}")
            return False


class WindowsUpdater:
    """Windows OTA updater using self-contained appcast parser

    Uses industry-standard Sparkle-format appcast.xml but with independent implementation.
    No dependency on WinSparkle - fully self-contained OTA system.
    """

    def __init__(self, ota_manager):
        self.ota_manager = ota_manager
        # Import appcast parsing functionality
        try:
            from .appcast import parse_appcast, select_latest_for_platform, normalize_arch_tag
            self.appcast_parser = True
        except ImportError:
            logger.warning("Appcast parser not available, falling back to generic updater")
            self.appcast_parser = False

    def check_for_updates(self, silent: bool = False, return_info: bool = False):
        """Check for updates by parsing the appcast file."""
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
                    "source": "windows_appcast"
                }
                return (True, update_info) if return_info else True
            else:
                return (False, None) if return_info else False

        except Exception as e:
            error = create_error_from_exception(e, "Windows appcast check")
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
            logger.error(f"Windows install failed: {e}")
            return False

    def _install_windows_package(self, package_path) -> bool:
        """Install Windows EXE/MSI package"""
        try:
            # In dev mode, only log without actual installation
            if ota_config.is_dev_mode():
                logger.info("Development mode: Installation simulated")
                return True

            logger.info(f"Installing Windows package: {package_path}")
            
            # Determine package type and install
            if package_path.endswith('.msi'):
                # MSI package: use msiexec with quiet mode
                cmd = ['msiexec', '/i', package_path, '/quiet', '/norestart']
            elif package_path.endswith('.exe'):
                # EXE package: try silent install flag
                cmd = [package_path, '/S', '/SILENT']  # Common silent flags
            else:
                logger.error(f"Unsupported package type: {package_path}")
                return False
            
            # Start installation process
            subprocess.Popen(cmd)
            logger.info("Installation started successfully")
            
            # IMPORTANT: Exit the application immediately to allow the installer 
            # to overwrite files. The installer should handle the restart.
            logger.info("Exiting application to allow update...")
            sys.exit(0)
            
            return True

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
        return MacOSUpdater(ota_manager)
    elif system == 'windows':
        return WindowsUpdater(ota_manager)
    else:  # Linux and other platforms
        return GenericUpdater(ota_manager)
