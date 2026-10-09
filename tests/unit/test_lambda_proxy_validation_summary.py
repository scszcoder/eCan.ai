"""A schema miss from the llm-proxy must reach the model as a readable reason.

2026-10-09: the model called search_page with {"query"} instead of {"pattern"};
the raw text was returned, browser-use failed on `.action`, and the model saw
only "'str' object has no attribute 'action'" six times in a row.
"""
import json

import pytest
from browser_use.agent.views import AgentOutput
from browser_use.tools.service import Tools

from agent.ec_skills.browser_use_extension.lambda_proxy_llm import _summarize_validation_error


def _output_model():
    return AgentOutput.type_with_custom_actions(Tools().registry.create_action_model())


def _summary(action):
    text = json.dumps({"thinking": "", "evaluation_previous_goal": "", "memory": "",
                       "next_goal": "", "action": [action]})
    with pytest.raises(Exception) as exc:
        _output_model().model_validate_json(text)
    return _summarize_validation_error(exc.value, text)


def test_wrong_argument_name_names_the_fields():
    msg = _summary({"search_page": {"query": "PIC10"}})
    assert "search_page.pattern: Field required" in msg
    assert "click" not in msg  # other actions' union noise is dropped


def test_unknown_action_is_named():
    msg = _summary({"no_such_action": {}})
    assert "unknown action(s): no_such_action" in msg


def test_missing_action_list_says_use_done():
    # 2026-10-09: the model put its round result at the top level, no action
    text = json.dumps({"thinking": "", "evaluation_previous_goal": "", "memory": "",
                       "next_goal": "", "all_done": False, "work_done": False, "summary": "x"})
    with pytest.raises(Exception) as exc:
        _output_model().model_validate_json(text)
    msg = _summarize_validation_error(exc.value, text)
    assert "action: Field required" in msg and "`done` action" in msg
