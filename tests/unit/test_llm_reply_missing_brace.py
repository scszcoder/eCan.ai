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


def test_complete_reply_is_unchanged():
    assert standard_post_llm_func("a", "n", {}, _reply(SAVE_CALL))["llm_result"] == SAVE_CALL


def test_text_reply_still_becomes_a_message():
    assert standard_post_llm_func("a", "n", {}, "{not json}")["llm_result"] == {"message": "{not json}"}
