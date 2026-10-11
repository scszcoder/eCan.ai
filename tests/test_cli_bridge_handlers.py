"""App-side handlers the CLI calls: run a task once, pin a pool, resource
locks, who is signed in, and saved settings reaching the running task."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from gui.ipc.w2p_handlers import agent_handler as ah
from gui.ipc.w2p_handlers import task_handler as th


def _req(method):
    return {"id": "1", "method": method, "source": "graphql"}


def _agent(aid, tasks):
    return SimpleNamespace(card=SimpleNamespace(id=aid), tasks=tasks)


@pytest.fixture
def agents(monkeypatch):
    t1 = SimpleNamespace(id="t1", name="Daily", metadata={"run_class": "background", "task_vars": {"a": 1},
                                                          "pool": {"min": 2}})
    t2 = SimpleNamespace(id="t2", name="Other", metadata={})
    ags = [_agent("a1", [t2]), _agent("a2", [t1])]
    ctx = SimpleNamespace(get_agents=lambda: ags, main_window="MW")
    monkeypatch.setattr(th, "get_handler_context", lambda *a, **k: ctx)
    monkeypatch.setattr("gui.ipc.context_bridge.get_handler_context", lambda *a, **k: ctx)
    return ags, t1


def test_launch_runs_on_the_agent_that_has_the_task(agents, monkeypatch):
    seen = {}

    def fake_launch(mainwin, config):
        seen.update(config, mainwin=mainwin)
        return {"success": True, "task_id": "t1", "run_id": "r1", "task_name": "Daily"}
    monkeypatch.setattr("agent.ec_tasks.task_mcp_tools.launch_agent_task", fake_launch)
    resp = th.handle_launch_agent_task(_req("launch_agent_task"), {"task_id": "t1", "task_inputs": {"x": 1}})
    assert resp["status"] == "success" and resp["result"]["run_id"] == "r1"
    assert seen["agent_id"] == "a2" and seen["task_inputs"] == {"x": 1} and seen["mainwin"] == "MW"


def test_launch_unknown_task(agents):
    resp = th.handle_launch_agent_task(_req("launch_agent_task"), {"task_id": "nope"})
    assert resp["status"] == "error" and resp["error"]["code"] == "TASK_NOT_FOUND"
    resp = th.handle_launch_agent_task(_req("launch_agent_task"), {})
    assert resp["error"]["code"] == "INVALID_PARAMS"


def test_saved_settings_reach_the_running_task(agents):
    ags, t1 = agents
    n = th._apply_settings_to_running_tasks("t1", {"overlap_policy": "queue_one", "pool": {"min": 4, "max": 4},
                                                    "task_vars": {"a": 2}})
    assert n == 1
    # run rules / pool replaced; run_class removed (not in the saved settings);
    # other runtime keys (task_vars) are left to their own sync path
    assert t1.metadata == {"task_vars": {"a": 1}, "overlap_policy": "queue_one", "pool": {"min": 4, "max": 4}}


def test_resource_locks(monkeypatch):
    from agent.ec_tasks import resource_gate as rg
    gate = rg.ResourceGate(spawn=lambda fn: None)
    gate.acquire_or_wait("t1", ("user:printer",), rg.SCHEDULED, 0, lambda: None, label="a")
    monkeypatch.setattr(rg, "get_gate", lambda: gate)
    resp = th.handle_get_resource_locks(_req("get_resource_locks"), {})
    assert resp["result"]["held"] == {"user:printer": {"holder": "t1", "count": 1}}
    assert resp["result"]["enabled"] is True


def test_pool_pin_handler(monkeypatch):
    calls = []
    monkeypatch.setattr("agent.ec_agents.agent_pool.set_pin", lambda fd, size: calls.append((fd, size)) or ["q1"])
    monkeypatch.setattr("agent.ec_agents.agent_pool.pool_view", lambda fd: {"pinned": 1})
    resp = ah.handle_set_agent_pool_pin(_req("set_agent_pool_pin"), {"agent_id": "fd", "size": 1})
    assert resp["status"] == "success" and calls == [("fd", 1)]
    assert ah.handle_set_agent_pool_pin(_req("set_agent_pool_pin"), {"agent_id": "fd", "size": 0})["status"] == "error"
    assert ah.handle_set_agent_pool_pin(_req("set_agent_pool_pin"), {"size": 2})["status"] == "error"
    monkeypatch.setattr("agent.ec_agents.agent_pool.set_pin", lambda fd, size: None)
    resp = ah.handle_set_agent_pool_pin(_req("set_agent_pool_pin"), {"agent_id": "x", "size": None})
    assert resp["error"]["code"] == "POOL_NOT_FOUND"


def test_cli_session(monkeypatch):
    monkeypatch.setattr("gui.ipc.handlers.resolve_username", lambda req, params: "me@x.com")
    resp = ah.handle_get_cli_session(_req("get_cli_session"), None)
    assert resp["result"] == {"username": "me@x.com"}


# ── run_agent_task: one run on the task's own loop, never a second loop ──

class _Future:
    def __init__(self, done=False):
        self._done = done

    def done(self):
        return self._done


def _run_ctx(monkeypatch, loop_running):
    task = SimpleNamespace(id="t1", name="Daily", trigger=["manual", "schedule"], run_id="r1", agent_id="a1",
                           metadata={}, skill=None)
    submitted = []
    pool = SimpleNamespace(submit=lambda fn, *a: submitted.append(a) or _Future())
    agent = SimpleNamespace(card=SimpleNamespace(id="a1"), tasks=[task], runner=SimpleNamespace(launch_unified_run=None),
                            thread_pool_executor=pool, task_lock=__import__("threading").Lock(),
                            active_tasks={"r1": _Future()} if loop_running else {})
    ctx = SimpleNamespace(get_agents=lambda: [agent], get_agent_tasks=lambda: [task], get_agent_skills=lambda: [],
                          main_window="MW")
    monkeypatch.setattr("gui.ipc.context_bridge.get_handler_context", lambda *a, **k: ctx)
    launched = []
    monkeypatch.setattr("agent.ec_tasks.task_mcp_tools.launch_agent_task",
                        lambda mw, cfg: launched.append(cfg) or {"success": True, "run_id": "r1"})
    return agent, submitted, launched


def test_run_button_queues_on_the_running_loop(monkeypatch):
    agent, submitted, launched = _run_ctx(monkeypatch, loop_running=True)
    resp = th.handle_run_agent_task(_req("run_agent_task"), {"task_id": "t1", "username": "me"})
    assert resp["status"] == "success", resp
    assert submitted == []                                   # no second loop
    assert launched == [{"agent_id": "a1", "task_id": "t1"}]


def test_run_button_starts_one_loop_when_none_runs(monkeypatch):
    agent, submitted, launched = _run_ctx(monkeypatch, loop_running=False)
    resp = th.handle_run_agent_task(_req("run_agent_task"), {"task_id": "t1", "username": "me"})
    assert resp["status"] == "success", resp
    assert len(submitted) == 1
    task, triggers = submitted[0]
    assert triggers == ["schedule", "message"]               # manual->auto dropped: it would run a 2nd time
    assert "r1" in agent.active_tasks and len(launched) == 1


# ── agents: save restarts, delete / disable stop ──

class _Agent:
    def __init__(self, running):
        self._running = running
        self.events = []

    def stop(self, reason=""):
        self.events.append("stop")
        self._running = False

    def start(self):
        self.events.append("start")
        self._running = True


def test_save_swaps_a_running_agent():
    old, new = _Agent(True), _Agent(False)
    agents = [old]
    ah._swap_agent(agents, 0, new)
    assert agents == [new] and old.events == ["stop"] and new.events == ["start"]


def test_save_leaves_a_stopped_agent_stopped():
    old, new = _Agent(False), _Agent(False)
    agents = [old]
    ah._swap_agent(agents, 0, new)
    assert agents == [new] and old.events == [] and new.events == []


def test_save_of_a_cold_lazy_agent_that_should_run_starts_the_new_one():
    from agent.ec_agents.lazy_agent import LazyAgent
    lazy = LazyAgent({"id": "a1", "name": "x"}, None, build=lambda: pytest.fail("must not build"))
    lazy.lazy_defer_start()
    new = _Agent(False)
    agents = [lazy]
    ah._swap_agent(agents, 0, new)
    assert agents == [new] and new.events == ["start"]


def test_stop_skips_agents_that_never_started():
    a = _Agent(False)
    ah._stop_running_agent(a, "x")
    assert a.events == []
    b = _Agent(True)
    ah._stop_running_agent(b, "x")
    assert b.events == ["stop"]
