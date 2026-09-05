"""ws190: one shared WS observer per Chrome endpoint.

Live 2026-09-04 22:36: five per-customer chat-scoped browser sessions each
started their own observer against the same Chrome → every frame dispatched
5× → four duplicate replies to one product card. Now the second start on the
same cdp_url returns a subscriber handle, dispatch goes to the ACTIVE (first)
subscriber only, stopping one subscriber hands over, and the real CDP client
is stopped with the last one.
"""

import asyncio
import sys
import types
from types import SimpleNamespace

import pytest

CDP = "http://127.0.0.1:9228"


class _Registry:
    def __init__(self):
        self.handlers = {}

    def register(self, name, fn):
        self.handlers[name] = fn


class FakeCDPClient:
    instances = []

    def __init__(self, url):
        self.url = url
        self.started = False
        self.stopped = False
        self.dead = False
        self._event_registry = _Registry()
        FakeCDPClient.instances.append(self)

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True

    async def send_raw(self, method, params=None, session_id=None):
        if self.dead:
            raise RuntimeError("connection closed")
        if method == "Target.getTargets":
            return {"targetInfos": [{"targetId": "T-main", "type": "page", "url": "https://im.jinritemai.com/pc_seller_v2/main/workspace"}]}
        if method == "Target.attachToTarget":
            return {"sessionId": f"S-{params.get('targetId')}"}
        if method == "Runtime.evaluate":
            return {"result": {"value": None}}
        return {}


@pytest.fixture
def observer(monkeypatch):
    monkeypatch.setenv("ECAN_FEIGE_WS", "1")
    from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import ws_observer as W
    import cdp_use  # the observer does `from cdp_use import CDPClient` at call time
    monkeypatch.setattr(cdp_use, "CDPClient", FakeCDPClient)
    FakeCDPClient.instances.clear()
    W._SHARED_OBSERVERS.clear()
    yield W
    W._SHARED_OBSERVERS.clear()


def _session():
    return SimpleNamespace(cdp_url=CDP, browser_profile=None)


def test_second_session_reuses_the_observer_and_handover_on_stop(observer):
    W = observer
    got1, got2 = [], []

    async def main():
        h1 = await W.start_ws_shadow_observer(_session(), "T-det-1", "新消息", dispatch_fn=got1.append)
        h2 = await W.start_ws_shadow_observer(_session(), "T-det-2", "新消息", dispatch_fn=got2.append)
        assert isinstance(h1, W._SharedObserverHandle) and isinstance(h2, W._SharedObserverHandle)
        assert len(FakeCDPClient.instances) == 1, "second session must NOT open a second CDP client"
        entry = W._SHARED_OBSERVERS[h1.key]
        assert entry["dispatchers"] == [got1.append, got2.append]

        W._shared_dispatch(entry, {"msg_id": "m1"})
        assert got1 == [{"msg_id": "m1"}] and got2 == []        # active subscriber only

        await W.stop_ws_shadow_observer(h1)                       # first session torn down
        assert FakeCDPClient.instances[0].stopped is False        # client kept alive
        W._shared_dispatch(entry, {"msg_id": "m2"})
        assert got2 == [{"msg_id": "m2"}]                         # handed over

        await W.stop_ws_shadow_observer(h2)                       # last subscriber
        assert FakeCDPClient.instances[0].stopped is True
        assert h1.key not in W._SHARED_OBSERVERS
    asyncio.run(main())


def test_dead_shared_client_is_replaced(observer):
    W = observer

    async def main():
        h1 = await W.start_ws_shadow_observer(_session(), "T-det-1", "新消息", dispatch_fn=lambda i: None)
        FakeCDPClient.instances[0].dead = True                    # Chrome went away
        h2 = await W.start_ws_shadow_observer(_session(), "T-det-2", "新消息", dispatch_fn=lambda i: None)
        assert len(FakeCDPClient.instances) == 2                  # fresh observer started
        assert h2.key == h1.key and W._SHARED_OBSERVERS[h2.key]["client"] is FakeCDPClient.instances[1]
    asyncio.run(main())


def test_different_chrome_endpoints_get_their_own_observer(observer):
    W = observer

    async def main():
        await W.start_ws_shadow_observer(SimpleNamespace(cdp_url=CDP, browser_profile=None), "T1", "新消息", dispatch_fn=lambda i: None)
        await W.start_ws_shadow_observer(SimpleNamespace(cdp_url="http://127.0.0.1:9229", browser_profile=None), "T2", "新消息", dispatch_fn=lambda i: None)
        assert len(FakeCDPClient.instances) == 2 and len(W._SHARED_OBSERVERS) == 2
    asyncio.run(main())
