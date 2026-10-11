"""Scheduled-run rules in the runner (multi-task Phase 2): max lateness ->
missed, overlap_policy, background deferral, per-task schedule picking, and
the scheduling settings carried from the DB task row."""
from __future__ import annotations

import concurrent.futures
import os
import sys
import threading
import time
from datetime import datetime, timedelta
from queue import Queue
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.ec_tasks import resource_gate as rg
from agent.ec_tasks.models import RepeatType, TaskSchedule

BROWSER_DIAGRAM = {"nodes": [{"type": "browser-automation"}]}


def _sched(start: datetime, minutes: int = 60) -> TaskSchedule:
    fmt = "%Y-%m-%d %H:%M:%S"
    return TaskSchedule(repeat_type=RepeatType.BY_MINUTES, repeat_number=minutes, repeat_unit="minutes",
                        start_date_time=start.strftime(fmt),
                        end_date_time=(start + timedelta(days=30)).strftime(fmt), time_out=60)


def _task(tid, **meta):
    t = SimpleNamespace(id=tid, name=tid, agent_id="", metadata=dict(meta),
                        skill=SimpleNamespace(diagram=BROWSER_DIAGRAM, requires=[], name="s", price=0, skill_owner=""),
                        status=SimpleNamespace(state=None, message=None), queue=Queue(), future=None,
                        cancellation_event=threading.Event(), trigger=["schedule"], schedule=None,
                        last_run_datetime=None, already_run_flag=False)
    t.metadata.setdefault("browser_identity", {"browser_profile_id": "p1"})
    return t


def _runner(tasks):
    from agent.ec_tasks.runner import TaskRunner
    r = TaskRunner.__new__(TaskRunner)
    r._task_states = {}
    r._task_execution_lock = threading.RLock()
    r._stop_event = threading.Event()
    r.futures = []

    def _submit(fn):
        f = concurrent.futures.Future()
        r.futures.append(f)
        return f
    r._skill_executor = MagicMock()
    r._skill_executor.submit = MagicMock(side_effect=_submit)
    r._is_hybrid_cloud_task = lambda *_a, **_kw: False
    r._is_pure_cloud_task = lambda *_a, **_kw: False
    r._amend_event_routing_for_task = lambda *_a, **_kw: None
    def _done(future, task, *_a, **_kw):   # what _on_skill_complete does for a finished run
        task.future = None
        task.status.state = None
    r._on_skill_complete = _done
    r._emit_task_status = lambda *_a, **_kw: None
    r.agent = SimpleNamespace(card=SimpleNamespace(id="ag1"), tasks=tasks)
    return r


@pytest.fixture(autouse=True)
def inline_gate(monkeypatch):
    g = rg.ResourceGate(spawn=lambda fn: fn())
    monkeypatch.setattr(rg, "_gate", g)
    monkeypatch.setenv("ECAN_TASK_RESOURCE_GATE", "1")
    return g


def _due(minutes_ago: float) -> dict:
    return {"__trigger_source__": "schedule", "__due_at__": time.time() - minutes_ago * 60}


def test_late_scheduled_run_is_missed_and_recorded():
    t = _task("A", max_lateness_min=10)
    r = _runner([t])
    r._submit_task_execution(t, _due(25), "schedule", None)
    assert r.futures == [] and t.metadata["last_missed"]["why"].startswith("25 min late")
    r._submit_task_execution(t, _due(5), "schedule", None)
    assert len(r.futures) == 1


def test_waiting_for_a_resource_past_max_lateness_is_missed(inline_gate):
    a, b = _task("A"), _task("B", max_lateness_min=10)
    r = _runner([a, b])
    r._submit_task_execution(a, _due(0), "schedule", None)
    late_b = _due(0)
    r._submit_task_execution(b, late_b, "schedule", None)          # waits behind A
    late_b["__due_at__"] -= 20 * 60                                 # A ran 20 min
    r.futures[0].set_result(None)
    assert len(r.futures) == 1 and "min late" in b.metadata["last_missed"]["why"]
    assert inline_gate.snapshot()["held"] == {}


def test_overlap_skip_is_the_default_and_marks_missed():
    t = _task("A")
    r = _runner([t])
    r._submit_task_execution(t, _due(0), "schedule", None)
    r._submit_task_execution(t, _due(0), "schedule", None)
    assert len(r.futures) == 1 and "previous run" in t.metadata["last_missed"]["why"]


def test_overlap_queue_one_runs_once_after_the_current_run(monkeypatch):
    started = []
    monkeypatch.setattr(threading, "Thread", lambda target, args, **kw: SimpleNamespace(
        start=lambda: (started.append(1), target(*args))))
    t = _task("A", overlap_policy="queue_one")
    r = _runner([t])
    r._submit_task_execution(t, _due(0), "schedule", None)
    r._submit_task_execution(t, _due(0), "schedule", None)          # queued
    r._submit_task_execution(t, _due(0), "schedule", None)          # one is already queued
    assert len(r.futures) == 1 and "already queued" in t.metadata["last_missed"]["why"]
    r.futures[0].set_result(None)
    assert started == [1] and len(r.futures) == 2


def test_background_run_waits_when_a_scheduled_task_on_its_browser_is_due_soon(monkeypatch):
    timers = []

    class _T:
        def __init__(self, secs, fn):
            timers.append(secs)
            self.daemon = False

        def start(self):
            pass
    monkeypatch.setattr(threading, "Timer", _T)
    bg = _task("scrape", run_class="background", run_durations=[600, 600])
    other = _task("report")
    other.schedule = _sched(datetime.now() - timedelta(minutes=55))          # next run in ~5 min
    r = _runner([bg, other])
    r._submit_task_execution(bg, _due(0), "schedule", None)
    assert r.futures == [] and len(timers) == 1
    r._submit_task_execution(bg, _due(0), "schedule", None)                  # no second timer
    assert len(timers) == 1
    # Different browser: no conflict.
    r2 = _runner([_task("scrape2", run_class="background"), other])
    other.metadata["browser_identity"] = {"browser_profile_id": "p2"}
    r2._submit_task_execution(r2.agent.tasks[0], _due(0), "schedule", None)
    assert len(r2.futures) == 1


def test_each_loop_fires_only_its_own_schedule():
    a, b = _task("A"), _task("B")
    for t in (a, b):
        t.schedule = _sched(datetime.now() - timedelta(minutes=61))
    r = _runner([a, b])
    task, msg, _ = r._get_next_work_item(["schedule"], a, None, 0, False, None)
    assert task is a and msg["__trigger_source__"] == "schedule" and msg["__due_at__"] <= time.time()
    task, msg, _ = r._get_next_work_item(["schedule"], b, None, 0, False, None)
    assert task is b


def test_scheduling_settings_are_carried_from_the_db_row():
    from agent.agent_converter import _convert_dict_to_task as conv
    t = conv({"id": "t1", "name": "x", "trigger": "schedule", "metadata": {
        "run_class": "Background", "overlap_policy": "queue_one", "max_lateness_min": "30",
        "exclusive_resources": ["printer", ""]}})
    assert t.metadata["run_class"] == "background"
    assert t.metadata["overlap_policy"] == "queue_one"
    assert t.metadata["max_lateness_min"] == 30.0
    assert t.metadata["exclusive_resources"] == ["printer"]


# ── run_once / start_after_idle_min (7b: a one-time background job on a busy browser) ──

def test_gate_idle_for(monkeypatch):
    t = [1000.0]
    monkeypatch.setattr(rg.time, "time", lambda: t[0])
    g = rg.ResourceGate(spawn=lambda fn: fn())
    t[0] = 1100.0
    assert g.idle_for(("k",)) == 100.0                  # unused since the gate started
    g.acquire_or_wait("A", ("k",), rg.REACTIVE, 0, on_grant=lambda: None)
    assert g.idle_for(("k",)) == 0.0
    t[0] = 1200.0
    g.release("A", ("k",))
    t[0] = 1260.0
    assert g.idle_for(("k",)) == 60.0


def test_run_once_never_runs_again():
    t = _task("export", run_once=True)
    r = _runner([t])
    saved = []
    r._persist_task_settings = lambda task, **v: (task.metadata.update(v), saved.append(v))
    r._submit_task_execution(t, {"__trigger_source__": "auto"}, "auto", None)
    assert len(r.futures) == 1
    r.futures[0].set_result({"rows": 12})
    assert saved and "completed_once_at" in saved[0]
    r._submit_task_execution(t, {"__trigger_source__": "auto"}, "auto", None)
    assert len(r.futures) == 1


def test_start_after_idle_waits_for_the_browser_to_go_quiet(monkeypatch, inline_gate):
    timers = []

    class _T:
        def __init__(self, secs, fn):
            timers.append((secs, fn))
            self.daemon = False

        def start(self):
            pass
    monkeypatch.setattr(threading, "Timer", _T)
    clock = [5000.0]
    monkeypatch.setattr(rg.time, "time", lambda: clock[0])
    inline_gate._started = 5000.0
    chat = _task("前台")
    export = _task("导出商品", start_after_idle_min=5, run_class="background")
    r = _runner([chat, export])
    r._submit_task_execution(chat, {"__trigger_source__": "message"}, "message", None)
    r.futures[0].set_result(None)                       # a chat turn just used the browser
    clock[0] = 5060.0
    r._submit_task_execution(export, {"__trigger_source__": "auto"}, "auto", None)
    assert len(r.futures) == 1 and len(timers) == 1 and timers[0][0] == pytest.approx(240.0)
    r._submit_task_execution(export, {"__trigger_source__": "auto"}, "auto", None)
    assert len(timers) == 1                              # one retry pending, not two
    clock[0] = 5000.0 + 301
    timers[0][1]()                                       # the retry: quiet for 5 min now
    assert len(r.futures) == 2
