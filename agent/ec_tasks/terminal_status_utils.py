"""Shared helpers for deriving task/node terminal statuses."""

from __future__ import annotations

from typing import Any


def task_is_blocked(cp_values: Any) -> bool:
    """Determine if the completed task reached a blocked terminal state.

    Unlike ``contains_blocked_status`` (which scans everything), this function
    only examines the task-level result and the final tool_result entries — NOT
    intermediate history, messages, or agent logs.  This prevents a node that
    internally handled a transient block (e.g. risk-control on one platform)
    from incorrectly flagging the *entire* task as blocked.

    Returns True only when:
    - state["result"]["status"] == "blocked", OR
    - state["tool_result"][<last_node>]["status"] == "blocked"  (top-level only)
    """
    if not isinstance(cp_values, dict):
        return False

    # 1. Direct task result
    result = cp_values.get("result")
    if isinstance(result, dict):
        if str(result.get("status") or "").lower() == "blocked":
            return True

    # 2. Most-recent node's tool_result entry (top-level status only)
    tool_result = cp_values.get("tool_result")
    if isinstance(tool_result, dict) and tool_result:
        # Check nodes in reverse insertion order (most recent last in Py3.7+)
        for node_output in reversed(list(tool_result.values())):
            if isinstance(node_output, dict):
                if str(node_output.get("status") or "").lower() == "blocked":
                    return True
            # Only inspect the most-recent entry
            break

    # 3. Plain-text blocked marker in state["result"] text fields (top-level)
    if isinstance(result, dict):
        for key in ("final", "text", "content", "extracted_content"):
            v = result.get(key)
            if isinstance(v, str) and "blocked(reason=" in v.lower():
                return True

    return False
