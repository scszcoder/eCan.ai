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
    # No dedicated builder for group; groups are expanded via process_blocks
    # Best-effort support for event/comment/variable/sheet-call
    "event": lambda data, node_id, skill_name, owner, bp_mgr: (lambda state, **kwargs: {}),
    "comment": lambda data, node_id, skill_name, owner, bp_mgr: (lambda state, **kwargs: {}),
    "variable": lambda data, node_id, skill_name, owner, bp_mgr: _build_variable_node(data),
    "sheet-call": lambda data, node_id, skill_name, owner, bp_mgr: (lambda state, **kwargs: {}),
    "default": build_debug_node,
}


def _build_variable_node(data: dict):
    """Return a callable that assigns variables to state.attributes/metadata/tool_input.
    Expected data shape (best-effort): {
      assignments: [ { target: 'attributes.x'|'metadata.y'|'tool_input.z', value: <any> }, ... ]
    }
    """
    assignments = (data or {}).get("assignments") or []
    def _node(state: dict, **kwargs) -> dict:
        try:
            for a in assignments:
                tgt = str(a.get("target", ""))
                val = a.get("value")
                root, _, path = tgt.partition(".")
                if not root or not path:
                    continue
                container = state.setdefault(root, {}) if isinstance(state.get(root), dict) else state.setdefault(root, {})
                # Drill down
                parts = [p for p in path.split(".") if p]
                cur = container
                for p in parts[:-1]:
                    if not isinstance(cur.get(p), dict):
                        cur[p] = {}
                    cur = cur[p]
                cur[parts[-1]] = val
        except Exception:
            pass
        return {}
    return _node

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
        # Sanitize block id as well (blocks might inherit ids that include colons)
        sanitized_block_id = str(block_id).replace(":", "__")
        node_map[block_id] = sanitized_block_id
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
        workflow.add_node(sanitized_block_id, node_callable)

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

def flowgram2langgraph(flowgram_json, bundle_json=None):
    try:
        flow = json.loads(flowgram_json) if isinstance(flowgram_json, str) else flowgram_json
        # Optionally attach bundle (multi-sheet)
        if bundle_json is not None:
            flow["bundle"] = bundle_json

        # Prepare global workflow
        workflow = StateGraph(NodeState)
        node_map = {}          # global_id -> global_id
        id_to_node = {}        # global_id -> node json (with sheet info)
        per_sheet_entry = {}   # sheet_key -> entry global node id
        breakpoints = []

        # Debug marker to ensure the latest code is running
        print("flowgram2langgraph[v_sanitize_colon_1]", type(flowgram_json))
        skill_name = flow.get("skillName", "")
        owner = flow.get("owner", "")
        # breakpoint manager (dev/test path)
        login: Login = AppContext.login
        tester_agent = next((ag for ag in login.main_win.agents if "test" in ag.card.name.lower()), None)
        bp_manager = tester_agent.runner.bp_manager if tester_agent else None

        # Collect sheets: from flow.bundle.sheets, or single workFlow as one sheet
        sheets = []
        # Preferred: bundle
        try:
            b = flow.get("bundle") or {}
            if isinstance(b, dict) and isinstance(b.get("sheets"), list):
                for s in b["sheets"]:
                    name = s.get("name") or s.get("id") or f"sheet_{len(sheets)}"
                    doc = s.get("document") or {}
                    wf = doc if (isinstance(doc, dict) and "nodes" in doc and "edges" in doc) else None
                    if wf:
                        sheets.append({"name": str(name), "workFlow": wf})
        except Exception:
            pass
        # Fallback: single sheet
        if not sheets:
            sheets.append({"name": flow.get("sheetName", "main"), "workFlow": flow.get("workFlow", {})})

        # Determine main sheet: first one
        main_sheet_name = sheets[0]["name"] if sheets else "main"

        # Helper to compute entry for a sheet
        def _find_entry(wf: dict):
            start_id = None
            entry_id = None
            for n in wf.get("nodes", []):
                if n.get("type") == "start":
                    start_id = n.get("id")
                    break
            if start_id:
                for e in wf.get("edges", []):
                    if e.get("sourceNodeID") == start_id:
                        entry_id = e.get("targetNodeID")
                        break
            return entry_id

        # First pass: add nodes from all sheets (prefix global ids)
        for sheet in sheets:
            sname = str(sheet.get("name") or "sheet")
            wf = sheet.get("workFlow", {})
            entry_local = _find_entry(wf)
            # Register nodes
            for node in wf.get("nodes", []):
                node_id = node.get("id")
                node_type = node.get("type", "basic")
                if node_type in ("start", "end"):
                    continue
                node_data = node.get("data", {})
                if node_data.get("break_point") is True:
                    breakpoints.append(f"{sname}:{node_id}")

                global_id = f"{sname}:{node_id}"
                # LangGraph forbids ':' in node names; sanitize for workflow usage
                sanitized_id = global_id.replace(":", "__")
                node_map[global_id] = sanitized_id
                id_to_node[global_id] = {"sheet": sname, "node": node}

                # Builder
                builder_func = function_registry.get(node_type, build_debug_node)
                raw_callable = builder_func(node_data, global_id, skill_name, owner, bp_manager)
                node_callable = node_builder(raw_callable, global_id, skill_name, owner, bp_manager)
                # Debug to verify sanitized ids are used
                if ":" in sanitized_id:
                    print("[WARN] unsanitized id detected:", global_id, "->", sanitized_id)
                workflow.add_node(sanitized_id, node_callable)

            # Record per-sheet entry (global id)
            if entry_local:
                per_sheet_entry[sname] = f"{sname}:{entry_local}"

        # Set entry point to main sheet's entry
        main_entry = per_sheet_entry.get(main_sheet_name)
        if not main_entry:
            raise ValueError("Could not determine the entry point from the start node of the main sheet.")
        # Map to sanitized id if present
        entry_sanitized = node_map.get(main_entry, main_entry)
        workflow.set_entry_point(entry_sanitized)

        # Second pass: add edges across all sheets
        for sheet in sheets:
            sname = str(sheet.get("name") or "sheet")
            wf = sheet.get("workFlow", {})
            # Identify local start id to skip that outgoing edge
            local_start = None
            for n in wf.get("nodes", []):
                if n.get("type") == "start":
                    local_start = n.get("id")
                    break
            for edge in wf.get("edges", []):
                source_id = edge.get("sourceNodeID")
                target_id = edge.get("targetNodeID")
                if source_id == local_start:
                    # skip, handled via per-sheet entry
                    continue
                source_global = f"{sname}:{source_id}"
                target_global = f"{sname}:{target_id}" if target_id != "end" else "end"
                if source_global not in node_map:
                    logger.warning(f"Edge source node not found in map: {source_global}")
                    continue
                if target_global == "end":
                    workflow.add_edge(node_map[source_global], END)
                    continue
                if target_global not in node_map:
                    logger.warning(f"Edge target node not found in map: {target_global}")
                    continue
                workflow.add_edge(node_map[source_global], node_map[target_global])

        # Conditional edges (by sheet)
        for sheet in sheets:
            sname = str(sheet.get("name") or "sheet")
            wf = sheet.get("workFlow", {})
            for node in wf.get("nodes", []):
                if node.get("type") == "condition":
                    node_id = node.get("id")
                    gid_global = f"{sname}:{node_id}"
                    gid = node_map.get(gid_global)
                    if not gid:
                        logger.warning(f"Condition node not found in map: {gid_global}")
                        continue
                    outgoing_edges = [e for e in wf.get("edges", []) if e.get("sourceNodeID") == node_id]
                    port_map = {}
                    for e in outgoing_edges:
                        port = e.get("sourcePortID")
                        if port:
                            tgt = e.get("targetNodeID")
                            tgt_gid = f"{sname}:{tgt}"
                            if tgt_gid in node_map:
                                port_map[port] = node_map[tgt_gid]
                            else:
                                logger.warning(f"Conditional edge target not found in map: {tgt_gid}")
                    # Build selector with sanitized id and a port_map that points to sanitized ids
                    selector = make_condition_selector(gid, node.get("data", {}), port_map)
                    workflow.add_conditional_edges(gid, selector, path_map=port_map)

        # Expand in-node groups
        for sheet in sheets:
            sname = str(sheet.get("name") or "sheet")
            wf = sheet.get("workFlow", {})
            for node in wf.get("nodes", []):
                if node.get("type") in ["loop", "group"] and "blocks" in node:
                    edges_in_block = node.get("edges", [])
                    process_blocks(workflow, node["blocks"], node_map, id_to_node, skill_name, owner, bp_manager, edges_in_block)

        # Treat sheet-call as a jump to target sheet entry (best-effort)
        for sheet in sheets:
            sname = str(sheet.get("name") or "sheet")
            wf = sheet.get("workFlow", {})
            for node in wf.get("nodes", []):
                if node.get("type") == "sheet-call":
                    data = node.get("data", {})
                    target_sheet = data.get("target_sheet") or data.get("targetSheet") or data.get("sheet") or data.get("name")
                    if target_sheet and target_sheet in per_sheet_entry:
                        src_gid_global = f"{sname}:{node.get('id')}"
                        dst_gid_global = per_sheet_entry[target_sheet]
                        src_gid = node_map.get(src_gid_global)
                        dst_gid = node_map.get(dst_gid_global)
                        if not src_gid or not dst_gid:
                            logger.warning(f"Failed to resolve sheet-call ids: {src_gid_global} -> {dst_gid_global}")
                            continue
                        try:
                            workflow.add_edge(src_gid, dst_gid)
                        except Exception:
                            logger.warning(f"Failed to add sheet-call edge: {src_gid} -> {dst_gid}")

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
