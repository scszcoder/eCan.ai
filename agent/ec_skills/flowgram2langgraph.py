import json
from langgraph.graph import StateGraph, START, END
from agent.ec_skills.build_node import *
import importlib
# from agent.ec_skills.llm_utils.llm_utils import node_maker
from gui.LoginoutGUI import Login
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from app_context import AppContext
from agent.ec_skill import NodeState


# Simulated function registry to map node types to actual Python functions.
# You need to populate this in your real implementation
function_registry = {
    "llm": build_llm_node,
    "basic": build_mcp_tool_calling_node,
    "code": build_basic_node,
    "http-api": build_api_node,
    "loop": build_loop_node,
    "condition": build_condition_node,
    "tool": build_mcp_tool_calling_node,
    # "group": process_blocks,
    "default": build_debug_node,
}

def evaluate_condition_legacy(state, conditions):
    """Legacy evaluator: list of { value: {left/right/operator} }. Kept for backward compatibility."""
    for cond in conditions:
        value = cond["value"]
        left = extract_value(state, value["left"])
        right = extract_value(state, value["right"]) if "right" in value else None
        op = value["operator"]
        if not apply_operator(left, right, op):
            return False
    return True

def extract_value(state, operand):
    if operand["type"] == "constant":
        return operand["content"]
    elif operand["type"] == "ref":
        keys = operand["content"]
        val = state
        for key in keys:
            val = val.get(key, None)
            if val is None:
                break
        return val
    return None

def apply_operator(left, right, operator):
    if operator == "Equal":
        return left == right
    elif operator == "Not Equal":
        return left != right
    elif operator == "Is True":
        return bool(left) is True
    elif operator == "Is False":
        return bool(left) is False
    elif operator == "In":
        return left in right if isinstance(right, list) else False
    elif operator == "Not In":
        return left not in right if isinstance(right, list) else False
    elif operator == "Is Empty":
        return left in (None, "", [], {})
    elif operator == "Is Not Empty":
        return left not in (None, "", [], {})
    elif operator == "Larger Than":
        return float(left) > float(right)
    elif operator == "Smaller Than":
        return float(left) < float(right)
    elif operator == "Larger Or Equal Than":
        return float(left) >= float(right)
    elif operator == "Smaller Or Equal Than":
        return float(left) <= float(right)
    return False

def _safe_eval_expr(expr: str, state: dict) -> bool:
    """Evaluate a simple python expression with extremely limited context.
    Exposes 'state' and 'attributes' only. Returns False on error.
    """
    try:
        safe_globals = {"__builtins__": {}}
        safe_locals = {
            "state": state,
            "attributes": state.get("attributes", {}),
        }
        return bool(eval(expr, safe_globals, safe_locals))
    except Exception:
        return False


def _is_truthy_state_condition(value_obj: dict, state: dict) -> bool:
    """Support the simplified 'state.condition' mode, or fallback to left/is_true if provided."""
    # Preferred: explicit left/operator from UI
    left = None
    if isinstance(value_obj, dict) and "left" in value_obj:
        left = extract_value(state, value_obj["left"])  # pragma: no cover - passthrough
        return bool(left) is True
    # Fallback to state.get('condition') or attributes.condition
    cond = state.get("condition")
    if cond is None:
        cond = state.get("attributes", {}).get("condition")
    return bool(cond) is True


def make_condition_selector(node_id: str, node_data: dict, port_map: dict):
    """Build a selector for new condition model: conditions list with keys if_*/elif_*/else_*.
    Returns a function(state) -> selected_port_id.
    """
    conditions = node_data.get("conditions", []) or []

    # Sort by if -> elif... -> else
    def _ctype(k: str) -> int:
        if k.startswith("if_"): return 0
        if k.startswith("elif_"): return 1
        if k.startswith("else_"): return 2
        return 1

    ordered = sorted(conditions, key=lambda c: _ctype(c.get("key", "")))

    def selector(state: dict):
        # Evaluate IF/ELIF; default to ELSE if present; otherwise None
        for cond in ordered:
            key = cond.get("key", "")
            val = cond.get("value")
            if key.startswith("else_"):
                # Only choose else if no prior branch matched; we continue loop and pick later if nothing matched
                continue
            # New formats:
            # - { mode: 'state.condition', left:{...}, operator:'is_true' } or similar
            # - { mode: 'custom', expr: '...' }
            matched = False
            if isinstance(val, dict):
                mode = val.get("mode", "state.condition")
                if mode == "state.condition":
                    matched = _is_truthy_state_condition(val, state)
                elif mode == "custom":
                    expr = val.get("expr", "")
                    matched = _safe_eval_expr(expr, state) if expr else False
                else:
                    # Legacy fallback
                    try:
                        matched = evaluate_condition_legacy(state, [cond])
                    except Exception:
                        matched = False
            else:
                # Legacy structure or empty; default False
                matched = False

            if matched:
                # Return the port id that matches this condition key
                if key in port_map:
                    return key
                # Some diagrams might use sourcePortID equal to the key; fall back to first mapping
                return list(port_map.keys())[0] if port_map else None

        # No IF/ELIF matched: pick ELSE if present
        else_key = next((c.get("key") for c in ordered if str(c.get("key", "")).startswith("else_")), None)
        if else_key and else_key in port_map:
            return else_key
        # Fallback: second mapping or first available
        keys = list(port_map.keys())
        if len(keys) > 1:
            return keys[1]
        return keys[0] if keys else None

    selector.__name__ = node_id
    return selector

def process_blocks(workflow, blocks, node_map, id_to_node, skill_name, owner, bp_manager, edges_in_block):
    # Process all blocks (nodes) within the group/loop
    for block in blocks:
        block_id = block["id"]
        node_map[block_id] = block_id
        id_to_node[block_id] = block

        node_type = block.get("type", "code")
        node_data = block.get("data", {})

        # Get the appropriate builder function from the registry
        builder_func = function_registry.get(node_type, build_debug_node)

        # Call the builder function with the node's data to get the raw callable
        raw_callable = builder_func(node_data, block_id, skill_name, owner, bp_manager)

        # Wrap the raw callable with the node_builder to add retries, context, etc.
        node_callable = node_builder(raw_callable, block_id, skill_name, owner, bp_manager)

        # Add the constructed node to the workflow
        workflow.add_node(block_id, node_callable)

        if node_type in ["loop", "group"] and "blocks" in block:
            nested_edges = block.get("edges", [])
            process_blocks(workflow, block["blocks"], node_map, id_to_node, skill_name, owner, bp_manager, nested_edges)

    # Process all edges within the group/loop
    for edge in edges_in_block:
        source_id = edge["sourceNodeID"]
        target_id = edge["targetNodeID"]

        # Ensure both source and target nodes are in the map
        if source_id in node_map and target_id in node_map:
            source = node_map[source_id]
            target = node_map[target_id]

            if target == "end":
                workflow.add_edge(source, END)
            else:
                workflow.add_edge(source, target)
        else:
            logger.warning(f"Edge source or target not found in node_map: {source_id} -> {target_id}")

def flowgram2langgraph(flowgram_json):
    try:
        flow = json.loads(flowgram_json) if isinstance(flowgram_json, str) else flowgram_json
        workflow = StateGraph(NodeState)
        node_map = {}
        id_to_node = {}
        breakpoints = []
        print("flowgram2langgraph", type(flowgram_json), flowgram_json)
        skill_name = flowgram_json["skillName"]
        owner = flow.get("owner", "")
        # find breakpoint manager of the dev task, since it will always be that.
        login: Login = AppContext.login
        tester_agent = next((ag for ag in login.main_win.agents if "test" in ag.card.name.lower()), None)
        bp_manager = tester_agent.runner.bp_manager

        # Find the actual entry point node ID
        start_node_id = None
        entry_point_node_id = None
        for node in flow.get("workFlow", {}).get("nodes", []):
            if node.get("type") == "start":
                start_node_id = node["id"]
                break

        if start_node_id:
            for edge in flow.get("workFlow", {}).get("edges", []):
                if edge.get("sourceNodeID") == start_node_id:
                    entry_point_node_id = edge.get("targetNodeID")
                    break

        if not entry_point_node_id:
            raise ValueError("Could not determine the entry point from the start node.")

        for node in flow.get("workFlow", {}).get("nodes", []):
            node_id = node["id"]
            node_type = node.get("type", "basic")

            # Skip the visual 'start' and 'end' nodes, as they aren't executable parts of the graph
            if node_type in ["start", "end"]:
                continue

            node_data = node.get("data", {})

            if node_data.get("break_point") is True:
                breakpoints.append(node_id)

            node_map[node_id] = node_id
            id_to_node[node_id] = node

            # Get the appropriate builder function from the registry
            print("node_type:", node_type)
            builder_func = function_registry.get(node_type, build_debug_node)
            print("builder_func:", builder_func)

            # Call the builder function with the node's data to get the raw callable
            raw_callable = builder_func(node_data, node_id, skill_name, owner, bp_manager)

            # Wrap the raw callable with the node_builder to add retries, context, etc.
            node_callable = node_builder(raw_callable, node_id, skill_name, owner, bp_manager)

            # Add the constructed node to the workflow
            workflow.add_node(node_id, node_callable)

            if node_type in ["loop", "group"] and "blocks" in node:
                edges_in_block = node.get("edges", [])
                process_blocks(workflow, node["blocks"], node_map, id_to_node, skill_name, owner, bp_manager, edges_in_block)
        
        # Set the entry point after all nodes have been added
        workflow.set_entry_point(entry_point_node_id)

        # Add edges
        for edge in flow.get("workFlow", {}).get("edges", []):
            source_id = edge.get("sourceNodeID")
            target_id = edge.get("targetNodeID")

            # Skip edges originating from the start node as it's already handled by set_entry_point
            if source_id == start_node_id:
                continue

            source_node = node_map.get(source_id)
            if not source_node:
                logger.warning(f"Edge source node not found in map: {source_id}")
                continue

            # If the target is the special 'end' node, link to LangGraph's END
            if target_id == "end":
                workflow.add_edge(source_node, END)
            else:
                # Otherwise, it's a regular edge between two nodes
                target_node = node_map.get(target_id)
                if not target_node:
                    logger.warning(f"Edge target node not found in map: {target_id}")
                    continue
                workflow.add_edge(source_node, target_node)

        # Add conditional edges (supporting new Condition model)
        for node in flow.get("workFlow", {}).get("nodes", []):
            if node["type"] == "condition":
                node_id = node["id"]
                outgoing_edges = [e for e in flow.get("workFlow", {}).get("edges", []) if e["sourceNodeID"] == node_id]
                port_map = {}
                for edge in outgoing_edges:
                    port = edge.get("sourcePortID") # In Flowgram, the handle on the source node is the port
                    if port:
                        port_map[port] = edge["targetNodeID"]
                selector = make_condition_selector(node_id, node.get("data", {}), port_map)
                workflow.add_conditional_edges(node_id, selector, path_map=port_map)
    except Exception as e:
        err_msg = get_traceback(e, "ErrorFlowgram2Langgraph")
        logger.error(f"{err_msg}")
        workflow = {}
        breakpoints = []
    return workflow, breakpoints

def flatten_blocks(blocks):
    """Recursively flatten blocks for edge mapping."""
    flat = []
    for block in blocks:
        flat.append(block)
        if block["type"] in ["group", "loop"] and "blocks" in block:
            flat += flatten_blocks(block["blocks"])
    return flat


def debug_condition_function(state):
    return "if_0"  # just always select first condition for testing
