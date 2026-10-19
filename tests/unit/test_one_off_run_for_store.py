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
