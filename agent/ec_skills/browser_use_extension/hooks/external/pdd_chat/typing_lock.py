"""One typing lock for the Pinduoduo chat page: a single reply box, one sender at a time.

Non-blocking by design (Feige ws175: a blocking ``threading.Lock.acquire`` on
the CDP loop deadlocked the whole process). ``try_acquire`` never waits; the
bounded wait lives in ``hot_path_v2._acquire_typing_lock`` as ``await sleep``.
A holder that outlives the TTL is presumed dead and its lock is taken over.
"""
from __future__ import annotations

import os
import threading
import time

from utils.logger_helper import logger_helper as logger

_DEFAULT_TTL_S = 30.0


class TypingLock:
    def __init__(self):
        self._guard = threading.Lock()      # held only for these few assignments
        self._holder = ""
        self._since = 0.0

    def _ttl(self) -> float:
        try:
            return float(os.environ.get("ECAN_PDD_TYPING_LOCK_TTL_S", "") or _DEFAULT_TTL_S)
        except (TypeError, ValueError):
            return _DEFAULT_TTL_S

    def try_acquire(self, key: str) -> bool:
        key = str(key or "")
        if not key:
            return False
        with self._guard:
            now = time.monotonic()
            if not self._holder or self._holder == key:
                self._holder, self._since = key, now
                return True
            if now - self._since > self._ttl():
                logger.warning(f"[PDD-TYPING-LOCK] taking over from {self._holder!r} "
                               f"(held {now - self._since:.0f}s) for {key!r}")
                self._holder, self._since = key, now
                return True
            return False

    def release(self, key: str) -> None:
        with self._guard:
            if self._holder and (not key or self._holder == str(key)):
                self._holder, self._since = "", 0.0

    def holder(self) -> str:
        return self._holder


_LOCK = TypingLock()


def get_lock() -> TypingLock:
    return _LOCK


# Module-level API (the platform reads the bridge's ``typing_lock`` as an object
# with try_acquire / release / holder).
try_acquire = _LOCK.try_acquire
release = _LOCK.release
holder = _LOCK.holder
