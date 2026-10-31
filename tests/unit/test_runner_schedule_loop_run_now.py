"""Run now on a schedule-only task reaches its loop.

The loop dropped its task after the first idle pass (nothing due), so a launch
message queued later sat in the task's queue until the app restarted.
"""
import threading
import time
from queue import Queue
from types import SimpleNamespace

from a2a.types import TaskState

from agent.ec_tasks import runner as runner_mod
from agent.ec_tasks.runner import TaskRunner


class _Runner:
    _launch_unified_run_impl = TaskRunner._launch_unified_run_impl
    _get_next_work_item = TaskRunner._get_next_work_item
    _check_pending_timeout = TaskRunner._check_pending_timeout

    def __init__(self, task):
        self._stop_event = threading.Event()
        self._task_states = {}
        self.agent = SimpleNamespace(card=SimpleNamespace(name="Store Operator"), tasks=[task])
        self.submitted = []

    def _validate_task_for_execution(self, task):
        return True

    def _submit_task_execution(self, task, msg, trigger, dev_init_state):
        self.submitted.append((task, msg, trigger))
        self._stop_event.set()


def test_a_message_queued_after_an_idle_pass_is_run(monkeypatch):
    monkeypatch.setattr(runner_mod, "find_tasks_ready_to_run", lambda tasks: None)
    cancel = threading.Event()
    task = SimpleNamespace(id="t1", name="daily", queue=Queue(), future=None,
                           status=SimpleNamespace(state=TaskState.completed),
                           cancellation_event=cancel, pause_event=threading.Event(),
                           is_cancelled=cancel.is_set)
    r = _Runner(task)
    loop = threading.Thread(target=r._launch_unified_run_impl, args=(task, ["schedule"]), daemon=True)
    loop.start()
    time.sleep(2.0)                      # a few idle passes: nothing due, queue empty
    task.queue.put({"mtype": "launch_task"})
    loop.join(timeout=8)
    r._stop_event.set()
    assert r.submitted, "the queued launch message was never picked up"
    ran_task, msg, trigger = r.submitted[0]
    assert ran_task is task and msg.get("mtype") == "launch_task" and trigger == "message"
