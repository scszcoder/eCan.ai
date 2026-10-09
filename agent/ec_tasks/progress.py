"""Last-progress timestamps for running tasks.

The runner's blocked-task clear counts from a task's last sign of life (node
entered, browser step taken), so a run that is busy for longer than
RUNNING_TASK_BLOCKED_CLEAR_SEC is not mistaken for a hung one (2026-10-09:
every chip-docs coordinator round was cancelled at 300 s). Kept dependency-free
so node code and cloud workers can call it cheaply.
"""

import time
from typing import Dict, Optional

_TASK_LAST_PROGRESS: Dict[str, float] = {}


def note_task_progress(task_id: Optional[str] = None) -> None:
    """Record that a task is making progress; defaults to the current log scope's task."""
    if not task_id:
        from utils.log_scope import get_scope
        task_id = get_scope().get("task_id")
    if task_id:
        _TASK_LAST_PROGRESS[str(task_id)] = time.monotonic()


def seconds_since_progress(task_id: str) -> Optional[float]:
    """Seconds since the task last reported progress, or None if it never did."""
    t = _TASK_LAST_PROGRESS.get(str(task_id))
    return None if t is None else time.monotonic() - t
