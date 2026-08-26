"""DB NULL description must not break DB→object conversion (v0.9.95r).

A task/skill row with description=NULL arrives as an existing None key, so
``.get('description', '')`` returns None — pydantic then rejects the str
field, and the converter fell back to a ghost stub (fresh uuid, no
trigger/skill) that showed up as a gray duplicate task on the Tasks page.
"""

from unittest.mock import patch

import agent.ec_tasks  # noqa: F401  (import-order guard)
from agent.agent_converter import _convert_dict_to_task, _convert_dict_to_skill


class TestNullDescription:
    def test_task_with_null_description_converts_cleanly(self):
        task = _convert_dict_to_task({
            "id": "task_x", "name": "飞鸽客服应答001", "description": None,
            "trigger": "auto", "source": "fast_deploy",
        })
        assert task.id == "task_x"          # NOT a fallback uuid stub
        assert task.description == ""
        assert task.trigger                  # trigger survived

    def test_skill_with_null_description_converts_cleanly(self):
        skill = _convert_dict_to_skill({
            "id": "skill_x", "name": "飞鸽客服问答00", "description": None,
        })
        assert skill.name == "飞鸽客服问答00"
        assert skill.description == ""
