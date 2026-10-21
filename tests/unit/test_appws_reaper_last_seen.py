"""The AppWS reaper closes connections not heard from for
_CONNECTION_TIMEOUT_SEC. The timestamp used to be set only at accept, so every
healthy GUI socket (client pings every 30s) was force-closed 5-6 minutes after
connecting -- 157 times a day in a customer log. A ping now counts as heard."""
import asyncio
import time

import pytest
from starlette.applications import Starlette
from starlette.routing import WebSocketRoute
from starlette.testclient import TestClient

from gui import LocalServer as ls


@pytest.fixture
def client():
    mgr = ls.skill_editor_ws_manager
    mgr._all_connections.clear()
    mgr._connection_timestamps.clear()
    handlers = ls.RequestHandlers.__new__(ls.RequestHandlers)
    handlers.main_win = None
    app = Starlette(routes=[WebSocketRoute("/ws", handlers.skill_editor_websocket)])
    with TestClient(app) as c:
        yield c, mgr


def _age_all(mgr, seconds):
    for k in list(mgr._connection_timestamps):
        mgr._connection_timestamps[k] -= seconds


def _reap(mgr, portal):
    portal.call(mgr._cleanup_stale_connections)


def test_pinging_client_is_not_reaped(client):
    c, mgr = client
    with c.websocket_connect("/ws") as ws:
        _age_all(mgr, mgr._CONNECTION_TIMEOUT_SEC + 60)   # connected long ago
        ws.send_json({"type": "ping"})                     # ...but it just pinged
        assert ws.receive_json() == {"type": "pong"}
        _reap(mgr, c.portal)
        assert len(mgr._all_connections) == 1


def test_silent_client_is_still_reaped(client):
    c, mgr = client
    with c.websocket_connect("/ws") as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}
        _age_all(mgr, mgr._CONNECTION_TIMEOUT_SEC + 60)   # nothing heard since
        _reap(mgr, c.portal)
        assert len(mgr._all_connections) == 0
