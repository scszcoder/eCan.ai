"""Workspace (knowledge base) filesystem helpers.

Regressions covered:
- deleteWorkspace looked in ``<user data>/lightrag_<name>`` while the list
  read ``rag_storage/<name>``, so deletes never found the real folder.
- Workspace paths were derived with ``split('/')``, which broke on Windows.
- Query/conversation history was one global file shared by all workspaces.
"""
import json

import pytest

from knowledge import lightrag_workspaces as lw


@pytest.fixture
def storage(tmp_path):
    root = tmp_path / "lightrag" / "rag_storage"
    for name in ("default", "shop_a", "inputs", ".hidden"):
        (root / name).mkdir(parents=True)
    (root / "shop_a" / "kv_store_full_docs.json").write_text("{}", encoding="utf-8")
    return root


def test_root_is_found_from_inside_a_workspace(storage):
    assert lw.rag_storage_root(str(storage / "shop_a")) == storage
    assert lw.rag_storage_root(str(storage)) == storage


def test_windows_style_path(storage):
    # Backslash paths are what Windows users have in WORKING_DIR.
    win = str(storage).replace("/", "\\")
    assert lw.rag_storage_root(win + "\\shop_a").name == "rag_storage"


def test_list_skips_system_and_hidden_dirs(storage):
    assert lw.list_workspaces(str(storage)) == ["default", "shop_a"]


@pytest.mark.parametrize("bad", ["", "  ", "..", "../x", "a/b", "a\\b", ".git", "inputs", "c:x"])
def test_invalid_names_are_rejected(bad):
    with pytest.raises(ValueError):
        lw.validate_workspace_name(bad)


def test_unicode_names_are_allowed():
    assert lw.validate_workspace_name(" 童装店 ") == "童装店"


def test_delete_removes_only_that_workspace(storage, tmp_path):
    legacy = tmp_path / "userdata"
    (legacy / "lightrag_shop_a").mkdir(parents=True)
    removed = lw.delete_workspace_files(str(storage), "shop_a", str(legacy))
    assert len(removed) == 2
    assert not (storage / "shop_a").exists()
    assert not (legacy / "lightrag_shop_a").exists()
    assert (storage / "default").exists()


def test_delete_missing_workspace_removes_nothing(storage):
    assert lw.delete_workspace_files(str(storage), "nope") == []


def test_history_is_per_workspace(storage):
    lw.write_history(str(storage), "shop_a", "input", ["q1"])
    lw.write_history(str(storage), "default", "input", ["q2"])
    assert lw.read_history(str(storage), "shop_a", "input") == ["q1"]
    assert lw.read_history(str(storage), "default", "input") == ["q2"]
    assert lw.read_history(str(storage), "shop_a", "conversation") == []


def test_legacy_global_history_shows_for_default_workspace_only(storage):
    (storage / "lightrag_input_history.json").write_text(json.dumps(["old"]), encoding="utf-8")
    assert lw.read_history(str(storage), "default", "input", default_workspace="default") == ["old"]
    assert lw.read_history(str(storage), "shop_a", "input", default_workspace="default") == []


def test_corrupt_history_reads_as_empty(storage):
    p = lw.history_path(str(storage), "shop_a", "conversation")
    p.write_text("{not json", encoding="utf-8")
    assert lw.read_history(str(storage), "shop_a", "conversation") == []


class _Resp:
    def __init__(self, payload, code=200):
        self._payload, self.status_code, self.text = payload, code, json.dumps(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


def test_clear_documents_is_scoped_and_reports_busy(monkeypatch):
    from knowledge.lightrag_client import LightragClient
    c = LightragClient(base_url="http://127.0.0.1:1")
    seen = {}

    def fake_delete(url, headers=None, timeout=None):
        seen["url"], seen["headers"] = url, headers
        return _Resp({"status": "busy", "message": "pipeline running"})

    monkeypatch.setattr(c.session, "delete", fake_delete)
    out = c.clear_documents(workspace="童装店")
    assert seen["url"].endswith("/documents")
    assert seen["headers"]["LIGHTRAG-WORKSPACE"] == "%E7%AB%A5%E8%A3%85%E5%BA%97"
    assert out["status"] == "error" and "pipeline running" in out["message"]
