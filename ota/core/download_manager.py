#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OTA Download Manager - Global download state management
Manages download progress and state across the application
"""

import os as _os
from typing import Optional, Callable, Dict, Any

# PySide6 is OPTIONAL here. The download manager is a singleton that's
# touched by both:
#   * GUI code (Qt slots / signals for live progress in UpdateDialog)
#   * Headless installer code (ota.core.installer calls
#     ``download_manager.set_installing(True)`` to suppress the
#     "are you sure you want to exit?" prompt while Inno Setup is
#     waiting for the process to die).
#
# When PySide6 is missing — every CI runner, every lightweight
# unit-test environment — we still need the installer's flag calls to
# work. We therefore:
#   1. Make the ``QObject`` inheritance conditional: subclass
#      ``QObject`` only when PySide6 is importable, otherwise fall
#      back to a plain ``object`` whose ``Signal`` attributes become
#      inert ``_OtaSignal`` instances that swallow ``.connect`` /
#      ``.emit`` calls.
#   2. The plain ``object`` subclass keeps the same public method
#      surface (``set_installing``, ``is_installing``, ``reset``,
#      state attributes) so the installer's non-Qt code path is
#      unchanged.
#
# This unblocks ``ota.core.installer`` (and all tests that exercise
# it, e.g. ``tests/unit/test_ota_path_safety.py``) from running in
# CI without PySide6 — which is the canonical regression case from
# Bug 2026-09-16 where the test suite crashed at collection time
# because ``ota.core.installer`` pulled PySide6 through its
# ``ota.gui.i18n`` import (since fixed by moving i18n out of ota.gui/).
try:
    from PySide6.QtCore import QObject as _QObjectBase
    _PYSIDE_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised by CI without PySide6
    _PYSIDE_AVAILABLE = False

    class _QObjectBase:  # type: ignore[no-redef]
        """Minimal stand-in for ``QObject`` when PySide6 is unavailable.

        Qt-specific methods (``__getattr__`` for dynamic props, signal
        routing, etc.) are not needed by the non-GUI call sites — only
        the constructor and ``super().__init__()`` chain are.
        """
        def __init__(self, *args, **kwargs):
            pass

    class _OtaSignal:
        """Inert signal stand-in.

        ``UpdateDialog`` connects Qt signals with ``.connect(slot)``
        and emits via ``.emit(*args)``. In headless mode neither call
        site is reached, but to be defensive we keep both methods
        well-defined so accidental non-GUI calls don't crash.
        """
        def __init__(self, *args, **kwargs):
            self._args = args

        def connect(self, *args, **kwargs):
            return None

        def disconnect(self, *args, **kwargs):
            return None

        def emit(self, *args, **kwargs):
            return None


def _maybe_signal(*signature):
    """Return a real Qt ``Signal`` if PySide6 is available, else an inert one."""
    if _PYSIDE_AVAILABLE:
        from PySide6.QtCore import Signal  # local import — bound to current frame
        return Signal(*signature)
    return _OtaSignal(*signature)


from utils.logger_helper import logger_helper as logger
from ota.i18n import get_translator

# Get translator instance
_tr = get_translator()


class DownloadState:
    """Download state enumeration"""
    IDLE = "idle"
    CHECKING = "checking"
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DownloadManager(_QObjectBase):
    """Global download manager - Singleton pattern

    Inherits from ``QObject`` when PySide6 is available so that
    ``state_changed``, ``progress_updated`` and ``download_completed``
    are real Qt signals the GUI can ``.connect()`` to. In a headless
    test/CI environment those become inert ``_OtaSignal`` stand-ins
    that no-op ``.connect`` / ``.emit`` calls.
    """

    # Signals for download state changes
    state_changed = _maybe_signal(str)  # state
    progress_updated = _maybe_signal(int, str, str)  # progress%, speed, remaining_time
    download_completed = _maybe_signal(bool, str)  # success, message

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        super().__init__()
        self._initialized = True
        
        # Download state
        self.state = DownloadState.IDLE
        self.progress = 0
        self.speed = ""
        self.remaining_time = ""
        self.version = None
        self.update_info = None
        self.error_message = None
        
        # Download worker reference
        self.download_worker = None
        
        # OTA installation flag - set to True when installer is about to launch
        self._ota_installing = False
        
        logger.info("[DownloadManager] Initialized")
    
    @classmethod
    def get_instance(cls):
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def set_state(self, state: str):
        """Set download state"""
        if self.state != state:
            self.state = state
            self.state_changed.emit(state)
            logger.debug(f"[DownloadManager] State changed: {state}")
    
    def update_progress(self, progress: int, speed: str = "", remaining_time: str = ""):
        """Update download progress"""
        self.progress = progress
        self.speed = speed
        self.remaining_time = remaining_time
        self.progress_updated.emit(progress, speed, remaining_time)
    
    def start_download(self, version: str, update_info: Dict[str, Any], worker):
        """Start download"""
        self.version = version
        self.update_info = update_info
        self.download_worker = worker
        self.progress = 0
        self.speed = ""
        self.remaining_time = ""
        self.error_message = None
        self.set_state(DownloadState.DOWNLOADING)
        logger.info(f"[DownloadManager] Download started: version {version}")
    
    def complete_download(self, success: bool, message: str = ""):
        """Complete download"""
        if success:
            self.set_state(DownloadState.COMPLETED)
            self.progress = 100
        else:
            self.set_state(DownloadState.FAILED)
            self.error_message = message
        
        self.download_completed.emit(success, message)
        self.download_worker = None
        logger.info(f"[DownloadManager] Download completed: success={success}")
    
    def cancel_download(self):
        """Cancel download"""
        if self.download_worker:
            self.download_worker.cancel()
            self.download_worker = None
        
        self.set_state(DownloadState.CANCELLED)
        self.progress = 0
        logger.info("[DownloadManager] Download cancelled")
    
    def reset(self):
        """Reset to idle state"""
        self.state = DownloadState.IDLE
        self.progress = 0
        self.speed = ""
        self.remaining_time = ""
        self.version = None
        self.update_info = None
        self.error_message = None
        self.download_worker = None
        self._ota_installing = False
    
    def set_installing(self, installing: bool = True):
        """Set OTA installation flag"""
        self._ota_installing = installing
        if installing:
            logger.info("[DownloadManager] OTA installation flag set - app will exit without confirmation")
        else:
            logger.info("[DownloadManager] OTA installation flag cleared")

    def is_installing(self) -> bool:
        """Check if OTA installer has been launched and installation is in progress"""
        return bool(self._ota_installing)
    
    def is_downloading(self) -> bool:
        """Check if currently downloading"""
        return self.state == DownloadState.DOWNLOADING
    
    def get_status_text(self, lang: str = None) -> str:
        """
        Get status text for display
        
        Args:
            lang: Language code (deprecated, kept for compatibility)
            
        Returns:
            Translated status text
        """
        if self.state == DownloadState.IDLE:
            return _tr.tr("check_for_updates")
        elif self.state == DownloadState.CHECKING:
            return _tr.tr("checking_for_updates")
        elif self.state == DownloadState.DOWNLOADING:
            if self.progress > 0:
                return _tr.tr("downloading_progress").format(progress=self.progress)
            else:
                return _tr.tr("preparing_download_state")
        elif self.state == DownloadState.VERIFYING:
            return _tr.tr("verifying_state")
        elif self.state == DownloadState.COMPLETED:
            return _tr.tr("download_complete_state")
        elif self.state == DownloadState.FAILED:
            return _tr.tr("download_failed_state")
        elif self.state == DownloadState.CANCELLED:
            return _tr.tr("cancelled_state")
        else:
            return _tr.tr("check_for_updates")


# Global instance - lazy initialization to avoid circular imports
_download_manager = None

def get_download_manager():
    """Get the global download manager instance (lazy initialization)"""
    global _download_manager
    if _download_manager is None:
        _download_manager = DownloadManager.get_instance()
    return _download_manager

# For backward compatibility - property-like access
class _DownloadManagerProxy:
    """Proxy class for lazy access to download_manager"""
    def __getattr__(self, name):
        return getattr(get_download_manager(), name)
    
    def __setattr__(self, name, value):
        setattr(get_download_manager(), name, value)

download_manager = _DownloadManagerProxy()
