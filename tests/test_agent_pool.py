"""agent/ec_agents/agent_pool.py: which pool member gets the next turn, and the
front desk's pool refresh (Phase 6a)."""
from __future__ import annotations

import os
import sys
import threading
from queue import Queue
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.ec_agents import agent_pool as ap


class _Done:
    def done(self):
        return True


class _Running:
    def done(self):
        return False


def _agent(queued=0, executing=False, running=True):
    q = Queue()
    for _ in range(queued):
        q.put(1)
    task = SimpleNamespace(queue=q, future=_Running() if executing else _Done())
    return SimpleNamespace(tasks=[task], _running=running)


@pytest.fixture(autouse=True)
def clean(monkeypatch, tmp_path):
    ap._reserved.clear()
    ap._pools.clear()
    ap._turns.clear()
    ap._enqueued.clear()
    monkeypatch.setattr(ap, "_traffic", None)
    monkeypatch.setattr(ap, "_traffic_hour", None)
    monkeypatch.setattr(ap, "_traffic_path", lambda: str(tmp_path / "pool_traffic.json"))
    monkeypatch.delenv("ECAN_POOL_PICK", raising=False)
    yield
    ap._reserved.clear()


def _pick(agents, state=None, prefer=""):
    return ap.pick(list(agents), state if state is not None else {}, prefer_id=prefer, lookup=agents.get)


def test_load_counts_queued_and_executing_turns():
    assert ap.agent_load(_agent()) == 0
    assert ap.agent_load(_agent(queued=2, executing=True)) == 3
    assert ap.agent_load(SimpleNamespace(tasks=[])) == 0


def test_idle_member_beats_busy_one():
    agents = {"a": _agent(executing=True), "b": _agent(), "c": _agent(queued=1)}
    assert _pick(agents) == "b"


def test_sticky_customer_on_a_tie_but_not_over_an_idle_member():
    agents = {"a": _agent(), "b": _agent()}
    assert _pick(agents, prefer="b") == "b"
    ap._reserved.clear()
    agents["b"] = _agent(executing=True)       # its agent is busy, another is idle
    assert _pick(agents, prefer="b") == "a"


def test_ties_rotate():
    agents = {"a": _agent(), "b": _agent(), "c": _agent()}
    state, got = {}, []
    for _ in range(3):
        c = _pick(agents, state)
        got.append(c)
        ap.release(c)
    assert sorted(got) == ["a", "b", "c"]


def test_a_burst_spreads_over_idle_members_until_released():
    agents = {"a": _agent(), "b": _agent(), "c": _agent()}
    burst = [_pick(agents) for _ in range(3)]
    assert sorted(burst) == ["a", "b", "c"]     # reservations: not all on "a"
    for c in burst:
        ap.release(c)
    assert ap._reserved == {}


def test_concurrent_picks_balance():
    agents = {k: _agent() for k in "abcd"}
    got, lock = [], threading.Lock()

    def worker():
        c = _pick(agents)
        with lock:
            got.append(c)
    ts = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(got.count(k) for k in "abcd") == [2, 2, 2, 2]


def test_members_not_running_here_are_skipped():
    agents = {"a": _agent(running=False), "b": _agent(queued=3)}
    assert _pick(agents) == "b"
    ap._reserved.clear()
    agents = {"a": _agent(running=False), "b": _agent(running=False)}
    assert _pick(agents) in ("a", "b")           # none running: still deliver


def test_stale_reservations_expire(monkeypatch):
    agents = {"a": _agent(), "b": _agent()}
    t = [1000.0]
    monkeypatch.setattr(ap.time, "time", lambda: t[0])
    assert _pick(agents) == "a"                 # reserved, never released
    t[0] += ap._RESERVATION_TTL_S + 1
    assert _pick(agents) in ("a", "b") and ap._reservations("a", t[0]) <= 1


def test_kill_switch_is_plain_round_robin(monkeypatch):
    monkeypatch.setenv("ECAN_POOL_PICK", "0")
    agents = {"a": _agent(executing=True), "b": _agent()}
    state = {}
    assert [_pick(agents, state) for _ in range(3)] == ["a", "b", "a"]


def test_front_desk_pool_is_refreshed(monkeypatch):
    import agent.ec_skills.node_runtime.frontdesk_dispatch as fd
    members = [[{"id": "qa1", "status": "active"}]]
    monkeypatch.setattr("agent.mcp.server.chat_utils.chat_tools.list_chat_agents",
                        lambda mw, p: {"agents": members[0]})
    monkeypatch.setattr(fd, "narrow_to_listeners", lambda live, sender, log_tag="": live)
    clock = [100.0]
    monkeypatch.setattr(fd.time, "monotonic", lambda: clock[0])
    cfg = SimpleNamespace(log_tag="t", task_keywords=[], skill_keywords=[])
    ctx = SimpleNamespace(mainwin=None)
    state = {}
    assert fd._resolve_recipient_agents(cfg, ctx, "fd", state) == ["qa1"]
    members[0] = members[0] + [{"id": "qa2", "status": "active"}]
    assert fd._resolve_recipient_agents(cfg, ctx, "fd", state) == ["qa1"]          # cached
    clock[0] += fd._POOL_REFRESH_S + 1
    assert fd._resolve_recipient_agents(cfg, ctx, "fd", state) == ["qa1", "qa2"]   # sees the new member
    assert ap.pools()["fd"]["members"] == ["qa1", "qa2"]                          # registered as a pool


# ── 6b: settings and metrics ──

def test_pool_settings_defaults_and_clamping():
    assert ap.pool_settings(None, 8) == {"min": 2, "max": 8, "idle_minutes": 10}
    assert ap.pool_settings({"min": 5, "max": 20, "idle_minutes": 3}, 8) == {"min": 5, "max": 8, "idle_minutes": 3}
    assert ap.pool_settings({"min": 9, "max": 4}, 8) == {"min": 4, "max": 4, "idle_minutes": 10}
    assert ap.pool_settings({"min": "x"}, 1) == {"min": 1, "max": 1, "idle_minutes": 10}
    assert ap.pool_settings({}, 0)["max"] == 0


def test_settings_come_from_the_front_desk_task():
    fd = SimpleNamespace(tasks=[SimpleNamespace(metadata={}), SimpleNamespace(metadata={"pool": {"max": 3}})])
    assert ap.settings_of(fd) == {"max": 3}
    assert ap.settings_of(SimpleNamespace(tasks=[])) is None


def test_waits_and_turns(monkeypatch):
    t = [10_000.0]
    monkeypatch.setattr(ap.time, "time", lambda: t[0])
    ap.register_pool("fd", ["a", "b"], {"min": 1})
    for wait, member in ((0.5, "a"), (4.0, "b"), (1.0, "a")):
        req = {"turn": wait}
        ap.note_enqueued(req)
        t[0] += wait
        ap.note_started(member, req)
    ap.note_started("a", {"never": "queued"})            # unknown request: ignored
    st = ap.pool_stats("fd", lookup=lambda i: _agent())
    assert st["turns_10min"] == 3 and st["turns_last_hour"] == 3
    assert st["wait_p50_s"] == 1.0 and st["wait_p90_s"] == 4.0
    assert st["settings"] == {"min": 1, "max": 2, "idle_minutes": 10}
    assert st["load"] == {"a": 0, "b": 0}
    assert ap.pool_stats("nope") == {}


def test_hourly_traffic_counts_quiet_hours_and_persists(monkeypatch, tmp_path):
    base = 3600 * 500_000.0
    t = [base + 60]
    monkeypatch.setattr(ap.time, "time", lambda: t[0])
    ap.register_pool("fd", ["a"])

    def turn():
        r = object()
        ap.note_enqueued(r)
        ap.note_started("a", r)
    turn()                       # first turn: starts the hour clock
    turn()
    turn()
    t[0] = base + 3 * 3600 + 5   # two quiet hours pass
    turn()
    import json
    saved = json.loads((tmp_path / "pool_traffic.json").read_text(encoding="utf-8"))["fd"]
    assert saved[ap._slot(base)] == 3
    assert saved[ap._slot(base + 3600)] == 0 and saved[ap._slot(base + 7200)] == 0
    assert ap.expected_turns("fd", base) == 3
