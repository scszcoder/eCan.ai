#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cross-Platform Power Event Monitor

Detects system sleep/wake transitions using Qt events and provides hooks
for reconnection and catch-up logic on wake.

Usage:
    from utils.power_monitor import PowerMonitor, get_power_monitor

    # During app startup (after QApplication exists):
    monitor = get_power_monitor()
    monitor.install()

    # Register wake callbacks:
    monitor.on_wake(my_reconnect_function)
    monitor.on_sleep(my_save_state_function)

Qt maps OS-specific power broadcasts into unified events:
    - Windows: WM_POWERBROADCAST → QEvent.Sleep / QEvent.Resume
    - macOS:   NSWorkspaceWillSleepNotification → QEvent.Sleep / QEvent.Resume
    - Linux:   PrepareForSleep D-Bus signal → QEvent.Sleep / QEvent.Resume

TODO(cli-task-execution): When CLI mode supports running/scheduling tasks,
    add a headless NativePowerBackend that detects sleep/wake without Qt:
    - Windows: RegisterPowerSettingNotification via ctypes
    - macOS:   IOKit power notifications
    - Linux:   D-Bus PrepareForSleep signal (org.freedesktop.login1.Manager)
    Extract PowerMonitor.install() into a protocol/ABC with two backends:
    QtPowerBackend (current) and NativePowerBackend (headless).
    SleepInhibitor already works headless — no changes needed there.
"""

import time
import logging
import threading
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_instance: Optional["PowerMonitor"] = None
_instance_lock = threading.Lock()


def get_power_monitor() -> "PowerMonitor":
    """Get or create the global PowerMonitor singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = PowerMonitor()
    return _instance


class PowerMonitor:
    """Monitors system sleep/wake events via Qt and dispatches callbacks.

    Callbacks are invoked on the **main Qt thread** (since Qt delivers
    QEvent.Sleep / QEvent.Resume on the main thread).

    Attributes:
        last_sleep_time: epoch timestamp of the most recent sleep event
        last_wake_time:  epoch timestamp of the most recent wake event
        sleep_duration:  seconds the machine was asleep (approximate)
    """

    def __init__(self):
        self._sleep_callbacks: List[Callable] = []
        self._wake_callbacks: List[Callable] = []
        self._filter: Optional["_PowerEventFilter"] = None
        self._installed = False

        # Timing info
        self.last_sleep_time: float = 0.0
        self.last_wake_time: float = 0.0
        self.sleep_duration: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def install(self) -> bool:
        """Install the Qt event filter on QApplication. Call once after QApp exists.

        Returns True on success.
        """
        if self._installed:
            return True

        try:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is None:
                logger.warning("[PowerMonitor] QApplication not yet created — cannot install")
                return False

            self._filter = _PowerEventFilter(self)
            app.installEventFilter(self._filter)
            self._installed = True
            logger.info("[PowerMonitor] Installed — listening for sleep/wake events")
            return True
        except Exception as e:
            logger.warning(f"[PowerMonitor] Failed to install event filter: {e}")
            return False

    def on_sleep(self, callback: Callable) -> None:
        """Register a callback to be invoked when the system is about to sleep.

        Callback signature: ``callback() -> None``
        """
        if callback not in self._sleep_callbacks:
            self._sleep_callbacks.append(callback)

    def on_wake(self, callback: Callable) -> None:
        """Register a callback to be invoked when the system wakes from sleep.

        Callback signature: ``callback(sleep_duration_seconds: float) -> None``
        """
        if callback not in self._wake_callbacks:
            self._wake_callbacks.append(callback)

    def remove_sleep_callback(self, callback: Callable) -> None:
        """Remove a previously registered sleep callback."""
        try:
            self._sleep_callbacks.remove(callback)
        except ValueError:
            pass

    def remove_wake_callback(self, callback: Callable) -> None:
        """Remove a previously registered wake callback."""
        try:
            self._wake_callbacks.remove(callback)
        except ValueError:
            pass

    # ------------------------------------------------------------------
    # Internal: called by the event filter
    # ------------------------------------------------------------------

    def _handle_sleep(self) -> None:
        self.last_sleep_time = time.time()
        logger.info(f"[PowerMonitor] System entering sleep at {time.strftime('%H:%M:%S')}")

        for cb in self._sleep_callbacks:
            try:
                cb()
            except Exception as e:
                logger.error(f"[PowerMonitor] Sleep callback {cb.__name__} failed: {e}")

    def _handle_wake(self) -> None:
        now = time.time()
        self.last_wake_time = now
        if self.last_sleep_time > 0:
            self.sleep_duration = now - self.last_sleep_time
        else:
            self.sleep_duration = 0.0

        logger.info(
            f"[PowerMonitor] System woke up at {time.strftime('%H:%M:%S')} "
            f"(asleep for {self.sleep_duration:.1f}s)"
        )

        for cb in self._wake_callbacks:
            try:
                cb(self.sleep_duration)
            except Exception as e:
                logger.error(f"[PowerMonitor] Wake callback {cb.__name__} failed: {e}")


# ---------------------------------------------------------------------------
# Qt event filter (internal)
# ---------------------------------------------------------------------------

class _PowerEventFilter(QObject):
    """Lightweight QObject event filter that intercepts QEvent.Sleep / QEvent.Resume."""

    def __init__(self, monitor: "PowerMonitor"):
        from PySide6.QtCore import QObject, QEvent
        super().__init__()
        self._monitor = monitor

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        etype = event.type()
        # QEvent.Type.Sleep = 168, QEvent.Type.Resume = 169 (Qt 6)
        # 使用 hasattr 安全检查，避免 macOS 上不存在这些类型
        if hasattr(QEvent.Type, 'Sleep') and etype == QEvent.Type.Sleep:
            self._monitor._handle_sleep()
        elif hasattr(QEvent.Type, 'Resume') and etype == QEvent.Type.Resume:
            self._monitor._handle_wake()
        return False  # never consume the event
