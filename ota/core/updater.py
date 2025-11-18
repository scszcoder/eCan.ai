import os
import platform
import subprocess
import threading
import time
import time
from typing import Optional, Callable
from threading import Lock, Event

import sys
from pathlib import Path

# Add project root directory to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from config.app_info import app_info
    from config.constants import APP_NAME
except ImportError:
    # If import fails, use default values
    class DefaultAppInfo:
        def __init__(self):
            self.app_home_path = str(Path.cwd())

    app_info = DefaultAppInfo()
    APP_NAME = 'ecbot'
from utils.logger_helper import logger_helper as logger

from ota.config.loader import ota_config
from .package_manager import package_manager, UpdatePackage
from .platforms import SparkleUpdater, WinSparkleUpdater, GenericUpdater
from .errors import UpdateError, UpdateErrorCode, get_user_friendly_message


class OTAUpdater:
    """OTA update manager"""

    def __init__(self):
        self.platform = platform.system()
        # Get version from app_info (which reads from VERSION file)
        try:
            self.app_version = app_info.version
        except Exception as e:
            logger.warning(f"Failed to get version from app_info: {e}, using fallback")
            self.app_version = ota_config.get('app_version', '1.0.0')
        self.update_server_url = ota_config.get_update_server()

        # Thread safety related
        self._check_lock = Lock()  # Check update lock
        self._install_lock = Lock()  # Install update lock
        self._callback_lock = Lock()  # Callback lock
        self._stop_event = Event()  # Stop event

        self.is_checking = False
        self.is_installing = False
        self.update_callback: Optional[Callable] = None
        self.error_callback: Optional[Callable] = None
        self._auto_check_thread = None

        # Get application path
        self.app_home_path = app_info.app_home_path

        # Platform-specific updater
        self.platform_updater = self._create_platform_updater()

        logger.info(f"OTA Updater initialized for {self.platform}")

    def _create_platform_updater(self):
        """Create platform-specific updater"""
        # Dev mode can force generic updater for local debugging without platform dependencies
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

    def check_for_updates(self, silent: bool = False, return_info: bool = False):
        """Check for updates

        Args:
            silent: If True, suppress log messages
            return_info: If True, return (has_update, update_info) tuple

        Returns:
            bool or tuple: If return_info is False, returns bool indicating if update is available.
                          If return_info is True, returns (has_update, update_info) tuple.
        """
        with self._check_lock:
            if self.is_checking:
                if not silent:
                    logger.info("Update check already in progress")
                return (False, None) if return_info else False

            self.is_checking = True

        try:
            logger.info("Checking for updates...")

            has_update, update_info = self.platform_updater.check_for_updates(silent, return_info=True)

            # Check if error information was returned
            if isinstance(update_info, UpdateError):
                # Thread-safe error callback call
                self._safe_error_callback(update_info)
                return (False, update_info) if return_info else False

            # Thread-safe callback call
            if has_update:
                self._safe_callback(has_update, update_info)

            if return_info:
                return has_update, update_info
            else:
                return has_update

        except UpdateError as e:
            logger.error(f"Update check failed: {e}")
            self._safe_error_callback(e)
            return (False, e) if return_info else False
        except Exception as e:
            logger.error(f"Update check failed with unexpected error: {e}")
            error = UpdateError(
                UpdateErrorCode.UNKNOWN_ERROR,
                f"Unexpected error during update check: {str(e)}",
                {"original_error": str(e)}
            )
            self._safe_error_callback(error)
            return (False, error) if return_info else False
        finally:
            with self._check_lock:
                self.is_checking = False

    def install_update(self) -> bool:
        """Install update"""
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
        """Thread-safe callback call"""
        with self._callback_lock:
            if self.update_callback:
                try:
                    self.update_callback(has_update, update_info)
                except Exception as e:
                    logger.error(f"Update callback failed: {e}")

    def _safe_error_callback(self, error: UpdateError):
        """Thread-safe error callback call"""
        with self._callback_lock:
            if self.error_callback:
                try:
                    self.error_callback(error)
                except Exception as e:
                    logger.error(f"Error callback failed: {e}")
            else:
                # If no error callback, log user-friendly error message
                user_message = get_user_friendly_message(error)
                logger.error(f"Update error: {user_message}")

    def start_auto_check(self):
        """Start automatic checking"""
        if self._auto_check_thread and self._auto_check_thread.is_alive():
            logger.info("Auto check already running")
            return

        # Reset stop event
        self._stop_event.clear()

        def check_loop():
            check_interval = ota_config.get_check_interval()
            while not self._stop_event.is_set():
                try:
                    # Check if stop was requested
                    if self._stop_event.is_set():
                        break

                    self.check_for_updates(silent=True)

                    # Use event wait, can be interrupted immediately
                    if self._stop_event.wait(timeout=check_interval):
                        break  # Received stop signal

                except Exception as e:
                    logger.error(f"Auto check failed: {e}")
                    # Wait shorter time on error before retry
                    if self._stop_event.wait(timeout=300):  # 5 minutes
                        break  # Received stop signal

        self._auto_check_thread = threading.Thread(target=check_loop, daemon=True)
        self._auto_check_thread.start()
        logger.info("Auto update check started")

    def stop_auto_check(self):
        """Stop automatic checking"""
        if self._auto_check_thread and self._auto_check_thread.is_alive():
            # Set stop event
            self._stop_event.set()

            # Wait for thread to end
            self._auto_check_thread.join(timeout=5)  # Wait up to 5 seconds

            if self._auto_check_thread.is_alive():
                logger.warning("Auto check thread did not stop gracefully")
            else:
                logger.info("Auto update check stopped")
        else:
            logger.info("Auto check not running")

    def set_update_callback(self, callback: Callable):
        """Set update callback"""
        with self._callback_lock:
            self.update_callback = callback

    def set_error_callback(self, callback: Callable):
        """Set error callback"""
        with self._callback_lock:
            self.error_callback = callback

    def is_busy(self) -> bool:
        """Check if update-related operations are in progress"""
        return self.is_checking or self.is_installing

    def get_status(self) -> dict:
        """Get current status"""
        return {
            "is_checking": self.is_checking,
            "is_installing": self.is_installing,
            "auto_check_running": self._auto_check_thread and self._auto_check_thread.is_alive(),
            "platform": self.platform,
            "app_version": self.app_version
        }

    @classmethod
    def start_auto_check_in_background(cls, ctx=None, logger_instance=None):
        """Start OTA auto-check in a fully non-blocking way with initial delay.

        This spawns a bootstrap thread which then creates an OTAUpdater
        instance and starts its own auto-check thread. All potentially slow
        operations (I/O, network) are kept off the main thread.
        """
        log = logger_instance or logger

        def _bootstrap():
            try:
                if not ota_config.get("auto_check", True):
                    log.info("[OTA] Auto check disabled by config")
                    return

                # Delay OTA startup to avoid impacting application startup and login
                default_delay = 5 # 60  # Default delay: 1 minute
                delay = ota_config.get("auto_check_initial_delay", default_delay)
                try:
                    delay = float(delay)
                except (TypeError, ValueError):
                    delay = default_delay
                if delay > 0:
                    log.info(
                        f"[OTA] Delaying OTA auto check startup by {delay} seconds"
                    )
                    time.sleep(delay)

                # Create updater instance
                updater = cls()

                # Attach updater to global application context if possible
                if ctx is not None:
                    try:
                        setattr(ctx, "ota_updater", updater)
                    except Exception:
                        log.debug(
                            "[OTA] Failed to attach ota_updater to context",
                            exc_info=True,
                        )

                def on_update_available(has_update, info):
                    if has_update and info:
                        latest = info.get("latest_version") or info.get("version")
                        log.info(f"[OTA] New version available: {latest}")

                        # Check if this version is ignored
                        try:
                            from ota.core.version_ignore import get_version_ignore_manager
                            ignore_mgr = get_version_ignore_manager()
                            if ignore_mgr.is_ignored(latest):
                                log.info(f"[OTA] Version {latest} is ignored by user, skipping notification")
                                return
                        except Exception as e:
                            log.warning(f"[OTA] Failed to check version ignore status: {e}")

                        # Notify UI (WebGUI) on the main thread if available
                        if ctx is not None:
                            try:
                                web_gui = getattr(ctx, "web_gui", None)
                                if web_gui is not None:
                                    try:
                                        from utils.gui_dispatch import post_to_main_thread
                                    except Exception:
                                        post_to_main_thread = None

                                    if post_to_main_thread is not None:
                                        def _notify_ui_update():
                                            """On auto-check, update menu and show confirmation dialog."""
                                            try:
                                                # Update menu indicator to show update available
                                                if hasattr(web_gui, "_set_update_badge"):
                                                    try:
                                                        web_gui._set_update_badge(True, latest)
                                                        log.info(f"[OTA] Auto-check: Menu indicator updated for version {latest}")
                                                    except Exception as e:
                                                        log.warning(f"[OTA] Failed to update menu indicator on auto-check: {e}")
                                                
                                                # Show update confirmation dialog
                                                if hasattr(web_gui, "_show_update_confirmation"):
                                                    try:
                                                        web_gui._show_update_confirmation(latest, info, is_manual=False)
                                                        log.info(f"[OTA] Auto-check: Showing update confirmation for version {latest}")
                                                    except Exception as e:
                                                        log.warning(f"[OTA] Failed to show update confirmation: {e}")

                                            except Exception:
                                                log.debug(
                                                    "[OTA] Failed to dispatch OTA update notification",
                                                    exc_info=True,
                                                )

                                        post_to_main_thread(_notify_ui_update)
                            except Exception:
                                log.debug(
                                    "[OTA] Failed to dispatch OTA notification to GUI",
                                    exc_info=True,
                                )

                def on_update_error(error):
                    log.warning(f"[OTA] Auto check error: {error}")

                updater.set_update_callback(on_update_available)
                updater.set_error_callback(on_update_error)

                updater.start_auto_check()
            except Exception as e:
                log.warning(f"[OTA] Failed to start auto check in background: {e}")

        thread = threading.Thread(
            target=_bootstrap,
            name="OTAStartupBootstrap",
            daemon=True,
        )
        thread.start()
