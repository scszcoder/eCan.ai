"""Fast Deploy: N 售后 agents (电商售后应答) for a store, in one click. Their task
names carry 售后 -- how the front desk's after-sales routing finds them."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from cli.deploy import commands as cmd


class _B:
    def __init__(self):
        self.tasks, self.agents = [], []

    def task(self, name, skill_id, task_vars, identity=None, **kw):
        self.tasks.append((name, skill_id, dict(task_vars)))
        return f"t{len(self.tasks)}"

    def agent(self, name, skill_id, task_id, vehicle_id):
        self.agents.append((name, skill_id, task_id))
        return f"a{len(self.agents)}"


def _ctx(rows):
    return SimpleNamespace(db=SimpleNamespace(skill_service=SimpleNamespace(
        query_skills=lambda name=None: {"data": [r for r in rows if r["name"] == name]})))


def test_adds_after_sales_agents_listening_to_the_front_desk():
    b, log = _B(), []
    ids = cmd._add_aftersales_agents(_ctx([{"id": "skill_as", "name": "电商售后应答"}]),
                                     {"aftersales_agents": 2}, b, {"store_id": "s1"}, ["fd1"], "钛斯特的小店",
                                     "veh", log)
    assert ids == ["a1", "a2"]
    assert all("售后" in name and skill == "skill_as" for name, skill, _ in b.tasks)
    assert all(tv["front_desk_agent_id"] == "fd1" and tv["store_id"] == "s1" for _, _, tv in b.tasks)
    assert all(name.startswith("售后小") for name, _, _ in b.agents)
    from agent.ec_agents.aftersales_router import _mark
    assert all(_mark() in name for name, _, _ in b.tasks)          # the router will recognise them


def test_none_requested_creates_nothing():
    b = _B()
    assert cmd._add_aftersales_agents(_ctx([]), {}, b, {}, ["fd1"], "店", "veh", []) == []
    assert b.tasks == []


def test_a_missing_skill_stops_the_deploy_with_a_clear_message():
    with patch.object(cmd, "_register_skill_files", return_value=None):
        with pytest.raises(RuntimeError, match="电商售后应答"):
            cmd._add_aftersales_agents(_ctx([]), {"aftersales_agents": 1}, _B(), {}, ["fd1"], "店", "veh", [])
