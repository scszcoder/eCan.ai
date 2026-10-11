"""Catalog files an agent staged for review (knowledge/ks/pending_imports.py),
the ks.* handlers around them, and importing one with a single click."""
import csv
import os
import time

import pytest

from gui.ipc.w2p_handlers import knowledge_service_handler as h
from knowledge.ks import pending_imports as pi


def _req(method, params=None):
    return {"id": "1", "type": "request", "method": method, "params": params, "meta": {}, "timestamp": 0}


def _ok(resp):
    assert resp.get("status") == "success", resp
    return resp["result"]


def _export(path, rows=(("A1", "羊毛围巾", "900001"), ("B2", "棉袜", "900002"))):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["商家编码", "商品名称", "商品ID"])
        for r in rows:
            w.writerow(r)
    return str(path)


@pytest.fixture
def wired(svc, monkeypatch, tmp_path):
    svc.data_dir = str(tmp_path / "ks_data")
    monkeypatch.setattr(h, "_svc", lambda: svc)
    return svc


def test_newest_file_picks_the_latest_export(tmp_path):
    old = _export(tmp_path / "old.csv")
    os.utime(old, (1000, 1000))
    new = _export(tmp_path / "new.csv")
    (tmp_path / "notes.txt").write_text("x")
    assert pi.newest_file(str(tmp_path)) == new
    assert pi.newest_file(str(tmp_path), since=time.time() + 60) == ""
    assert pi.newest_file(str(tmp_path / "missing")) == ""


def test_stage_list_dismiss(tmp_path):
    store = pi.PendingImports(str(tmp_path / "data"))
    e = store.stage(_export(tmp_path / "导出.csv"), store_id="s1", source="抖店商品导出")
    assert e["rows"] == 2 and e["file_name"] == "导出.csv" and os.path.isfile(e["path"])
    assert [x["id"] for x in store.list()] == [e["id"]]
    assert store.remove(e["id"]) is True and store.list() == [] and not os.path.exists(e["path"])
    assert store.remove("nope") is False
    with pytest.raises(FileNotFoundError):
        store.stage(str(tmp_path / "missing.csv"))
    empty = tmp_path / "empty.csv"
    empty.write_text("商品名称\n", encoding="utf-8")
    with pytest.raises(ValueError):
        store.stage(str(empty))


def test_stage_for_review_from_a_downloads_folder(wired, tmp_path, monkeypatch):
    monkeypatch.setattr("knowledge.ks.service.get_service", lambda *a, **k: wired)
    dl = tmp_path / "downloads"
    dl.mkdir()
    t0 = time.time() - 1
    _export(dl / "商品导出.csv")
    e = pi.stage_for_review(str(dl), store_id="s9", source="抖店商品导出", since=t0)
    assert e["store_id"] == "s9" and wired.pending_imports()[0]["id"] == e["id"]
    with pytest.raises(FileNotFoundError):
        pi.stage_for_review(str(dl), since=time.time() + 60)


def test_one_click_import_of_a_staged_file(wired, tmp_path):
    store = _ok(h.handle_save_store(_req("ks.saveStore"), {"name": "抖音店"}))
    staged = wired.stage_catalog(_export(tmp_path / "x.csv"), store_id=store["id"], source="抖店商品导出")
    items = _ok(h.handle_list_pending_imports(_req("ks.listPendingImports"), {}))["items"]
    assert [i["id"] for i in items] == [staged["id"]]
    pv = _ok(h.handle_preview_catalog(_req("ks.previewCatalog"), {"path": items[0]["path"]}))
    job = _ok(h.handle_import_catalog(_req("ks.importCatalog"), {
        "path": items[0]["path"], "mapping": pv["mapping"], "default_store_id": store["id"],
        "pending_id": staged["id"]}))
    assert _ok(h.handle_list_pending_imports(_req("ks.listPendingImports"), {}))["items"] == []
    for _ in range(100):
        job = _ok(h.handle_get_job(_req("ks.getJob"), {"id": job["id"]}))
        if job["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.05)
    assert job["status"] == "succeeded", job      # the staged copy was still there to read


def test_dismiss_handler(wired, tmp_path):
    staged = wired.stage_catalog(_export(tmp_path / "y.csv"))
    assert _ok(h.handle_dismiss_pending_import(_req("ks.dismissPendingImport"), {"id": staged["id"]}))["dismissed"]
    assert _ok(h.handle_list_pending_imports(_req("ks.listPendingImports"), {}))["items"] == []
    resp = h.handle_dismiss_pending_import(_req("ks.dismissPendingImport"), {})
    assert resp["error"]["code"] == "INVALID_PARAMS"
