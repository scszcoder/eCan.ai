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


def test_browser_step_outside_the_run_scope_still_counts_for_the_task():
    """browser_use calls the step callback outside the run's log scope; the
    step must still count for the task that created it (KEN 2026-10-25: every
    商品上架 run was cleared at 300 s while taking a step every ~10 s)."""
    import threading
    from agent.ec_skills.browser_node.runner import make_browser_step_callback

    with scope(task_id="task_browser_step_t3"):
        cb = make_browser_step_callback("browser_publish")
    t = threading.Thread(target=cb, args=(None, None, 1))   # a fresh thread has no scope
    t.start()
    t.join()
    idle = progress.seconds_since_progress("task_browser_step_t3")
    assert idle is not None and idle < 1.0


def test_browser_step_counts_for_the_task_passed_in_without_any_scope():
    """A node built outside every log scope still credits the run's task when
    the runner passes its id (KEN 2026-10-27: an 运营 agent's 抖店商品上架 run
    was cleared at 300 s while stepping)."""
    from agent.ec_skills.browser_node.runner import make_browser_step_callback

    cb = make_browser_step_callback("browser_publish", task_id="task_browser_step_t4")
    cb(None, None, 1)
    idle = progress.seconds_since_progress("task_browser_step_t4")
    assert idle is not None and idle < 1.0


def test_a_failed_browser_llm_call_still_counts_for_the_task():
    """Four 75 s LLM timeouts in a row must not look like a hung task: browser-use
    stops on its own after max_failures (KEN 2026-10-27: 抖店商品上架12 was cleared
    at 300 s between retries)."""
    import asyncio

    import pytest

    from agent.ec_skills.browser_node.runner import _trace_llm_calls

    class _LLM:
        async def ainvoke(self, *a, **k):
            raise TimeoutError()

    llm = _trace_llm_calls(_LLM(), "eCanAI", "qwen3.8-flash", task_id="task_llm_fail_t5")
    with pytest.raises(TimeoutError):
        asyncio.run(llm.ainvoke([]))
    idle = progress.seconds_since_progress("task_llm_fail_t5")
    assert idle is not None and idle < 1.0
