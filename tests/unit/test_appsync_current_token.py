"""Long-lived AppSync clients (A2A gateway, cloud discovery) use the token as it is now:
a refreshed token is picked up, a 401 is retried once with a fresh token, then calls pause."""

import asyncio

import httpx
import pytest

from agent.ec_tasks import appsync_pubsub as ap


def _401():
    req = httpx.Request("POST", "https://x.appsync-api.example/graphql")
    return httpx.HTTPStatusError("401 Unauthorized", request=req, response=httpx.Response(401, request=req))


def _cfg(tokens):
    it = iter(tokens)
    return ap.AppSyncApiKeyConfig(http_endpoint="https://x.appsync-api.example/graphql", api_key="",
                                  auth_token="startup.tok.en", token_fn=lambda: next(it))


def test_each_call_takes_the_token_as_it_is_now(monkeypatch):
    seen = []

    async def post(url, *, api_key, query, variables, auth_token=None):
        seen.append(auth_token)
        return {"data": {}}

    monkeypatch.setattr(ap, "_post_graphql", post)
    cfg = _cfg(["a.a.a", "b.b.b"])
    asyncio.run(ap.post_graphql_current_token(cfg, "q", {}))
    asyncio.run(ap.post_graphql_current_token(cfg, "q", {}))
    assert seen == ["a.a.a", "b.b.b"]


def test_without_a_token_source_the_startup_token_is_used():
    cfg = ap.AppSyncApiKeyConfig(http_endpoint="h", api_key="", auth_token="s.s.s")
    assert cfg.current_token() == "s.s.s"


def test_a_401_is_retried_once_with_a_fresh_token(monkeypatch):
    seen = []

    async def post(url, *, api_key, query, variables, auth_token=None):
        seen.append(auth_token)
        if auth_token == "old.old.old":
            raise _401()
        return {"data": {"ok": True}}

    monkeypatch.setattr(ap, "_post_graphql", post)
    backoff = ap.AuthBackoff()
    out = asyncio.run(ap.post_graphql_current_token(_cfg(["old.old.old", "new.new.new"]), "q", {}, backoff=backoff))
    assert out == {"data": {"ok": True}} and seen == ["old.old.old", "new.new.new"]
    assert not backoff.blocked()


def test_a_401_a_fresh_token_doesnt_fix_pauses_calls_and_the_pause_grows(monkeypatch):
    calls = []

    async def post(url, *, api_key, query, variables, auth_token=None):
        calls.append(auth_token)
        raise _401()

    monkeypatch.setattr(ap, "_post_graphql", post)
    backoff = ap.AuthBackoff(first_sec=60, max_sec=900)
    cfg = ap.AppSyncApiKeyConfig(http_endpoint="h", api_key="", token_fn=lambda: "t.t.t")
    with pytest.raises(ap.Unauthorized):
        asyncio.run(ap.post_graphql_current_token(cfg, "q", {}, backoff=backoff))
    assert len(calls) == 2 and backoff.blocked() and backoff.wait_sec == 60
    # while paused, no request goes out at all (29 agents' upserts cost nothing)
    for _ in range(29):
        with pytest.raises(ap.Unauthorized):
            asyncio.run(ap.post_graphql_current_token(cfg, "q", {}, backoff=backoff))
    assert len(calls) == 2
    backoff.until = 0                                   # the pause ends; still 401 -> it doubles
    with pytest.raises(ap.Unauthorized):
        asyncio.run(ap.post_graphql_current_token(cfg, "q", {}, backoff=backoff))
    assert backoff.wait_sec == 120
    for _ in range(10):
        backoff.failed()
    assert backoff.wait_sec == 900


def test_other_errors_are_not_retried(monkeypatch):
    calls = []

    async def post(url, *, api_key, query, variables, auth_token=None):
        calls.append(1)
        raise RuntimeError("Cannot query field x")

    monkeypatch.setattr(ap, "_post_graphql", post)
    with pytest.raises(RuntimeError):
        asyncio.run(ap.post_graphql_current_token(_cfg(["a.a.a", "b.b.b"]), "q", {}, backoff=ap.AuthBackoff()))
    assert calls == [1]


def test_a_subscription_reconnect_uses_the_refreshed_token(monkeypatch):
    urls = []

    class FailingSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def ws_connect(self, url, **kw):
            urls.append(url)
            raise RuntimeError("401 on connect")

    monkeypatch.setattr(ap.aiohttp, "ClientSession", FailingSession)

    async def no_sleep(_):
        return None

    monkeypatch.setattr(ap.asyncio, "sleep", no_sleep)
    cfg = _cfg(["old.old.old", "new.new.new"])

    async def on_env(_):
        return None

    with pytest.raises(RuntimeError):
        asyncio.run(ap._subscribe(config=cfg, query="subscription {x}", variables={}, operation_name="X",
                                  field_name="x", on_envelope=on_env, max_retries=2))
    assert len(urls) == 2 and urls[0] != urls[1]
    import base64
    import json
    headers = [json.loads(base64.b64decode(u.split("header=")[1].split("&")[0])) for u in urls]
    assert [h["Authorization"] for h in headers] == ["old.old.old", "new.new.new"]


def test_the_machine_subscription_hands_the_record_to_the_gateway(monkeypatch):
    """A pushed message reaches Gateway.handle; its payload is an AWSJSON string (was: crash on .get)."""
    import json

    from agent.a2a import gateway as gw_mod

    record = {"id": "m1", "toAgentId": "machine_abc", "fromAgentId": "cloud_manager", "createdAt": "2026-11-11T22:45:33Z",
              "payload": json.dumps({"v": 1, "kind": "request", "intent": "tool_call", "correlation_id": "c1",
                                     "reply_to": "cloud_manager", "task": {"tool": "find_skill", "args": {}}})}

    class OneMessageSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def ws_connect(self, url, **kw):
            return FakeWs()

    class Msg:
        def __init__(self, data):
            self.type, self.data = ap.aiohttp.WSMsgType.TEXT, json.dumps(data)

    class FakeWs:
        def __init__(self):
            self.out = [Msg({"type": "connection_ack"}), Msg({"type": "start_ack"}),
                        Msg({"type": "data", "payload": {"data": {"onA2AMessageForMachine": record}}})]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def send_str(self, s):
            return None

        async def receive(self):
            if self.out:
                return self.out.pop(0)
            raise asyncio.CancelledError()

    monkeypatch.setattr(ap.aiohttp, "ClientSession", OneMessageSession)
    handled = []
    g = gw_mod.Gateway(mainwin=None, machine_id="abc", org="o", post=None)

    async def handle(m):
        handled.append(m)
        return "ok"

    monkeypatch.setattr(g, "handle", handle)
    cfg = ap.AppSyncApiKeyConfig(http_endpoint="https://x.appsync-api.example/graphql", api_key="", auth_token="a.b.c")
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(ap._subscribe(config=cfg, query=gw_mod.GQL_SUB, variables={}, operation_name="OnA2AMessageForMachine",
                                  field_name="onA2AMessageForMachine", on_envelope=g._on_envelope, max_retries=1))
    assert handled == [record]


def test_discovery_stops_calling_for_every_agent_after_an_unfixable_401(monkeypatch):
    from agent.a2a.discovery import cloud_directory as cd

    calls = []

    async def post(url, *, api_key, query, variables, auth_token=None):
        calls.append(auth_token)
        raise _401()

    monkeypatch.setattr(ap, "_post_graphql", post)
    loop = asyncio.new_event_loop()
    try:
        cfg = ap.AppSyncApiKeyConfig(http_endpoint="h", api_key="", token_fn=lambda: "t.t.t")
        client = cd.CloudDirectoryClient(config=cfg, org="o", machine_id="m" * 12, loop=loop,
                                         directory=object())
        regs = [cd.AgentRegistration(agent_id=f"agent_{i}", machine_id="m" * 12) for i in range(29)]

        async def heartbeat_round():
            for r in regs:
                await client._upsert_endpoint(r)

        loop.run_until_complete(heartbeat_round())
    finally:
        loop.close()
    assert len(calls) == 2          # one call + one retry with a fresh token, then the other 28 are skipped
