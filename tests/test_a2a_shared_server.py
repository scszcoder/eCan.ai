"""agent/a2a/shared_server.py: one A2A server for every agent of the process,
dispatching /a2a/<agent id>/ to that agent's own a2a-sdk app (Phase 5b)."""
from __future__ import annotations

import os
import socket
import sys
import time

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from a2a.server.agent_execution import AgentExecutor
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard
from a2a.utils import new_agent_text_message

from agent.a2a.langgraph_agent.a2a_client_wrapper import A2AClientWrapper
from agent.a2a.shared_server import SharedA2AServer


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class _Recorder(AgentExecutor):
    def __init__(self, name):
        self.name, self.got = name, []

    async def execute(self, context, event_queue):
        self.got.append(context.message.parts[0].root.text)
        await event_queue.enqueue_event(new_agent_text_message(f"{self.name} ok"))

    async def cancel(self, context, event_queue):
        pass


def _app(name, url):
    card = AgentCard(name=name, description=name, url=url, version="1", capabilities=AgentCapabilities(),
                     default_input_modes=["text"], default_output_modes=["text"], skills=[])
    ex = _Recorder(name)
    app = A2AStarletteApplication(agent_card=card, http_handler=DefaultRequestHandler(
        agent_executor=ex, task_store=InMemoryTaskStore())).build()
    return app, ex


def _payload(text):
    return {"message": {"role": "user", "parts": [{"kind": "text", "text": text}], "messageId": f"m-{text}",
                        "metadata": {"mtype": "send_chat"}}, "metadata": {"params": {}}}


@pytest.fixture(scope="module")
def server():
    port = _free_port()
    srv = SharedA2AServer(port_allocator=lambda: port, host_ip=lambda: "127.0.0.1")
    apps = {}
    for aid in ("fd1", "qa1"):
        app, ex = _app(aid, srv.url_for(aid))
        apps[aid] = ex
        srv.register(aid, app)
    for _ in range(100):
        try:
            httpx.get(f"http://127.0.0.1:{port}/a2a/fd1/.well-known/agent.json", timeout=0.5)
            break
        except Exception:
            time.sleep(0.1)
    yield srv, apps
    srv.stop()


def test_url_for(server):
    srv, _ = server
    assert srv.url_for("qa1") == f"http://127.0.0.1:{srv.port()}/a2a/qa1/"


def test_each_agent_gets_its_own_messages(server):
    srv, apps = server
    # The way EC_Agent sends: card.url with the trailing slash stripped.
    for aid, text in (("fd1", "to front desk"), ("qa1", "to qa")):
        client = A2AClientWrapper(url=srv.url_for(aid).rstrip("/"))
        res = client.sync_send_task(_payload(text))
        assert res["result"]["parts"][0]["text"] == f"{aid} ok", res
    assert apps["fd1"].got == ["to front desk"] and apps["qa1"].got == ["to qa"]


def test_agent_card_is_served_per_agent(server):
    srv, _ = server
    card = httpx.get(srv.url_for("qa1") + ".well-known/agent.json").json()
    assert card["name"] == "qa1" and card["url"] == srv.url_for("qa1")
    # url + '/.well-known/...' (as MainWindow.wait_for_server_async builds it)
    assert httpx.get(srv.url_for("fd1") + "/.well-known/agent.json").json()["name"] == "fd1"


def test_unknown_and_unregistered_agents_are_404(server):
    srv, apps = server
    base = f"http://127.0.0.1:{srv.port()}"
    assert httpx.post(f"{base}/a2a/nobody/", json={}).status_code == 404
    assert httpx.post(f"{base}/", json={}).status_code == 404
    app, ex = _app("tmp", srv.url_for("tmp"))
    srv.register("tmp", app)
    assert A2AClientWrapper(url=srv.url_for("tmp")).sync_send_task(_payload("x")) and ex.got == ["x"]
    srv.unregister("tmp")
    assert httpx.post(srv.url_for("tmp"), json={}).status_code == 404
