import json
import os
from typing import Dict, List, Tuple, Optional, Set
from langgraph.graph import StateGraph, END, START
from utils.logger_helper import logger_helper as logger


# Compute the longest simple path from DAG-like edges for primary layout
def find_longest_branch(edges: List[Tuple[str, str]], nodes: List[str]) -> List[str]:
    """Returns the longest path as a list of node ids."""
    from collections import defaultdict
    graph = defaultdict(list)
    for edge in edges:
        graph[edge[0]].append(edge[1])

    longest = []
    def dfs(path):
        nonlocal longest
        node = path[-1]
        if len(path) > len(longest):
            longest = path[:]
        for nbr in graph[node]:
            if nbr not in path:
                dfs(path + [nbr])
    # Try all starting points (no incoming edges)
    all_targets = set(e[1] for e in edges)
    sources = [n for n in nodes if n not in all_targets]
    for s in sources:
        dfs([s])
    return longest

def place_nodes(node_ids: List[str], edge_tuples: List[Tuple[str, str]]) -> Dict[str, Tuple[int, int]]:
    """Returns layout positions for nodes given edges.
    Node width=200, height=120, spacing=30 -> hstep=230, vstep=150.
    """
    main_path = find_longest_branch(edge_tuples, node_ids)
    placement = {}
    x, y = 0, 0
    hstep = 200 + 30
    vstep = 120 + 30
    # Place main path nodes horizontally
    for node in main_path:
        placement[node] = (x, y)
        x += hstep
    # Place all other nodes below, in grid
    grid_x, grid_y = 0, vstep
    for node in node_ids:
        if node not in main_path:
            placement[node] = (grid_x, grid_y)
            grid_x += hstep
            if grid_x > 8 * hstep:
                grid_x = 0
                grid_y += vstep
    return placement


def _is_subgraph_node(stategraph: StateGraph, node_id: str) -> Tuple[bool, Optional[StateGraph]]:
    """Heuristic: a node is a subgraph if its runnable holds a nested StateGraph under common attributes."""
    try:
        runnable = stategraph.nodes[node_id].runnable
    except Exception:
        runnable = None
    # Common places to find a nested graph
    candidates = []
    for attr in ("graph", "subgraph", "workflow", "stategraph"):
        if hasattr(runnable, attr):
            candidates.append(getattr(runnable, attr))
    for c in candidates:
        if isinstance(c, StateGraph):
            return True, c
    return False, None


def _default_code_node(node_id: str, x: int, y: int) -> dict:
    return {
        "id": node_id,
        "type": "code",
        "data": {
            "title": node_id,
            "script": {
                "language": "python",
                "content": """
def main(state, *, runtime, store):
    # TODO: fill in node logic
    return {}
""".strip()
            }
        },
        "meta": {"position": {"x": x, "y": y}},
    }


def _end_node_present(edges: List[Tuple[str, str]]) -> bool:
    return any(t == END for _, t in edges)


def _graph_topology(g: StateGraph) -> Tuple[List[str], List[Tuple[str, str]]]:
    nodes = list(getattr(g, "nodes").keys())
    edges = [(u, v) for (u, v) in getattr(g, "edges")]  # contains END possibly
    return nodes, edges


def langgraph2flowgram(workflow: StateGraph, out_dir: str = "test_skill/diagram_dir") -> Tuple[dict, dict]:
    """Convert a StateGraph into Flowgram main sheet and bundle files.
    - Non-subgraph nodes become code nodes in main sheet.
    - Subgraph nodes get their own sheets with internal topology (as code nodes).
    - Sheet IO nodes are added per rules.
    Writes test_skill.json and test_skill_bundle.json under out_dir.
    Returns (main_sheet_doc, bundle_doc).
    """
    os.makedirs(out_dir, exist_ok=True)

    # Collect subgraph nodes
    node_ids_main = list(workflow.nodes.keys())
    edges_main = [(u, v) for (u, v) in workflow.edges]
    subgraph_nodes: Dict[str, StateGraph] = {}
    for nid in node_ids_main:
        is_sub, subg = _is_subgraph_node(workflow, nid)
        if is_sub and isinstance(subg, StateGraph):
            subgraph_nodes[nid] = subg

    # Placement for main sheet (all nodes for positioning now)
    placements_main = place_nodes(node_ids_main, edges_main)

    # Build main sheet nodes: code nodes for non-subgraphs; sheet-call nodes for subgraphs
    main_nodes: List[dict] = []
    for nid in node_ids_main:
        x, y = placements_main.get(nid, (0, 0))
        if nid in subgraph_nodes:
            # Represent subgraph in main as a sheet-call stub
            main_nodes.append({
                "id": nid,
                "type": "sheet-call",
                "data": {"title": nid, "nextSheet": nid},
                "meta": {"position": {"x": x, "y": y}},
            })
        else:
            main_nodes.append(_default_code_node(nid, x, y))

    # Build main edges, but first compute conditional branch pairs to avoid duplicating direct edges
    try:
        branches_all = getattr(workflow, "branches", {}) or {}
    except Exception:
        branches_all = {}
    cond_pairs_main: Dict[str, Set[str]] = {}
    for src, br in (branches_all or {}).items():
        try:
            ends_map = {}
            for _, bobj in (br or {}).items():
                if hasattr(bobj, "ends") and isinstance(bobj.ends, dict):
                    ends_map.update(bobj.ends)
            targets = {t for t in ends_map.values() if t != END}
            if targets:
                cond_pairs_main[src] = targets
            # If END is a branch target, we also count it specially to skip direct (src->END)
            if any(t == END for t in ends_map.values()):
                cond_pairs_main.setdefault(src, set())  # marker
        except Exception:
            continue

    # Map START/END to explicit start/end nodes in main sheet if present
    has_start = any(u == START for (u, _) in edges_main)
    has_end = any(v == END for ((_, v)) in edges_main)
    if has_start:
        # Provide a visible START node in flowgram
        main_nodes.append({"id": "start_0", "type": "start", "data": {"title": "START"}, "meta": {"position": {"x": -230, "y": 150}}})
    if has_end:
        # Place END to align horizontally after the longest chain; keep same Y as START
        try:
            max_x = max((placements_main.get(nid, (0, 0))[0] for nid in node_ids_main), default=0)
        except Exception:
            max_x = 0
        end_x = max_x + 230  # one step to the right of farthest node
        main_nodes.append({"id": "end", "type": "end", "data": {"title": "END"}, "meta": {"position": {"x": end_x, "y": 150}}})
    main_edges: List[dict] = []
    for u, v in edges_main:
        # Skip direct edges that will be represented via condition nodes
        if u in cond_pairs_main:
            # Skip direct to END if this source has a branch to END
            if v == END:
                continue
            # Skip if v is one of the conditional targets
            if v in cond_pairs_main.get(u, set()):
                continue
        # Map START -> start_0
        if u == START:
            main_edges.append({"sourceNodeID": "start_0", "targetNodeID": v})
            continue
        if v == END:
            main_edges.append({"sourceNodeID": u, "targetNodeID": "end"})
        else:
            main_edges.append({"sourceNodeID": u, "targetNodeID": v})

    # Translate LangGraph conditional edges (branches) into Flowgram condition nodes
    branches = branches_all
    for src, br in (branches or {}).items():
        # Create a condition node per source that owns conditional edges
        cond_id = f"condition_{src}"
        sx, sy = placements_main.get(src, (0, 0))
        # Place condition node between source and its successors
        cond_x, cond_y = sx + (200 + 30)//2, sy
        main_nodes.append({
            "id": cond_id,
            "type": "condition",
            "data": {"title": cond_id, "conditions": []},
            "meta": {"position": {"x": cond_x, "y": cond_y}},
        })
        # Wire source -> condition
        main_edges.append({"sourceNodeID": src, "targetNodeID": cond_id})
        # For each branch map key -> target
        # Heuristic: look for .ends mapping
        try:
            ends = {}
            for _, bobj in (br or {}).items():
                if hasattr(bobj, "ends") and isinstance(bobj.ends, dict):
                    ends.update(bobj.ends)
        except Exception:
            ends = {}
        for key, tgt in (ends or {}).items():
            if tgt == END:
                main_edges.append({"sourceNodeID": cond_id, "targetNodeID": "end", "sourcePortID": key})
            else:
                main_edges.append({"sourceNodeID": cond_id, "targetNodeID": tgt, "sourcePortID": key})

    # Determine next sheet mapping for subgraphs from main edges
    sub_next: Dict[str, Optional[str]] = {k: None for k in subgraph_nodes.keys()}
    for u, v in edges_main:
        if u in subgraph_nodes and v in subgraph_nodes:
            sub_next[u] = v

    # Build sheets for each subgraph
    sheets: List[dict] = []
    # First, main sheet entry (no sheet-inputs here)
    main_sheet = {"id": "main", "name": "main", "document": {"nodes": main_nodes, "edges": main_edges}}
    sheets.append(main_sheet)

    for sname, sg in subgraph_nodes.items():
        snodes, sedges = _graph_topology(sg)
        pos = place_nodes(snodes, sedges)
        sheet_nodes: List[dict] = []
        sheet_edges: List[dict] = []

        # Insert sheet-inputs and connect to entry nodes (no predecessors within subgraph)
        sheet_inputs_id = f"sheet_inputs_{sname}"
        sheet_nodes.append({"id": sheet_inputs_id, "type": "sheet-inputs", "data": {"title": f"inputs_{sname}"}, "meta": {"position": {"x": 0, "y": 0}}})

        preds: Dict[str, Set[str]] = {}
        for su, tv in sedges:
            preds.setdefault(tv, set()).add(su)
        entry_nodes = [n for n in snodes if len([p for p in preds.get(n, set()) if p in snodes]) == 0]

        # Add internal nodes as code nodes
        for nid in snodes:
            x, y = pos.get(nid, (0, 0))
            sheet_nodes.append(_default_code_node(nid, x, y))

        # Connect sheet-inputs to entries
        for en in entry_nodes:
            sheet_edges.append({"sourceNodeID": sheet_inputs_id, "targetNodeID": en})

        # Add internal edges; map END appropriately, but compute subgraph conditional pairs to skip direct edges
        need_end = False
        try:
            s_branches_all = getattr(sg, "branches", {}) or {}
        except Exception:
            s_branches_all = {}
        cond_pairs_sub: Dict[str, Set[str]] = {}
        for ssrc, br in (s_branches_all or {}).items():
            try:
                ends_map = {}
                for _, bobj in (br or {}).items():
                    if hasattr(bobj, "ends") and isinstance(bobj.ends, dict):
                        ends_map.update(bobj.ends)
                targets = {t for t in ends_map.values() if t != END}
                if targets:
                    cond_pairs_sub[ssrc] = targets
                if any(t == END for t in ends_map.values()):
                    cond_pairs_sub.setdefault(ssrc, set())
            except Exception:
                continue

        for su, tv in sedges:
            if su in cond_pairs_sub:
                if tv == END:
                    need_end = True
                    continue
                if tv in cond_pairs_sub.get(su, set()):
                    continue
            if tv == END:
                need_end = True
            else:
                sheet_edges.append({"sourceNodeID": su, "targetNodeID": tv})

        # Translate conditional edges inside subgraph to condition nodes
        try:
            s_branches = getattr(sg, "branches", {}) or {}
        except Exception:
            s_branches = {}
        for src, br in (s_branches or {}).items():
            cond_id = f"condition_{src}"
            sx, sy = pos.get(src, (0, 0))
            cond_x, cond_y = sx + (200 + 30)//2, sy
            sheet_nodes.append({
                "id": cond_id,
                "type": "condition",
                "data": {"title": cond_id, "conditions": []},
                "meta": {"position": {"x": cond_x, "y": cond_y}},
            })
            sheet_edges.append({"sourceNodeID": src, "targetNodeID": cond_id})
            try:
                ends = {}
                for _, bobj in (br or {}).items():
                    if hasattr(bobj, "ends") and isinstance(bobj.ends, dict):
                        ends.update(bobj.ends)
            except Exception:
                ends = {}
            for key, tgt in (ends or {}).items():
                if tgt == END:
                    need_end = True
                    sheet_edges.append({"sourceNodeID": cond_id, "targetNodeID": "end", "sourcePortID": key})
                else:
                    sheet_edges.append({"sourceNodeID": cond_id, "targetNodeID": tgt, "sourcePortID": key})

        # If this subgraph reaches END, add an end node and wire edges to it
        if need_end:
            sheet_nodes.append({"id": "end", "type": "end", "data": {"title": "END"}, "meta": {"position": {"x": 0, "y": 300}}})
            for su, tv in sedges:
                if tv == END:
                    sheet_edges.append({"sourceNodeID": su, "targetNodeID": "end"})

        # If no END and we have a next sheet, add sheet-outputs with nextSheet field
        next_sheet = sub_next.get(sname)
        if not need_end and next_sheet:
            sheet_outputs_id = f"sheet_outputs_{sname}"
            sheet_nodes.append({
                "id": sheet_outputs_id,
                "type": "sheet-outputs",
                "data": {"title": f"outputs_{sname}", "nextSheet": next_sheet},
                "meta": {"position": {"x": 400, "y": 0}}
            })
            # Heuristic: connect last nodes (no outgoing) to sheet-outputs
            succs: Dict[str, Set[str]] = {}
            for su, tv in sedges:
                if tv != END:
                    succs.setdefault(su, set()).add(tv)
            last_nodes = [n for n in snodes if len([s for s in succs.get(n, set()) if s in snodes]) == 0]
            for ln in last_nodes:
                sheet_edges.append({"sourceNodeID": ln, "targetNodeID": sheet_outputs_id})

        sheets.append({"id": sname, "name": sname, "document": {"nodes": sheet_nodes, "edges": sheet_edges}})

    # Build bundle file
    bundle = {"mainSheetId": "main", "activeSheetId": "main", "sheets": sheets}

    # Main skill doc for convenience mirrors main sheet
    main_skill = {"sheetName": "main", "workFlow": main_sheet["document"], "bundle": bundle}

    # Write files
    main_path = os.path.join(out_dir, "test_skill.json")
    bundle_path = os.path.join(out_dir, "test_skill_bundle.json")
    with open(main_path, "w", encoding="utf-8") as f:
        json.dump(main_skill, f, ensure_ascii=False, indent=2)
    with open(bundle_path, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, indent=2)

    return main_skill, bundle


def test_langgraph2flowgram() -> dict:
    """Build a single-sheet StateGraph with branching and export.
    Topology:
      START -> n1 -> n2 -> (if_out -> n3, else_out -> n4) -> n5 -> END
    """
    logger.info('[LG2FG][TEST] test_langgraph2flowgram invoked (branching)')
    def _noop(state: dict, **kwargs):
        return state
    sg = StateGraph(dict)
    logger.debug('[LG2FG][TEST] building nodes n1..n5')
    for nid in ("n1", "n2", "n3", "n4", "n5"):
        sg.add_node(nid, _noop)
    # Edges (no direct n2->n3/n4; those will be condition branches)
    logger.debug('[LG2FG][TEST] wiring edges START->n1->n2, n3->n5, n4->n5, n5->END')
    sg.add_edge(START, "n1")
    sg.add_edge("n1", "n2")
    sg.add_edge("n3", "n5")
    sg.add_edge("n4", "n5")
    sg.add_edge("n5", END)
    # Inject a minimal branches structure for converter to render condition node at n2
    class _Br:  # simple holder for .ends
        def __init__(self, ends: dict): self.ends = ends
    sg.branches = {
        "n2": {
            "if_out": _Br({"if_out": "n3"}),
            "else_out": _Br({"else_out": "n4"}),
        }
    }
    # Export
    logger.info('[LG2FG][TEST] exporting sample graph to flowgram files')
    main_doc, bundle_doc = langgraph2flowgram(sg)
    try:
        out_dir = "test_skill/diagram_dir"
        logger.info(f"[LG2FG][TEST] export complete (minimal). main and bundle written to: {out_dir}")
        logger.debug(f"[LG2FG][TEST] main nodes={len(main_doc.get('workFlow', {}).get('nodes', []))}, sheets={len((bundle_doc or {}).get('sheets', []))}")
    except Exception:
        pass
    return {
        "ok": True,
        "out_dir": "test_skill/diagram_dir",
        "main_sheets_nodes": len(main_doc.get("workFlow", {}).get("nodes", [])),
        "bundle_sheets": len((bundle_doc or {}).get("sheets", [])),
    }

