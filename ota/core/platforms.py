import os
import platform
import subprocess
import tempfile
import shutil
import zipfile
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


from utils.logger_helper import logger_helper as logger
from .package_manager import UpdatePackage, package_manager
from ota.config.loader import ota_config
from .installer import safe_makedirs
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
            from .appcast import (
                parse_appcast,
                select_latest_for_platform,
                select_eligible_versions,
                item_to_update_dict,
                normalize_arch_tag,
            )
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
            from .appcast import (
                parse_appcast,
                select_latest_for_platform,
                select_eligible_versions,
                item_to_update_dict,
                normalize_arch_tag,
            )

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
            user_prefix = getattr(self.ota_manager, "user_prefix", None)
            logger.info(
                f"[OTA] Current version: {current_version} "
                f"(user_prefix={user_prefix!r})"
            )
            
            # Select every eligible item newest-first, filtered by this
            # user's prefix. Keep the single newest for the legacy
            # update_info fields so older callers (notification toast,
            # single-version confirmation dialog) keep working
            # unchanged; surface the full list via 'available_versions'
            # for the new multi-version picker.
            eligible = select_eligible_versions(
                items,
                None,
                current_version,
                arch_tag=arch,
                user_prefix=user_prefix,
            )

            if eligible:
                selected = eligible[0]
                logger.info(f"[OTA] ✅ Update available!")
                logger.info(f"[OTA]    Current version:  {current_version}")
                logger.info(
                    f"[OTA]    Eligible items:   {len(eligible)} "
                    f"(newest: {selected.version}, user_prefix={selected.user_prefix!r})"
                )
                logger.info(f"[OTA]    Download URL:     {selected.url}")
                logger.info(f"[OTA]    File size:        {selected.length or 0} bytes")
                logger.info(f"[OTA]    Has signature:    {'Yes' if selected.ed_signature else 'No'}")

                selected_dict = item_to_update_dict(selected)
                alternate_url = selected_dict["alternate_url"]
                if alternate_url and alternate_url != selected.alternate_url:
                    logger.info(f"[OTA]    Alternate URL (auto-generated): {alternate_url}")
                elif alternate_url:
                    logger.info(f"[OTA]    Alternate URL (configured): {alternate_url}")

                update_info = {
                    "update_available": True,
                    "latest_version": selected.version,
                    "download_url": selected_dict["download_url"],
                    "alternate_url": alternate_url,
                    "file_size": selected_dict["file_size"],
                    "signature": selected_dict["signature"],
                    "description": selected_dict["description"],
                    "source": "macos_appcast",
                    # New: full list for the multi-version picker.
                    "available_versions": [item_to_update_dict(it) for it in eligible],
                    "user_prefix": user_prefix,
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
        """Install update

        Delegates to :class:`InstallationManager` so macOS and Windows share
        one canonical install path. Keeping the implementation in
        ``installer.py`` matters because that module owns:
          * custom install-directory lookup via Windows registry
          * Inno Setup silent-flag handling (``/SILENT`` / ``/NORESTART`` / ``/SP-`` / ``/CLOSEAPPLICATIONS``)
          * detached BAT launcher with delayed exit
          * pre-install process termination (QtWebEngineProcess etc.)

        This entry point must NOT reimplement those — see Bug #1 in
        ``ota/core/platforms.py`` history (the previous ``_install_dmg``
        here used a separate ``osascript`` call that bypassed the shared
        AppleScript argv-safe template in ``installer.py``).
        """
        try:
            if not package_manager or not package_manager.current_package:
                logger.error("No package available for installation")
                return False

            package = package_manager.current_package
            if not package.is_downloaded or not package.download_path:
                logger.error("Package not downloaded")
                return False

            # Delegate to the canonical installer. The GUI path
            # (UpdateDialog.install_update) calls InstallationManager
            # directly; this entry point is the headless / CLI path and
            # MUST match it so behaviour stays consistent.
            from .installer import InstallationManager

            installer = InstallationManager()
            return installer.install_package(
                package_path=Path(package.download_path),
                install_options={
                    'silent': True,
                    'create_backup': True,
                    # PKG / DMG already restart via ``delayed_restart``
                    # inside ``_install_pkg`` / ``_install_dmg``; this
                    # flag is the canonical signal across platforms
                    # that the new app should come back up.
                    'auto_restart': True,
                },
            )

        except Exception as e:
            logger.error(f"macOS install failed: {e}")
            return False

    # Legacy method kept only for backwards compatibility with
    # third-party callers / mock test fixtures that may still reference
    # it. All new code MUST go through ``install_update`` above.
    def _install_dmg(self, dmg_path) -> bool:  # pragma: no cover - legacy
        """Legacy DMG installer entry point. Use ``install_update`` instead.

        Retained only so imports don't break. The current behaviour is to
        open the DMG and log a warning, which matches the historical
        macOS behaviour for unsigned DMG artifacts.
        """
        logger.warning(
            "[OTA] _install_dmg is deprecated; use InstallationManager.install_package "
            "via WindowsUpdater/MacOSUpdater.install_update instead."
        )
        try:
            if ota_config.is_dev_mode():
                logger.info("Development mode: Installation simulated")
                return True
            logger.warning("[OTA] DMG installation not fully implemented - opening DMG only")
            subprocess.run(['open', str(dmg_path)], check=False)
            return False
        except Exception as e:
            logger.error(f"DMG installation failed: {e}")
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
            from .appcast import (
                parse_appcast,
                select_latest_for_platform,
                select_eligible_versions,
                item_to_update_dict,
                normalize_arch_tag,
            )
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
            from .appcast import (
                parse_appcast,
                select_latest_for_platform,
                select_eligible_versions,
                item_to_update_dict,
                normalize_arch_tag,
            )

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
            user_prefix = getattr(self.ota_manager, "user_prefix", None)
            logger.info(
                f"[OTA] Current version: {current_version} "
                f"(user_prefix={user_prefix!r})"
            )
            
            # See the matching comment in MacOSUpdater for the rationale
            # behind returning the full eligible list plus a legacy
            # single-item shape.
            eligible = select_eligible_versions(
                items,
                None,
                current_version,
                arch_tag=arch,
                user_prefix=user_prefix,
            )

            if eligible:
                selected = eligible[0]
                logger.info(f"[OTA] ✅ Update available!")
                logger.info(f"[OTA]    Current version:  {current_version}")
                logger.info(
                    f"[OTA]    Eligible items:   {len(eligible)} "
                    f"(newest: {selected.version}, user_prefix={selected.user_prefix!r})"
                )
                logger.info(f"[OTA]    Download URL:     {selected.url}")
                logger.info(f"[OTA]    File size:        {selected.length or 0} bytes")
                logger.info(f"[OTA]    Has signature:    {'Yes' if selected.ed_signature else 'No'}")

                selected_dict = item_to_update_dict(selected)
                alternate_url = selected_dict["alternate_url"]
                if alternate_url and alternate_url != selected.alternate_url:
                    logger.info(f"[OTA]    Alternate URL (auto-generated): {alternate_url}")
                elif alternate_url:
                    logger.info(f"[OTA]    Alternate URL (configured): {alternate_url}")

                update_info = {
                    "update_available": True,
                    "latest_version": selected.version,
                    "download_url": selected_dict["download_url"],
                    "alternate_url": alternate_url,
                    "file_size": selected_dict["file_size"],
                    "signature": selected_dict["signature"],
                    "description": selected_dict["description"],
                    "source": "windows_appcast",
                    "available_versions": [item_to_update_dict(it) for it in eligible],
                    "user_prefix": user_prefix,
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
        """Install update

        Delegates to :class:`InstallationManager` so the Windows OTA path
        uses the SAME code as the GUI flow (UpdateDialog → InstallWorker
        → InstallationManager._install_exe/_install_msi). This guarantees:

          * Inno Setup silent flags (``/SILENT`` + ``/NORESTART`` + ``/SP-``
            + ``/CLOSEAPPLICATIONS``) instead of the wrong NSIS-only
            ``/S`` flag that the old inline ``_install_windows_package``
            used — see Bug #1 in this file's history.
          * Custom install-directory lookup via Windows registry (so users
            who installed to D:\\MyApps\\eCan get upgraded in place).
          * DETACHED_PROCESS / CREATE_NEW_PROCESS_GROUP so the installer
            survives our ``os._exit(0)`` (the old inline path called
            ``sys.exit(0)`` WITHOUT detach and could be killed along
            with its child — see Bug #1).
          * BAT launcher with 3 s delay so the launcher can outlive the
            Python interpreter that spawned it.

        Do NOT reimplement any of this here; the headless / CLI path
        must match what users actually see on Windows desktop.
        """
        try:
            if not package_manager or not package_manager.current_package:
                logger.error("No package available for installation")
                return False

            package = package_manager.current_package
            if not package.is_downloaded or not package.download_path:
                logger.error("Package not downloaded")
                return False

            from .installer import InstallationManager

            installer = InstallationManager()
            return installer.install_package(
                package_path=Path(package.download_path),
                install_options={
                    'silent': True,
                    'create_backup': True,
                    # Inno Setup's [Run] (without skipifsilent — see
                    # the ecan_build.py change 2026-09-16) auto-launches
                    # the new exe after install, so the flag here is
                    # irrelevant for Windows. We keep it True to match
                    # Linux / macOS — a future refactor that moves
                    # Windows off Inno Setup will then Just Work.
                    'auto_restart': True,
                },
            )

        except Exception as e:
            logger.error(f"Windows install failed: {e}")
            return False

    # Legacy method kept for backwards compatibility with tests / mock
    # fixtures that still import it. All real callers MUST go through
    # ``install_update`` above, which delegates to InstallationManager.
    def _install_windows_package(self, package_path) -> bool:  # pragma: no cover - legacy
        """Legacy Windows installer entry point. Use ``install_update`` instead.

        Returns False with a warning so a caller using the legacy method
        by accident will be loudly redirected at runtime, instead of
        silently using the broken ``/S`` flag / no-detach behaviour.
        """
        logger.warning(
            "[OTA] _install_windows_package is deprecated; use "
            "InstallationManager.install_package via "
            "WindowsUpdater.install_update instead."
        )
        try:
            from .installer import InstallationManager
            installer = InstallationManager()
            return installer.install_package(
                package_path=Path(package_path),
                install_options={'silent': True},
            )
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
            from .appcast import (
                parse_appcast,
                select_latest_for_platform,
                select_eligible_versions,
                item_to_update_dict,
                normalize_arch_tag,
            )
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
            from .appcast import (
                parse_appcast,
                select_latest_for_platform,
                select_eligible_versions,
                item_to_update_dict,
                normalize_arch_tag,
            )

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

            # Select eligible items for current platform / user. Linux
            # previously did an extra ``packaging.version`` check on top
            # of ``select_latest_for_platform``; ``select_eligible_versions``
            # already filters strictly-newer-than-current using our
            # homegrown ``compare_versions`` (which handles multi-segment
            # date-based versions like ``26.05.03.22.22``), so the extra
            # check is redundant. We keep ``packaging.version`` as a
            # best-effort cross-check for extra safety in case an
            # appcast carries pre-1.0 semver strings.
            current_version = self.ota_manager.app_version
            user_prefix = getattr(self.ota_manager, "user_prefix", None)
            eligible = select_eligible_versions(
                items,
                'linux',
                current_version,
                arch,
                user_prefix=user_prefix,
            )

            if not eligible:
                logger.info("[OTA] No applicable updates for this platform / user")
                return (False, None) if return_info else False

            latest_item = eligible[0]

            # Defensive cross-check with ``packaging.version`` only when
            # both sides look semver-shaped; if it disagrees we trust our
            # own comparator (already vetted in
            # tests/test_ota_appcast_user_prefix.py).
            from packaging import version as pkg_version
            try:
                if pkg_version.parse(latest_item.version) <= pkg_version.parse(current_version):
                    logger.warning(
                        f"[OTA] packaging.version disagrees with select_eligible_versions "
                        f"({latest_item.version} vs {current_version}); trusting the latter."
                    )
            except Exception as e:
                logger.debug(f"[OTA] packaging.version cross-check skipped: {e}")

            # Update available (match Mac/Windows update_info shape).
            logger.info(f"[OTA] ✅ Update available!")
            logger.info(f"[OTA]    Current version:  {current_version}")
            logger.info(
                f"[OTA]    Eligible items:   {len(eligible)} "
                f"(newest: {latest_item.version}, user_prefix={latest_item.user_prefix!r})"
            )
            logger.info(f"[OTA]    Download URL:     {latest_item.url}")

            if return_info:
                selected_dict = item_to_update_dict(latest_item)
                update_info = {
                    'update_available': True,
                    'latest_version': latest_item.version,
                    'download_url': selected_dict['download_url'],
                    'alternate_url': selected_dict['alternate_url'],
                    'file_size': selected_dict['file_size'],
                    'signature': selected_dict['signature'],
                    'description': selected_dict['description'],
                    'source': 'linux_appcast',
                    'available_versions': [item_to_update_dict(it) for it in eligible],
                    'user_prefix': user_prefix,
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
        """Install update using package manager

        Delegates to :class:`InstallationManager` (same as macOS and
        Windows) so the Linux path uses the canonical install logic.
        That matters because ``InstallationManager._install_appimage``
        and ``InstallationManager._install_deb`` are the methods
        that respect ``install_options['auto_restart']`` — the
        legacy ``LinuxUpdater._install_appimage`` /
        ``LinuxUpdater._install_deb`` below NEVER called
        ``_schedule_linux_restart``, so AppImage / DEB upgrades
        left the user staring at no app at all until they relaunched
        it from the .desktop file. See Bug 2026-09-16 in this file's
        history.
        """
        try:
            logger.info("[OTA] Linux updater: install_update called")

            # In dev mode, only log without actual installation
            if ota_config.is_dev_mode():
                logger.info("[OTA] Development mode: Linux installation simulated")
                return True

            if not package_manager or not package_manager.current_package:
                logger.error("[OTA] No package available for Linux installation")
                return False

            package = package_manager.current_package
            if not package.is_downloaded or not package.download_path:
                logger.error("[OTA] Package not downloaded")
                return False

            # Hand off to InstallationManager so ``auto_restart`` is
            # honoured. The supported Linux formats (.appimage, .deb)
            # route through the right internal method based on suffix.
            from .installer import InstallationManager
            installer = InstallationManager()
            return installer.install_package(
                package_path=Path(package.download_path),
                install_options={
                    'silent': True,
                    'create_backup': True,
                    # True so ``_install_appimage`` / ``_install_deb``
                    # schedule the restart helper. Without this, the
                    # running exe is gone (we copied over it) and the
                    # user has no obvious way to start the new app.
                    'auto_restart': True,
                },
            )

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
            install_dir = safe_makedirs(Path.home() / '.local' / 'bin', purpose="AppImage install directory")
            
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
        """Schedule application restart after installation

        Writes the helper script under ``<appdata>/ota_scripts/`` (NOT
        ``tempfile.NamedTemporaryFile`` with ``delete=False``) so the
        path is stable, survives ``$TMPDIR`` rotation, and is visible to
        the user for debugging. The previous tempfile-based version
        leaked one ``/tmp/tmpXXXXXX.sh`` per OTA upgrade — the script
        only ``rm -f "$0"``'d itself on success; if the process was
        killed mid-way (Ctrl-C, OOM, parent crash), the file persisted.
        """
        try:
            from config.app_info import app_info
            script_dir = safe_makedirs(Path(app_info.appdata_path) / "ota_scripts", purpose="OTA scripts")

            script_path = script_dir / f"restart_{os.getpid()}_{time.time_ns()}.sh"
            script_content = f'''#!/bin/bash
# Wait for current process to exit
sleep 2

# Start new version
"{app_path}" &

# Clean up this script
rm -f "$0"
'''
            script_path.write_text(script_content, encoding='utf-8')
            os.chmod(script_path, 0o755)

            # Execute restart script in background
            subprocess.Popen([str(script_path)], start_new_session=True)

            logger.info(f"[OTA] Restart scheduled: {app_path} (script={script_path})")

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
