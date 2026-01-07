"""
Node Placement Algorithm for Skill Editor

Provides automatic layout for flowgram nodes to avoid overlapping
and tangled edges. Uses a Sugiyama-style layered DAG placement algorithm.

Based on the placement algorithm in agent/ec_skills/langgraph2flowgram.py
"""

from typing import Dict, List, Tuple, Set, Optional
from collections import defaultdict, deque


# ------------------------------
# Placement configuration
# ------------------------------
PLACEMENT_CFG = {
    # Node dimensions (default canvas node size)
    "node_width": 200,
    "node_height": 134,
    # Minimum margin between nodes (30px on each side = 60px total between nodes)
    "margin_x": 60,  # 30px margin on each side
    "margin_y": 60,  # 30px margin on each side
    # Baseline Y for the main/longest path
    "baseline_y": 200,
    # Starting X position
    "start_x": 100,
}

# Node type specific sizes (width, height)
NODE_SIZES = {
    "loop": (570, 345),
    "condition": (300, 200),  # Base size; add 27px height per elseif branch
    "start": (100, 50),
    "end": (100, 50),
    "block-start": (80, 40),
    "block-end": (80, 40),
    # Default for other nodes
    "default": (200, 134),
}

# Height added per elseif branch in condition nodes
CONDITION_ELSEIF_HEIGHT = 27

# Extra margin for container nodes like loop (in addition to base margin)
CONTAINER_MARGIN = 30

# Minimum margin around all nodes (all 4 sides)
NODE_MARGIN = 30

# Internal layout config for loop nodes
LOOP_INTERNAL_CFG = {
    # Usable area inside loop node (relative to loop's top-left)
    "x_start": 120,      # Left boundary of usable area
    "x_end": 450,        # Right boundary of usable area  
    "y_start": 178,      # Top boundary of usable area
    # Spacing between internal nodes (node width + 2*margin for both sides)
    "node_spacing_x": 200 + 2 * 30,  # 260px (node width 200 + 30 margin each side)
    "node_spacing_y": 134 + 2 * 30,  # 194px (node height 134 + 30 margin each side)
    # Block marker positions
    "block_start_x": 30,
    "block_start_y": 0,
    "block_end_x": 450,
    "block_end_y": 16,
}


def get_node_size(node_type: str) -> Tuple[int, int]:
    """Get the size (width, height) for a node type."""
    return NODE_SIZES.get(node_type, NODE_SIZES["default"])


def compute_horizontal_step() -> int:
    """Compute horizontal step between layers"""
    return PLACEMENT_CFG["node_width"] + PLACEMENT_CFG["margin_x"]


def compute_vertical_step() -> int:
    """Compute vertical step between nodes in same layer"""
    return PLACEMENT_CFG["node_height"] + PLACEMENT_CFG["margin_y"]


def find_longest_path(edges: List[Tuple[str, str]], nodes: List[str]) -> List[str]:
    """
    Find the longest path in the DAG.
    Returns the longest path as a list of node ids.
    """
    graph = defaultdict(list)
    for src, tgt in edges:
        graph[src].append(tgt)
    
    longest = []
    
    def dfs(path: List[str]):
        nonlocal longest
        node = path[-1]
        if len(path) > len(longest):
            longest = path[:]
        for neighbor in graph[node]:
            if neighbor not in path:
                dfs(path + [neighbor])
    
    # Find source nodes (no incoming edges)
    all_targets = set(tgt for _, tgt in edges)
    sources = [n for n in nodes if n not in all_targets]
    
    # If no sources found, try all nodes
    if not sources:
        sources = nodes
    
    for source in sources:
        dfs([source])
    
    return longest


def detect_back_edges(
    nodes: List[str],
    edges: List[Tuple[str, str]]
) -> Set[Tuple[str, str]]:
    """
    Detect back-edges via DFS to break cycles.
    Returns set of back-edges that should be ignored for layering.
    """
    adj = defaultdict(list)
    for src, tgt in edges:
        adj[src].append(tgt)
    
    temp_mark: Set[str] = set()
    perm_mark: Set[str] = set()
    back_edges: Set[Tuple[str, str]] = set()
    
    def dfs(u: str):
        if u in perm_mark:
            return
        if u in temp_mark:
            return
        temp_mark.add(u)
        for v in adj.get(u, []):
            if v in temp_mark:
                back_edges.add((u, v))
            else:
                dfs(v)
        temp_mark.remove(u)
        perm_mark.add(u)
    
    for n in nodes:
        dfs(n)
    
    return back_edges


def topological_sort(
    nodes: List[str],
    edges: List[Tuple[str, str]]
) -> List[str]:
    """
    Perform topological sort using Kahn's algorithm.
    Returns nodes in topological order.
    """
    adj = defaultdict(list)
    indegree = {n: 0 for n in nodes}
    
    for src, tgt in edges:
        if src in indegree and tgt in indegree:
            adj[src].append(tgt)
            indegree[tgt] += 1
    
    queue = deque([n for n in nodes if indegree[n] == 0])
    result = []
    
    while queue:
        u = queue.popleft()
        result.append(u)
        for v in adj[u]:
            indegree[v] -= 1
            if indegree[v] == 0:
                queue.append(v)
    
    # Append any remaining nodes (in case of cycles)
    seen = set(result)
    for n in nodes:
        if n not in seen:
            result.append(n)
    
    return result


def assign_layers(
    nodes: List[str],
    edges: List[Tuple[str, str]],
    topo_order: List[str]
) -> Dict[str, int]:
    """
    Assign layers to nodes using longest-path layering.
    Layer 0 is the leftmost (start), higher layers are to the right.
    """
    adj = defaultdict(list)
    for src, tgt in edges:
        adj[src].append(tgt)
    
    layer = {n: 0 for n in nodes}
    
    # Forward pass: assign layers based on predecessors
    for u in topo_order:
        for v in adj[u]:
            if v in layer:
                layer[v] = max(layer[v], layer[u] + 1)
    
    # Stabilization pass: ensure layer[v] >= layer[u] + 1 for all edges
    for _ in range(len(nodes)):
        changed = False
        for src, tgt in edges:
            if src in layer and tgt in layer:
                need = layer[src] + 1
                if layer[tgt] < need:
                    layer[tgt] = need
                    changed = True
        if not changed:
            break
    
    return layer


def order_nodes_in_layers(
    nodes: List[str],
    edges: List[Tuple[str, str]],
    layer_assignment: Dict[str, int],
    main_path: List[str]
) -> Dict[int, List[str]]:
    """
    Order nodes within each layer using barycenter heuristic.
    Main path nodes are prioritized to stay on the baseline.
    """
    # Group nodes by layer
    by_layer: Dict[int, List[str]] = defaultdict(list)
    for n in nodes:
        by_layer[layer_assignment[n]].append(n)
    
    # Build predecessor map
    preds: Dict[str, List[str]] = defaultdict(list)
    for src, tgt in edges:
        preds[tgt].append(src)
    
    # Initial x positions by layer (for barycenter calculation)
    hstep = compute_horizontal_step()
    x_pos = {n: layer_assignment[n] * hstep for n in nodes}
    
    main_path_set = set(main_path)
    
    # Order each layer
    for layer_idx in sorted(by_layer.keys()):
        arr = by_layer[layer_idx]
        
        def barycenter(n: str) -> float:
            ps = preds.get(n, [])
            if not ps:
                return -1.0
            return sum(x_pos[p] for p in ps if p in x_pos) / len(ps)
        
        def sort_key(n: str) -> Tuple[int, float, str]:
            # Main path nodes come first (lower priority value)
            is_main = 0 if n in main_path_set else 1
            return (is_main, barycenter(n), n)
        
        arr.sort(key=sort_key)
        by_layer[layer_idx] = arr
    
    return dict(by_layer)


def place_nodes(
    node_ids: List[str],
    edge_tuples: List[Tuple[str, str]],
    node_types: Optional[Dict[str, str]] = None
) -> Dict[str, Tuple[int, int]]:
    """
    The main placement algorithm.
    
    Uses Sugiyama-style layered DAG placement:
    1. Detect and remove back-edges (break cycles)
    2. Topological sort
    3. Assign layers (longest-path layering)
    4. Order nodes within layers (barycenter heuristic)
    5. Assign X/Y coordinates with variable spacing based on node sizes
    
    Args:
        node_ids: List of node IDs
        edge_tuples: List of (source, target) edge tuples
        node_types: Optional dict mapping node_id to node type (for size-aware placement)
        
    Returns:
        Dict mapping node_id to (x, y) position tuple
    """
    if not node_ids:
        return {}
    
    nodes = list(node_ids)
    node_set = set(nodes)
    node_types = node_types or {}
    
    # Filter edges to only those within our node set
    filtered_edges = [(src, tgt) for src, tgt in edge_tuples 
                      if src in node_set and tgt in node_set]
    
    # Handle single node case
    if len(nodes) == 1:
        return {nodes[0]: (PLACEMENT_CFG["start_x"], PLACEMENT_CFG["baseline_y"])}
    
    # Handle no edges case - arrange in a line
    if not filtered_edges:
        hstep = compute_horizontal_step()
        return {n: (PLACEMENT_CFG["start_x"] + i * hstep, PLACEMENT_CFG["baseline_y"]) 
                for i, n in enumerate(nodes)}
    
    # Step 1: Detect back-edges
    back_edges = detect_back_edges(nodes, filtered_edges)
    dag_edges = [(src, tgt) for src, tgt in filtered_edges 
                 if (src, tgt) not in back_edges]
    
    # Step 2: Topological sort
    topo_order = topological_sort(nodes, dag_edges)
    
    # Step 3: Assign layers
    layer_assignment = assign_layers(nodes, dag_edges, topo_order)
    
    # Step 4: Find main path and order nodes
    main_path = find_longest_path(dag_edges, nodes)
    by_layer = order_nodes_in_layers(nodes, dag_edges, layer_assignment, main_path)
    
    # Step 5: Assign coordinates with variable spacing based on node sizes
    margin_x = PLACEMENT_CFG["margin_x"]
    vstep = compute_vertical_step()
    baseline_y = PLACEMENT_CFG["baseline_y"]
    start_x = PLACEMENT_CFG["start_x"]
    
    main_path_set = set(main_path)
    
    x_pos: Dict[str, int] = {}
    y_pos: Dict[str, int] = {}
    
    # Compute cumulative X positions based on actual node widths in each layer
    layer_x_start: Dict[int, int] = {}
    current_x = start_x
    
    for layer_idx in sorted(by_layer.keys()):
        layer_x_start[layer_idx] = current_x
        
        # Find the widest node in this layer and check for container nodes
        layer_nodes = by_layer[layer_idx]
        max_width = 0
        has_container = False
        for n in layer_nodes:
            ntype = node_types.get(n, "default")
            width, _ = get_node_size(ntype)
            max_width = max(max_width, width)
            if ntype in ("loop", "condition"):
                has_container = True
        
        # Add extra margin for container nodes
        extra_margin = CONTAINER_MARGIN if has_container else 0
        
        # Move to next layer position
        current_x += max_width + margin_x + extra_margin
    
    for layer_idx in sorted(by_layer.keys()):
        arr = by_layer[layer_idx]
        x = layer_x_start[layer_idx]
        
        # Separate main path nodes and others
        main_in_layer = [n for n in arr if n in main_path_set]
        others = [n for n in arr if n not in main_path_set]
        
        # Place main path nodes on baseline
        for n in main_in_layer:
            x_pos[n] = x
            y_pos[n] = baseline_y
        
        # Place other nodes above and below baseline
        if others:
            # Alternate above and below
            above_offset = 1
            below_offset = 1
            place_above = True
            
            for n in others:
                x_pos[n] = x
                if place_above:
                    y_pos[n] = baseline_y - above_offset * vstep
                    above_offset += 1
                else:
                    y_pos[n] = baseline_y + below_offset * vstep
                    below_offset += 1
                place_above = not place_above
    
    # Build final placement
    placement = {n: (x_pos[n], y_pos[n]) for n in nodes}
    
    return placement


def apply_placement_to_flowgram(flowgram_dict: Dict) -> Dict:
    """
    Apply automatic placement to a flowgram dictionary.
    
    Args:
        flowgram_dict: Flowgram with nodes and edges
        
    Returns:
        Updated flowgram with node positions set
    """
    nodes = flowgram_dict.get("nodes", [])
    edges = flowgram_dict.get("edges", [])
    
    if not nodes:
        return flowgram_dict
    
    # Extract node IDs and edge tuples
    node_ids = [n.get("id") for n in nodes if n.get("id")]
    edge_tuples = [(e.get("source"), e.get("target")) 
                   for e in edges 
                   if e.get("source") and e.get("target")]
    
    # Compute placement
    placement = place_nodes(node_ids, edge_tuples)
    
    # Apply placement to nodes
    for node in nodes:
        node_id = node.get("id")
        if node_id and node_id in placement:
            x, y = placement[node_id]
            if "position" not in node:
                node["position"] = {}
            node["position"]["x"] = x
            node["position"]["y"] = y
    
    return flowgram_dict


def layout_flowgram_nodes(
    nodes: List[Dict],
    edges: List[Dict]
) -> List[Dict]:
    """
    Compute and apply layout to a list of node dictionaries.
    
    Args:
        nodes: List of node dicts with 'id' field
        edges: List of edge dicts with 'source' and 'target' fields
        
    Returns:
        Updated nodes list with positions set
    """
    if not nodes:
        return nodes
    
    # Extract IDs and edges
    node_ids = [n.get("id") for n in nodes if n.get("id")]
    edge_tuples = [(e.get("source"), e.get("target")) 
                   for e in edges 
                   if e.get("source") and e.get("target")]
    
    # Compute placement
    placement = place_nodes(node_ids, edge_tuples)
    
    # Apply to nodes
    for node in nodes:
        node_id = node.get("id")
        if node_id and node_id in placement:
            x, y = placement[node_id]
            node["position"] = {"x": x, "y": y}
    
    return nodes
