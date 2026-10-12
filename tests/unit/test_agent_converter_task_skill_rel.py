"""A task whose name doesn't match its skill still gets the skill its
task-skill relation names (千牛 front desk 天猫客服前台001 -> 淘宝客服前台01,
customer log 2026-10-12: SKILL_MISSING, buyer messages dispatched to 0 runners)."""
from types import SimpleNamespace

from agent.agent_converter import _bind_task_skills_from_db


class _Tasks:
    def __init__(self, rels):
        self.rels = rels

    def get_task_skills(self, task_id, role=None):
        return {"success": True, "data": [{"skill_id": s} for s in self.rels.get(task_id, [])]}


def _mw(rels):
    return SimpleNamespace(ec_db_mgr=SimpleNamespace(task_service=_Tasks(rels)))


def test_unbound_task_gets_its_related_skill():
    skill = SimpleNamespace(id="skill_e92218", name="淘宝客服前台01", runnable=object())
    other = SimpleNamespace(id="skill_x", name="天猫客服前台", runnable=object())
    task = SimpleNamespace(id="task_ac58", name="天猫客服前台001", skill=None)
    _bind_task_skills_from_db(_mw({"task_ac58": ["skill_e92218"]}), [task], [skill], [other])
    assert task.skill is skill


def test_bound_task_and_unrunnable_skill_are_left_alone():
    kept = SimpleNamespace(id="skill_a", name="a", runnable=object())
    stub = SimpleNamespace(id="skill_b", name="b", runnable=None)
    bound = SimpleNamespace(id="t1", name="t1", skill=kept)
    unbound = SimpleNamespace(id="t2", name="t2", skill=None)
    _bind_task_skills_from_db(_mw({"t1": ["skill_b"], "t2": ["skill_b"]}), [bound, unbound], [stub], [])
    assert bound.skill is kept
    assert unbound.skill is None
