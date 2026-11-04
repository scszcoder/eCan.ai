"""Every run is submitted inside its task's scope, from any thread (KEN 2026-10-31).

A one-off that waited for a quiet browser was resubmitted from a threading.Timer:
that run had no scope at all -- no X-Ecan-* attribution, no billing_test, no log tags.
"""

import threading
from types import SimpleNamespace

from agent.ec_tasks.runner import TaskRunner
from utils.log_scope import get_scope, scope


def _runner(seen):
    r = object.__new__(TaskRunner)
    r._run_scope_fields = lambda t: {"task_id": t.id, "skill_id": "skill_1", "billing_test": True}
    r._submit_task_execution_impl = lambda t, m, tt, d: seen.append(get_scope())
    return r


def test_a_submit_from_a_timer_thread_runs_in_the_task_scope():
    seen = []
    r, task = _runner(seen), SimpleNamespace(id="task_1")
    th = threading.Thread(target=r._submit_task_execution, args=(task, None, "auto", None))
    th.start(); th.join()
    assert seen == [{"task_id": "task_1", "skill_id": "skill_1", "billing_test": True}]
    assert get_scope() == {}          # nothing leaks out


def test_a_submit_already_in_the_task_scope_keeps_it():
    seen = []
    r, task = _runner(seen), SimpleNamespace(id="task_1")
    with scope(task_id="task_1", agent_name="a"):
        r._submit_task_execution(task, None, "auto", None)
    assert seen == [{"task_id": "task_1", "agent_name": "a"}]
