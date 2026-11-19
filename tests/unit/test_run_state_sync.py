"""Background runs keep their task record's status in step, locally and in the cloud
(server note 9a.6 item 4: the cloud read crawl tasks as "pending, 0 %" for weeks)."""
import types

import pytest

from agent.ec_tasks import run_state_sync as R


class Tasks:
    def __init__(self):
        self.rows = {"T1": {"id": "T1", "name": "crawl", "status": "pending", "progress": 0.0, "error_message": "",
                            "schedule": {"repeat_type": "by days"}, "trigger": "schedule"}}

    def update_task(self, task_id, fields):
        if task_id not in self.rows:
            return {"success": False, "error": "Task not found"}
        self.rows[task_id].update(fields)
        return {"success": True}

    def get_task_by_id(self, task_id):
        return {"success": True, "data": dict(self.rows[task_id])}


@pytest.fixture
def env(monkeypatch):
    synced = []

    class Sync:
        def sync_to_cloud(self, data_type, data, operation):
            synced.append((str(data_type), data, str(operation)))
            return {"success": True}
    from agent.cloud_api import offline_sync_manager
    monkeypatch.setattr(offline_sync_manager, "get_sync_manager", lambda: Sync())
    tasks = Tasks()
    queued = []
    monkeypatch.setattr(R._pool, "submit", lambda fn, *a: queued.append((fn, a)))
    mw = types.SimpleNamespace(ec_db_mgr=types.SimpleNamespace(task_service=tasks))
    return types.SimpleNamespace(mw=mw, tasks=tasks, synced=synced, queued=queued)


def _drain(env):
    for fn, a in env.queued:
        fn(*a)
    env.queued.clear()


def _task(state="completed", text=""):
    msg = types.SimpleNamespace(parts=[types.SimpleNamespace(root=types.SimpleNamespace(text=text))]) if text else None
    return types.SimpleNamespace(id="T1", source="ui",
                                 status=types.SimpleNamespace(state=types.SimpleNamespace(value=state), message=msg))


def test_a_scheduled_run_marks_its_task_running_then_completed_and_syncs_the_whole_record(env):
    R.record(env.mw, _task(), "running", "schedule")
    _drain(env)
    assert env.tasks.rows["T1"]["status"] == "running"
    R.record(env.mw, _task(), R.outcome(_task("completed")), "schedule")
    _drain(env)
    assert env.tasks.rows["T1"]["status"] == "completed" and env.tasks.rows["T1"]["progress"] == 1.0
    kind, data, op = env.synced[-1]
    assert "task" in kind.lower() and "update" in op.lower()
    assert data["id"] == "T1" and data["schedule"] == {"repeat_type": "by days"} and data["status"] == "completed"


def test_a_failed_run_keeps_its_error_and_a_later_success_clears_it(env):
    t = _task("failed", "the page did not load")
    R.record(env.mw, t, R.outcome(t), "auto", R.error_text(t))
    _drain(env)
    assert env.tasks.rows["T1"]["status"] == "failed" and env.tasks.rows["T1"]["error_message"] == "the page did not load"
    R.record(env.mw, _task(), "completed", "auto")
    _drain(env)
    assert env.tasks.rows["T1"]["error_message"] == ""


def test_chat_and_message_turns_and_code_tasks_are_not_recorded(env):
    R.record(env.mw, _task(), "running", "message")
    R.record(env.mw, _task(), "running", "chat_queue")
    R.record(env.mw, types.SimpleNamespace(id="T1", source="code"), "running", "schedule")
    assert env.queued == []


def test_a_run_waiting_for_input_goes_back_to_pending():
    assert R.outcome(_task("input-required")) == "pending" and R.outcome(_task("canceled")) == "cancelled"


def test_a_task_without_a_local_record_is_skipped_quietly(env):
    R.record(env.mw, types.SimpleNamespace(id="T9", source="ui"), "running", "schedule")
    _drain(env)
    assert env.synced == []
