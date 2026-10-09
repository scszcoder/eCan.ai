"""A busy task must not be cleared as "blocked".

2026-10-09: the queue watchdog cancelled every chip-docs coordinator round at
300 s although the browser agent was taking a step every ~10 s. The blocked
timer now counts from the task's last progress (node entered / browser step).
"""
import time

from agent.ec_tasks import progress
from utils.log_scope import scope


def test_note_progress_uses_scope_task_id():
    with scope(task_id="task_progress_scope_t1"):
        progress.note_task_progress()
    idle = progress.seconds_since_progress("task_progress_scope_t1")
    assert idle is not None and idle < 1.0


def test_unknown_task_has_no_progress():
    assert progress.seconds_since_progress("task_never_seen") is None


def test_progress_resets_idle_time(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(progress.time, "monotonic", lambda: now[0])
    progress.note_task_progress("task_progress_t2")
    now[0] += 400.0
    assert progress.seconds_since_progress("task_progress_t2") == 400.0
    progress.note_task_progress("task_progress_t2")
    now[0] += 10.0
    assert progress.seconds_since_progress("task_progress_t2") == 10.0
