"""ws075 (Phase 0): WS-vs-DOM coverage metrics for the WS-only-detection milestone.

Counters ONLY — no behaviour change. The point is per-run EVIDENCE of how often the
WS reader actually covers detection / name / reconnects vs falling back to DOM, so the
later phases retire DOM paths on data, not guesswork (removing a DOM path blind is how
ws069 froze). Gated by the caller on ``ECAN_FEIGE_WS_COVERAGE=1``.

Thread-safe: the observer feeds it from its own CDP loop/thread; other subsystems may
feed it from theirs. Cheap (dict increments under a lock).
"""
from __future__ import annotations

import os
import threading
import time

_lock = threading.Lock()
_counts: dict = {}
_coldstart_gap_ms = None          # one-shot: observer-start -> first frame
_window_start = time.time()


def enabled() -> bool:
    return os.environ.get("ECAN_FEIGE_WS_COVERAGE", "") == "1"


def note(key: str, n: int = 1) -> None:
    """Increment counter *key* by *n* (no-op on empty key)."""
    if not key:
        return
    with _lock:
        _counts[key] = _counts.get(key, 0) + n


def note_coldstart_gap(ms: float) -> None:
    """Record the observer-start -> first-frame blind window, ONCE per process."""
    global _coldstart_gap_ms
    with _lock:
        if _coldstart_gap_ms is None:
            _coldstart_gap_ms = round(float(ms), 1)


def snapshot() -> dict:
    with _lock:
        d = dict(_counts)
        d["coldstart_gap_ms"] = _coldstart_gap_ms
        d["window_s"] = round(time.time() - _window_start, 1)
        return d


def format_line() -> str:
    """Single ``[WS-COVERAGE] k=v ...`` line for the periodic emitter / teardown."""
    s = snapshot()
    return "[WS-COVERAGE] " + " ".join(f"{k}={v}" for k, v in s.items())


def reset_window() -> None:
    """Roll the window start (counts are cumulative; window_s is per-emit context)."""
    global _window_start
    with _lock:
        _window_start = time.time()
