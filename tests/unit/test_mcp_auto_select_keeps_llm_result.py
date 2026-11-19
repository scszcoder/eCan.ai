"""An LLM node's own {next_tool_name, ...} result must survive the MCP auto-select node.

The browser-handoff fallback (adopt an upstream browser node's text as the message)
used to fire on it too, replacing the whole result with the browser's {'all_done': True}:
the LLM's tool picks never ran and the loop's pass_count/done flags were wiped."""
from unittest.mock import patch

from agent.ec_skills import build_node as bn


def _mcp_node():
    with patch.object(bn, "node_builder", lambda fn, *a, **k: fn):
        return bn.build_mcp_tool_calling_node(
            {"callable": {"id": "llm-auto-select"}}, "mcp_drafting_tools", "skill", "me", None)


def _state(llm_result):
    return {
        "result": {"llm_result": llm_result},
        "tool_result": {"browser_check": {"final": '{"all_done": true, "aborted": true}'}},
        "attributes": {}, "messages": [],
    }


def test_final_pass_keeps_the_llm_fields():
    state = _mcp_node()(_state({"pass_count": 7, "next_tool_name": "", "next_tool_input": {},
                                "drafting_done": True, "status": "done"}))
    lr = state["result"]["llm_result"]
    assert lr["pass_count"] == 7 and lr["drafting_done"] is True and lr["status"] == "done"


def test_browser_only_result_still_adopts_the_browser_text():
    state = _mcp_node()(_state({"all_done": False, "work_done": False}))
    # The browser's flags were parsed out of its text, as before.
    assert state["result"]["llm_result"]["all_done"] is True


def test_run_local_tool_runs_directly_on_the_desktop(tmp_path):
    """run_local means "send it to the desktop" from a cloud worker; on the desktop
    itself there is no transport to send it over, so it must just call the tool."""
    (tmp_path / "grill.jpg").write_bytes(b"x")
    with patch.object(bn, "node_builder", lambda fn, *a, **k: fn):
        node = bn.build_mcp_tool_calling_node(
            {"callable": {"id": "llm-auto-select"}, "data": {"run_local": True}},
            "mcp_drafting_tools", "skill", "me", None)
    with patch.object(bn, "_is_cloud_mode", return_value=False):
        state = node(_state({"pass_count": 1, "next_tool_name": "find_files",
                             "next_tool_input": {"path": str(tmp_path)}}))
    assert "grill.jpg" in str(state["tool_result"])
