"""A task loaded before skills compile arrives unbound. Its DB skill rel must
win over the name heuristics, which pick 'chip_docs_crawl_manager_00' for task
'chip_docs_crawl_1' (3 shared words vs 2 with its own 'chip_docs_crawler_00')."""
from types import SimpleNamespace

from agent.agent_converter import _attach_skills_and_triggers, _bind_skills_from_task_rels

CRAWLER = SimpleNamespace(id="skill_crawler", name="chip_docs_crawler_00", runnable=object())
MANAGER = SimpleNamespace(id="skill_manager", name="chip_docs_crawl_manager_00", runnable=object())


class FakeTaskService:
    def __init__(self, rels):
        self.rels = rels

    def get_task_skills(self, task_id, role=None):
        sid = self.rels.get(task_id)
        return {"success": True, "data": [{"skill_id": sid}] if sid else []}


def _task(tid, name):
    return SimpleNamespace(id=tid, name=name, skill=None, trigger=["message"])


def _mainwin(rels):
    return SimpleNamespace(ec_db_mgr=SimpleNamespace(task_service=FakeTaskService(rels)))


def _bind(tasks, rels):
    _bind_skills_from_task_rels(tasks, [CRAWLER, MANAGER], _mainwin(rels))
    _attach_skills_and_triggers(tasks, [], [CRAWLER, MANAGER])


def test_name_heuristic_alone_picks_the_wrong_skill():
    t = _task("t1", "chip_docs_crawl_1")
    _attach_skills_and_triggers([t], [], [CRAWLER, MANAGER])
    assert t.skill is MANAGER  # the bug this guards against


def test_skill_rel_binds_the_worker_to_its_own_skill():
    w, c = _task("t1", "chip_docs_crawl_1"), _task("t2", "chip_docs_coordinate")
    _bind([w, c], {"t1": "skill_crawler", "t2": "skill_manager"})
    assert w.skill is CRAWLER and c.skill is MANAGER


def test_no_rel_falls_back_to_the_heuristics():
    t = _task("t1", "chip_docs_crawl_1")
    _bind([t], {})
    assert t.skill is MANAGER


def test_an_already_runnable_skill_is_kept():
    t = _task("t1", "chip_docs_crawl_1")
    t.skill = MANAGER
    _bind([t], {"t1": "skill_crawler"})
    assert t.skill is MANAGER


def test_missing_task_service_is_harmless():
    t = _task("t1", "chip_docs_crawl_1")
    _bind_skills_from_task_rels([t], [CRAWLER], SimpleNamespace())
    assert t.skill is None
