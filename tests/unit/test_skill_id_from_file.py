"""A diagram skill loaded from its folder keeps the skillId from its file.

2026-10-09 (fresh platoon machine, skills only on disk): the loaded skill got a
random id, task->skill binding by id failed, and the name heuristics bound the
crawler task chip_docs_crawl_1 to chip_docs_crawl_manager_00.
"""
from pathlib import Path
from unittest.mock import MagicMock

from agent.ec_skills.build_agent_skills import _create_skill_from_workflow


def _wf():
    wf = MagicMock()
    wf.compile.return_value = object()
    return wf


def test_ui_skill_takes_skill_id_from_file():
    sk = _create_skill_from_workflow(
        {"skillName": "chip_docs_crawler_00", "skillId": "skill_dec3beb141d74d71"},
        _wf(), "chip_docs_crawler_00", Path("x.json"), source="ui")
    assert sk.id == "skill_dec3beb141d74d71"


def test_ui_skill_without_skill_id_keeps_default():
    sk = _create_skill_from_workflow({"skillName": "s"}, _wf(), "s", Path("x.json"), source="ui")
    assert sk.id and sk.id != ""
