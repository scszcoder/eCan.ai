"""One PDD WS observer per chat tab. A monitor restart left a second observer on
the same tab and every message was dispatched -- and answered -- twice (customer
run 99v, 2026-10-05). Starting one now replaces the old one, and the replaced
observer's late stop must not switch WS dispatch off under its replacement."""

import asyncio
import sys
import types
from types import SimpleNamespace

import pytest

from agent.ec_skills.browser_use_extension.hooks.external.pdd_chat import ws_observer as wo


class _Registry:
    def register(self, *a, **k):
        pass


class _FakeClient:
    made = []

    def __init__(self, url):
        self.url, self.stopped = url, False
        self._event_registry = _Registry()
        _FakeClient.made.append(self)

    async def start(self):
        pass

    async def stop(self):
        self.stopped = True

    async def send_raw(self, method, params=None, session_id=None):
        return {"sessionId": "S1"} if method == "Target.attachToTarget" else {}


@pytest.fixture
def env(monkeypatch):
    _FakeClient.made = []
    monkeypatch.setitem(sys.modules, "cdp_use", types.SimpleNamespace(CDPClient=_FakeClient))
    monkeypatch.setattr(wo, "dispatch_enabled", lambda: True)
    monkeypatch.setattr(wo, "_LIVE_BY_TAB", {})

    async def _noop(*a, **k):
        return True

    monkeypatch.setattr(wo, "_ensure_single_session", _noop)
    monkeypatch.setattr(wo, "_cold_start", _noop)
    monkeypatch.setattr(wo, "_watch_list", _noop)
    live = []
    monkeypatch.setattr(wo.ws_session, "set_dispatch_live", lambda on, shop=None: live.append(on))
    import agent.ec_skills.browser_use_extension.site_probe as sp
    monkeypatch.setattr(sp, "browser_ws_url", lambda u: u + "/ws")
    return live


def test_second_start_on_the_same_tab_replaces_the_first(env):
    session = SimpleNamespace(cdp_url="http://127.0.0.1:61211")

    async def go():
        first = await wo.start_ws_shadow_observer(session, "TAB-6FA68A", "新消息", dispatch_fn=lambda i: None)
        second = await wo.start_ws_shadow_observer(session, "TAB-6FA68A", "新消息", dispatch_fn=lambda i: None)
        return first, second

    first, second = asyncio.run(go())
    assert first.stopped and not second.stopped
    assert list(wo._LIVE_BY_TAB.values()) == [second]


def test_late_stop_of_the_replaced_observer_keeps_ws_dispatch_live(env):
    session = SimpleNamespace(cdp_url="http://127.0.0.1:61211")

    async def go():
        first = await wo.start_ws_shadow_observer(session, "TAB-6FA68A", "x", dispatch_fn=lambda i: None)
        await wo.start_ws_shadow_observer(session, "TAB-6FA68A", "x", dispatch_fn=lambda i: None)
        env.clear()
        await wo.stop_ws_shadow_observer(first)       # the old monitor shutting down later

    asyncio.run(go())
    assert False not in env


def test_other_tabs_keep_their_own_observer(env):
    session = SimpleNamespace(cdp_url="http://127.0.0.1:61211")

    async def go():
        a = await wo.start_ws_shadow_observer(session, "TAB-A", "x", dispatch_fn=lambda i: None)
        b = await wo.start_ws_shadow_observer(session, "TAB-B", "x", dispatch_fn=lambda i: None)
        return a, b

    a, b = asyncio.run(go())
    assert not a.stopped and not b.stopped and len(wo._LIVE_BY_TAB) == 2
