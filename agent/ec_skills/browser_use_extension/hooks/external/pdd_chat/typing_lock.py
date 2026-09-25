"""The Pinduoduo chat page's typing lock: one reply box per store, one sender at a time.

Non-blocking by design (Feige ws175: a blocking ``threading.Lock.acquire`` on
the CDP loop deadlocked the whole process). ``try_acquire`` never waits; the
bounded wait lives in ``hot_path_v2._acquire_typing_lock`` as ``await sleep``.
A holder that outlives the TTL is presumed dead and its lock is taken over.

Several stores in one process each have their own page, so each has its own
slot, named by the store's browser (``session_key``: a key or the browser
session). A caller that names no store contends with every store -- it can
cost parallelism, never let two sends race inside one page. With one store
this is exactly one lock.
"""
from __future__ import annotations

import os
import threading
import time

from utils.logger_helper import logger_helper as logger

_DEFAULT_TTL_S = 30.0
_ANY = ""


def store_key_of(session_or_key) -> str:
    """The store's browser: its profile folder, else its CDP endpoint."""
    s = session_or_key
    if s is None:
        return _ANY
    if isinstance(s, str):
        return s
    bp = getattr(s, "browser_profile", None)
    udd = getattr(bp, "user_data_dir", None) if bp is not None else None
    if udd:
        return "profile:" + os.path.normcase(os.path.abspath(str(udd)))
    return str(getattr(s, "cdp_url", None) or getattr(bp, "cdp_url", None) or _ANY)


class TypingLock:
    def __init__(self):
        self._guard = threading.Lock()      # held only for these few assignments
        self._slots: dict = {}              # store key -> (holder, since)

    @property
    def _holder(self) -> str:               # one-store view, kept for callers/tests
        return self.holder()

    def _ttl(self) -> float:
        try:
            return float(os.environ.get("ECAN_PDD_TYPING_LOCK_TTL_S", "") or _DEFAULT_TTL_S)
        except (TypeError, ValueError):
            return _DEFAULT_TTL_S

    def _contenders(self, store: str) -> list:
        return list(self._slots) if store == _ANY else [store, _ANY]

    def try_acquire(self, key: str, session_key=None) -> bool:
        key = str(key or "")
        if not key:
            return False
        store = store_key_of(session_key)
        with self._guard:
            now = time.monotonic()
            for slot in self._contenders(store):
                cur, since = self._slots.get(slot, ("", 0.0))
                if not cur or cur == key:
                    continue
                if now - since > self._ttl():
                    logger.warning(f"[PDD-TYPING-LOCK] taking over from {cur!r} "
                                   f"(held {now - since:.0f}s) for {key!r}")
                    self._slots.pop(slot, None)
                    continue
                return False
            self._slots[store] = (key, now)
            return True

    def release(self, key: str, session_key=None) -> None:
        store = store_key_of(session_key)
        with self._guard:
            cur, _ = self._slots.get(store, ("", 0.0))
            if cur and (not key or cur == str(key)):
                self._slots.pop(store, None)

    def holder(self, session_key=None) -> str:
        store = store_key_of(session_key)
        with self._guard:
            for slot in self._contenders(store):
                cur, _ = self._slots.get(slot, ("", 0.0))
                if cur:
                    return cur
        return ""


_LOCK = TypingLock()


def get_lock() -> TypingLock:
    return _LOCK
