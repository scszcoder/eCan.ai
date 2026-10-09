"""ks.access / connection IPC: local admin and remote (connected server) admin."""
import pytest

from gui.ipc.w2p_handlers import knowledge_service_handler as h
from knowledge.ks.planes import ConnectionStore, PlaneRouter
from tests.ks.test_planes import _TestClientRemote, private_server  # noqa: F401  (fixture)


def _req(method):
    return {"id": "1", "type": "request", "method": method, "params": None, "meta": {}, "timestamp": 0}


def _ok(resp):
    assert resp.get("status") == "success", resp
    return resp["result"]


@pytest.fixture
def wired(svc, tmp_path, monkeypatch, private_server):  # noqa: F811
    client, token, tid = private_server
    router = PlaneRouter(svc, ConnectionStore(str(tmp_path / "c.json")),
                         client_factory=lambda c: _TestClientRemote(client, token, c["tenant_id"]))
    monkeypatch.setattr(h, "_svc", lambda: svc)
    monkeypatch.setattr(h, "_router", lambda: router)
    return svc, router, tid


def test_local_access_admin(wired):
    svc, _, _ = wired
    svc.default_tenant()
    view = _ok(h.handle_access(_req("ks.access"), {"op": "view"}))
    assert view["members"][0]["role"] == "owner"
    m = _ok(h.handle_access(_req("ks.access"), {"op": "saveMember", "email": "a@b.com", "role": "editor"}))
    assert m["status"] == "invited"
    kb = view["kbs"][0]["id"]
    _ok(h.handle_access(_req("ks.access"), {"op": "updateKb", "kb_id": kb, "sensitivity": "confidential"}))
    g = _ok(h.handle_access(_req("ks.access"), {"op": "saveGroup", "name": "研发", "member_ids": [m["id"]]}))
    _ok(h.handle_access(_req("ks.access"), {"op": "setGrant", "kb_id": kb, "principal_type": "group",
                                            "principal_id": g["id"], "permission": "read"}))
    assert len(_ok(h.handle_access(_req("ks.access"), {"op": "view"}))["grants"]) >= 2
    resp = h.handle_access(_req("ks.access"), {"op": "nope"})
    assert resp["error"]["code"] == "INVALID_PARAMS"


def test_remote_connection_test_and_admin(wired):
    _, router, tid = wired
    conn = _ok(h.handle_save_connection(_req("ks.saveConnection"), {
        "plane": "private", "base_url": "http://10.0.0.5:8790", "tenant_id": tid, "name": "公司服务器"}))
    # health() on the TestClient-backed remote
    router.client_factory = (lambda f: (lambda c: _with_health(f(c))))(router.client_factory)
    res = _ok(h.handle_test_connection(_req("ks.testConnection"), {"id": conn["id"]}))
    assert res["ok"], res
    assert [s["step"] for s in res["steps"]] == ["reach", "identity", "tenant"]

    view = _ok(h.handle_access(_req("ks.access"), {"op": "view", "connection_id": conn["id"]}))
    assert view["tenant"]["name"] == "设计公司"
    m = _ok(h.handle_access(_req("ks.access"), {"op": "saveMember", "connection_id": conn["id"],
                                                "email": "eng@corp.cn", "role": "viewer"}))
    assert m["email"] == "eng@corp.cn"
    audit = _ok(h.handle_access(_req("ks.access"), {"op": "audit", "connection_id": conn["id"]}))
    assert any(a["action"] == "member.save" for a in audit)

    r = _ok(h.handle_router_search(_req("ks.routerSearch"), {"query": "工作电压", "platform_item_id": "880001"}))
    assert r["plane"] == "private" and r["sensitivity"] == "private"


def _with_health(remote):
    remote.health = lambda: remote._client.get("/v1/health").json()
    return remote
