"""千牛 desktop typing lock — one 千牛 client per process, so one sender at a time.

The desktop send path drives a single shared window via the mouse/keyboard, so
two sends must never interleave. Simpler than the browser bundles' per-page
lock: one slot, non-blocking ``try_acquire`` with a TTL takeover for a holder
that died mid-send. Interface matches the browser bundles so the runner bridge
exposes it the same way.
"""
from __future__ import annotations

import os
import threading
import time

from utils.logger_helper import logger_helper as logger

_DEFAULT_TTL_S = 30.0


class TypingLock:
    def __init__(self):
        self._guard = threading.Lock()
        self._holder = ""
        self._since = 0.0

    def _ttl(self) -> float:
        try:
            return float(os.environ.get("ECAN_QIANNIU_TYPING_LOCK_TTL_S", "") or _DEFAULT_TTL_S)
        except (TypeError, ValueError):
            return _DEFAULT_TTL_S

    def try_acquire(self, key: str, session_key=None) -> bool:
        key = str(key or "")
        if not key:
            return False
        with self._guard:
            now = time.monotonic()
            if self._holder and self._holder != key:
                if now - self._since <= self._ttl():
                    return False
                logger.warning(f"[QIANNIU-TYPING-LOCK] taking over from {self._holder!r} "
                               f"(held {now - self._since:.0f}s) for {key!r}")
            self._holder, self._since = key, now
            return True

    def release(self, key: str, session_key=None) -> None:
        with self._guard:
            if self._holder and (not key or self._holder == str(key)):
                self._holder, self._since = "", 0.0

    def holder(self, session_key=None) -> str:
        with self._guard:
            return self._holder


_LOCK = TypingLock()


def get_lock() -> TypingLock:
    return _LOCK
