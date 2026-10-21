"""An MCP node must record its output under state["tool_result"][node_name].

tool_result is keyed by node name (LLM promotion, media-gen, loop/route
conditions read tool_result[<node>][field]). The MCP node assigned the raw
CallToolResult to the whole key, wiping every other entry: a looping skill's
router then failed ("'CallToolResult' object is not subscriptable") after its
first tool call and the run fell off the end, posting the LLM's tool request
to the user as raw JSON.
"""
from types import SimpleNamespace

from agent.ec_skills import build_node as bn


def _state():
    return {
        "input": "create an image similar to c:\\tmp\\perfum0.png",
        "attributes": {}, "history": [], "messages": ["agent_x", "chat-1"],
        "result": {"llm_result": {"all_done": False, "tool_name": "find_files"}},
        "tool_result": {"llm_reqCollector": {"all_done": False, "tool_name": "find_files"}},
    }


def test_mcp_output_is_stored_under_its_node():
    # Off the desktop the node calls the real tool handler in-process; with no
    # path it returns its own "path is required" result, which is all we need.
    node = bn.build_mcp_tool_calling_node(
        {"tool_name": "find_files", "inputsValues": {}}, "mcp_reqTools", "skill_t", "owner_t", None)
    st = node(_state(), runtime=SimpleNamespace(context={}), store=None)

    tr = st["tool_result"]
    assert isinstance(tr, dict)
    # the LLM node's entry survives, so tool_result["llm_reqCollector"][...] still works
    assert tr["llm_reqCollector"]["tool_name"] == "find_files"
    entry = tr["mcp_reqTools"]
    assert entry["tool_name"] == "find_files"
    assert isinstance(entry["text"], str) and entry["text"]
    assert isinstance(entry["data"], dict)          # JSON-shaped, checkpoint-safe
