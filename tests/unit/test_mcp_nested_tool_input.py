"""A tool input that backfill wrapped as {'input': {empty defaults}, field: value} keeps the
LLM's values, for a single tool call and for each call of a multi-tool list alike."""
from agent.ec_skills.build_node import _merge_nested_tool_input


def test_top_level_values_win_over_empty_nested_defaults():
    ti = {"input": {"op": "", "collection": "", "key": ""},
          "op": "get", "collection": "owner_settings", "key": "s1"}
    assert _merge_nested_tool_input(ti) == {"input": {"op": "get", "collection": "owner_settings", "key": "s1"}}


def test_nested_values_stay_when_top_level_is_empty():
    ti = {"input": {"path": "C:/r", "recursive": True}, "path": ""}
    assert _merge_nested_tool_input(ti) == {"input": {"path": "C:/r", "recursive": True}}


def test_input_without_a_wrapper_is_unchanged():
    ti = {"op": "get"}
    assert _merge_nested_tool_input(ti) is ti
