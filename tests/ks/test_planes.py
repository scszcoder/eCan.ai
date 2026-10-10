"""Plane routing across local/private/public and the private-data guard."""
import pytest
from fastapi.testclient import TestClient

from knowledge.ks import taint
from knowledge.ks.embedding import HashingEmbedder
from knowledge.ks.identity import IdentityRegistry, LocalVerifier
from knowledge.ks.planes import ConnectionStore, PlaneRouter, RemoteKS
from knowledge.ks.server import ServerConfig, create_app
from knowledge.ks.service import KnowledgeService


@pytest.fixture
def private_server(tmp_path):
    """An on-prem KS with an enterprise datasheet product, reached over HTTP."""
    svc = KnowledgeService(f"sqlite:///{(tmp_path / 'onprem.db').as_posix()}", embedder=HashingEmbedder(), owner="server")
    local = LocalVerifier(secret="onprem")
    cfg = ServerConfig(plane="private", data_dir=str(tmp_path / "onprem"), bootstrap_admin="fae@corp.cn:pw",
                       bootstrap_tenant="设计公司")
    client = TestClient(create_app(svc, IdentityRegistry([local]), cfg, local))
    token = client.post("/v1/auth/local", json={"email": "fae@corp.cn", "password": "pw"}).json()["access_token"]
    tid = client.get("/v1/me", headers={"Authorization": f"Bearer {token}"}).json()["tenants"][0]["id"]
    st = client.post(f"/v1/tenants/{tid}/stores", headers={"Authorization": f"Bearer {token}"}, json={"name": "内部"}).json()
    client.post(f"/v1/tenants/{tid}/products", headers={"Authorization": f"Bearer {token}"}, json={
        "code": "FT62F0Mx", "title": "FT62F0Mx 8位MCU", "attributes": {"工作电压": "1.9V-5.5V", "封装": "SOP28"},
        "listings": [{"store_id": st["id"], "platform_item_id": "880001"}]})
    return client, token, tid


class _TestClientRemote(RemoteKS):
    """RemoteKS that talks to a FastAPI TestClient instead of the network."""

    def __init__(self, client, token, tenant_id):
        super().__init__("http://testserver", lambda: token, tenant_id)
        self._client = client

    def _request(self, method, path, **kw):
        r = self._client.request(method, path, headers=self._headers(), **kw)
        if r.status_code >= 400:
            from knowledge.ks.planes import RemoteError
            raise RemoteError(r.status_code, r.text)
        return r.json()


def test_connection_validation(tmp_path):
    cs = ConnectionStore(str(tmp_path / "connections.json"))
    with pytest.raises(ValueError):
        cs.save({"plane": "public", "base_url": "http://cloud.example.com"})  # cloud must be https
    with pytest.raises(ValueError):
        cs.save({"plane": "lan", "base_url": "https://x"})
    c = cs.save({"plane": "private", "base_url": "http://192.168.1.50:8790/", "name": "公司服务器", "auth": "local"})
    assert c["base_url"] == "http://192.168.1.50:8790" and cs.list()[0]["name"] == "公司服务器"
    cs.set_token(c["id"], "tok")
    assert cs.token(c["id"]) == "tok"
    assert "tok" not in (tmp_path / "connections.json").read_text(encoding="utf-8")  # tokens never on disk
    cs.delete(c["id"])
    assert cs.list() == []


def test_router_merges_local_and_private_and_marks_private(svc, shop, private_server, tmp_path):
    client, token, tid = private_server
    cs = ConnectionStore(str(tmp_path / "c.json"))
    conn = cs.save({"plane": "private", "base_url": "http://10.0.0.5:8790", "tenant_id": tid, "name": "公司服务器"})
    router = PlaneRouter(svc, cs, client_factory=lambda c: _TestClientRemote(client, token, c["tenant_id"]))

    # The datasheet product only exists on the private server.
    r = router.search("工作电压是多少", platform_item_id="880001")
    assert r["product"]["code"] == "FT62F0Mx" and r["plane"] == "private"
    assert r["sensitivity"] == "private"
    assert {p["plane"] for p in r["planes"]} == {"local", "private"}

    # A merchant question is answered locally and is not private.
    r2 = router.search("这件是什么材质", platform_item_id="6600001")
    assert r2["product"]["code"] == "TS-001" and r2["plane"] == "local" and r2["sensitivity"] == "internal"
    assert conn["id"]


def test_router_survives_an_unreachable_server(svc, shop, tmp_path):
    cs = ConnectionStore(str(tmp_path / "c.json"))
    cs.save({"plane": "public", "base_url": "https://127.0.0.1:1", "tenant_id": "t", "name": "云端"})

    class Down(RemoteKS):
        def search(self, *a, **k):
            raise ConnectionError("server down")

    router = PlaneRouter(svc, cs, client_factory=lambda c: Down(c["base_url"], lambda: "", "t"))
    r = router.search("这件是什么材质", platform_item_id="6600001")
    assert r["product"]["code"] == "TS-001"
    assert r["plane_errors"][0]["source"] == "云端"


def test_confidential_local_kb_is_private(svc, shop):
    kb = svc.catalog_kb(shop["tid"])
    svc.update_kb(kb["id"], sensitivity="confidential")
    assert svc.search("材质", platform_item_id="6600001")["sensitivity"] == "private"


# ---- guard -----------------------------------------------------------------------------
class FakeLLM:
    def __init__(self, base_url):
        self.openai_api_base = base_url


class Bound:
    def __init__(self, inner):
        self.bound = inner


def test_guard_only_acts_on_tainted_runs():
    state = {}
    taint.check_llm(state, FakeLLM("https://api.openai.com/v1"))  # not tainted: allowed
    taint.mark(state, "internal")
    taint.check_llm(state, FakeLLM("https://api.openai.com/v1"))
    taint.mark(state, "private")
    taint.mark(state, "internal")  # cannot be downgraded within a run
    with pytest.raises(taint.PrivateDataBlocked):
        taint.check_llm(state, FakeLLM("https://api.openai.com/v1"), "openai", "qa:answer")


@pytest.mark.parametrize("url,ok", [
    ("http://127.0.0.1:8000/v1", True), ("http://localhost:11434", True), ("http://192.168.10.5:8000/v1", True),
    ("http://10.1.2.3/v1", True), ("http://gpu01.corp/v1", True), ("https://dashscope.aliyuncs.com/v1", False),
    ("https://sccb0-xyz.service.tcloudbase.com/api/llm-proxy/v1", False), (None, False),
])
def test_guard_endpoint_classification(url, ok):
    state = {taint.TAINT_KEY: "private"}
    llm = Bound(FakeLLM(url)) if url else object()
    if ok:
        taint.check_llm(state, llm)
    else:
        with pytest.raises(taint.PrivateDataBlocked):
            taint.check_llm(state, llm)


def test_guard_extra_hosts_and_disable(monkeypatch):
    state = {taint.TAINT_KEY: "private"}
    monkeypatch.setenv("ECAN_PRIVATE_LLM_HOSTS", "llm.mycompany.com")
    taint.check_llm(state, FakeLLM("https://llm.mycompany.com/v1"))
    monkeypatch.setenv("ECAN_KS_TAINT_GUARD", "0")
    taint.check_llm(state, FakeLLM("https://api.openai.com/v1"))
