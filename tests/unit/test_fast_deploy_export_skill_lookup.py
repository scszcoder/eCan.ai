"""快速生成 must add the store's product export even when 抖店商品导出 exists only as
files in my_skills (2026-10-19 customer: never registered in the skills DB, so
the DB-only lookup missed it and the deploy silently added no export)."""
import importlib
from types import SimpleNamespace

import pytest

dc = importlib.import_module("cli.deploy.commands")


class _Skills:
    def __init__(self, rows):
        self.rows = rows

    def query_skills(self, name=None):
        return {"data": [r for r in self.rows if r["name"] == name]}


@pytest.fixture
def skill_files(tmp_path, monkeypatch):
    d = tmp_path / "抖店商品导出_skill" / "diagram_dir"
    d.mkdir(parents=True)
    (d / "抖店商品导出_skill.json").write_text('{"skillName": "抖店商品导出"}', encoding="utf-8")
    ext = importlib.import_module("agent.ec_skills.extern_skills.extern_skills")
    monkeypatch.setattr(ext, "user_skills_root", lambda: tmp_path)
    return tmp_path


def test_skill_only_on_disk_is_registered_and_found(skill_files, monkeypatch):
    rows = []
    ctx = SimpleNamespace(db=SimpleNamespace(skill_service=_Skills(rows)))
    sh = importlib.import_module("gui.ipc.w2p_handlers.skill_handler")
    calls = []

    def fake_sync(path, params=None):
        calls.append((path, params))
        rows.append({"id": "skill_export1", "name": "抖店商品导出"})
        return {"success": True, "skill_id": "skill_export1"}

    monkeypatch.setattr(sh, "sync_skill_from_file", fake_sync)
    log = []
    row = dc._find_skill_named(ctx, "抖店商品导出", log)
    assert row and row["id"] == "skill_export1"
    assert calls and calls[0][1] == {"_skip_cloud_sync": True}
    assert any("抖店商品导出" in x for x in log)


def test_missing_skill_is_a_visible_warning_not_a_quiet_skip(tmp_path, monkeypatch):
    ext = importlib.import_module("agent.ec_skills.extern_skills.extern_skills")
    monkeypatch.setattr(ext, "user_skills_root", lambda: tmp_path)
    ctx = SimpleNamespace(db=SimpleNamespace(skill_service=_Skills([])))
    profile = SimpleNamespace(catalog_skill_name="抖店商品导出", promo_skill_name="", fd_task_prefix="飞鸽客服前台")
    log = []
    out = dc._store_side_tasks(ctx, {"fetch_catalog": True}, profile, "抖音二号",
                               lambda *a, **k: "t", log)
    assert out == () and any("WARNING" in x or "警告" in x for x in log)


def test_store_side_tasks_add_export_and_promos_for_the_store():
    ctx = SimpleNamespace(db=SimpleNamespace(skill_service=_Skills([
        {"id": "s_cat", "name": "抖店商品导出"}, {"id": "s_promo", "name": "抖店营销导出"}])))
    profile = SimpleNamespace(catalog_skill_name="抖店商品导出", promo_skill_name="抖店营销导出",
                              fd_task_prefix="飞鸽客服前台")
    made = []
    out = dc._store_side_tasks(ctx, {"fetch_catalog": True, "fetch_promos": True}, profile, "抖音二号",
                               lambda name, sid, **k: made.append((name, sid, k.get("trigger", "auto"))) or name,
                               [])
    assert [m[:2] for m in made] == [("飞鸽客服前台商品导出-抖音二号", "s_cat"),
                                     ("飞鸽客服前台活动刷新-抖音二号", "s_promo")]
    assert made[1][2] == "schedule"
    assert out == (("飞鸽客服前台商品导出-抖音二号", "s_cat"), ("飞鸽客服前台活动刷新-抖音二号", "s_promo"))
