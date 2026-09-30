"""An agent created without a vehicle still gets its task links (2026-09-30).

create_agent_from_data used to write agent_task_rels only when a vehicle_id
was given. A store-placed Fast Deploy (拼多多客服) pins no vehicle, so its
agents loaded with 0 tasks and never ran.
"""

import pytest
from sqlalchemy import create_engine

from agent.db.core.base import Base
from agent.db.services.db_agent_service import DBAgentService
from agent.db.services.db_task_service import DBTaskService


@pytest.fixture
def services():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return DBAgentService(engine=engine), DBTaskService(engine=engine)


def _task(tasks, name):
    r = tasks.add_task({"name": name, "owner": "u@x", "status": "pending"})
    assert r["success"], r
    return r["id"]


def test_task_link_created_without_vehicle(services):
    agents, tasks = services
    tid = _task(tasks, "拼多多客服前台001")
    r = agents.create_agent_from_data({"name": "前台小张", "tasks": [tid]}, "u@x")
    assert r["success"], r
    rows = agents.query_agents_with_relations(id=r["id"])["data"]
    row = rows[0] if isinstance(rows, list) else rows
    assert [t["id"] for t in row["tasks"]] == [tid]


def _rels(agents, agent_id):
    from agent.db.models.association_models import DBAgentTaskRel
    with agents.session_scope() as s:
        return [(r.task_id, r.vehicle_id) for r in
                s.query(DBAgentTaskRel).filter(DBAgentTaskRel.agent_id == agent_id)]


def test_agent_keeps_vehicle_but_link_carries_none(services):
    agents, tasks = services
    tid = _task(tasks, "t1")
    r = agents.create_agent_from_data({"name": "a", "tasks": [tid], "vehicle_id": "veh-1"}, "u@x")
    assert r["success"], r
    assert r["data"]["vehicle_id"] == "veh-1"
    assert _rels(agents, r["id"]) == [(tid, None)]


def test_update_links_tasks_without_vehicle(services):
    agents, tasks = services
    t1, t2 = _task(tasks, "t1"), _task(tasks, "t2")
    r = agents.create_agent_from_data({"name": "a", "tasks": [t1]}, "u@x")
    u = agents.update_agent(r["id"], {"tasks": [t2], "vehicle_id": "veh-2"})
    assert u["success"], u
    assert _rels(agents, r["id"]) == [(t2, None)]
