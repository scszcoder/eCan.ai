"""A skill-editor Run must not be dropped by its own launcher future.

launch_dev_run_task stored the thread-pool future that runs launch_dev_run on
the dev task, and the run's submit guard treats a running task.future as a
prior execution still in progress, so it blocked itself: every Run on KEN
(2026-10-27) logged "Blocking 'dev:run task …' because prior execution future
is still running" and nothing ran.
"""
import concurrent.futures
import threading
from types import SimpleNamespace

from agent.ec_agent import EC_Agent
from agent.ec_tasks.runner import _task_execution_future_running


def test_the_launched_dev_run_does_not_see_its_own_future_as_running():
    seen = {}
    started = threading.Event()
    release = threading.Event()
    template = SimpleNamespace(name="dev:run task for skill under development", id="dev-t1",
                               run_id=None, cancellation_event=threading.Event(),
                               future=concurrent.futures.Future())  # leftover from an earlier run
    template.future.set_running_or_notify_cancel()

    def launch_dev_run(init_state, task):
        started.set()
        release.wait(5)  # the launcher has returned by now
        seen["running"] = _task_execution_future_running(task)
        return {"success": True}

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    agent = SimpleNamespace(tasks=[template], task_lock=threading.Lock(), active_tasks={},
                            runner=SimpleNamespace(launch_dev_run=launch_dev_run),
                            mainwin=SimpleNamespace(threadPoolExecutor=pool),
                            is_task_running=lambda key: False,
                            _task_done_callback=lambda key, f: None)
    try:
        result = EC_Agent.launch_dev_run_task(agent, {})
        assert result["success"]
        assert started.wait(5)
        release.set()
        agent.active_tasks["dev_run"].result(timeout=5)
    finally:
        pool.shutdown(wait=True)
    assert seen["running"] is False
