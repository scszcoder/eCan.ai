""""After task" trigger (multi-task Phase 3): agent/ec_tasks/task_deps.py, the
runner's completion hook, and the save-time cycle check."""
from __future__ import annotations

import concurrent.futures
import os
import sys
import threading
import time
from queue import Queue
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from a2a.types import TaskState
from agent.ec_tasks import resource_gate as rg
from agent.ec_tasks.task_deps import AfterTracker, after_config, find_cycle


# ── task_deps ────────────────────────────────────────────────────────────────

def test_find_cycle():
    g = {"A": ["B"], "B": ["C"], "C": [], "X": ["Y"], "Y": ["X"], "S": ["S"]}
    assert find_cycle("A", g.get) is None
    assert find_cycle("X", g.get) == ["X", "Y", "X"]
    assert find_cycle("S", g.get) == ["S", "S"]
    g["C"] = ["A"]
    assert find_cycle("A", g.get) == ["A", "B", "C", "A"]


def _t(tid, trigger=("after",), after=None, **meta):
    m = dict(meta)
    if after is not None:
        m["after"] = after
    return SimpleNamespace(id=tid, name=tid, agent_id="", metadata=m, trigger=list(trigger),
                           skill=SimpleNamespace(diagram={}, requires=[], name="s", price=0, skill_owner=""),
                           status=SimpleNamespace(state=None, message=None), queue=Queue(), future=None,
                           cancellation_event=threading.Event(), schedule=None,
                           last_run_datetime=None, already_run_flag=False)


def test_tracker_all_of_and_require_success():
    tr = AfterTracker()
    c = _t("C", after={"tasks": ["A", "B", "A"], "require_success": True})
    assert after_config(c) == (["A", "B"], True)
    tr.record("A", True)
    assert tr.status(c) == (False, ["B"])
    tr.record("B", False)
    assert tr.status(c) == (False, ["B (failed)"])
    tr.record("B", True)
    assert tr.status(c)[0] is True
    assert set(tr.consume(c)) == {"A", "B"}
    assert tr.status(c) == (False, ["A", "B"])          # needs fresh finishes next time


# ── runner ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def inline(monkeypatch):
    monkeypatch.setattr(rg, "_gate", rg.ResourceGate(spawn=lambda fn: fn()))
    # Threads the runner starts (after-runs, queued runs) run inline.
    import agent.ec_tasks.runner as runner_mod

    class _InlineThreading:
        def __getattr__(self, name):
            return getattr(threading, name)

        @staticmethod
        def Thread(target, args=(), **kw):
            return SimpleNamespace(start=lambda: target(*args))
    monkeypatch.setattr(runner_mod, "threading", _InlineThreading())


def _runner(tasks):
    from agent.ec_tasks.runner import TaskRunner
    r = TaskRunner.__new__(TaskRunner)
    r._task_states = {}
    r._task_execution_lock = threading.RLock()
    r._stop_event = threading.Event()
    r.runs = []

    def _submit(fn):
        f = concurrent.futures.Future()
        r.runs.append(f)
        return f
    r._skill_executor = MagicMock()
    r._skill_executor.submit = MagicMock(side_effect=_submit)
    r._is_hybrid_cloud_task = lambda *_a, **_kw: False
    r._is_pure_cloud_task = lambda *_a, **_kw: False
    r._amend_event_routing_for_task = lambda *_a, **_kw: None

    def _done(future, task, *_a, **_kw):
        task.future = None
        try:
            task.status.state = TaskState.failed if future.exception() else TaskState.completed
        except BaseException:
            task.status.state = TaskState.canceled
    r._on_skill_complete = _done
    r._emit_task_status = lambda *_a, **_kw: None
    r.agent = SimpleNamespace(card=SimpleNamespace(id="ag1"), tasks=tasks)
    r.submitted = []
    real = r._submit_task_execution

    def _spy(task, msg, trigger, dev):
        r.submitted.append((task.id, trigger, msg))
        return real(task, msg, trigger, dev)
    r._submit_task_execution = _spy
    return r


def _run_and_finish(r, task, ok=True, result="done"):
    r._submit_task_execution(task, {"__trigger_source__": "auto"}, "auto", None)
    fut = r.runs[-1]
    fut.set_result(result) if ok else fut.set_exception(RuntimeError("boom"))


def test_b_runs_when_a_finishes_with_a_result():
    a, b = _t("A", trigger=("auto",)), _t("B", after={"tasks": ["A"]})
    r = _runner([a, b])
    _run_and_finish(r, a, result={"rows": 12})
    tid, trig, msg = r.submitted[-1]
    assert (tid, trig) == ("B", "after")
    assert msg["upstream"]["A"]["ok"] is True and "rows" in msg["upstream"]["A"]["summary"]


def test_waits_for_all_prerequisites():
    a, c = _t("A", trigger=("auto",)), _t("C", trigger=("auto",))
    b = _t("B", after={"tasks": ["A", "C"]})
    r = _runner([a, c, b])
    _run_and_finish(r, a)
    assert [s[0] for s in r.submitted] == ["A"]
    _run_and_finish(r, c)
    assert [s[0] for s in r.submitted] == ["A", "C", "B"]


def test_require_success():
    a = _t("A", trigger=("auto",))
    strict, lax = _t("S", after={"tasks": ["A"], "require_success": True}), _t("L", after={"tasks": ["A"]})
    r = _runner([a, strict, lax])
    _run_and_finish(r, a, ok=False)
    started = [s[0] for s in r.submitted]
    assert "L" in started and "S" not in started
    assert r.submitted[-1][2]["upstream"]["A"]["summary"].startswith("error:")


def test_parked_run_is_not_a_finish():
    a, b = _t("A", trigger=("auto",)), _t("B", after={"tasks": ["A"]})
    r = _runner([a, b])
    r._on_skill_complete = lambda future, task, *_a, **_kw: setattr(task.status, "state", TaskState.input_required)
    _run_and_finish(r, a)
    assert [s[0] for s in r.submitted] == ["A"]


def test_scheduled_run_waits_for_its_prerequisite():
    a = _t("A", trigger=("auto",))
    b = _t("B", trigger=("schedule", "after"), after={"tasks": ["A"]})
    r = _runner([a, b])
    due = {"__trigger_source__": "schedule", "__due_at__": time.time()}
    r._submit_task_execution(b, due, "schedule", None)        # 10:30 comes, A not done
    assert len(r.runs) == 0
    _run_and_finish(r, a)                                     # A done -> B's held run starts
    assert r.submitted[-1][:2] == ("B", "schedule") and len(r.runs) == 2
    assert "A" in r.submitted[-1][2]["upstream"]


def test_scheduled_task_with_done_prerequisite_waits_for_its_schedule():
    a = _t("A", trigger=("auto",))
    b = _t("B", trigger=("schedule", "after"), after={"tasks": ["A"]})
    r = _runner([a, b])
    _run_and_finish(r, a)
    assert [s[0] for s in r.submitted] == ["A"]               # not due yet: nothing starts
    r._submit_task_execution(b, {"__trigger_source__": "schedule", "__due_at__": time.time()}, "schedule", None)
    assert len(r.runs) == 2


def test_cycle_is_not_started():
    a = _t("A", trigger=("auto", "after"), after={"tasks": ["B"]})
    b = _t("B", after={"tasks": ["A"]})
    r = _runner([a, b])
    _run_and_finish(r, a)
    assert [s[0] for s in r.submitted] == ["A"]


def test_converter_carries_after():
    from agent.agent_converter import _convert_dict_to_task
    t = _convert_dict_to_task({"id": "t1", "name": "x", "trigger": "after",
                               "metadata": {"after": {"tasks": ["a"], "require_success": True}}})
    assert t.metadata["after"] == {"tasks": ["a"], "require_success": True}
    assert "after" in t.trigger


def test_save_rejects_a_cycle():
    from gui.ipc.w2p_handlers.task_handler import _after_cycle_error
    rows = {"B": {"name": "日报", "metadata": {"after": {"tasks": ["A"]}}},
            "C": {"name": "清理", "metadata": {}}}
    svc = SimpleNamespace(query_tasks=lambda id: {"success": True, "data": [rows[id]]} if id in rows
                          else {"success": True, "data": []})
    err = _after_cycle_error("A", {"name": "抓取", "settings": {"after": {"tasks": ["B"]}}}, svc)
    assert err == "Task dependencies form a cycle: 抓取 -> 日报 -> 抓取"
    assert _after_cycle_error("A", {"name": "抓取", "settings": {"after": {"tasks": ["C"]}}}, svc) == ""
    assert _after_cycle_error("A", {"name": "抓取", "settings": {}}, svc) == ""


def test_a_finish_before_a_restart_still_counts():
    a = _t("A", trigger=("auto",))
    b = _t("B", trigger=("schedule", "after"), after={"tasks": ["A"]})
    r1 = _runner([a, b])
    _run_and_finish(r1, a)
    assert a.metadata["last_finish"]["ok"] is True          # saved with the task's settings
    assert "last_finish" not in b.metadata                    # only prerequisites save their finish
    r2 = _runner([a, b])                                      # the app restarted: fresh runner
    r2._submit_task_execution(b, {"__trigger_source__": "schedule"}, "schedule", None)
    assert r2.submitted[-1][0] == "B" and len(r2.runs) == 1   # not held: A's finish counts
    assert b.metadata["after_consumed_at"] > 0                # used up, also across a restart
    r3 = _runner([a, b])
    assert r3._after_tracker().status(b)[0] is False          # same finish doesn't count twice
