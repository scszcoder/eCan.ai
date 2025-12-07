import json
from langgraph.graph import StateGraph, START, END
from agent.ec_skills.dev_defs import BreakpointManager
from agent.ec_skills.build_node import *
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from agent.ec_skill import NodeState


# Simulated function registry to map node types to actual Python functions.
# You need to populate this in your real implementation
def _default_noop_builder(data, node_id, skill_name, owner, bp_mgr):
    def _noop(state: dict, **kwargs):
        return state
    return _noop

function_registry = {
    "llm": build_llm_node,
    # Basic/code nodes
    "basic": build_basic_node,
    "code": build_basic_node,
    # HTTP/API
    "http": build_api_node,
    # Flow control
    "loop": build_loop_node,
    "condition": build_condition_node,
    # MCP tools
    "mcp": build_mcp_tool_calling_node,
    # Backward-compat alias
    "tool": build_mcp_tool_calling_node,
    # UX/structural/non-exec nodes -> debug no-ops
    "event": lambda data, node_id, skill_name, owner, bp_mgr: (lambda state, **kwargs: {}),
    "comment": lambda data, node_id, skill_name, owner, bp_mgr: (lambda state, **kwargs: {}),
    "variable": lambda data, node_id, skill_name, owner, bp_mgr: _build_variable_node(data),
    "sheet-call": lambda data, node_id, skill_name, owner, bp_mgr: (lambda state, **kwargs: {}),
    # Newly added concrete builders
    "pend_event_node": build_pend_event_node,
    # Back-compat alias for common typo
    "chat_node": build_chat_node,
    "rag_node": build_rag_node,
    # Back-compat alias for old rag type
    "rag": build_rag_node,
    "browser-automation": build_browser_automation_node,
    # New organizational nodes
    "task": build_task_node,
    "tool-picker": build_tool_picker_node,
    # Dummy node is removed during preprocessing, no runtime builder needed
    "dummy": lambda data, node_id, skill_name, owner, bp_mgr: (lambda state, **kwargs: state),
    # Local default to avoid import-time NameError and double wrapping issues
    "default": _default_noop_builder,
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
        log_msg = f"🤖 Executing conditional edge: {expr}"
        # print(state['result']['llm_result']['request_to_work'])
        logger.debug(log_msg)
        web_gui.get_ipc_api().send_skill_editor_log("log", log_msg)

        safe_globals = {"__builtins__": {}}
        attrs = state.get("attributes", {}) if isinstance(state, dict) else {}
        # Merge attributes as bare names so flags like `data_ready` can be used
        safe_locals = {"state": state, "attributes": attrs}
        if isinstance(attrs, dict):
            for k, v in attrs.items():
                if isinstance(k, str) and k.isidentifier() and k not in safe_locals:
                    safe_locals[k] = v
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
    # Defensive copy so later mutations (e.g., graph wiring) don't change our view of available ports.
    # Keep an immutable snapshot we can recreate on every selector invocation.
    port_map = dict(port_map or {})
    frozen_port_items = tuple(port_map.items())
    logger.debug(f"[selector-debug] {node_id} frozen={frozen_port_items}")
    conditions = node_data.get("conditions", []) or []

    # Sort by if -> elif... -> else
    def _ctype(k: str) -> int:
        if k.startswith("if_"): return 0
        if k.startswith("elif_"): return 1
        if k.startswith("else_"): return 2
        return 1

    ordered = sorted(conditions, key=lambda c: _ctype(c.get("key", "")))
    logger.debug(f"[selector-debug] {node_id} port_map={port_map}")

    def _resolve_port_for_key(key: str, runtime_map: dict) -> str | None:
        """Resolve the correct port id for a given condition key when names differ.
        Prefer exact match; fallback by semantic prefix (if/elif/else) to common port ids like 'if_out'.
        """
        if key in runtime_map:
            return key
        k = str(key)
        ports = list(runtime_map.keys())
        logger.debug(f"[selector-debug] resolve key={key} keys={ports}")
        # Prefer explicit *_out forms if present
        if k.startswith("if_"):
            if "if_out" in runtime_map: return "if_out"
            # fallback to any port starting with 'if'
            for p in ports:
                if str(p).startswith("if"): return p
        if k.startswith("elif_"):
            if "elif_out" in runtime_map: return "elif_out"
            for p in ports:
                if str(p).startswith("elif"): return p
        if k.startswith("else_"):
            if "else_out" in runtime_map: return "else_out"
            for p in ports:
                if str(p).startswith("else"): return p
        # Last resort: first available
        return ports[0] if ports else None

    def selector(state: dict):
        # Evaluate IF/ELIF; default to ELSE if present; otherwise None
        runtime_map = dict(frozen_port_items)
        logger.debug(f"[selector-debug] {node_id} runtime keys={list(runtime_map.keys())}")
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
                # Resolve to appropriate port id even when key != sourcePortID
                chosen = _resolve_port_for_key(key, runtime_map)
                logger.debug(f"[selector-debug] {node_id} matched key={key}, chosen={chosen}")
                return chosen

        # No IF/ELIF matched: pick ELSE if present
        else_key = next((c.get("key") for c in ordered if str(c.get("key", "")).startswith("else_")), None)
        if else_key:
            rp = _resolve_port_for_key(else_key, runtime_map)
            if rp:
                logger.debug(f"[selector-debug] {node_id} taking else -> {rp}")
                return rp
        # Fallback: keep previous heuristic
        keys = list(runtime_map.keys())
        if len(keys) > 1:
            return keys[1]
        fallback = keys[0] if keys else None
        logger.debug(f"[selector-debug] {node_id} fallback -> {fallback}")
        return fallback

    selector.__name__ = node_id
    return selector

def process_blocks(workflow, blocks, node_map, id_to_node, skill_name, owner, bp_manager, edges_in_block, parent_gid: str = "", edges_debug: list | None = None, cond_edges_debug: list | None = None):
    # Process all blocks (nodes) within the group/loop
    for block in blocks:
        block_id = block["id"]
        # Sanitize block id as well (blocks might inherit ids that include colons)
        raw_ns = f"{parent_gid}:{block_id}" if parent_gid else str(block_id)
        sanitized_block_id = str(raw_ns).replace(":", "__")
        node_map[raw_ns] = sanitized_block_id
        id_to_node[raw_ns] = block

        node_type = block.get("type", "code")
        node_data = block.get("data", {})

        # Get the appropriate builder function from the registry
        builder_func = function_registry.get(node_type, _default_noop_builder)

        # Call the builder function with the node's data to get the raw callable
        raw_callable = builder_func(node_data, raw_ns, skill_name, owner, bp_manager)

        # Wrap the raw callable with the node_builder to add retries, context, etc.
        node_callable = node_builder(raw_callable, block_id, skill_name, owner, bp_manager)

        # Add the constructed node to the workflow
        workflow.add_node(sanitized_block_id, node_callable)

        if node_type in ["loop", "group"] and "blocks" in block:
            nested_edges = block.get("edges", [])
            process_blocks(workflow, block["blocks"], node_map, id_to_node, skill_name, owner, bp_manager, nested_edges, parent_gid=raw_ns, edges_debug=edges_debug, cond_edges_debug=cond_edges_debug)

    # Process all edges within the group/loop
    for edge in edges_in_block:
        source_id = edge["sourceNodeID"]
        target_id = edge["targetNodeID"]
        src_ns = f"{parent_gid}:{source_id}" if parent_gid else source_id
        tgt_ns = f"{parent_gid}:{target_id}" if parent_gid else target_id

        # Ensure both source and target nodes are in the map
        if src_ns in node_map and tgt_ns in node_map:
            source = node_map[src_ns]
            target = node_map[tgt_ns]

            if target == "end":
                workflow.add_edge(source, END)
                if isinstance(edges_debug, list):
                    edges_debug.append({"from": source, "to": str(END)})
            else:
                workflow.add_edge(source, target)
                if isinstance(edges_debug, list):
                    edges_debug.append({"from": source, "to": target})
        else:
            logger.warning(f"Edge source or target not found in node_map: {src_ns} -> {tgt_ns}")

    # Conditional edges within this block scope
    try:
        for block in blocks:
            if block.get("type") == "condition":
                node_id = block.get("id")
                gid_global = f"{parent_gid}:{node_id}" if parent_gid else node_id
                gid = node_map.get(gid_global)
                if not gid:
                    continue
                outgoing_edges = [e for e in edges_in_block if e.get("sourceNodeID") == node_id]
                port_map = {}
                for e in outgoing_edges:
                    port = e.get("sourcePortID")
                    if port:
                        tgt = e.get("targetNodeID")
                        tgt_gid_global = f"{parent_gid}:{tgt}" if parent_gid else tgt
                        if tgt == "end":
                            port_map[port] = END
                        elif tgt_gid_global in node_map:
                            port_map[port] = node_map[tgt_gid_global]
                selector = make_condition_selector(gid, block.get("data", {}), {k: (v if v == END else v) for k, v in port_map.items()})
                # LangGraph expects path_map with ids; END is supported
                workflow.add_conditional_edges(gid, selector, path_map=port_map)
                if isinstance(cond_edges_debug, list):
                    for ck, tgt in (port_map or {}).items():
                        cond_edges_debug.append({"from": gid, "condition": ck, "to": (str(END) if tgt == END else tgt)})
    except Exception as e:
        logger.debug(f"block conditional edges not fully captured: {e}")

def flowgram2langgraph(flow: dict, bundle_json: dict | None = None, bp_mgr: BreakpointManager | None = None):
    """
    Convert a flowgram-style JSON to an EC_Skill workflow and breakpoints list.
    """
    try:
        # Ensure flow is a dict and log
        if not isinstance(flow, dict):
            raise ValueError("flow must be a dict")
        logger.debug(f"flowgram raw: {flow}")
        # If bundle is provided by caller, attach for reference (v2 may already have preprocessed)
        if bundle_json is not None:
            flow["bundle"] = bundle_json

        # Resolve the working workflow schema (flat nodes/edges expected)
        wf = flow.get("workFlow") or {}
        if (not wf) and bundle_json and isinstance(bundle_json, dict):
            # Fallback: take the first sheet's document
            try:
                sheets = bundle_json.get("sheets") or []
                if sheets:
                    doc = sheets[0].get("document") or {}
                    if isinstance(doc, dict) and "nodes" in doc and "edges" in doc:
                        wf = doc
            except Exception:
                wf = {}

        nodes = (wf.get("nodes") or []) if isinstance(wf, dict) else []
        edges = (wf.get("edges") or []) if isinstance(wf, dict) else []

        # New fallback: some exports provide nodes/edges at the top-level (no workFlow)
        if (not nodes or not edges) and isinstance(flow.get("nodes"), list) and isinstance(flow.get("edges"), list):
            try:
                logger.debug("[flowgram2langgraph] using top-level nodes/edges fallback")
            except Exception:
                pass
            nodes = flow.get("nodes") or []
            edges = flow.get("edges") or []

        # Detect virtual start/end node IDs that may only exist in top-level flow['nodes']
        top_nodes = flow.get("nodes") or []
        start_ids = set()
        end_ids = set()
        try:
            # From workFlow.nodes
            for n in nodes:
                nid = str(n.get("id"))
                ntype = (n.get("type") or "")
                if ntype == "start" or nid.startswith("start"):
                    start_ids.add(nid)
                if ntype == "end" or nid.startswith("end"):
                    end_ids.add(nid)
            # From top-level nodes
            for n in top_nodes:
                nid = str(n.get("id"))
                ntype = (n.get("type") or "")
                if ntype == "start" or nid.startswith("start"):
                    start_ids.add(nid)
                if ntype == "end" or nid.startswith("end"):
                    end_ids.add(nid)
        except Exception:
            pass

        # Prepare LangGraph
        skill_name = str(flow.get("skillName") or flow.get("name") or "skill")
        owner = str(flow.get("owner") or flow.get("createdBy") or "")
        # Use provided BreakpointManager (if any); nodes will consult it at runtime
        # If None, breakpoint checks will be skipped in node_builder
        bp_mgr = bp_mgr

        workflow = StateGraph(NodeState)

        # Helper to sanitize node ids for LangGraph (avoid special chars like ':')
        def sid(x: str) -> str:
            try:
                return str(x).replace(":", "__")
            except Exception:
                return str(x)

        # Index nodes and types
        id_to_node = {}
        id_to_type = {}
        for n in nodes:
            try:
                nid = str(n.get("id"))
            except Exception:
                continue
            id_to_node[nid] = n
            ntype = (n.get("type") or "code")
            id_to_type[nid] = ntype

        # Build and add graph nodes (skip virtual start/end)
        for nid, n in id_to_node.items():
            ntype = id_to_type.get(nid, "code")
            if ntype in ("start", "end", "sheet-inputs", "sheet_inputs"):
                continue

            node_data = n.get("data", {})
            # Normalize MCP tool config from GUI schema if needed
            if ntype == "mcp" and isinstance(node_data, dict):
                try:
                    tn = (node_data.get("tool_name")
                          or node_data.get("toolName")
                          or (((node_data.get("inputsValues") or {}).get("tool_name") or {}).get("content"))
                          or (((node_data.get("inputsValues") or {}).get("toolName") or {}).get("content")))
                    if not tn:
                        callable_name = (((node_data.get("data") or {}).get("callable") or {}).get("name"))
                        if callable_name:
                            node_data["tool_name"] = callable_name
                except Exception:
                    pass
            builder_func = function_registry.get(ntype, _default_noop_builder)
            # Create runtime callable via builder
            raw_callable = builder_func(node_data, nid, skill_name, owner, bp_mgr)
            # Wrap with node_builder to add retries/context/breakpoints
            node_callable = node_builder(raw_callable, nid, skill_name, owner, bp_mgr)
            workflow.add_node(sid(nid), node_callable)

            # If loop/group provides nested blocks, add those into the same graph namespace (best-effort)
            try:
                if ntype in ["loop", "group"] and (n.get("blocks") or n.get("edges")):
                    nested_edges = n.get("edges", [])
                    process_blocks(workflow, n.get("blocks") or [], {}, {}, skill_name, owner, bp_mgr, nested_edges, parent_gid="", edges_debug=None, cond_edges_debug=None)
            except Exception as _e:
                logger.debug(f"process_blocks skipped for node {nid}: {_e}")

        # Build edges
        # 1) Handle condition nodes via add_conditional_edges
        condition_ids = {nid for nid, t in id_to_type.items() if t == "condition"}
        for cid in condition_ids:
            gid = sid(cid)
            cnode = id_to_node.get(cid, {})
            outgoing = [e for e in edges if str(e.get("sourceNodeID")) == cid]
            if not outgoing:
                continue
            port_map = {}
            for e in outgoing:
                port = e.get("sourcePortID")
                tgt = str(e.get("targetNodeID"))
                if not port:
                    continue
                if id_to_type.get(tgt) == "end" or tgt == "end" or tgt in end_ids or str(tgt).startswith("end"):
                    port_map[port] = END
                else:
                    port_map[port] = sid(tgt)
            logger.debug(f"[selector-debug] build {gid} outgoing={outgoing} port_map={port_map}")
            if port_map:
                selector = make_condition_selector(gid, cnode.get("data", {}) or {}, port_map)
                workflow.add_conditional_edges(gid, selector, path_map=dict(port_map))

        # 2) Add normal edges (skip those emitted by condition handling)
        for e in edges:
            try:
                src = str(e.get("sourceNodeID"))
                tgt = str(e.get("targetNodeID"))
            except Exception:
                continue

            # Skip edges originating from condition nodes (already handled)
            if src in condition_ids:
                continue

            # Resolve START/END (support ids like 'start_0' present only in top-level nodes)
            # Also treat 'sheet-inputs' as START-equivalent entry for the sheet
            if (
                src == "start"
                or id_to_type.get(src) == "start"
                or src in start_ids
                or str(src).startswith("start")
                or id_to_type.get(src) in ("sheet-inputs", "sheet_inputs")
            ):
                u = START
            else:
                u = sid(src)

            if tgt == "end" or id_to_type.get(tgt) == "end" or tgt in end_ids or str(tgt).startswith("end"):
                v = END
            else:
                v = sid(tgt)

            # Only add edges where both endpoints exist or are START/END
            try:
                workflow.add_edge(u, v)
            except Exception as _e:
                logger.debug(f"edge add skipped {src}->{tgt}: {_e}")

        # Ensure there is an entrypoint. Some diagrams may omit an explicit START edge.
        try:
            # If no edge from START exists, pick a best-effort entry node (no incoming edges)
            # Build sets of added node ids and incoming targets
            added_nodes = set()
            for nid, n in id_to_node.items():
                ntype = id_to_type.get(nid, "code")
                if ntype in ("start", "end", "sheet-inputs", "sheet_inputs"):
                    continue
                added_nodes.add(sid(nid))

            incoming = set()
            # From condition edges (port_map already wired)
            for cid in condition_ids:
                for e in edges:
                    if str(e.get("sourceNodeID")) == cid:
                        tgt = str(e.get("targetNodeID"))
                        if id_to_type.get(tgt) == "end" or tgt == "end" or tgt in end_ids or str(tgt).startswith("end"):
                            continue
                        incoming.add(sid(tgt))
            # From normal edges
            for e in edges:
                src = str(e.get("sourceNodeID"))
                tgt = str(e.get("targetNodeID"))
                if src in condition_ids:
                    continue
                if id_to_type.get(tgt) == "end" or tgt == "end" or tgt in end_ids or str(tgt).startswith("end"):
                    continue
                incoming.add(sid(tgt))

            # Detect if there was any START edge
            has_start_edge = any(
                (str(e.get("sourceNodeID")) == "start")
                or (id_to_type.get(str(e.get("sourceNodeID"))) == "start")
                or (id_to_type.get(str(e.get("sourceNodeID"))) in ("sheet-inputs", "sheet_inputs"))
                or (str(e.get("sourceNodeID")) in start_ids)
                or str(e.get("sourceNodeID", "")).startswith("start")
                for e in edges
            )

            if not has_start_edge and added_nodes:
                # Prefer nodes with no incoming edges
                candidates = [n for n in added_nodes if n not in incoming]
                entry = candidates[0] if candidates else sorted(list(added_nodes))[0]
                try:
                    workflow.set_entry_point(entry)
                    # Also add explicit START edge to be safe across LangGraph versions
                    try:
                        workflow.add_edge(START, entry)
                    except Exception as _ee2:
                        logger.debug(f"START edge add fallback failed: {_ee2}")
                    logger.debug(f"[flowgram2langgraph] set_entry_point fallback -> {entry}")
                except Exception as _ee:
                    logger.debug(f"fallback set_entry_point failed: {_ee}")
        except Exception as _e:
            logger.debug(f"entrypoint fallback calc failed: {_e}")

        # Collect breakpoint-enabled node IDs
        breakpoints: list[str] = []
        try:
            for n in nodes:
                nid = None
                try:
                    nid = str(n.get("id"))
                except Exception:
                    nid = None
                if not nid:
                    continue
                d = n.get("data") or {}
                has_bp = False
                try:
                    # Accept both UI shapes: 'break_point' (UI save) and 'breakpoint' (legacy)
                    has_bp = (d.get("break_point") is True) or (d.get("breakpoint") is True) or (n.get("breakpoint") is True)
                except Exception:
                    has_bp = False
                if has_bp:
                    breakpoints.append(nid)
        except Exception as _e:
            logger.debug(f"breakpoints collection failed: {_e}")

        return workflow, breakpoints
    except Exception as e_flat:
        err_msg = get_traceback(e_flat, "ErrorFlowgram2LangGraphV1")
        logger.error(f"{err_msg}")
        return None, []



# =============================
# v2 Converter (layered approach)
# =============================
def _v2_debug_workflow(tag: str, wf: dict):
    try:
        nodes = wf.get('nodes', []) or []
        edges = wf.get('edges', []) or []
        info = {
            'tag': tag,
            'nodes': [{'id': n.get('id'), 'type': n.get('type')} for n in nodes],
            'edges': [{'s': e.get('sourceNodeID'), 't': e.get('targetNodeID'), 'sp': e.get('sourcePortID') } for e in edges],
            'node_count': len(nodes),
            'edge_count': len(edges),
        }
        logger.debug(f"[v2][wf] {json.dumps(info, ensure_ascii=False)}")
    except Exception:
        pass


def _v2_find_sheet_entry(wf: dict) -> str | None:
    try:
        sheet_input_id = None
        for n in wf.get('nodes', []) or []:
            if n.get('type') == 'sheet-inputs':
                sheet_input_id = n.get('id')
                break
        if not sheet_input_id:
            return None
        for e in wf.get('edges', []) or []:
            if e.get('sourceNodeID') == sheet_input_id:
                return e.get('targetNodeID')
        return None
    except Exception:
        return None


def _v2_flatten_sheets(main_wf: dict, sheets: list[dict]) -> dict:
    """Return a new workflow with other sheets stitched into the main sheet.
    - For any edge to a 'sheet-call' or 'sheet-outputs' (with next sheet), redirect it to the entry node of that sheet.
    - Merge the secondary sheet nodes/edges (prefixed with sheetName__) into the main wf.
    - Remove structural sheet nodes from the main graph.
    - Log reconnections.
    """
    merged_nodes = list((main_wf.get('nodes') or []).copy())
    merged_edges = list((main_wf.get('edges') or []).copy())

    # Build sheet map
    sheet_map: dict[str, dict] = {}
    for s in sheets:
        sname = str(s.get('name'))
        sheet_map[sname] = s.get('workFlow') or {}

    # Helper to prefix ids for imported sheet nodes/edges
    def qid(sname: str, nid: str) -> str:
        return f"{sname}__{nid}"

    # Bring in all secondary sheets (except the first, which is main)
    brought: set[str] = set()
    for s in sheets[1:]:
        sname = str(s.get('name'))
        swf = s.get('workFlow') or {}
        # copy nodes
        for n in swf.get('nodes', []) or []:
            if n.get('type') in ('sheet-inputs', 'start'):
                continue
            nn = json.loads(json.dumps(n))
            nn['id'] = qid(sname, n.get('id'))
            merged_nodes.append(nn)
        # copy edges
        for e in swf.get('edges', []) or []:
            if not e: continue
            ee = json.loads(json.dumps(e))
            ee['sourceNodeID'] = qid(sname, e.get('sourceNodeID'))
            ee['targetNodeID'] = qid(sname, e.get('targetNodeID'))
            merged_edges.append(ee)
        brought.add(sname)

    # Redirect edges in main that go to sheet-call / sheet-outputs(nextSheet)
    def is_sheet_struct(n: dict) -> bool:
        return (n.get('type') in ('sheet-call', 'sheet-outputs'))

    id_to_node = {n.get('id'): n for n in merged_nodes}
    new_edges = []
    for e in merged_edges:
        tgt = e.get('targetNodeID')
        n = id_to_node.get(tgt)
        if n and is_sheet_struct(n):
            # Determine target sheet
            next_sheet = (n.get('data') or {}).get('nextSheet') or (n.get('data') or {}).get('next_sheet') or (n.get('data') or {}).get('sheet')
            if not next_sheet:
                # keep as-is if we cannot resolve
                new_edges.append(e)
                continue
            swf = sheet_map.get(next_sheet)
            if not isinstance(swf, dict):
                logger.warning(f"[v2][sheets] nextSheet not found: {next_sheet}")
                new_edges.append(e)
                continue
            entry = _v2_find_sheet_entry(swf)
            if not entry:
                logger.warning(f"[v2][sheets] sheet has no entry via sheet-inputs: {next_sheet}")
                new_edges.append(e)
                continue
            # Reconnect to the sheet entry (prefixed id)
            target_qid = qid(next_sheet, entry)
            logger.debug(f"[v2][sheets] redirect edge {e.get('sourceNodeID')} -> {tgt} to {target_qid}")
            ee = json.loads(json.dumps(e))
            ee['targetNodeID'] = target_qid
            # Drop structural node from merged nodes set (later filtered)
            new_edges.append(ee)
        else:
            new_edges.append(e)

    merged_edges = new_edges

    # Remove structural sheet nodes from merged nodes
    cleaned_nodes = [n for n in merged_nodes if n.get('type') not in ('sheet-call', 'sheet-outputs', 'sheet-inputs', 'start')]
    stitched = {'nodes': cleaned_nodes, 'edges': merged_edges}
    _v2_debug_workflow('after_flatten_sheets', stitched)
    return stitched


def _v2_remove_groups(wf: dict) -> dict:
    cleaned_nodes = [n for n in (wf.get('nodes') or []) if n.get('type') != 'group']
    out = {'nodes': cleaned_nodes, 'edges': wf.get('edges') or []}
    _v2_debug_workflow('after_remove_groups', out)
    return out


def _v2_convert_conditions_schema_level(wf: dict) -> dict:
    """Optional schema-level conversion of condition nodes to edges.
    For now, keep condition nodes (original converter handles it). This is a hook.
    """
    _v2_debug_workflow('after_condition_convert_noop', wf)
    return wf


def _v2_remove_dummy_nodes(wf: dict) -> dict:
    """
    Remove dummy nodes from the workflow and rewire their connections.
    For each dummy node:
    - Find all incoming edges (edges pointing to the dummy node)
    - Find all outgoing edges (edges from the dummy node)
    - Connect all incoming sources directly to all outgoing targets
    - Remove the dummy node and its edges
    """
    nodes = wf.get('nodes', []) or []
    edges = wf.get('edges', []) or []
    
    # Find all dummy nodes
    dummy_node_ids = {n['id'] for n in nodes if n.get('type') == 'dummy'}
    
    if not dummy_node_ids:
        return wf  # No dummy nodes to remove
    
    logger.debug(f"[v2] Removing {len(dummy_node_ids)} dummy node(s): {dummy_node_ids}")
    
    # For each dummy node, find incoming and outgoing edges
    new_edges = []
    for edge in edges:
        src = edge.get('sourceNodeID')
        tgt = edge.get('targetNodeID')
        
        # Skip edges connected to dummy nodes (will be replaced)
        if src in dummy_node_ids or tgt in dummy_node_ids:
            continue
        
        new_edges.append(edge)
    
    # For each dummy node, create bridging edges
    for dummy_id in dummy_node_ids:
        # Find incoming edges (edges pointing TO this dummy node)
        incoming = [e for e in edges if e.get('targetNodeID') == dummy_id]
        # Find outgoing edges (edges FROM this dummy node)
        outgoing = [e for e in edges if e.get('sourceNodeID') == dummy_id]
        
        # Bridge: connect each incoming source to each outgoing target
        for in_edge in incoming:
            for out_edge in outgoing:
                new_edge = {
                    'sourceNodeID': in_edge.get('sourceNodeID'),
                    'targetNodeID': out_edge.get('targetNodeID'),
                }
                # Preserve source port if specified
                if in_edge.get('sourcePortID'):
                    new_edge['sourcePortID'] = in_edge['sourcePortID']
                # Preserve target port if specified
                if out_edge.get('targetPortID'):
                    new_edge['targetPortID'] = out_edge['targetPortID']
                
                new_edges.append(new_edge)
                logger.debug(f"[v2] Bridged: {in_edge.get('sourceNodeID')} -> {dummy_id} -> {out_edge.get('targetNodeID')} "
                           f"became {new_edge['sourceNodeID']} -> {new_edge['targetNodeID']}")
    
    # Remove dummy nodes from node list
    new_nodes = [n for n in nodes if n.get('id') not in dummy_node_ids]
    
    logger.debug(f"[v2] Removed {len(nodes) - len(new_nodes)} dummy node(s), {len(edges)} edges -> {len(new_edges)} edges")
    
    return {'nodes': new_nodes, 'edges': new_edges}


def flowgram2langgraph_v2(flow: dict, bundle_json: dict | None = None, enable_subgraph: bool = False):
    """
    v2 layered converter. Same inputs/outputs as flowgram2langgraph().
    We currently implement the flat (enable_subgraph=False) path via schema preprocessing, then delegate to the existing converter.
    """
    try:
        # Prepare sheets list like v1
        sheets: list[dict] = []
        base = flow
        b = (bundle_json or base.get('bundle') or {})
        if isinstance(b, dict) and isinstance(b.get('sheets'), list):
            for s in b['sheets']:
                name = s.get('name') or s.get('id')
                doc = s.get('document') or {}
                if isinstance(doc, dict) and 'nodes' in doc and 'edges' in doc:
                    sheets.append({'name': str(name), 'workFlow': doc})
        if not sheets:
            # Single sheet fallback
            sheets.append({'name': base.get('sheetName', 'main'), 'workFlow': base.get('workFlow', {})})

        main_wf = sheets[0].get('workFlow') or {}
        _v2_debug_workflow('original_main', main_wf)

        # 1) Flatten sheets
        stitched = _v2_flatten_sheets(main_wf, sheets)

        # 2) Remove groups
        stitched = _v2_remove_groups(stitched)

        # 3) Convert conditions (deferred to v1 for now)
        stitched = _v2_convert_conditions_schema_level(stitched)

        # 4) Remove dummy nodes and rewire their connections
        stitched = _v2_remove_dummy_nodes(stitched)

        # Delegate to v1 by re-wrapping as a single-sheet flow
        new_flow = {
            **{k: v for k, v in flow.items() if k not in ('workFlow', 'bundle')},
            'workFlow': stitched,
        }
        logger.debug('[v2] Delegating to v1 after preprocessing (flat mode)')
        return flowgram2langgraph(new_flow, bundle_json=None)
    except Exception as e:
        logger.error(f"[v2] conversion failed: {e}")
        # fallback to v1
        return flowgram2langgraph(flow, bundle_json=bundle_json)

def flatten_blocks(blocks):
    """Recursively flatten blocks for edge mapping."""
    flat = []
    for block in blocks:
        if block["type"] in ["group", "loop"] and "blocks" in block:
            flat += flatten_blocks(block["blocks"])
    return flat


def debug_condition_function(state):
    return "if_0"  # just always select first condition for testing
