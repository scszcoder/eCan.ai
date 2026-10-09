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
