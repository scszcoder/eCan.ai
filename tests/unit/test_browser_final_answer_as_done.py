"""A browser model that ignores the action schema and replies with the task's own answer
JSON is taken as `done` with that answer, instead of failing the step (6 in a row = node fails)."""
import asyncio

import pytest
from pydantic import ValidationError
from browser_use.agent.views import AgentOutput
from browser_use.tools.service import Tools

from agent.ec_skills.browser_node.runner import _final_answer_as_done, _trace_llm_calls

FMT = AgentOutput.type_with_custom_actions(Tools().registry.create_action_model())
ANSWER = '{"all_done": true, "aborted": false, "session_ok": true, "page_title": "Seller Hub"}'


def test_bare_answer_becomes_done_with_the_answer_as_text():
    out = _final_answer_as_done(FMT).model_validate_json(ANSWER)
    assert isinstance(out, FMT)
    assert out.action[0].model_dump(exclude_none=True)["done"]["text"] == ANSWER


def test_proper_replies_and_junk_are_unchanged():
    ok = '{"action": [{"navigate": {"url": "https://www.ebay.com"}}]}'
    assert "navigate" in _final_answer_as_done(FMT).model_validate_json(ok).action[0].model_dump(exclude_none=True)
    for bad in ('not json', '[1, 2]', '{"action": "x"}'):
        with pytest.raises(ValidationError):
            _final_answer_as_done(FMT).model_validate_json(bad)


def test_the_traced_browser_llm_uses_it():
    class FakeLLM:
        async def ainvoke(self, messages, output_format=None, **kw):
            return output_format.model_validate_json(ANSWER)

    llm = _trace_llm_calls(FakeLLM(), "ecanai", "m")
    out = asyncio.run(llm.ainvoke([], output_format=FMT))
    assert "done" in out.action[0].model_dump(exclude_none=True)
    # browser-use's token tracker sits outside and passes output_format positionally.
    out = asyncio.run(llm.ainvoke([], FMT))
    assert "done" in out.action[0].model_dump(exclude_none=True)


def test_a_bare_action_runs_as_that_action_not_as_the_final_answer():
    # 2026-11-18: a model replied just {"wait": {"seconds": 8}} mid-check; taken as "done",
    # the store report became that text and said the check did not complete.
    out = _final_answer_as_done(FMT).model_validate_json('{"wait": {"seconds": 8}}')
    act = out.action[0].model_dump(exclude_none=True)
    assert "wait" in act and "done" not in act
