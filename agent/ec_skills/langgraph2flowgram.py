import json
import os
from typing import Dict, List, Tuple, Optional, Set
from langgraph.graph import StateGraph, END, START
from utils.logger_helper import logger_helper as logger


# ------------------------------
# Placement configuration (tweakable)
# ------------------------------
PLACEMENT_CFG = {
    # Node dimensions and spacing
    "node_width": 200,
    "node_height": 120,
    "margin": 50,                # >= 50px as requested
    # Baseline Y for the main/longest path
    "baseline_y": 150,
    # Centering controls
    "center_main_longest": True, # center middle node of main longest path at (0,0)
    "center_sub_longest": True,  # center middle node of each sub-sheet longest path at (0,0)
    # Branch selection preference when equal-length: prefer 'if_out' over 'else_out'
    "prefer_if_branch": True,
}


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
    """The Placement Algorithm: (Sugiyama-style layering, simplified)
    Layered DAG placement with ≥50px margins, straight longest path baseline, and barycenter ordering.
    - Node size: width=200, height=120
    - Margins: 50px -> hstep=250, vstep=170
    - Baseline Y: 150 for the main/longest path
    """
    # Parameters
    width, height = PLACEMENT_CFG.get("node_width", 200), PLACEMENT_CFG.get("node_height", 120)
    margin = PLACEMENT_CFG.get("margin", 50)
    hstep = width + margin  # 250
    vstep = height + margin  # 170
    baseline_y = PLACEMENT_CFG.get("baseline_y", 150)

    nodes = list(node_ids)
    node_set = set(nodes)

    # Build adjacency and indegree, and filter edges to those within node_set
    from collections import defaultdict, deque
    adj: Dict[str, List[str]] = defaultdict(list)
    indeg: Dict[str, int] = {n: 0 for n in nodes}
    filtered_edges: List[Tuple[str, str]] = []
    for u, v in edge_tuples:
        if u in node_set and v in node_set:
            filtered_edges.append((u, v))
            adj[u].append(v)
            indeg[v] = indeg.get(v, 0) + 1

    # Detect back-edges via DFS and ignore them for layering (break cycles)
    temp_mark, perm_mark = set(), set()
    back_edges: Set[Tuple[str, str]] = set()
    def dfs(u: str):
        if u in perm_mark:
            return
        if u in temp_mark:
            return
        temp_mark.add(u)
        for v in adj.get(u, []):
            if v in temp_mark and (u, v) in filtered_edges:
                back_edges.add((u, v))
            else:
                dfs(v)
        temp_mark.remove(u)
        perm_mark.add(u)
    for n in nodes:
        dfs(n)

    dag_edges = [(u, v) for (u, v) in filtered_edges if (u, v) not in back_edges]

    # Topological order (Kahn)
    indeg_dag: Dict[str, int] = {n: 0 for n in nodes}
    for u, v in dag_edges:
        indeg_dag[v] += 1
    q = deque([n for n in nodes if indeg_dag[n] == 0])
    topo: List[str] = []
    while q:
        u = q.popleft()
        topo.append(u)
        for v in adj.get(u, []):
            if (u, v) not in dag_edges:
                continue
            indeg_dag[v] -= 1
            if indeg_dag[v] == 0:
                q.append(v)
    if len(topo) != len(nodes):
        # Fallback: append any missing
        seen = set(topo)
        topo.extend([n for n in nodes if n not in seen])

    # Longest path layering L(u) with stabilization to enforce strict increases along edges
    layer: Dict[str, int] = {n: 0 for n in nodes}
    for u in topo:
        for v in adj.get(u, []):
            if (u, v) not in dag_edges:
                continue
            layer[v] = max(layer.get(v, 0), layer.get(u, 0) + 1)
    # Enforce layer[v] >= layer[u]+1 for all edges (iterate to fix any out-of-order topo remnants)
    for _ in range(len(nodes)):
        changed = False
        for u, v in dag_edges:
            need = layer[u] + 1
            if layer[v] < need:
                layer[v] = need
                changed = True
        if not changed:
            break

    # Compute main path (on DAG edges) and clamp to baseline
    main_path = find_longest_branch(dag_edges, nodes)

    # Group by layer
    by_layer: Dict[int, List[str]] = defaultdict(list)
    for n in nodes:
        by_layer[layer[n]].append(n)

    # Initial X positions by layer
    x_pos: Dict[str, int] = {n: layer[n] * hstep for n in nodes}

    # Ordering within layers: barycenter of predecessors' X (then id)
    preds: Dict[str, List[str]] = defaultdict(list)
    for u, v in dag_edges:
        preds[v].append(u)
    for k in sorted(by_layer.keys()):
        arr = by_layer[k]
        def bary(n: str) -> float:
            ps = preds.get(n, [])
            if not ps:
                return -1.0
            return sum(x_pos[p] for p in ps) / len(ps)
        arr.sort(key=lambda n: (bary(n), n))
        by_layer[k] = arr

    # Assign Y per layer, centered around baseline; clamp main path to baseline
    y_pos: Dict[str, int] = {}
    for k in sorted(by_layer.keys()):
        arr = by_layer[k]
        # If any node from main_path is in this layer, clamp it to baseline
        main_in_layer = [n for n in arr if n in set(main_path)]
        # Center others around baseline with vstep spacing
        if main_in_layer:
            # Put main path nodes at baseline
            for n in arr:
                if n in set(main_path):
                    y_pos[n] = baseline_y
            # Spread remaining above and below
            rem = [n for n in arr if n not in set(main_path)]
            up = True
            up_i, down_i = 1, 1
            for n in rem:
                if up:
                    y_pos[n] = baseline_y - up_i * vstep
                    up_i += 1
                else:
                    y_pos[n] = baseline_y + down_i * vstep
                    down_i += 1
                up = not up
        else:
            # No main node here; center the layer around baseline
            m = len(arr)
            start_offset = -((m - 1) // 2) * vstep
            for i, n in enumerate(arr):
                y_pos[n] = baseline_y + start_offset + i * vstep

    # Build final placement
    placement: Dict[str, Tuple[int, int]] = {}
    for n in nodes:
        placement[n] = (x_pos[n], y_pos[n])
    return placement


def _is_subgraph_node(stategraph: StateGraph, node_id: str) -> Tuple[bool, Optional[StateGraph]]:
    """Detect whether a node is a subgraph.
    Priority: use explicit registry stategraph._subgraphs if present; otherwise fall back to runnable attribute heuristics.
    """
    # 1) Explicit registry set by builder/tests
    try:
        registry = getattr(stategraph, "_subgraphs", None)
        if isinstance(registry, dict) and node_id in registry and isinstance(registry[node_id], StateGraph):
            return True, registry[node_id]
    except Exception:
        pass
    # 2) Heuristic: nested StateGraph under common attributes on runnable
    try:
        runnable = stategraph.nodes[node_id].runnable
    except Exception:
        runnable = None
    # Common places to find a nested graph
    for attr in ("graph", "subgraph", "workflow", "stategraph", "inner", "wrapped"):
        try:
            candidate = getattr(runnable, attr)
            if isinstance(candidate, StateGraph):
                return True, candidate
        except Exception:
            continue
    # Try __dict__ fallback
    try:
        d = getattr(runnable, "__dict__", {})
        for k, v in (d.items() if isinstance(d, dict) else []):
            if isinstance(v, StateGraph):
                return True, v
    except Exception:
        pass
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
        # Try to get runnable and provide diagnostics regardless of detection
        try:
            runnable = getattr(workflow.nodes.get(nid), 'runnable', None)
            rtype = type(runnable).__name__ if runnable is not None else None
        except Exception:
            runnable, rtype = None, None
        is_sub, subg = _is_subgraph_node(workflow, nid)
        if is_sub and isinstance(subg, StateGraph):
            subgraph_nodes[nid] = subg
            try:
                snodes = list(getattr(subg, 'nodes').keys())
                sedges = [(u, v) for (u, v) in getattr(subg, 'edges')]
                msg = f"[LG2FG] Detected subgraph node '{nid}' with {len(snodes)} nodes and {len(sedges)} edges"
                logger.info(msg)
                logger.debug(f"[LG2FG] Subgraph '{nid}' nodes: {snodes}")
                logger.debug(f"[LG2FG] Subgraph '{nid}' edges: {sedges}")
            except Exception:
                logger.warning(f"[LG2FG] Subgraph '{nid}' detected but failed to introspect topology")
        else:
            # Not detected as subgraph; log runnable type for visibility
            try:
                logger.info(f"[LG2FG] Node '{nid}' not a subgraph (runnable type: {rtype})")
            except Exception:
                pass
    try:
        logger.info(f"[LG2FG] Subgraph nodes detected: {list(subgraph_nodes.keys())}")
    except Exception:
        pass

    # Placement for main sheet (all nodes for positioning now)
    placements_main = place_nodes(node_ids_main, edges_main)
    try:
        logger.debug(f"[LG2FG] Main placements: {placements_main}")
    except Exception:
        pass

    # Build main sheet nodes:
    # - Non-subgraphs: code nodes
    # - Subgraphs: a sheet-outputs node that sends flow to the subgraph sheet
    main_nodes: List[dict] = []
    # Map subgraph id -> synthetic sheet-outputs node id on main
    sub_main_exit_map: Dict[str, str] = {}
    for nid in node_ids_main:
        x, y = placements_main.get(nid, (0, 0))
        if nid in subgraph_nodes:
            # Represent transition to subgraph sheet via a sheet-outputs node
            exit_id = f"sheet_outputs_call_{nid}"
            sub_main_exit_map[nid] = exit_id
            main_nodes.append({
                "id": exit_id,
                "type": "sheet-outputs",
                "data": {
                    "title": f"to_{nid}",
                    "nextSheet": nid,
                    "nextSheetId": nid,
                },
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
    # Only consider END on main if any non-subgraph node connects to END
    has_end_from_non_sub = any((u not in subgraph_nodes) and (v == END) for (u, v) in edges_main)
    if has_start:
        # Provide a visible START node in flowgram
        main_nodes.append({"id": "start_0", "type": "start", "data": {"title": "START"}, "meta": {"position": {"x": -230, "y": 150}}})
    if has_end_from_non_sub:
        # Place END to align horizontally after the longest chain; keep same Y as START
        try:
            max_x = max((placements_main.get(nid, (0, 0))[0] for nid in node_ids_main), default=0)
        except Exception:
            max_x = 0
        end_x = max_x + 230  # one step to the right of farthest node
        main_nodes.append({"id": "end", "type": "end", "data": {"title": "END"}, "meta": {"position": {"x": end_x, "y": 150}}})
    main_edges: List[dict] = []
    # Track subgraphs that should terminate (END) within their sheet due to main edge u->END
    subgraphs_end_on_sheet: Set[str] = set()
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
            if u in subgraph_nodes:
                # Let the subgraph handle END inside its own sheet
                subgraphs_end_on_sheet.add(u)
                continue
            else:
                main_edges.append({"sourceNodeID": u, "targetNodeID": "end"})
        else:
            # If target is a subgraph, redirect to its synthetic sheet-outputs node
            if v in subgraph_nodes:
                main_edges.append({"sourceNodeID": u, "targetNodeID": sub_main_exit_map.get(v, v)})
            else:
                main_edges.append({"sourceNodeID": u, "targetNodeID": v})
    try:
        logger.debug(f"[LG2FG] Main edges (post-process): {main_edges}")
    except Exception:
        pass

    # Translate LangGraph conditional edges (branches) into Flowgram condition nodes
    branches = branches_all
    for src, br in (branches or {}).items():
        # Create a condition node per source that owns conditional edges
        cond_id = f"condition_{src}"
        sx, sy = placements_main.get(src, (0, 0))
        # Place condition node on baseline half a step to the right of source
        cond_x, cond_y = sx + (PLACEMENT_CFG.get("node_width", 200) + PLACEMENT_CFG.get("margin", 50))//2, PLACEMENT_CFG.get("baseline_y", 150)
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

    # FINAL PASS LAYOUT for main sheet: recompute positions using the fully transformed graph
    try:
        main_ids = [n.get("id") for n in main_nodes]
        main_pairs = [(e.get("sourceNodeID"), e.get("targetNodeID")) for e in main_edges]
        relayout = place_nodes(main_ids, main_pairs)
        for n in main_nodes:
            nid = n.get("id")
            xy = relayout.get(nid)
            if xy:
                n.setdefault("meta", {}).setdefault("position", {})
                n["meta"]["position"] = {"x": xy[0], "y": xy[1]}
        # Force the longest path from start_0 to be perfectly horizontal on baseline
        try:
            from collections import defaultdict
            g = defaultdict(list)
            for u, v in main_pairs:
                g[u].append(v)
            best_path: list[str] = []
            def dfs(u: str, path: list[str]):
                nonlocal best_path
                if len(path) > len(best_path):
                    best_path = path[:]
                for v in g.get(u, []):
                    if v not in path:
                        dfs(v, path + [v])
            if "start_0" in set(main_ids):
                dfs("start_0", ["start_0"])
            # Clamp baseline
            for n in main_nodes:
                if n.get("id") in best_path:
                    n.setdefault("meta", {}).setdefault("position", {})
                    n["meta"]["position"]["y"] = 150
            # Center the middle node of longest path at (0,0)
            if best_path:
                mid = best_path[len(best_path)//2]
                # find current coordinates
                mid_node = next((nn for nn in main_nodes if nn.get("id") == mid), None)
                if mid_node:
                    pos = mid_node.get("meta", {}).get("position", {})
                    cx, cy = pos.get("x", 0), pos.get("y", 0)
                    dx, dy = -cx, -cy
                    for nn in main_nodes:
                        p = nn.setdefault("meta", {}).setdefault("position", {})
                        p["x"] = (p.get("x", 0) + dx)
                        p["y"] = (p.get("y", 0) + dy)
        except Exception:
            pass
    except Exception:
        pass

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

        # If this subgraph reaches END (either internally or due to main u->END), add END node and wire last nodes to it
        if need_end or (sname in subgraphs_end_on_sheet):
            sheet_nodes.append({"id": "end", "type": "end", "data": {"title": "END"}, "meta": {"position": {"x": 400, "y": 0}}})
            # Wire explicit internal edges to END if any
            for su, tv in sedges:
                if tv == END:
                    sheet_edges.append({"sourceNodeID": su, "targetNodeID": "end"})
            # Also wire last nodes (no outgoing inside subgraph) to END
            succs: Dict[str, Set[str]] = {}
            for su, tv in sedges:
                if tv != END:
                    succs.setdefault(su, set()).add(tv)
            last_nodes = [n for n in snodes if len([s for s in succs.get(n, set()) if s in snodes]) == 0]
            for ln in last_nodes:
                # Avoid duplicate edge
                if {"sourceNodeID": ln, "targetNodeID": "end"} not in sheet_edges:
                    sheet_edges.append({"sourceNodeID": ln, "targetNodeID": "end"})

        # If no END (not terminating) and we have a next sheet, add sheet-outputs with nextSheet field
        next_sheet = sub_next.get(sname)
        if not (need_end or (sname in subgraphs_end_on_sheet)) and next_sheet:
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
        # FINAL PASS LAYOUT for subgraph sheet
        try:
            s_ids = [n.get("id") for n in sheet_nodes]
            s_pairs = [(e.get("sourceNodeID"), e.get("targetNodeID")) for e in sheet_edges]
            s_layout = place_nodes(s_ids, s_pairs)
            for n in sheet_nodes:
                nid = n.get("id")
                xy = s_layout.get(nid)
                if xy:
                    n.setdefault("meta", {}).setdefault("position", {})
                    n["meta"]["position"] = {"x": xy[0], "y": xy[1]}
            # Center the middle node of the longest path in this sheet at (0,0)
            from collections import defaultdict as _dd
            g2 = _dd(list)
            for u, v in s_pairs:
                g2[u].append(v)
            best2: list[str] = []
            def _dfs2(u: str, path: list[str]):
                nonlocal best2
                if len(path) > len(best2):
                    best2 = path[:]
                for v in g2.get(u, []):
                    if v not in path:
                        _dfs2(v, path + [v])
            # prefer sheet-inputs as start if present
            start_candidates = [i for i in s_ids if i.startswith("sheet_inputs_")] or s_ids
            _dfs2(start_candidates[0], [start_candidates[0]])
            if best2:
                mid2 = best2[len(best2)//2]
                midn = next((nn for nn in sheet_nodes if nn.get("id") == mid2), None)
                if midn:
                    pos2 = midn.get("meta", {}).get("position", {})
                    cx2, cy2 = pos2.get("x", 0), pos2.get("y", 0)
                    dx2, dy2 = -cx2, -cy2
                    for nn in sheet_nodes:
                        p2 = nn.setdefault("meta", {}).setdefault("position", {})
                        p2["x"] = (p2.get("x", 0) + dx2)
                        p2["y"] = (p2.get("y", 0) + dy2)
        except Exception:
            pass

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
    """Build a two-sheet StateGraph with branching and export.
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
    sg.add_edge(START, "n1")
    sg.add_edge("n1", "n2")
    sg.add_edge("n3", "n5")
    sg.add_edge("n4", "n5")
    # Add a subgraph node n6 with two internal nodes s1->s2
    sg6 = StateGraph(dict)
    sg6.add_node("s1", _noop)
    sg6.add_node("s2", _noop)
    sg6.add_edge("s1", "s2")
    # Wrap as a callable runnable with a nested graph attribute for subgraph detection
    class SubRunner:
        def __init__(self, g): self.graph = g
        def __call__(self, state: dict, **kwargs): return state
    sub_runner = SubRunner(sg6)
    sg.add_node("n6", sub_runner)  # treated as subgraph by converter
    # Explicitly register subgraph for robust detection (RunnableCallable wrappers may hide attributes)
    try:
        setattr(sg, "_subgraphs", {**getattr(sg, "_subgraphs", {}), "n6": sg6})
    except Exception:
        sg._subgraphs = {"n6": sg6}
    # Connect main: n5 -> n6 (subgraph) -> END
    sg.add_edge("n5", "n6")
    sg.add_edge("n6", END)
    # Inject a minimal branches structure for converter to render condition node at n2
    class _Br:  # simple holder for .ends
        def __init__(self, ends: dict): self.ends = ends
    sg.branches = {
        "n2": {
            "if_out": _Br({"if_out": "n3"}),
            "else_out": _Br({"else_out": "n4"}),
        }
    }
    logger.debug('[LG2FG][TEST] main edges:', sg.edges)
    # Export
    logger.info('[LG2FG][TEST] exporting sample graph to flowgram files')
    main_doc, bundle_doc = langgraph2flowgram(sg)
    try:
        out_dir = "test_skill/diagram_dir"
        logger.info(f"[LG2FG][TEST] export complete (minimal). main and bundle written to: {out_dir}")
        logger.debug(f"[LG2FG][TEST] main nodes={len(main_doc.get('workFlow', {}).get('nodes', []))}, sheets={len((bundle_doc or {}).get('sheets', []))}")
    except Exception:
        pass
    # Build a simple subgraph report for the IPC response
    try:
        subgraphs_report = []
        # We know we created 'n6' with sg6. Build its topology summary
        sg6_nodes = list(getattr(sg6, 'nodes').keys())
        sg6_edges = [(u, v) for (u, v) in getattr(sg6, 'edges')]
        subgraphs_report.append({
            "id": "n6",
            "nodes": sg6_nodes,
            "edges": sg6_edges,
        })
    except Exception:
        subgraphs_report = []
    return {
        "ok": True,
        "out_dir": "test_skill/diagram_dir",
        "main_sheets_nodes": len(main_doc.get("workFlow", {}).get("nodes", [])),
        "bundle_sheets": len((bundle_doc or {}).get("sheets", [])),
        "subgraphs": subgraphs_report,
    }

