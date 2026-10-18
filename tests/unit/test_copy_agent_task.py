"""copy_agent_task: a new task with the source task's definition (skill,
trigger, schedule, settings) under a new name -- what the agent editor offers
when a task picked for an agent already belongs to another agent."""
import json

import pytest
from sqlalchemy import create_engine

from agent.db.core.base import Base
from agent.db.services.db_skill_service import DBSkillService
from agent.db.services.db_task_service import DBTaskService
from gui.ipc.w2p_handlers import task_handler as th


@pytest.fixture
def svc(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    DBSkillService(engine=engine).add_skill({"id": "sk_img", "name": "亚马逊电商做图00", "owner": "u", "version": "1"})
    s = DBTaskService(engine=engine)
    s.add_task({"id": "task_src", "name": "电商做图00", "owner": "u", "description": "d", "task_type": "local",
                "trigger": "message", "priority": "high", "schedule": {"repeat_type": "none"},
                "settings": {"task_vars": {"store": "A"}}})
    s.add_skill_to_task(task_id="task_src", skill_id="sk_img", role="primary", is_required=True)
    calls = []
    monkeypatch.setattr(th, "_get_agent_task_service", lambda *a, **k: s)
    monkeypatch.setattr(th, "resolve_username", lambda req, params: "u")
    monkeypatch.setattr(th, "_update_agent_task_in_memory", lambda tid, data: calls.append(("memory", tid)))
    monkeypatch.setattr(th, "_sync_runtime_task_skill", lambda tid, **k: calls.append(("runtime", tid, k.get("agent_id"))))
    monkeypatch.setattr(th, "_trigger_cloud_sync", lambda data, op: calls.append(("cloud", data["id"], data["name"])))
    monkeypatch.setattr(th, "_sync_task_skill_relations", lambda tid, ids, op: calls.append(("cloud_rels", tid, ids)))
    s.calls = calls
    return s


def _copy(**params):
    req = {"id": "r", "type": "request", "method": "copy_agent_task", "params": params}
    return th.handle_copy_agent_task(req, params)


def test_copy_keeps_the_definition_under_a_new_id_and_name(svc):
    resp = _copy(task_id="task_src", new_name="电商做图00-做图专家小王", agent_id="agent_wang")
    assert resp["status"] == "success", resp
    new_id = resp["result"]["task_id"]
    assert new_id and new_id != "task_src"

    row = svc.get_task_by_id(new_id)["data"]
    assert row["name"] == "电商做图00-做图专家小王"
    assert row["trigger"] == "message" and row["priority"] == "high" and row["task_type"] == "local"
    meta = row["metadata"] if isinstance(row["metadata"], dict) else json.loads(row["metadata"])
    assert meta["task_vars"] == {"store": "A"}
    assert [r["skill_id"] for r in svc.get_task_skills(new_id)["data"]] == ["sk_img"]

    # Same steps as creating a task: memory, runtime skill, cloud (row + skill rels).
    assert ("memory", new_id) in svc.calls
    assert ("runtime", new_id, "agent_wang") in svc.calls
    assert ("cloud", new_id, "电商做图00-做图专家小王") in svc.calls
    assert ("cloud_rels", new_id, ["sk_img"]) in svc.calls

    # The source task is untouched.
    src = svc.get_task_by_id("task_src")["data"]
    assert src["name"] == "电商做图00"
    assert [r["skill_id"] for r in svc.get_task_skills("task_src")["data"]] == ["sk_img"]


def test_missing_source_or_name_is_an_error(svc):
    assert _copy(task_id="nope", new_name="x")["status"] == "error"
    assert _copy(task_id="task_src", new_name="")["status"] == "error"
