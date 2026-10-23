"""A store with catalog auto-apply on (its operations agent's nightly export)
imports the fetched catalog straight into 商品知识 instead of staging it."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from knowledge.ks import pending_imports as pi


@pytest.fixture
def svc(tmp_path):
    s = MagicMock()
    s.data_dir = str(tmp_path)
    s.tenant_id.return_value = "t1"
    s.recheck_catalog.return_value = {"report": {"errors": []}}
    s.store.find_store.return_value = {"id": "ks_store_1"}
    s.import_catalog.return_value = {"_message": "导入完成：3 个商品"}
    s.stage_catalog.return_value = {"staged": True}
    with patch("knowledge.ks.service.get_service", return_value=s):
        yield s


@pytest.fixture
def export(tmp_path):
    f = tmp_path / "export.xlsx"
    f.write_bytes(b"x")
    return str(f)


def _table():
    return patch.object(pi.catalog_import, "read_table", return_value=(["商品ID", "标题"], [])), \
        patch.object(pi.catalog_import, "suggest_mapping", return_value={"商品ID": "code", "标题": "title"})


def test_flag_round_trip(svc):
    assert not pi.auto_apply_enabled("douyin-A")
    pi.set_auto_apply("douyin-A", True)
    assert pi.auto_apply_enabled("douyin-A") and not pi.auto_apply_enabled("douyin-B")
    pi.set_auto_apply("douyin-A", False)
    assert not pi.auto_apply_enabled("douyin-A")


def test_auto_apply_imports_for_the_store(svc, export):
    pi.set_auto_apply("douyin-A", True)
    a, b = _table()
    with a, b:
        out = pi.stage_for_review(export, store_id="douyin-A", source="抖店商品导出")
    assert out["auto_applied"]
    args, kw = svc.import_catalog.call_args
    assert args[0] == export and kw["default_store_id"] == "ks_store_1" and kw["run_inline"]
    svc.stage_catalog.assert_not_called()


def test_without_the_flag_it_is_staged_for_review(svc, export):
    out = pi.stage_for_review(export, store_id="douyin-A", source="抖店商品导出")
    assert out == {"staged": True}
    svc.import_catalog.assert_not_called()


def test_a_file_that_does_not_map_cleanly_is_staged(svc, export):
    pi.set_auto_apply("douyin-A", True)
    svc.recheck_catalog.return_value = {"report": {"errors": ["no title column"]}}
    a, b = _table()
    with a, b:
        out = pi.stage_for_review(export, store_id="douyin-A")
    assert out == {"staged": True}
    svc.import_catalog.assert_not_called()


def test_a_flag_left_in_the_old_cli_folder_still_counts(tmp_path, monkeypatch):
    import json
    import os
    import knowledge.ks.pending_imports as pi
    monkeypatch.setattr(pi, "_auto_path", lambda: str(tmp_path / "account" / "catalog_auto_apply.json"))
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path / "home") if p == "~" else p)
    legacy = tmp_path / "home" / ".ecan" / "knowledge_service"
    legacy.mkdir(parents=True)
    (legacy / "catalog_auto_apply.json").write_text(json.dumps({"douyin-小店一号": True}), encoding="utf-8")
    assert pi.auto_apply_enabled("douyin-小店一号") and not pi.auto_apply_enabled("douyin-other")
