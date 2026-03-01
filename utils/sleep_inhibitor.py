#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cross-Platform Sleep Inhibitor

Prevents the system from entering idle sleep while tasks are actively running.
Uses OS-native APIs on Windows, macOS, and Linux.

Usage:
    from utils.sleep_inhibitor import SleepInhibitor

    inhibitor = SleepInhibitor(reason="Active agent tasks running")
    inhibitor.acquire()   # Prevent idle sleep
    inhibitor.release()   # Allow sleep again

Notes:
    - Only prevents *idle* sleep. User can still manually sleep the machine.
    - Safe to call acquire()/release() multiple times (idempotent).
    - Includes a watchdog: auto-releases after max_duration_minutes if caller
      forgets to release (prevents battery drain on laptops).
"""

import sys
import os
import time
import threading
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singleton instance
# ---------------------------------------------------------------------------
_instance = None
_instance_lock = threading.Lock()


def get_sleep_inhibitor() -> "SleepInhibitor":
    """Get or create the global SleepInhibitor singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = SleepInhibitor()
    return _instance


class SleepInhibitor:
    """Cross-platform sleep prevention.

    Prevents the OS from entering idle sleep while tasks are active.
    Each platform uses its native mechanism:

    - **Windows**: ``SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)``
    - **macOS**: ``caffeinate -i -w <pid>`` subprocess
    - **Linux**: D-Bus ``org.freedesktop.login1.Manager.Inhibit("sleep", …)``
    """

    def __init__(
        self,
        reason: str = "Active agent tasks running",
        max_duration_minutes: int = 480,  # 8 hours safety cap
    ):
        self._reason = reason
        self._max_duration_seconds = max_duration_minutes * 60
        self._active = False
        self._handle = None            # platform-specific handle
        self._acquired_at: float = 0.0
        self._watchdog_timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
        self._ref_count = 0            # allows nested acquire/release

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_active(self) -> bool:
        """Return True if sleep is currently inhibited."""
        return self._active

    def acquire(self) -> bool:
        """Prevent idle sleep. Returns True if successfully acquired.

        Thread-safe and ref-counted: multiple callers can acquire;
        sleep is allowed again only when all have released.
        """
        with self._lock:
            self._ref_count += 1
            if self._active:
                logger.debug(f"[SleepInhibitor] Already active (ref_count={self._ref_count})")
                return True
            return self._do_acquire()

    def release(self) -> None:
        """Allow idle sleep again.

        Only truly releases when ref_count drops to zero.
        """
        with self._lock:
            if self._ref_count > 0:
                self._ref_count -= 1
            if self._ref_count > 0:
                logger.debug(f"[SleepInhibitor] Still held (ref_count={self._ref_count})")
                return
            self._do_release()

    def force_release(self) -> None:
        """Unconditionally release regardless of ref count."""
        with self._lock:
            self._ref_count = 0
            self._do_release()

    # ------------------------------------------------------------------
    # Internal: platform dispatch
    # ------------------------------------------------------------------

    def _do_acquire(self) -> bool:
        try:
            if sys.platform == "win32":
                self._acquire_windows()
            elif sys.platform == "darwin":
                self._acquire_macos()
            else:
                self._acquire_linux()
            self._active = True
            self._acquired_at = time.time()
            self._start_watchdog()
            logger.info(f"[SleepInhibitor] Acquired — idle sleep prevented ({sys.platform})")
            return True
        except Exception as e:
            logger.warning(f"[SleepInhibitor] Failed to acquire: {e}")
            return False

    def _do_release(self) -> None:
        if not self._active:
            return
        try:
            if sys.platform == "win32":
                self._release_windows()
            elif sys.platform == "darwin":
                self._release_macos()
            else:
                self._release_linux()
        except Exception as e:
            logger.warning(f"[SleepInhibitor] Error during release: {e}")
        finally:
            self._active = False
            self._cancel_watchdog()
            elapsed = time.time() - self._acquired_at if self._acquired_at else 0
            logger.info(f"[SleepInhibitor] Released — idle sleep allowed (held for {elapsed:.0f}s)")

    # ------------------------------------------------------------------
    # Windows
    # ------------------------------------------------------------------

    def _acquire_windows(self) -> None:
        import ctypes
        ES_CONTINUOUS = 0x80000000
        ES_SYSTEM_REQUIRED = 0x00000002
        ctypes.windll.kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED
        )

    def _release_windows(self) -> None:
        import ctypes
        ES_CONTINUOUS = 0x80000000
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)

    # ------------------------------------------------------------------
    # macOS
    # ------------------------------------------------------------------

    def _acquire_macos(self) -> None:
        import subprocess
        # caffeinate -i prevents idle sleep; -w ties lifetime to our PID
        self._handle = subprocess.Popen(
            ["caffeinate", "-i", "-w", str(os.getpid())],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _release_macos(self) -> None:
        if self._handle is not None:
            try:
                self._handle.terminate()
                self._handle.wait(timeout=5)
            except Exception:
                try:
                    self._handle.kill()
                except Exception:
                    pass
            self._handle = None

    # ------------------------------------------------------------------
    # Linux (systemd-logind via D-Bus)
    # ------------------------------------------------------------------

    def _acquire_linux(self) -> None:
        try:
            import dbus  # type: ignore[import-untyped]
            bus = dbus.SystemBus()
            mgr = bus.get_object(
                "org.freedesktop.login1",
                "/org/freedesktop/login1",
            )
            iface = dbus.Interface(mgr, "org.freedesktop.login1.Manager")
            # Inhibit returns a file descriptor; keeping it open holds the lock
            self._handle = iface.Inhibit("sleep", "eCan.ai", self._reason, "block")
            logger.debug("[SleepInhibitor] Linux: D-Bus Inhibit lock acquired")
        except ImportError:
            logger.debug("[SleepInhibitor] Linux: dbus module not available, sleep inhibit skipped")
        except Exception as e:
            logger.debug(f"[SleepInhibitor] Linux: D-Bus inhibit failed: {e}")

    def _release_linux(self) -> None:
        if self._handle is not None:
            try:
                # The D-Bus inhibit fd just needs to be closed
                fd = self._handle
                if hasattr(fd, "take"):
                    os.close(fd.take())
                elif isinstance(fd, int):
                    os.close(fd)
                else:
                    # dbus.UnixFd — extract raw fd
                    raw = getattr(fd, "variant_level", None)
                    if raw is not None:
                        os.close(int(fd))
            except Exception as e:
                logger.debug(f"[SleepInhibitor] Linux: release error: {e}")
            self._handle = None

    # ------------------------------------------------------------------
    # Watchdog — auto-release safety net
    # ------------------------------------------------------------------

    def _start_watchdog(self) -> None:
        self._cancel_watchdog()
        if self._max_duration_seconds > 0:
            self._watchdog_timer = threading.Timer(
                self._max_duration_seconds, self._watchdog_expired
            )
            self._watchdog_timer.daemon = True
            self._watchdog_timer.start()

    def _cancel_watchdog(self) -> None:
        if self._watchdog_timer is not None:
            self._watchdog_timer.cancel()
            self._watchdog_timer = None

    def _watchdog_expired(self) -> None:
        logger.warning(
            f"[SleepInhibitor] Watchdog: max duration ({self._max_duration_seconds}s) exceeded — forcing release"
        )
        self.force_release()
