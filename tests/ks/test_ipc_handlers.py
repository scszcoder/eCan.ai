"""ks.* IPC handlers: wiring, validation errors and a full import round trip."""
import csv

import pytest

from gui.ipc.w2p_handlers import knowledge_service_handler as h


@pytest.fixture
def wired(svc, monkeypatch):
    monkeypatch.setattr(h, "_svc", lambda: svc)
    return svc


def _req(method, params=None):
    return {"id": "1", "type": "request", "method": method, "params": params, "meta": {}, "timestamp": 0}


def _ok(resp):
    assert resp.get("status") == "success", resp
    return resp["result"]


def test_overview_and_store_crud(wired):
    st = _ok(h.handle_save_store(_req("ks.saveStore"), {"name": "测试店", "platform": "pdd"}))
    ov = _ok(h.handle_overview(_req("ks.overview"), {}))
    assert [s["name"] for s in ov["stores"]] == ["测试店"]
    assert ov["embedder"]["is_fallback"] is True
    _ok(h.handle_delete_store(_req("ks.deleteStore"), {"id": st["id"]}))
    assert _ok(h.handle_overview(_req("ks.overview"), {}))["stores"] == []


def test_validation_errors_are_user_facing(wired):
    resp = h.handle_save_product(_req("ks.saveProduct"), {"product": {"title": ""}})
    assert resp["status"] == "error" and resp["error"]["code"] == "INVALID_PARAMS"
    resp = h.handle_search(_req("ks.search"), {})
    assert resp["error"]["code"] == "INVALID_PARAMS" and "query" in resp["error"]["message"]


def test_import_round_trip_and_search(wired, tmp_path):
    p = tmp_path / "c.csv"
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["货号", "商品名称", "商品ID", "面料"])
        w.writerow(["A1", "羊毛围巾", "900001", "100%羊毛"])
    store = _ok(h.handle_save_store(_req("ks.saveStore"), {"name": "冬季店"}))
    preview = _ok(h.handle_preview_catalog(_req("ks.previewCatalog"), {"path": str(p)}))
    assert preview["mapping"]["面料"] == "material"
    job = _ok(h.handle_import_catalog(_req("ks.importCatalog"), {
        "path": str(p), "mapping": preview["mapping"], "default_store_id": store["id"]}))
    import time
    for _ in range(100):
        job = _ok(h.handle_get_job(_req("ks.getJob"), {"id": job["id"]}))
        if job["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.05)
    assert job["status"] == "succeeded", job
    r = _ok(h.handle_search(_req("ks.search"), {"query": "什么材质", "store_id": store["id"],
                                                "platform_item_id": "900001"}))
    assert r["product"]["code"] == "A1" and r["facts"][0]["value"] == "100%羊毛"
    jobs = _ok(h.handle_list_jobs(_req("ks.listJobs"), {}))
    assert jobs[0]["kind"] == "catalog_import"


def test_policies_view(wired):
    st = _ok(h.handle_save_store(_req("ks.saveStore"), {"name": "店A"}))
    _ok(h.handle_save_policy(_req("ks.savePolicy"), {"topic": "shipping", "text": "24小时发货"}))
    _ok(h.handle_save_policy(_req("ks.savePolicy"), {"topic": "shipping", "text": "当天发货", "store_id": st["id"]}))
    view = _ok(h.handle_get_policies(_req("ks.getPolicies"), {}))
    assert view["defaults"]["shipping"]["text"] == "24小时发货"
    assert view["overrides"][st["id"]]["shipping"]["text"] == "当天发货"


def test_catalog_template_is_written_without_overwriting(tmp_path):
    first = _ok(h.handle_write_catalog_template(_req("ks.writeCatalogTemplate"), {"dir": str(tmp_path)}))["path"]
    second = _ok(h.handle_write_catalog_template(_req("ks.writeCatalogTemplate"), {"dir": str(tmp_path)}))["path"]
    assert first.endswith("商品资料导入模板.xlsx") and second.endswith("商品资料导入模板 (2).xlsx")
    resp = h.handle_write_catalog_template(_req("ks.writeCatalogTemplate"), {"dir": str(tmp_path / "missing")})
    assert resp["error"]["code"] == "FILE_NOT_FOUND"
