"""Deleting a store from the Stores page: the store, its agents and tasks go;
agents that also serve another store stay; the login profile stays; the cloud
record is deleted (archived while the server has no store_delete yet)."""

import os
import tempfile
from types import SimpleNamespace
from unittest import mock

import pytest
from sqlalchemy import create_engine

from agent.cloud_api import store_api
from agent.db.models.store_model import Store
from agent.db.services.db_store_service import DBStoreService
from agent.ec_agents import store_catalog as sc


def _task(tid, store_id):
    return SimpleNamespace(id=tid, name=tid, metadata={"task_vars": {"store_id": store_id} if store_id else {}})


def _agent(aid, *tasks):
    a = SimpleNamespace(card=SimpleNamespace(id=aid, name=aid), _running=True, status="active", tasks=list(tasks))
    a.stop = mock.Mock()
    return a


def _mainwin(agents):
    path = os.path.join(tempfile.mkdtemp(), "stores.db")
    engine = create_engine(f"sqlite:///{path}")
    Store.__table__.create(engine)
    svc = DBStoreService(engine=engine)
    svc.upsert_store({"store_id": "shopA", "name": "A", "platform": "douyin"})
    svc.upsert_store({"store_id": "shopB", "name": "B", "platform": "douyin"})
    return SimpleNamespace(ec_db_mgr=SimpleNamespace(store_service=svc), agents=list(agents))


@pytest.fixture
def mw():
    return _mainwin([
        _agent("fd_A", _task("fd_task_A", "shopA")),                         # A's front desk
        _agent("qa_A", _task("qa_task_A", "shopA")),                         # A-only Q&A
        _agent("both", _task("b_A", "shopA"), _task("b_B", "shopB")),        # serves A and B
        _agent("pool", _task("pool_t", None)),                               # shared pool, no store id
        _agent("fd_B", _task("fd_task_B", "shopB")),
    ])


def test_plan_takes_only_what_belongs_to_the_store(mw):
    p = sc.delete_plan(mw, "shopA")
    assert sorted(a["id"] for a in p["agents"]) == ["fd_A", "qa_A"]
    assert sorted(t["id"] for t in p["tasks"]) == ["b_A", "fd_task_A", "qa_task_A"]
    assert [a["id"] for a in p["kept_agents"]] == ["both"]


def test_dry_run_changes_nothing(mw):
    with mock.patch("gui.ipc.w2p_handlers.agent_handler.handle_delete_agent") as da:
        out = sc.delete_store(mw, {"store_id": "shopA", "dry_run": True})
    assert "plan" in out and not da.called
    assert mw.ec_db_mgr.store_service.get_store("shopA")


def test_delete_stops_then_removes_agents_tasks_cloud_and_local(mw):
    ok = {"status": "success"}
    with mock.patch("gui.ipc.w2p_handlers.agent_handler.handle_delete_agent", return_value=ok) as da, \
         mock.patch("gui.ipc.w2p_handlers.task_handler.handle_delete_agent_task", return_value=ok) as dt, \
         mock.patch("agent.cloud_api.store_api.store_delete", return_value={"cloud": "deleted"}) as cd:
        out = sc.delete_store(mw, {"store_id": "shopA", "username": "me"})
    by_id = {a.card.id: a for a in mw.agents}
    assert by_id["fd_A"].stop.called and by_id["qa_A"].stop.called
    assert not by_id["both"].stop.called and not by_id["pool"].stop.called
    assert sorted(da.call_args.args[1]["agent_id"]) == ["fd_A", "qa_A"]
    assert sorted(c.args[1]["task_id"] for c in dt.call_args_list) == ["b_A", "fd_task_A", "qa_task_A"]
    cd.assert_called_once_with("shopA")
    assert out["cloud"] == "deleted" and out["local"] is True
    assert mw.ec_db_mgr.store_service.get_store("shopA") is None
    assert mw.ec_db_mgr.store_service.get_store("shopB")
    assert any("both" in w for w in out["warnings"])


def test_username_is_required_for_a_real_delete(mw):
    with pytest.raises(ValueError):
        sc.delete_store(mw, {"store_id": "shopA"})


def test_cloud_without_store_delete_archives_instead():
    calls = []

    def fake_call(action, payload, timeout):
        calls.append(action)
        if action == "store_delete":
            raise store_api.StoreApiError("unknown action store_delete")
        return {"success": True}

    with mock.patch.object(store_api, "_call", side_effect=fake_call):
        out = store_api.store_delete("shopA")
    assert calls == ["store_delete", "store_archive"]
    assert out["cloud"] == "archived" and "unavailable" in out["note"]


def test_cloud_delete_when_supported():
    with mock.patch.object(store_api, "_call", return_value={"success": True}) as c:
        assert store_api.store_delete("shopA") == {"cloud": "deleted"}
    assert c.call_args.args[0] == "store_delete"
