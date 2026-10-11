"""Exclusive resources for task runs (agent/ec_tasks/resource_gate.py) and the
runner wiring in ``_submit_task_execution``."""
from __future__ import annotations

import concurrent.futures
import os
import sys
import threading
from queue import Queue
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.ec_tasks import resource_gate as rg
from agent.ec_tasks.resource_gate import ResourceGate, REACTIVE, SCHEDULED, BACKGROUND


def _gate():
    return ResourceGate(spawn=lambda fn: fn())   # grants run inline


def _waiter(gate, holder, keys, prio, tiebreak=0, log=None):
    log = log if log is not None else []
    return gate.acquire_or_wait(holder, keys, prio, tiebreak, on_grant=lambda: log.append(holder), label=holder)


# ── the gate ─────────────────────────────────────────────────────────────────

def test_free_keys_are_granted_and_unrelated_keys_run_in_parallel():
    g = _gate()
    assert g.acquire_or_wait("A", ("browser:1",), SCHEDULED, 0, on_grant=lambda: None) == "granted"
    assert g.acquire_or_wait("B", ("browser:2",), SCHEDULED, 0, on_grant=lambda: None) == "granted"
    assert g.acquire_or_wait("C", (), SCHEDULED, 0, on_grant=lambda: None) == "granted"


def test_shared_key_waits_and_is_granted_on_release():
    g, log = _gate(), []
    assert _waiter(g, "A", ("k",), SCHEDULED, log=log) == "granted"
    assert _waiter(g, "B", ("k",), SCHEDULED, log=log) == "queued"
    assert log == []
    g.release("A", ("k",))
    assert log == ["B"]                                  # B now holds k
    assert g.snapshot()["held"]["k"]["holder"] == "B"


def test_order_is_priority_then_arrival_then_list_position():
    g, log = _gate(), []
    _waiter(g, "A", ("k",), SCHEDULED, log=log)          # holds
    _waiter(g, "bg", ("k",), BACKGROUND, log=log)
    _waiter(g, "sched2", ("k",), SCHEDULED, tiebreak=5, log=log)
    _waiter(g, "sched1", ("k",), SCHEDULED, tiebreak=1, log=log)   # later, but same class
    _waiter(g, "chat", ("k",), REACTIVE, log=log)
    order = [w["holder"] for w in g.snapshot()["waiting"]]
    assert order == ["chat", "sched2", "sched1", "bg"]   # arrival beats list position
    for h in ["A", "chat", "sched2", "sched1"]:
        g.release(h, ("k",))
    assert log == ["chat", "sched2", "sched1", "bg"]


def test_list_position_breaks_exact_ties():
    g = _gate()
    _waiter(g, "A", ("k",), SCHEDULED)
    w1 = rg._Waiter("x", ("k",), SCHEDULED, 7, 3, lambda: None)
    w2 = rg._Waiter("y", ("k",), SCHEDULED, 7, 1, lambda: None)
    assert sorted([w1, w2], key=rg._Waiter.order)[0].holder == "y"


def test_newcomer_does_not_jump_a_queued_waiter():
    g, log = _gate(), []
    _waiter(g, "A", ("k",), SCHEDULED, log=log)
    _waiter(g, "B", ("k",), SCHEDULED, log=log)
    g.release("A", ("k",))                               # B granted
    g.release("B", ("k",))
    _waiter(g, "C", ("k",), SCHEDULED, log=log)
    _waiter(g, "D", ("k",), SCHEDULED, log=log)          # C holds; D queues
    assert log == ["B"] and g.snapshot()["waiting"][0]["holder"] == "D"


def test_multi_key_is_all_or_nothing_and_reserved_for_the_better_waiter():
    g, log = _gate(), []
    _waiter(g, "A", ("k1",), SCHEDULED, log=log)
    _waiter(g, "B", ("k1", "k2"), REACTIVE, log=log)     # waits for k1
    _waiter(g, "C", ("k2",), SCHEDULED, log=log)         # k2 is free but B is ahead for it
    assert log == [] and "k2" not in g.snapshot()["held"]
    g.release("A", ("k1",))
    assert log == ["B"]
    g.release("B", ("k1", "k2"))
    assert log == ["B", "C"]


def test_holder_is_reentrant_but_its_queued_runs_stay_serial():
    g, log = _gate(), []
    assert _waiter(g, "A", ("k",), SCHEDULED) == "granted"
    assert _waiter(g, "A", ("k",), REACTIVE) == "granted"          # own follow-up turn
    _waiter(g, "B", ("k",), SCHEDULED, log=log)
    g.release("A", ("k",))
    assert log == []                                                 # A still holds once
    g.release("A", ("k",))
    assert log == ["B"]


def test_duplicate_scheduled_wait_is_skipped():
    g = _gate()
    _waiter(g, "A", ("k",), SCHEDULED)
    kw = dict(on_grant=lambda: None, trigger="schedule", dedupe_trigger=True)
    assert g.acquire_or_wait("B", ("k",), SCHEDULED, 0, **kw) == "queued"
    assert g.acquire_or_wait("B", ("k",), SCHEDULED, 0, **kw) == "duplicate"


def test_drop_waiters():
    g, log = _gate(), []
    _waiter(g, "A", ("k",), SCHEDULED)
    _waiter(g, "B", ("k",), SCHEDULED, log=log)
    assert g.drop_waiters("B") == 1
    g.release("A", ("k",))
    assert log == [] and g.snapshot()["held"] == {}


# ── what a task needs ────────────────────────────────────────────────────────

def _task(tid="t1", diagram=None, identity=None, exclusive=None, run_class=None, requires=None):
    meta = {}
    if identity is not None:
        meta["browser_identity"] = identity
    if exclusive is not None:
        meta["exclusive_resources"] = exclusive
    if run_class:
        meta["run_class"] = run_class
    skill = SimpleNamespace(diagram=diagram or {}, requires=requires or [])
    return SimpleNamespace(id=tid, name=tid, metadata=meta, skill=skill, agent_id="")


BROWSER_DIAGRAM = {"workFlow": {"nodes": [{"type": "llm"}, {"type": "group", "blocks": [{"type": "browser-automation"}]}]}}


def test_browser_key_only_when_the_skill_drives_a_browser():
    ident = {"browser_profile_id": "store3"}
    assert rg.resource_keys(_task(diagram=BROWSER_DIAGRAM, identity=ident), "ag1") == ("agent:ag1/browser:store3",)
    # Fast Deploy binds every task (Q&A too) to the store's browser; a skill
    # without browser nodes must not be serialized behind the browser user.
    assert rg.resource_keys(_task(diagram={"nodes": [{"type": "llm"}]}, identity=ident), "ag1") == ()
    assert rg.resource_keys(_task(identity=ident, requires=["browser"]), "ag1") == ("agent:ag1/browser:store3",)
    assert rg.resource_keys(_task(diagram=BROWSER_DIAGRAM), "ag1") == ()     # no binding


def test_user_named_resources_are_global():
    t = _task(exclusive=["printer", " "], diagram=BROWSER_DIAGRAM, identity={"cdp_port": 9228})
    assert rg.resource_keys(t, "ag1") == ("agent:ag1/browser:9228", "user:printer")


def test_priority_class():
    assert rg.priority_class(_task(), "message") == REACTIVE
    assert rg.priority_class(_task(), "schedule") == SCHEDULED
    assert rg.priority_class(_task(run_class="background"), "message") == BACKGROUND


# ── runner wiring ────────────────────────────────────────────────────────────

@pytest.fixture
def inline_gate(monkeypatch):
    g = _gate()
    monkeypatch.setattr(rg, "_gate", g)
    monkeypatch.setenv("ECAN_TASK_RESOURCE_GATE", "1")
    return g


def _runner_with_tasks(tasks):
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
    r._on_skill_complete = lambda future, task, *_a, **_kw: setattr(task, "future", None)
    r._emit_task_status = lambda *_a, **_kw: None
    r.agent = SimpleNamespace(card=SimpleNamespace(id="ag1"), tasks=tasks)
    return r


def _runner_task(tid):
    t = _task(tid, diagram=BROWSER_DIAGRAM, identity={"browser_profile_id": "store3"})
    t.status = SimpleNamespace(state=None, message=None)
    t.queue = Queue()
    t.future = None
    t.cancellation_event = threading.Event()
    t.skill.name, t.skill.price, t.skill.skill_owner = "s", 0, ""
    return t


def test_runner_serializes_two_tasks_on_one_browser(inline_gate):
    a, b = _runner_task("A"), _runner_task("B")
    r = _runner_with_tasks([a, b])
    r._submit_task_execution(a, None, "schedule", None)
    r._submit_task_execution(b, None, "schedule", None)
    assert len(r.futures) == 1                       # B waits for the browser
    assert [w["holder"] for w in inline_gate.snapshot()["waiting"]] == ["B"]
    r.futures[0].set_result(None)                    # A's run ends -> B is submitted
    assert len(r.futures) == 2 and b.future is r.futures[1]
    assert inline_gate.snapshot()["held"]["agent:ag1/browser:store3"] == {"holder": "B", "count": 1}
    r.futures[1].set_exception(RuntimeError("boom"))  # released on failure too
    assert inline_gate.snapshot()["held"] == {}


def test_runner_stopped_task_does_not_start_after_waiting(inline_gate):
    a, b = _runner_task("A"), _runner_task("B")
    r = _runner_with_tasks([a, b])
    r._submit_task_execution(a, None, "schedule", None)
    r._submit_task_execution(b, None, "schedule", None)
    b.cancellation_event.set()
    r.futures[0].set_result(None)
    assert len(r.futures) == 1 and inline_gate.snapshot()["held"] == {}


def test_runner_kill_switch(inline_gate, monkeypatch):
    monkeypatch.setenv("ECAN_TASK_RESOURCE_GATE", "0")
    a, b = _runner_task("A"), _runner_task("B")
    r = _runner_with_tasks([a, b])
    r._submit_task_execution(a, None, "schedule", None)
    r._submit_task_execution(b, None, "schedule", None)
    assert len(r.futures) == 2
