"""Last-progress timestamps for running tasks.

The runner's blocked-task clear counts from a task's last sign of life (node
entered, browser step taken), so a run that is busy for longer than
RUNNING_TASK_BLOCKED_CLEAR_SEC is not mistaken for a hung one (2026-10-09:
every chip-docs coordinator round was cancelled at 300 s). Kept dependency-free
so node code and cloud workers can call it cheaply.
"""

import threading
import time
from typing import Dict, Optional

_TASK_LAST_PROGRESS: Dict[str, float] = {}
_LOCK = threading.Lock()
# Drop entries that haven't reported progress in this long. Task IDs are UUIDs
# and note_task_progress() is called on every busy node, so a live task always
# refreshes its entry within this window; anything older is dead or abandoned
# and would otherwise accumulate forever (unbounded-growth leak: every task
# that ever ran would leave a permanent entry).
_PROGRESS_TTL_SEC = 600.0
# Hard cap: if the dict ever exceeds this many entries (e.g. a burst of short
# tasks all refreshing within the TTL window), evict the oldest by timestamp.
_PROGRESS_MAX_ENTRIES = 5000


def _evict_stale(now: float) -> None:
    """Drop progress entries older than _PROGRESS_TTL_SEC. Caller holds _LOCK."""
    cutoff = now - _PROGRESS_TTL_SEC
    stale = [tid for tid, ts in _TASK_LAST_PROGRESS.items() if ts < cutoff]
    for tid in stale:
        _TASK_LAST_PROGRESS.pop(tid, None)
    if len(_TASK_LAST_PROGRESS) > _PROGRESS_MAX_ENTRIES:
        # Evict oldest by timestamp to bound memory in pathological bursts.
        for tid, _ in sorted(_TASK_LAST_PROGRESS.items(), key=lambda kv: kv[1])[
            : len(_TASK_LAST_PROGRESS) - _PROGRESS_MAX_ENTRIES
        ]:
            _TASK_LAST_PROGRESS.pop(tid, None)


def note_task_progress(task_id: Optional[str] = None) -> None:
    """Record that a task is making progress; defaults to the current log scope's task."""
    if not task_id:
        from utils.log_scope import get_scope
        task_id = get_scope().get("task_id")
    if task_id:
        now = time.monotonic()
        with _LOCK:
            _TASK_LAST_PROGRESS[str(task_id)] = now
            _evict_stale(now)


def seconds_since_progress(task_id: str) -> Optional[float]:
    """Seconds since the task last reported progress, or None if it never did."""
    now = time.monotonic()
    with _LOCK:
        t = _TASK_LAST_PROGRESS.get(str(task_id))
        if t is not None and t < now - _PROGRESS_TTL_SEC:
            # Lazy expiry: the entry aged out since the last write.
            _TASK_LAST_PROGRESS.pop(str(task_id), None)
            return None
        return None if t is None else now - t
