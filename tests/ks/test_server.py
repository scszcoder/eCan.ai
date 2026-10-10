"""Knowledge Service HTTP server: auth, permissions, search, upload + import."""
import csv
import io
import json
import time

import pytest
from fastapi.testclient import TestClient

from knowledge.ks.embedding import HashingEmbedder
from knowledge.ks.identity import IdentityRegistry, LocalVerifier
from knowledge.ks.server import ServerConfig, create_app
from knowledge.ks.service import KnowledgeService


@pytest.fixture
def env(tmp_path):
    svc = KnowledgeService(f"sqlite:///{(tmp_path / 'srv.db').as_posix()}", embedder=HashingEmbedder(), owner="server")
    local = LocalVerifier(secret="test-secret")
    cfg = ServerConfig(db_url="unused", plane="private", data_dir=str(tmp_path / "data"),
                       bootstrap_admin="admin@corp.cn:pw123", bootstrap_tenant="示例企业", allow_tenant_create=True)
    client = TestClient(create_app(svc, IdentityRegistry([local]), cfg, local))
    return client, svc, local


def _login(client):
    r = client.post("/v1/auth/local", json={"email": "admin@corp.cn", "password": "pw123"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_health_is_public_everything_else_needs_a_token(env):
    client, *_ = env
    assert client.get("/v1/health").json()["plane"] == "private"
    assert client.get("/v1/me").status_code == 401
    assert client.get("/v1/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert client.post("/v1/auth/local", json={"email": "admin@corp.cn", "password": "nope"}).status_code == 401


def test_bootstrap_admin_owns_the_first_tenant(env):
    client, *_ = env
    me = client.get("/v1/me", headers=_login(client)).json()
    assert me["tenants"][0]["name"] == "示例企业" and me["tenants"][0]["role"] == "owner"


def test_full_flow_upload_import_search_and_member_permissions(env):
    client, svc, local = env
    h = _login(client)
    tid = client.get("/v1/me", headers=h).json()["tenants"][0]["id"]
    store = client.post(f"/v1/tenants/{tid}/stores", headers=h, json={"name": "企业商城"}).json()

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["货号", "商品名称", "商品ID", "材质"])
    w.writerow(["MCU-1", "FT62F0Mx 开发板", "550001", "FR4"])
    files = {"file": ("catalog.csv", buf.getvalue().encode("utf-8-sig"), "text/csv")}
    pv = client.post(f"/v1/tenants/{tid}/catalog/preview", headers=h, files=files).json()
    assert pv["report"]["products"] == 1 and "path" not in pv  # server paths are not leaked
    job = client.post(f"/v1/tenants/{tid}/catalog/import", headers=h, data={
        "upload_id": pv["upload_id"], "mapping": json.dumps(pv["mapping"]), "default_store_id": store["id"]}).json()
    for _ in range(100):
        job = client.get(f"/v1/jobs/{job['id']}", headers=h).json()
        if job["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.05)
    assert job["status"] == "succeeded", job

    r = client.post(f"/v1/tenants/{tid}/search", headers=h, json={"query": "什么材质", "platform_item_id": "550001"})
    assert r.status_code == 200 and r.json()["product"]["code"] == "MCU-1" and r.json()["plane"] == "private"

    # A colleague is invited as viewer; they can search but not write or administer.
    assert client.post(f"/v1/tenants/{tid}/members", headers=h, json={"email": "eng@corp.cn", "role": "viewer"}).status_code == 200
    eng = {"Authorization": f"Bearer {local.issue('eng-sub', 'eng@corp.cn')}"}
    assert client.post(f"/v1/tenants/{tid}/search", headers=eng, json={"query": "材质", "platform_item_id": "550001"}).status_code == 200
    assert client.post(f"/v1/tenants/{tid}/products", headers=eng, json={"code": "X", "title": "x"}).status_code == 403
    assert client.get(f"/v1/tenants/{tid}/access", headers=eng).status_code == 403

    # A stranger with a valid token sees nothing.
    stranger = {"Authorization": f"Bearer {local.issue('s', 'someone@else.com')}"}
    assert client.post(f"/v1/tenants/{tid}/search", headers=stranger, json={"query": "材质"}).status_code == 403
    assert client.get("/v1/tenants/tn_missing/overview", headers=stranger).status_code == 404


def test_upload_type_is_checked(env):
    client, *_ = env
    h = _login(client)
    tid = client.get("/v1/me", headers=h).json()["tenants"][0]["id"]
    r = client.post(f"/v1/tenants/{tid}/catalog/preview", headers=h, files={"file": ("x.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 400


def test_self_service_tenant_creation(env):
    client, _, local = env
    h = {"Authorization": f"Bearer {local.issue('m-1', 'boss@shop.com')}"}
    t = client.post("/v1/tenants", headers=h, json={"name": "新商家"}).json()
    me = client.get("/v1/me", headers=h).json()
    assert [x["id"] for x in me["tenants"]] == [t["id"]] and me["tenants"][0]["role"] == "owner"


def test_unreachable_database_serves_a_degraded_health_report(monkeypatch, tmp_path):
    from knowledge.ks import server as srv
    monkeypatch.setenv("KS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KS_DB_URL", "postgresql+psycopg://u:secretpw@127.0.0.1:1/db")
    monkeypatch.setenv("KS_DB_CONNECT_TIMEOUT", "2")
    client = TestClient(srv.build_from_env())
    assert client.get("/healthz").status_code == 200
    r = client.get("/v1/health")
    assert r.status_code == 503 and r.json()["status"] == "degraded"
    assert "secretpw" not in r.text


def test_two_instances_share_writes_through_the_index_version(tmp_path):
    # Cloud functions run several instances, each with its own in-memory index.
    url = f"sqlite:///{(tmp_path / 'shared.db').as_posix()}"
    a = KnowledgeService(url, embedder=HashingEmbedder())
    b = KnowledgeService(url, embedder=HashingEmbedder())
    tid = a.tenant_id()
    st = a.save_store({"name": "店"})
    a.save_product({"code": "P1", "title": "纯棉T恤", "attributes": {"材质": "100%棉"},
                    "listings": [{"store_id": st["id"], "platform_item_id": "1001"}]})
    assert b.search("什么材质", platform_item_id="1001", tenant_id=tid)["product"]["code"] == "P1"
    a.save_product({"code": "P1", "title": "纯棉T恤", "attributes": {"材质": "95%棉 5%氨纶"},
                    "listings": [{"store_id": st["id"], "platform_item_id": "1001"}]})
    facts = b.search("什么材质", platform_item_id="1001", tenant_id=tid)["facts"]
    assert any(f["value"] == "95%棉 5%氨纶" for f in facts)


def test_path_prefix_is_stripped():
    from fastapi import FastAPI
    from knowledge.ks.server import StripPrefix
    inner = FastAPI()

    @inner.get("/v1/health")
    def h():
        return {"ok": True}

    c = TestClient(StripPrefix(inner, "/api/knowledge"))
    assert c.get("/api/knowledge/v1/health").json() == {"ok": True}
    assert c.get("/v1/health").json() == {"ok": True}



def test_catalog_import_accepts_the_file_again(env):
    # Cloud functions: the import request may reach an instance that never saw the preview.
    client, *_ = env
    h = _login(client)
    tid = client.get("/v1/me", headers=h).json()["tenants"][0]["id"]
    store = client.post(f"/v1/tenants/{tid}/stores", headers=h, json={"name": "店"}).json()
    data = "货号,商品名称,商品ID,材质\nP9,羊毛衫,770001,100%羊毛\n".encode("utf-8-sig")
    pv = client.post(f"/v1/tenants/{tid}/catalog/preview", headers=h, files={"file": ("c.csv", data, "text/csv")}).json()
    form = {"upload_id": "gone.csv", "mapping": json.dumps(pv["mapping"]), "default_store_id": store["id"]}
    assert client.post(f"/v1/tenants/{tid}/catalog/import", headers=h, data=form).status_code == 404
    job = client.post(f"/v1/tenants/{tid}/catalog/import", headers=h, data=form,
                      files={"file": ("c.csv", data, "text/csv")}).json()
    for _ in range(100):
        job = client.get(f"/v1/jobs/{job['id']}", headers=h).json()
        if job["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.05)
    assert job["status"] == "succeeded", job
    r = client.post(f"/v1/tenants/{tid}/search", headers=h, json={"query": "什么材质", "platform_item_id": "770001"})
    assert r.json()["product"]["code"] == "P9"


def test_forged_store_header_and_audit_are_tenant_bound(env):
    client, svc, local = env
    h = _login(client)
    tid = client.get("/v1/me", headers=h).json()["tenants"][0]["id"]
    store = client.post(f"/v1/tenants/{tid}/stores", headers=h, json={"name": "受害店"}).json()
    kb = svc.catalog_kb(tid)
    svc.update_kb(kb["id"], sensitivity="confidential")
    svc.set_grant(kb["id"], "store", store["id"], "read")

    # Another signed-in user, with their own tenant, names the victim's store.
    eve = {"Authorization": f"Bearer {local.issue('eve-sub', 'eve@evil.cn')}"}
    own = client.post("/v1/tenants", headers=eve, json={"name": "Eve Co"}).json()
    forged = dict(eve, **{"X-Ecan-Store": store["id"], "X-Ecan-Agent": "qa"})
    assert client.post(f"/v1/tenants/{tid}/search", headers=forged, json={"query": "材质"}).status_code == 403
    assert client.get(f"/v1/tenants/{tid}/products", headers=forged).status_code == 403
    assert client.get(f"/v1/tenants/{tid}/policies", headers=forged).status_code == 403

    # Eve administers her own tenant, and its audit log shows only her tenant.
    audit = client.get(f"/v1/tenants/{own['id']}/audit", headers=eve)
    assert audit.status_code == 200
    rows = audit.json() if isinstance(audit.json(), list) else audit.json().get("entries", audit.json().get("audit", []))
    assert rows and all("受害店" not in json.dumps(r, ensure_ascii=False) for r in rows)
    assert client.get(f"/v1/tenants/{tid}/audit", headers=eve).status_code == 403


def test_old_database_gets_the_audit_tenant_column(tmp_path):
    import sqlite3
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE ks_audit (id INTEGER PRIMARY KEY, ts DATETIME, actor VARCHAR(200), "
                "action VARCHAR(60) NOT NULL, target VARCHAR(200), detail JSON)")
    con.execute("INSERT INTO ks_audit (action) VALUES ('old.row')")
    con.commit()
    con.close()
    svc = KnowledgeService(f"sqlite:///{db.as_posix()}", embedder=HashingEmbedder())
    svc.store.audit("a", "new.row", tenant_id="t1")
    assert [r["action"] for r in svc.store.list_audit("t1")] == ["new.row"]
    assert svc.store.list_audit("") and svc.store.list_audit("")[0]["action"] == "old.row"
