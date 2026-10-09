"""An auto-trigger task fires once per app start, not again after it finishes.

2026-10-09: the completion cleanup drops the task's _task_states entry, which
held the "auto_started" flag, so the chip-docs coordinator was kicked off again
every loop pass (~40 s) after its crawl was complete.
"""
from queue import Queue
from types import SimpleNamespace

from agent.ec_tasks.runner import TaskRunner


def _runner():
    r = TaskRunner.__new__(TaskRunner)  # no agent/thread setup needed for this path
    r._task_states = {}
    r.agent = SimpleNamespace(tasks=[])
    return r


def _next(r, task):
    return r._get_next_work_item(["auto"], task, task, 1, False, None)


def test_auto_kickoff_not_repeated_after_completion_cleanup():
    r = _runner()
    task = SimpleNamespace(id="task_auto_1", name="t", queue=Queue(), status=None, future=None)
    first = _next(r, task)
    assert first[1].get("__auto_kickoff__") is True
    r._task_states.pop(task.id, None)  # what the completion handler does
    second = _next(r, task)
    assert not (isinstance(second[1], dict) and second[1].get("__auto_kickoff__"))
