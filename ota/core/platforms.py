import os
import platform
import subprocess
import tempfile
import shutil
import zipfile
import sys
from pathlib import Path
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
    
    def _get_user_language(self) -> str:
        """
        Get user's language preference for localized appcast
        
        Returns:
            Language code (e.g., 'en-US', 'zh-CN')
        """
        try:
            # Use unified language detection from utils.i18n_helper
            from utils.i18n_helper import detect_language
            
            # Detect language with supported languages
            detected = detect_language(
                default_lang='en-US',
                supported_languages=['zh-CN', 'en-US']
            )
            
            logger.debug(f"[OTA] Detected user language: {detected}")
            return detected
                
        except Exception as e:
            logger.debug(f"[OTA] Could not detect user language: {e}, using 'en-US'")
            return 'en-US'

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

            # Get user language for localized appcast
            language = self._get_user_language()
            logger.info(f"[OTA] Requesting appcast for language: {language}")
            
            # Get appcast URL using new configuration method (with language support)
            appcast_url = ota_config.get_appcast_url('macos', arch, language=language)

            if not appcast_url:
                raise PlatformError(
                    UpdateErrorCode.INVALID_CONFIG,
                    "No appcast URL configured for macOS platform",
                    {"platform_config": plat_config}
                )

            # Get appcast content with multiple fallback strategies
            response = None
            urls_to_try = []
            
            # Strategy 1: Try localized version with standard URL
            urls_to_try.append((appcast_url, f"{language} appcast"))
            
            # Strategy 2: Try localized version with accelerated URL
            accelerated_url = appcast_url.replace('.s3.', '.s3-accelerate.')
            urls_to_try.append((accelerated_url, f"{language} appcast (accelerated)"))
            
            # Strategy 3: Fallback to English if not already English
            if language != 'en-US':
                fallback_url = ota_config.get_appcast_url('macos', arch, language='en-US')
                urls_to_try.append((fallback_url, "English appcast"))
                
                # Strategy 4: English with accelerated URL
                fallback_accelerated = fallback_url.replace('.s3.', '.s3-accelerate.')
                urls_to_try.append((fallback_accelerated, "English appcast (accelerated)"))
            
            # Try each URL in sequence with retry
            last_error = None
            max_retries_per_url = 2  # Retry each URL once if it fails
            for url, description in urls_to_try:
                for retry in range(max_retries_per_url):
                    try:
                        retry_suffix = f" (retry {retry + 1}/{max_retries_per_url})" if retry > 0 else ""
                        logger.info(f"[OTA] Trying {description}: {url}{retry_suffix}")
                        # Use longer timeout for first attempt (60s for slow networks)
                        # Shorter timeout for retry (30s to fail fast if real issue)
                        timeout = 60 if retry == 0 else 30
                        response = requests.get(url, timeout=timeout)
                        response.raise_for_status()
                        logger.info(f"[OTA] Successfully fetched {description}")
                        break  # Success, exit retry loop
                    except Exception as e:
                        logger.warning(f"[OTA] Failed to fetch {description}{retry_suffix}: {e}")
                        last_error = e
                        if retry < max_retries_per_url - 1:
                            import time
                            time.sleep(1)  # Wait 1 second before retry
                            continue
                        # All retries for this URL failed, try next URL
                        break
                
                # If we got a successful response, exit URL loop
                if response is not None:
                    break
            
            # If all attempts failed, raise the last error
            if response is None:
                logger.error(f"[OTA] All appcast fetch attempts failed")
                raise last_error if last_error else Exception("Failed to fetch appcast")

            # Parse appcast
            logger.info(f"[OTA] Parsing appcast XML...")
            items = parse_appcast(response.text)
            logger.info(f"[OTA] Found {len(items)} version(s) in appcast")
            
            # Log current version
            current_version = self.ota_manager.app_version
            logger.info(f"[OTA] Current version: {current_version}")
            
            # Select latest version
            selected = select_latest_for_platform(
                items,
                None,
                current_version,
                arch_tag=arch
            )

            if selected:
                logger.info(f"[OTA] ✅ Update available!")
                logger.info(f"[OTA]    Current version:  {current_version}")
                logger.info(f"[OTA]    Latest version:   {selected.version}")
                logger.info(f"[OTA]    Download URL:     {selected.url}")
                logger.info(f"[OTA]    File size:        {selected.length or 0} bytes")
                logger.info(f"[OTA]    Has signature:    {'Yes' if selected.ed_signature else 'No'}")
                
                # Auto-generate S3 accelerate URL if not provided
                alternate_url = selected.alternate_url
                logger.debug(f"[OTA] Checking alternate URL: alternate_url={alternate_url}, url contains '.s3.'={'.s3.' in selected.url}")
                if not alternate_url and '.s3.' in selected.url and 'amazonaws.com' in selected.url:
                    alternate_url = selected.url.replace('.s3.', '.s3-accelerate.')
                    logger.info(f"[OTA]    Alternate URL (auto-generated): {alternate_url}")
                elif alternate_url:
                    logger.info(f"[OTA]    Alternate URL (configured): {alternate_url}")
                
                update_info = {
                    "update_available": True,
                    "latest_version": selected.version,
                    "download_url": selected.url,
                    "alternate_url": alternate_url,
                    "file_size": selected.length or 0,
                    "signature": selected.ed_signature or "",
                    "description": selected.description_html or "",
                    "source": "macos_appcast"
                }
                return (True, update_info) if return_info else True
            else:
                logger.info(f"[OTA] ℹ️  No update available")
                logger.info(f"[OTA]    Current version: {current_version}")
                logger.info(f"[OTA]    You are running the latest version")
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
    
    def _get_user_language(self) -> str:
        """
        Get user's language preference for localized appcast
        
        Returns:
            Language code (e.g., 'en-US', 'zh-CN')
        """
        try:
            # Use unified language detection from utils.i18n_helper
            from utils.i18n_helper import detect_language
            
            # Detect language with supported languages
            detected = detect_language(
                default_lang='en-US',
                supported_languages=['zh-CN', 'en-US']
            )
            
            logger.debug(f"[OTA] Detected user language: {detected}")
            return detected
                
        except Exception as e:
            logger.debug(f"[OTA] Could not detect user language: {e}, using 'en-US'")
            return 'en-US'

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

            # Get user language for localized appcast
            language = self._get_user_language()
            logger.info(f"[OTA] Requesting appcast for language: {language}")
            
            # Get appcast URL using new configuration method (with language support)
            appcast_url = ota_config.get_appcast_url('windows', arch, language=language)

            if not appcast_url:
                raise PlatformError(
                    UpdateErrorCode.INVALID_CONFIG,
                    "No appcast URL configured for Windows platform",
                    {"platform_config": plat_config}
                )

            # Get appcast content with multiple fallback strategies
            response = None
            urls_to_try = []
            
            # Strategy 1: Try localized version with standard URL
            urls_to_try.append((appcast_url, f"{language} appcast"))
            
            # Strategy 2: Try localized version with accelerated URL
            accelerated_url = appcast_url.replace('.s3.', '.s3-accelerate.')
            urls_to_try.append((accelerated_url, f"{language} appcast (accelerated)"))
            
            # Strategy 3: Fallback to English if not already English
            if language != 'en-US':
                fallback_url = ota_config.get_appcast_url('windows', arch, language='en-US')
                urls_to_try.append((fallback_url, "English appcast"))
                
                # Strategy 4: English with accelerated URL
                fallback_accelerated = fallback_url.replace('.s3.', '.s3-accelerate.')
                urls_to_try.append((fallback_accelerated, "English appcast (accelerated)"))
            
            # Try each URL in sequence with retry
            last_error = None
            max_retries_per_url = 2  # Retry each URL once if it fails
            for url, description in urls_to_try:
                for retry in range(max_retries_per_url):
                    try:
                        retry_suffix = f" (retry {retry + 1}/{max_retries_per_url})" if retry > 0 else ""
                        logger.info(f"[OTA] Trying {description}: {url}{retry_suffix}")
                        # Use longer timeout for first attempt (60s for slow networks)
                        # Shorter timeout for retry (30s to fail fast if real issue)
                        timeout = 60 if retry == 0 else 30
                        response = requests.get(url, timeout=timeout)
                        response.raise_for_status()
                        logger.info(f"[OTA] Successfully fetched {description}")
                        break  # Success, exit retry loop
                    except Exception as e:
                        logger.warning(f"[OTA] Failed to fetch {description}{retry_suffix}: {e}")
                        last_error = e
                        if retry < max_retries_per_url - 1:
                            import time
                            time.sleep(1)  # Wait 1 second before retry
                            continue
                        # All retries for this URL failed, try next URL
                        break
                
                # If we got a successful response, exit URL loop
                if response is not None:
                    break
            
            # If all attempts failed, raise the last error
            if response is None:
                logger.error(f"[OTA] All appcast fetch attempts failed")
                raise last_error if last_error else Exception("Failed to fetch appcast")

            # Parse appcast
            logger.info(f"[OTA] Parsing appcast XML...")
            items = parse_appcast(response.text)
            logger.info(f"[OTA] Found {len(items)} version(s) in appcast")
            
            # Log current version
            current_version = self.ota_manager.app_version
            logger.info(f"[OTA] Current version: {current_version}")
            
            # Select latest version
            selected = select_latest_for_platform(
                items,
                None,
                current_version,
                arch_tag=arch
            )

            if selected:
                logger.info(f"[OTA] ✅ Update available!")
                logger.info(f"[OTA]    Current version:  {current_version}")
                logger.info(f"[OTA]    Latest version:   {selected.version}")
                logger.info(f"[OTA]    Download URL:     {selected.url}")
                logger.info(f"[OTA]    File size:        {selected.length or 0} bytes")
                logger.info(f"[OTA]    Has signature:    {'Yes' if selected.ed_signature else 'No'}")
                
                # Auto-generate S3 accelerate URL if not provided
                alternate_url = selected.alternate_url
                logger.debug(f"[OTA] Checking alternate URL: alternate_url={alternate_url}, url contains '.s3.'={'.s3.' in selected.url}")
                if not alternate_url and '.s3.' in selected.url and 'amazonaws.com' in selected.url:
                    alternate_url = selected.url.replace('.s3.', '.s3-accelerate.')
                    logger.info(f"[OTA]    Alternate URL (auto-generated): {alternate_url}")
                elif alternate_url:
                    logger.info(f"[OTA]    Alternate URL (configured): {alternate_url}")
                
                update_info = {
                    "update_available": True,
                    "latest_version": selected.version,
                    "download_url": selected.url,
                    "alternate_url": alternate_url,
                    "file_size": selected.length or 0,
                    "signature": selected.ed_signature or "",
                    "description": selected.description_html or "",
                    "source": "windows_appcast"
                }
                return (True, update_info) if return_info else True
            else:
                logger.info(f"[OTA] ℹ️  No update available")
                logger.info(f"[OTA]    Current version: {current_version}")
                logger.info(f"[OTA]    You are running the latest version")
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


class LinuxUpdater:
    """Linux OTA updater using self-contained appcast parser
    
    Supports:
    - AppImage: Portable application packages
    - DEB: Debian/Ubuntu system packages
    
    Uses industry-standard Sparkle-format appcast.xml with independent implementation.
    No dependency on external OTA frameworks - fully self-contained OTA system.
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
    
    def _get_user_language(self) -> str:
        """Get user's language preference for localized appcast
        
        Returns:
            Language code (e.g., 'en-US', 'zh-CN')
        """
        try:
            from utils.i18n_helper import detect_language
            
            detected = detect_language(
                default_lang='en-US',
                supported_languages=['zh-CN', 'en-US']
            )
            
            logger.debug(f"[OTA] Detected user language: {detected}")
            return detected
                
        except Exception as e:
            logger.debug(f"[OTA] Could not detect user language: {e}, using 'en-US'")
            return 'en-US'

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

            # Get user language for localized appcast
            language = self._get_user_language()
            logger.info(f"[OTA] Requesting appcast for language: {language}")
            
            # Get appcast URL using configuration method (with language support)
            appcast_url = ota_config.get_appcast_url('linux', arch, language=language)

            if not appcast_url:
                raise PlatformError(
                    UpdateErrorCode.INVALID_CONFIG,
                    "No appcast URL configured for Linux platform",
                    {"platform_config": plat_config}
                )

            # Get appcast content with multiple fallback strategies
            response = None
            urls_to_try = []
            
            # Strategy 1: Try localized version with standard URL
            urls_to_try.append((appcast_url, f"{language} appcast"))
            
            # Strategy 2: Try localized version with accelerated URL
            accelerated_url = appcast_url.replace('.s3.', '.s3-accelerate.')
            urls_to_try.append((accelerated_url, f"{language} appcast (accelerated)"))
            
            # Strategy 3: Try English version as fallback
            if language != 'en-US':
                en_appcast_url = ota_config.get_appcast_url('linux', arch, language='en-US')
                urls_to_try.append((en_appcast_url, "en-US appcast (fallback)"))
                
                en_accelerated_url = en_appcast_url.replace('.s3.', '.s3-accelerate.')
                urls_to_try.append((en_accelerated_url, "en-US appcast (accelerated fallback)"))
            
            # Try each URL in sequence
            last_error = None
            for url, description in urls_to_try:
                try:
                    logger.info(f"[OTA] Trying {description}: {url}")
                    response = requests.get(url, timeout=10)
                    
                    if response.status_code == 200:
                        logger.info(f"[OTA] Successfully fetched {description}")
                        break
                    else:
                        logger.warning(f"[OTA] {description} returned status {response.status_code}")
                        last_error = f"HTTP {response.status_code}"
                        
                except requests.exceptions.Timeout:
                    logger.warning(f"[OTA] Timeout fetching {description}")
                    last_error = "Timeout"
                    continue
                except requests.exceptions.RequestException as e:
                    logger.warning(f"[OTA] Error fetching {description}: {e}")
                    last_error = str(e)
                    continue
            
            if not response or response.status_code != 200:
                raise NetworkError(
                    UpdateErrorCode.NETWORK_ERROR,
                    f"Failed to fetch appcast from all URLs. Last error: {last_error}",
                    {"urls_tried": [url for url, _ in urls_to_try]}
                )

            # Parse appcast
            appcast_content = response.text
            items = parse_appcast(appcast_content)

            if not items:
                logger.info("[OTA] No updates found in appcast")
                return (False, None) if return_info else False

            # Select latest item for current platform
            current_version = self.ota_manager.app_version
            latest_item = select_latest_for_platform(
                items,
                current_version=current_version,
                platform_name='linux',
                arch=arch
            )

            if not latest_item:
                logger.info("[OTA] No applicable updates for this platform")
                return (False, None) if return_info else False

            # Check if update is newer
            from packaging import version as pkg_version
            try:
                if pkg_version.parse(latest_item.version) <= pkg_version.parse(current_version):
                    logger.info(f"[OTA] Current version {current_version} is up to date")
                    return (False, None) if return_info else False
            except Exception as e:
                logger.warning(f"[OTA] Version comparison failed: {e}, proceeding with update check")

            # Update available
            logger.info(f"[OTA] Update available: {latest_item.version} (current: {current_version})")
            
            if return_info:
                update_info = {
                    'version': latest_item.version,
                    'url': latest_item.url,
                    'description': latest_item.description or '',
                    'release_notes_url': latest_item.release_notes_url,
                    'pub_date': latest_item.pub_date,
                    'length': latest_item.length,
                    'signature': latest_item.signature,
                    'os': latest_item.os,
                    'arch': latest_item.arch
                }
                return (True, update_info)
            else:
                return True

        except Exception as e:
            error = create_error_from_exception(e, "Linux update check failed")
            logger.error(f"[OTA] {error}")
            
            if not silent:
                raise error
            
            return (False, None) if return_info else False

    def install_update(self, package_manager=None) -> bool:
        """Install update using package manager"""
        try:
            logger.info("[OTA] Linux updater: install_update called")

            # In dev mode, only log without actual installation
            if ota_config.is_dev_mode():
                logger.info("[OTA] Development mode: Linux installation simulated")
                return True

            if not package_manager:
                logger.error("[OTA] Package manager required for Linux installation")
                return False

            # Get downloaded package
            package = package_manager.get_downloaded_package()
            if not package:
                logger.error("[OTA] No downloaded package available")
                return False

            # Install based on package type
            from .installer import InstallationManager
            installer = InstallationManager()
            
            package_path = Path(package.local_path)
            
            if package_path.suffix.lower() == '.appimage':
                return self._install_appimage(package_path, installer)
            elif package_path.suffix.lower() == '.deb':
                return self._install_deb(package_path, installer)
            else:
                logger.error(f"[OTA] Unsupported package format: {package_path.suffix}")
                return False

        except Exception as e:
            logger.error(f"[OTA] Linux install failed: {e}")
            return False
    
    def _install_appimage(self, package_path: Path, installer) -> bool:
        """Install AppImage package"""
        try:
            logger.info(f"[OTA] Installing AppImage: {package_path}")
            
            # Make AppImage executable
            os.chmod(package_path, 0o755)
            
            # Determine installation location
            install_dir = Path.home() / '.local' / 'bin'
            install_dir.mkdir(parents=True, exist_ok=True)
            
            app_name = ota_config.get_app_name()
            target_path = install_dir / f"{app_name}.AppImage"
            
            # Backup existing installation
            if target_path.exists():
                backup_path = target_path.with_suffix('.AppImage.backup')
                shutil.copy2(target_path, backup_path)
                logger.info(f"[OTA] Backed up existing AppImage to {backup_path}")
            
            # Copy new AppImage
            shutil.copy2(package_path, target_path)
            os.chmod(target_path, 0o755)
            
            logger.info(f"[OTA] AppImage installed to {target_path}")
            
            # Schedule restart
            self._schedule_restart(target_path)
            
            return True
            
        except Exception as e:
            logger.error(f"[OTA] AppImage installation failed: {e}")
            return False
    
    def _install_deb(self, package_path: Path, installer) -> bool:
        """Install DEB package"""
        try:
            logger.info(f"[OTA] Installing DEB package: {package_path}")
            
            # DEB installation requires sudo privileges
            # Check if we can use pkexec or sudo
            if shutil.which('pkexec'):
                cmd = ['pkexec', 'dpkg', '-i', str(package_path)]
            elif shutil.which('sudo'):
                cmd = ['sudo', 'dpkg', '-i', str(package_path)]
            else:
                logger.error("[OTA] No privilege elevation tool found (pkexec or sudo)")
                return False
            
            # Execute installation
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info("[OTA] DEB package installed successfully")
                
                # Schedule restart
                app_name = ota_config.get_app_name().lower()
                self._schedule_restart(f"/usr/bin/{app_name}")
                
                return True
            else:
                logger.error(f"[OTA] DEB installation failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"[OTA] DEB installation failed: {e}")
            return False
    
    def _schedule_restart(self, app_path):
        """Schedule application restart after installation"""
        try:
            # Create restart script
            restart_script = tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.sh',
                delete=False
            )
            
            restart_script.write(f'''#!/bin/bash
# Wait for current process to exit
sleep 2

# Start new version
"{app_path}" &

# Clean up this script
rm -f "$0"
''')
            restart_script.close()
            
            # Make script executable
            os.chmod(restart_script.name, 0o755)
            
            # Execute restart script in background
            subprocess.Popen([restart_script.name], start_new_session=True)
            
            logger.info(f"[OTA] Restart scheduled: {app_path}")
            
        except Exception as e:
            logger.warning(f"[OTA] Failed to schedule restart: {e}")


class GenericUpdater:
    """Generic updater (fallback for unsupported platforms)"""

    def __init__(self, ota_manager):
        self.ota_manager = ota_manager

    def check_for_updates(self, silent: bool = False, return_info: bool = False):
        """Check for updates"""
        logger.warning("[OTA] Generic updater: Platform not fully supported")
        return (False, None) if return_info else False

    def install_update(self, package_manager=None) -> bool:
        """Install update"""
        logger.warning("[OTA] Generic updater: Installation not supported")
        return False


def get_platform_updater(ota_manager):
    """Get updater for current platform"""
    system = platform.system().lower()

    if system == 'darwin':  # macOS
        return MacOSUpdater(ota_manager)
    elif system == 'windows':
        return WindowsUpdater(ota_manager)
    elif system == 'linux':  # Linux
        return LinuxUpdater(ota_manager)
    else:  # Other platforms
        return GenericUpdater(ota_manager)
