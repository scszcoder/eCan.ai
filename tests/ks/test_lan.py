"""LAN sharing: a commander serves knowledge to paired platoon machines.

Runs real HTTP servers on loopback: a fake LightRAG upstream (standing in for
the commander's loopback LightRAG) behind the real gateway.
"""
import socket
import time

import httpx
import pytest

from knowledge.ks import lan
from knowledge.ks.lan import GatewayRunner, LanAccess, LanSource, create_gateway_app
from knowledge.ks.planes import ConnectionStore, PlaneRouter


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def upstream():
    """Fake commander-side LightRAG: records what reaches it."""
    from fastapi import FastAPI, Request
    from fastapi.responses import StreamingResponse
    seen = []
    app = FastAPI()

    @app.post("/query")
    async def query(request: Request):
        seen.append(dict(request.headers))
        return {"response": "LightRAG answer", "references": []}

    @app.post("/query/stream")
    async def stream(request: Request):
        seen.append(dict(request.headers))

        async def gen():
            for part in ('{"response": "a"}\n', '{"response": "b"}\n'):
                yield part
        return StreamingResponse(gen(), media_type="application/x-ndjson")

    @app.post("/documents/upload")
    async def upload():
        seen.append({"upload": True})
        return {"status": "uploaded"}

    runner = GatewayRunner()
    port = _free_port()
    runner.start(app, port, host="127.0.0.1")
    assert runner.running, runner.error
    yield f"http://127.0.0.1:{port}", seen
    runner.stop()


@pytest.fixture
def gateway(svc, shop, upstream, tmp_path):
    base, seen = upstream
    access = LanAccess(str(tmp_path / "commander"))
    app = create_gateway_app(svc, access, lambda: base, lambda: "commander-key", "COMMANDER-PC")
    runner = GatewayRunner()
    port = _free_port()
    runner.start(app, port, host="127.0.0.1")
    assert runner.running, runner.error
    yield {"url": f"http://127.0.0.1:{port}", "access": access, "seen": seen}
    runner.stop()


def test_pairing_codes_are_single_use_and_rate_limited(tmp_path, monkeypatch):
    a = LanAccess(str(tmp_path))
    code = a.new_code()["code"]
    token = a.redeem(code, "platoon-1", "192.168.1.21")
    assert a.verify(token)["name"] == "platoon-1"
    assert "token" not in (tmp_path / "lan_devices.json").read_text(encoding="utf-8").replace("token_sha256", "")
    with pytest.raises(PermissionError):
        a.redeem(code, "again")  # single use
    for _ in range(lan.MAX_BAD_CODES - 1):
        with pytest.raises(PermissionError):
            a.redeem("000000", "x")
    good = a.new_code()["code"]
    with pytest.raises(PermissionError) as e:
        a.redeem(good, "x")  # locked out even with the right code
    assert "too many" in str(e.value)
    monkeypatch.setattr(lan, "LOCKOUT_S", 0)
    assert a.redeem(good, "x")


def test_expired_code(tmp_path, monkeypatch):
    a = LanAccess(str(tmp_path))
    code = a.new_code()["code"]
    monkeypatch.setattr(lan.time, "time", lambda: 10 ** 12)
    with pytest.raises(PermissionError):
        a.redeem(code, "late")


def test_platoon_pairs_and_uses_commander_knowledge(svc, gateway, tmp_path):
    url, access, seen = gateway["url"], gateway["access"], gateway["seen"]
    # Unpaired machines get nothing but the public info route.
    assert httpx.get(f"{url}/v1/lan/info").json()["machine"] == "COMMANDER-PC"
    assert httpx.post(f"{url}/v1/tenants/x/search", json={"query": "材质"}).status_code == 401
    assert httpx.post(f"{url}/lightrag/query", json={"query": "x"}).status_code == 401

    # Pair with the code shown on the commander.
    src = LanSource(str(tmp_path / "platoon"))
    with pytest.raises(PermissionError):
        src.pair(url, "123456", "PLATOON-1")
    src.pair(url, access.new_code()["code"], "PLATOON-1", commander="COMMANDER-PC")
    assert src.use_commander() and access.devices()[0]["name"] == "PLATOON-1"

    # Product knowledge through the router (the platoon's own store is empty).
    from knowledge.ks.embedding import HashingEmbedder
    from knowledge.ks.service import KnowledgeService
    platoon_ks = KnowledgeService(f"sqlite:///{(tmp_path / 'p.db').as_posix()}", embedder=HashingEmbedder())
    router = PlaneRouter(platoon_ks, ConnectionStore(str(tmp_path / "c.json")), lan_source=lambda: src)
    assert [c["plane"] for c in router.all_connections()] == ["lan"]
    r = router.search("这件是什么材质", platform_item_id="6600001")
    assert r["product"]["code"] == "TS-001" and r["plane"] == "lan" and r["sensitivity"] == "internal"

    # LightRAG documents through the gateway: the commander adds its own key.
    h = {"Authorization": f"Bearer {src.token()}", "LIGHTRAG-WORKSPACE": "shop_a"}
    assert httpx.post(f"{url}/lightrag/query", json={"query": "x"}, headers=h).json()["response"] == "LightRAG answer"
    assert seen[-1]["x-api-key"] == "commander-key" and seen[-1]["lightrag-workspace"] == "shop_a"
    assert "authorization" not in seen[-1]  # the device token never reaches LightRAG
    with httpx.stream("POST", f"{url}/lightrag/query/stream", json={"query": "x"}, headers=h) as resp:
        body = b"".join(resp.iter_raw())
    assert b'"a"' in body and b'"b"' in body
    # Writes stay on the commander.
    assert httpx.post(f"{url}/lightrag/documents/upload", headers=h).status_code == 403
    assert not any(s.get("upload") for s in seen)

    # Revoking the device cuts it off.
    access.revoke(access.devices()[0]["id"])
    assert httpx.post(f"{url}/lightrag/query", json={"query": "x"}, headers=h).status_code == 401


def test_lightrag_client_targets_commander_when_paired(monkeypatch, tmp_path):
    from knowledge import lightrag_client as lc

    class Src:
        def use_commander(self):
            return True

        def url(self):
            return "http://192.168.1.10:9630"

        def token(self):
            return "dev-token"

    monkeypatch.setattr(lc, "_commander_source", lambda: Src())
    c = lc.LightragClient()
    assert c.base_url == "http://192.168.1.10:9630/lightrag"
    assert c.session.headers["Authorization"] == "Bearer dev-token"
    assert "X-API-Key" not in c.session.headers
    assert lc._resolve_base_url(local_only=True).startswith("http://127.0.0.1")


def test_commander_source_is_off_without_the_desktop_app():
    from knowledge import lightrag_client as lc
    assert lc._commander_source() is None
