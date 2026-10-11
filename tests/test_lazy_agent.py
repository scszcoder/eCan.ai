"""Deferred agents (Phase 5c, ECAN_LAZY_AGENTS=1): agent/ec_agents/lazy_agent.py."""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.a2a import shared_server as ss
from agent.ec_agents import lazy_agent as la


@pytest.fixture(autouse=True)
def shared(monkeypatch):
    srv = ss.SharedA2AServer(port_allocator=lambda: 3999, host_ip=lambda: "10.0.0.2")
    monkeypatch.setattr(ss, "_shared", srv)
    return srv


DEF = {"id": "agent_x", "name": "客服小晴", "status": "active", "owner": "u1",
       "skills": [{"id": "sk1", "name": "问答"}], "tasks": ""}


class _Real:
    """Stands in for a built EC_Agent."""
    def __init__(self):
        self.card = SimpleNamespace(id="agent_x", name="客服小晴")
        self.tasks = ["t"]
        self.runner = MagicMock()
        self.started = 0
        self._running = False

    def start(self):
        self.started += 1
        self._running = True

    def get_card(self):
        return self.card


def _lazy():
    built = []

    def build():
        r = _Real()
        built.append(r)
        return r
    return la.LazyAgent(DEF, SimpleNamespace(agents=[]), build), built


def test_task_ids_from_every_source(monkeypatch):
    mw = SimpleNamespace()
    monkeypatch.setattr("agent.agent_converter._relation_ids_from_local_db", lambda m, i: ([], []))
    assert la.agent_task_ids({"tasks": [{"id": "t1"}]}, mw) == ["t1"]
    assert la.agent_task_ids({"tasks": "", "extra_data": '{"tasks": ["t2"]}'}, mw) == ["t2"]
    assert la.agent_task_ids({"id": "a", "tasks": ""}, mw) == []
    monkeypatch.setattr("agent.agent_converter._relation_ids_from_local_db", lambda m, i: ([], [{"id": "t3"}]))
    assert la.agent_task_ids({"id": "a"}, mw) == ["t3"]

    def boom(m, i):
        raise RuntimeError("db")
    monkeypatch.setattr("agent.agent_converter._relation_ids_from_local_db", boom)
    assert la.agent_task_ids({"id": "a"}, mw) == ["?"]          # unknown -> built at startup


def test_scanning_all_agents_does_not_build_it():
    ag, built = _lazy()
    # what the launcher / runtime-status poll / advertising / reconciler read
    assert ag.card.id == "agent_x" and ag.card.url == "http://10.0.0.2:3999/a2a/agent_x/"
    assert ag.tasks == [] and ag.status == "active" and ag._running is False
    with ag.task_lock:
        assert len(ag.active_tasks) == 0
    assert ag.is_task_running("r") is False and [s.name for s in ag.skills] == ["问答"]
    assert getattr(ag, "vehicle_id", None) is None and ag.lazy_is_cold
    ag.status = "active"                                          # _sync_agent_db_status_active
    assert built == []


def test_first_real_use_builds_once_and_then_forwards():
    ag, built = _lazy()
    ag.status = "busy"
    assert ag.runner is built[0].runner                           # builds
    assert ag.tasks == ["t"] and ag.card is built[0].card         # now the real agent's
    assert built[0].status == "busy"                              # carried over
    ag.some_flag = 1
    assert built[0].some_flag == 1 and len(built) == 1 and not ag.lazy_is_cold
    assert built[0].started == 0                                  # start was not deferred


def test_deferred_start_runs_when_built():
    ag, built = _lazy()
    ag.lazy_defer_start()
    la.wake(ag, "test")
    assert built[0].started == 1 and ag._running is True
    la.wake(ag, "again")
    assert built[0].started == 1


def test_concurrent_first_use_builds_once():
    ag, built = _lazy()
    ts = [threading.Thread(target=lambda: ag.runner) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(built) == 1


def test_in_process_chat_wakes_it(monkeypatch):
    from a2a.types import Message, TextPart
    from agent.a2a import local_delivery as ld
    ag, built = _lazy()
    ag.lazy_defer_start()
    monkeypatch.setattr("agent.agent_service.get_agent_by_id", lambda aid: ag if aid == "agent_x" else None)
    monkeypatch.delenv("ECAN_A2A_LOCAL_FASTPATH", raising=False)
    msg = Message(role="user", parts=[TextPart(text="在吗")], metadata={"mtype": "send_chat"}, message_id="m")
    res = ld.deliver_chat(ag, "客服小晴", "send_chat", msg, {})
    assert res and res["local_fastpath"] and built[0].started == 1
    assert built[0].runner.sync_task_wait_in_line.call_args[0][0] == "chat_message"


def test_shared_server_request_wakes_it(monkeypatch):
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    srv = ss.SharedA2AServer(port_allocator=lambda: port, host_ip=lambda: "127.0.0.1")
    woke = []

    def resolver(aid):
        if aid != "agent_x":
            return False
        woke.append(aid)          # what wake() + start() do: the agent registers its app
        srv.register(aid, Starlette(routes=[Route("/", lambda r: JSONResponse({"ok": aid}), methods=["POST"])]))
        return True
    srv.resolver = resolver
    srv.register("other", Starlette(routes=[]))
    for _ in range(100):
        try:
            httpx.get(f"http://127.0.0.1:{port}/a2a/other/", timeout=0.5)
            break
        except Exception:
            time.sleep(0.1)
    assert httpx.post(srv.url_for("agent_x"), json={}).json() == {"ok": "agent_x"} and woke == ["agent_x"]
    assert httpx.post(srv.url_for("nobody"), json={}).status_code == 404
    srv.stop()


def test_enabled_only_with_the_shared_server(monkeypatch):
    monkeypatch.setenv("ECAN_LAZY_AGENTS", "1")
    assert la.lazy_enabled()
    monkeypatch.setenv("ECAN_A2A_SHARED_SERVER", "0")
    assert not la.lazy_enabled()
    monkeypatch.delenv("ECAN_A2A_SHARED_SERVER")
    monkeypatch.delenv("ECAN_LAZY_AGENTS")
    assert not la.lazy_enabled()
