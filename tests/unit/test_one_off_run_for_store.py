"""为店铺运行一次 (agent/ec_tasks/one_off.py): a store-scoped skill (抖店商品导出)
runs once in the store's logged-in browser via the agent already running that
store -- a one-off task, no temporary agent, removed when its run ends."""
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from agent.ec_tasks import one_off

IDENT = {"browser_profile_id": "douyin-6a4b2c53-login"}


def _task(tid, store, one_off_=False, ident=True, skill_id="s_fd"):
    meta = {"task_vars": {"store_id": store, "store_url": f"https://{store}", "front_desk_agent_id": "x"}}
    if ident:
        meta["browser_identity"] = IDENT
    if one_off_:
        meta.update(one_off=True, one_off_skill_id=skill_id)
    return SimpleNamespace(id=tid, name=tid, metadata=meta, skill=SimpleNamespace(id=skill_id))


@pytest.fixture
def app():
    fd2 = SimpleNamespace(card=SimpleNamespace(id="agent_fd2", name="前台-抖音二号"),
                          tasks=[_task("t_fd2", "douyin-抖音二号")], runner=MagicMock(),
                          thread_pool_executor=MagicMock(), active_tasks={}, task_lock=threading.Lock())
    qa = SimpleNamespace(card=SimpleNamespace(id="agent_qa", name="客服小楠"),
                         tasks=[_task("t_qa", "", ident=False)], runner=MagicMock())
    db = MagicMock()
    db.skill_service.query_skills.side_effect = lambda **q: {"data": [{"id": "s_export", "name": "抖店商品导出"}]
                                                             if q.get("name") == "抖店商品导出" or q.get("id") == "s_export" else []}
    db.task_service.add_task.return_value = {"success": True, "id": "t_new"}
    db.task_service.add_skill_to_task.return_value = {"success": True}
    db.agent_service.assign_task_to_agent.return_value = {"success": True}
    db.task_service.query_tasks.return_value = {"data": [{"id": "t_new"}]}
    mw = SimpleNamespace(agents=[qa, fd2], ec_db_mgr=db, user="me")
    return mw, fd2, db


def test_runs_on_the_store_s_agent_with_its_store_and_browser(app):
    mw, fd2, db = app
    new = SimpleNamespace(id="t_new", name="抖店商品导出·douyin-抖音二号（一次性）", metadata={})
    with patch("agent.ec_agents.create_agent_tasks._convert_db_agent_task_to_object", return_value=new):
        res = one_off.run_for_store(mw, "抖店商品导出", "douyin-抖音二号")
    row = db.task_service.add_task.call_args.args[0]
    st = row["settings"]
    assert st["task_vars"] == {"store_id": "douyin-抖音二号", "store_url": "https://douyin-抖音二号"}  # no FD-only vars
    assert st["browser_identity"] == IDENT and st["one_off"] and st["run_once"]
    assert st["start_after_idle_min"] == 5 and st["start_after_idle_max_min"] == 60
    db.task_service.add_skill_to_task.assert_called_once_with("t_new", "s_export", role="primary")
    db.agent_service.assign_task_to_agent.assert_called_once_with("agent_fd2", "t_new", None)
    assert new in fd2.tasks and new.agent_id == "agent_fd2"
    submitted = fd2.thread_pool_executor.submit.call_args.args
    assert submitted[1] is new and "auto" in submitted[2]          # the runner's idle gate applies
    assert res["agent_name"] == "前台-抖音二号" and res["already_queued"] is False


def test_second_request_reports_the_queued_one(app):
    mw, fd2, db = app
    fd2.tasks.append(_task("t_q", "douyin-抖音二号", one_off_=True, skill_id="s_export"))
    res = one_off.run_for_store(mw, "抖店商品导出", "douyin-抖音二号")
    assert res["already_queued"] and res["task_id"] == "t_q"
    db.task_service.add_task.assert_not_called()


def test_unknown_store_names_the_stores_it_can_run_for(app):
    mw, _, _ = app
    with pytest.raises(ValueError, match="douyin-抖音二号"):
        one_off.run_for_store(mw, "抖店商品导出", "douyin-other")


def test_failed_setup_leaves_no_task_behind(app):
    mw, _, db = app
    db.agent_service.assign_task_to_agent.return_value = {"success": False, "error": "x"}
    with pytest.raises(RuntimeError):
        one_off.run_for_store(mw, "抖店商品导出", "douyin-抖音二号")
    db.task_service.delete_task.assert_called_once_with("t_new")


def test_store_hosts_lists_each_store_once(app):
    mw, _, _ = app
    assert one_off.store_hosts(mw) == [{"store_id": "douyin-抖音二号", "agent_id": "agent_fd2",
                                        "agent_name": "前台-抖音二号", "task_id": "t_fd2"}]


def test_retire_removes_the_task_from_agent_and_database():
    ev = threading.Event()
    task = SimpleNamespace(id="t_new", name="x", cancellation_event=ev)
    svc = MagicMock()
    agent = SimpleNamespace(tasks=[task], mainwin=SimpleNamespace(ec_db_mgr=SimpleNamespace(task_service=svc)))
    one_off.retire(agent, task, ok=True)
    assert agent.tasks == [] and ev.is_set()
    svc.delete_task.assert_called_once_with("t_new")


def test_cli_lists_stores_then_queues():
    from click.testing import CliRunner
    from cli.skills import commands as sc
    calls = []

    def fake_call(out, method, params=None, timeout=30):
        calls.append(method)
        if method == "skills.store_hosts":
            return {"stores": [{"store_id": "douyin-抖音二号", "store_name": "抖音二号", "agent_name": "前台-抖音二号"}]}
        return {"store_name": "抖音二号", "agent_name": "前台-抖音二号", "task_name": "t", "already_queued": False}

    out = MagicMock()
    with patch("cli.base.app_client.call_or_exit", side_effect=fake_call), \
         patch("cli.skills.commands.get_output", return_value=out), \
         patch("cli.base.context.get_context", return_value=SimpleNamespace(is_authenticated=True, username="me", require_auth=lambda: None)):
        r1 = CliRunner().invoke(sc.skills, ["run-for-store", "抖店商品导出"])
        r2 = CliRunner().invoke(sc.skills, ["run-for-store", "抖店商品导出", "--store", "douyin-抖音二号"])
    assert r1.exit_code == 0 and r2.exit_code == 0, (r1.output, r2.output)
    assert out.table.call_args.args[2][0][0] == "douyin-抖音二号"
    assert "Queued" in out.success.call_args.args[0]
    assert calls == ["skills.store_hosts", "skills.run_for_store"]


def test_prefers_the_store_s_operations_agent(app):
    mw, fd2, db = app
    ops_task = _task("t_ops", "douyin-抖音二号")
    ops_task.metadata["store_ops"] = True
    ops = SimpleNamespace(card=SimpleNamespace(id="agent_ops2", name="运营-抖音二号"), tasks=[ops_task],
                          runner=MagicMock(), thread_pool_executor=MagicMock(), active_tasks={},
                          task_lock=threading.Lock())
    mw.agents.append(ops)                      # listed after the front desk, still chosen
    assert one_off.store_hosts(mw)[0]["agent_name"] == "运营-抖音二号"
    new = SimpleNamespace(id="t_new", name="x", metadata={})
    with patch("agent.ec_agents.create_agent_tasks._convert_db_agent_task_to_object", return_value=new):
        res = one_off.run_for_store(mw, "抖店商品导出", "douyin-抖音二号")
    assert res["agent_id"] == "agent_ops2" and new in ops.tasks and new not in fd2.tasks


def test_a_skill_only_on_disk_is_registered_for_a_one_off(tmp_path, monkeypatch):
    # 2026-10-24 KEN: 抖店营销导出 existed only as files -> "skill not found".
    import importlib
    d = tmp_path / "抖店营销导出_skill" / "diagram_dir"
    d.mkdir(parents=True)
    (d / "抖店营销导出_skill.json").write_text('{"skillName": "抖店营销导出"}', encoding="utf-8")
    ext = importlib.import_module("agent.ec_skills.extern_skills.extern_skills")
    monkeypatch.setattr(ext, "user_skills_root", lambda: tmp_path)
    rows = []

    class Skills:
        def query_skills(self, **q):
            return {"data": [r for r in rows if r["name"] == q.get("name") or r["id"] == q.get("id")]}
    svc = Skills()
    sh = importlib.import_module("gui.ipc.w2p_handlers.skill_handler")
    seen = {}

    def fake_sync(path, params=None):
        seen.update(params or {})
        rows.append({"id": "s_promo", "name": "抖店营销导出"})
        return {"success": True}
    monkeypatch.setattr(sh, "sync_skill_from_file", fake_sync)
    mw = SimpleNamespace(ec_db_mgr=SimpleNamespace(skill_service=svc))
    assert one_off._skill_row(mw, "抖店营销导出")["id"] == "s_promo"
    assert seen["_skill_service"] is svc
    assert one_off._skill_row(mw, "没有这个技能") is None


# ---- schedule_for_store: "每天9点做价格核验" from chat, a saved store chore

DAILY_9 = {"repeat_type": "daily", "start_date_time": "2026-11-05T09:00:00"}


def test_a_chat_schedule_is_a_saved_store_chore_on_the_store_s_agent(app):
    mw, fd2, db = app
    new = SimpleNamespace(id="t_new", name="n", metadata={})
    with patch("agent.ec_agents.create_agent_tasks._convert_db_agent_task_to_object", return_value=new):
        res = one_off.schedule_for_store(mw, "抖店商品导出", "抖音二号", DAILY_9)   # the name the owner uses
    row = db.task_service.add_task.call_args.args[0]
    assert row["trigger"] == "schedule" and row["source"] == "chat_schedule"
    assert row["schedule"]["repeat_type"] == "by days" and row["schedule"]["start_date_time"] == "2026-11-05 09:00:00"
    assert row["settings"]["browser_identity"] == IDENT and row["settings"]["store_ops"]
    assert row["settings"]["task_vars"]["store_id"] == "douyin-抖音二号" and "one_off" not in row["settings"]
    assert fd2.thread_pool_executor.submit.call_args.args[2] == ["schedule"]
    assert res["replaced"] is False and res["agent_name"] == "前台-抖音二号"


def test_asking_again_moves_the_existing_schedule_instead_of_adding_one(app):
    mw, fd2, db = app
    chore = _task("t_chore", "douyin-抖音二号", skill_id="s_export")
    chore.trigger = "schedule"
    fd2.tasks.append(chore)
    db.task_service.update_task.return_value = {"success": True}
    fresh = SimpleNamespace(schedule="NEW")
    with patch("agent.ec_agents.create_agent_tasks._convert_db_agent_task_to_object", return_value=fresh):
        res = one_off.schedule_for_store(mw, "抖店商品导出", "douyin-抖音二号", dict(DAILY_9, start_date_time="2026-11-05 10:30:00"))
    db.task_service.add_task.assert_not_called()
    assert db.task_service.update_task.call_args.args[1]["schedule"]["start_date_time"] == "2026-11-05 10:30:00"
    assert chore.schedule == "NEW" and res["replaced"] and res["task_id"] == "t_chore"


def test_a_schedule_needs_a_repeat_and_a_start_time(app):
    mw, _, _ = app
    with pytest.raises(ValueError, match="repeating"):
        one_off.schedule_for_store(mw, "抖店商品导出", "douyin-抖音二号", {"repeat_type": "none", "start_date_time": "2026-11-05 09:00:00"})
    with pytest.raises(ValueError, match="start_date_time"):
        one_off.schedule_for_store(mw, "抖店商品导出", "douyin-抖音二号", {"repeat_type": "daily", "start_date_time": "明天9点"})


def test_the_schedule_tool_routes_store_chores_here(app):
    from agent.ec_tasks import task_mcp_tools
    mw, _, _ = app
    out = {"task_id": "t", "task_name": "x", "agent_name": "a", "store_id": "s", "replaced": False,
           "schedule": {"repeat_type": "by days", "start_date_time": "2026-11-05 09:00:00"}}
    with patch("agent.ec_tasks.one_off.schedule_for_store", return_value=out) as sfs:
        res = task_mcp_tools.schedule_agent_task(mw, {"skill_name": "抖店商品导出", "store_id": "douyin-抖音二号", "schedule": DAILY_9})
    sfs.assert_called_once_with(mw, "抖店商品导出", "douyin-抖音二号", DAILY_9)
    assert res["success"] and res["task_id"] == "t"
