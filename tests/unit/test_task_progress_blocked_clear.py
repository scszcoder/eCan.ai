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


def test_stale_progress_entries_are_evicted(monkeypatch):
    """Unbounded growth guard: dead tasks must not accumulate forever.

    Task IDs are UUIDs and note_task_progress() runs on every busy node, so
    without eviction every task that ever ran leaves a permanent entry.
    """
    progress._TASK_LAST_PROGRESS.clear()
    now = [10_000.0]
    monkeypatch.setattr(progress.time, "monotonic", lambda: now[0])

    progress.note_task_progress("task_evict_old")
    now[0] += progress._PROGRESS_TTL_SEC + 1.0
    # A write for a different task triggers the sweep and drops the stale one.
    progress.note_task_progress("task_evict_new")

    assert "task_evict_old" not in progress._TASK_LAST_PROGRESS
    assert "task_evict_new" in progress._TASK_LAST_PROGRESS


def test_seconds_since_progress_lazily_expires(monkeypatch):
    progress._TASK_LAST_PROGRESS.clear()
    now = [20_000.0]
    monkeypatch.setattr(progress.time, "monotonic", lambda: now[0])

    progress.note_task_progress("task_lazy_expire")
    now[0] += progress._PROGRESS_TTL_SEC + 5.0

    assert progress.seconds_since_progress("task_lazy_expire") is None
    assert "task_lazy_expire" not in progress._TASK_LAST_PROGRESS


def test_a_submitted_task_making_progress_is_not_a_stale_future():
    """2026-10-24: a chip-docs worker stays 'submitted' through a 5-minute batch run; the queue cleared that
    live run as a stale future after 60 s when the next batch came, and the batch was lost."""
    from a2a.types import TaskState
    from agent.ec_tasks.runner import _is_stale_future_suspect
    progress.note_task_progress("task_stale_busy")
    assert not _is_stale_future_suspect(TaskState.submitted, True, False, "task_stale_busy")
    # no sign of life at all: still a suspect, as before
    assert _is_stale_future_suspect(TaskState.submitted, True, False, "task_stale_never_seen")
    # a finished future is never a running zombie
    assert not _is_stale_future_suspect(TaskState.submitted, False, True, "task_stale_never_seen")
    assert not _is_stale_future_suspect(TaskState.working, True, False, "task_stale_never_seen")


def test_a_submitted_task_idle_too_long_is_a_stale_future(monkeypatch):
    from a2a.types import TaskState
    from agent.ec_tasks import runner
    now = [50_000.0]
    monkeypatch.setattr(progress.time, "monotonic", lambda: now[0])
    progress.note_task_progress("task_stale_idle")
    now[0] += runner.RUNNING_TASK_BLOCKED_CLEAR_SEC + 1
    assert runner._is_stale_future_suspect(TaskState.submitted, True, False, "task_stale_idle")
