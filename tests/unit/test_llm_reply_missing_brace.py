"""A long nested LLM reply that drops its last closing brace is still read as JSON,
so a tool node downstream gets its arguments instead of an empty input."""
import json

from agent.ec_skills.llm_hooks.llm_hooks import standard_post_llm_func


def _reply(obj, drop=0):
    text = json.dumps(obj, ensure_ascii=False)
    return text[:len(text) - drop] if drop else text


SAVE_CALL = {"run_complete": True, "next_tool_name": "save_store_report",
             "next_tool_input": {"store_id": "s1", "kind": "listing_draft", "complete": True,
                                 "report_md": "the box's plates are dishwasher-safe",
                                 "chat_brief": {"models_drafted": 1}}}


def test_reply_missing_its_last_brace_is_repaired():
    out = standard_post_llm_func("a", "n", {}, _reply(SAVE_CALL, drop=1))["llm_result"]
    assert out["next_tool_input"]["store_id"] == "s1"
    assert out["next_tool_input"]["report_md"] == "the box's plates are dishwasher-safe"


def test_reply_with_stray_closers_after_it_is_repaired():
    out = standard_post_llm_func("a", "n", {}, _reply(SAVE_CALL) + '"}')["llm_result"]
    assert out == SAVE_CALL


def test_reply_with_an_escaped_apostrophe_is_repaired():
    # JSON has no \' escape; a model quoting an error message wrote one.
    text = _reply(SAVE_CALL).replace("box's", "box\\'s")
    out = standard_post_llm_func("a", "n", {}, text)["llm_result"]
    assert out == SAVE_CALL


def test_escaped_apostrophe_and_missing_brace_are_both_repaired():
    text = _reply(SAVE_CALL, drop=1).replace("box's", "box\\'s")
    out = standard_post_llm_func("a", "n", {}, text)["llm_result"]
    assert out == SAVE_CALL


def test_a_reply_no_repair_can_read_is_reported_for_a_retry():
    from agent.ec_skills.llm_hooks.llm_hooks import json_reply_error
    # The report's model list is never closed (seen on a 6 KB market-research reply).
    broken = '{"next_tool_input": {"report": {"models": [{"id": 1}, "notes": ["x"]}, "report_md": "# r"}}'
    assert json_reply_error(broken)
    assert json_reply_error(_reply(SAVE_CALL)) is None
    assert json_reply_error(_reply(SAVE_CALL, drop=1)) is None  # repaired, no retry
    assert json_reply_error("Plain text answer.") is None


def test_complete_reply_is_unchanged():
    assert standard_post_llm_func("a", "n", {}, _reply(SAVE_CALL))["llm_result"] == SAVE_CALL


def test_text_reply_still_becomes_a_message():
    assert standard_post_llm_func("a", "n", {}, "{not json}")["llm_result"] == {"message": "{not json}"}
