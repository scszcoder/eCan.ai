
import json
from langgraph.graph import StateGraph, END
from all_callables import process_chat, custom_greeting, read_attachments, debug_node

# Simulated function registry to map node types to actual Python functions.
# You need to populate this in your real implementation
function_registry = {
    "llm": process_chat,  # or whatever your llm function is
    "basic": custom_greeting,  # your actual callable
    "loop": read_attachments,  # depends how you handle loops
    "condition": debug_node,  # condition is handled separately
    "default": debug_node,  # fallback
}



# Dummy function for condition branching
# You should replace this by analyzing Flowgram's actual condition operators

def debug_condition_function(state):
    return "if_0"  # just always select first condition for testing


# Now the reverse: convert LangGraph back to Flowgram json
def find_longest_branch(edges, nodes):
    """Returns the longest path as a list of node ids."""
    from collections import defaultdict, deque
    graph = defaultdict(list)
    for edge in edges:
        graph[edge[0]].append(edge[1])

    longest = []
    visited = set()
    def dfs(path):
        nonlocal longest
        node = path[-1]
        if node in visited:  # Avoid cycles
            return
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

def place_nodes(stategraph):
    """Returns a dict: {node_id: (x, y)} for visual placement."""
    node_ids = list(stategraph.nodes.keys())
    edge_tuples = list(stategraph.edges)
    main_path = find_longest_branch(edge_tuples, node_ids)
    placement = {}
    x, y = 0, 0
    spacing = 600
    # Place main path nodes horizontally
    for node in main_path:
        placement[node] = (x, y)
        x += spacing
    # Place all other nodes below, in grid
    grid_x, grid_y = 0, spacing
    for node in node_ids:
        if node not in main_path:
            placement[node] = (grid_x, grid_y)
            grid_x += spacing
            if grid_x > 2400:
                grid_x = 0
                grid_y += spacing
    return placement

def langgraph2flowgram(stategraph):
    nodes = []
    edges = []
    id_map = {}
    # Use real node ids
    for node in stategraph.nodes:
        id_map[node] = node
    # Intelligent placement:
    placements = place_nodes(stategraph)
    for node in stategraph.nodes:
        x, y = placements[node]
        meta = {"position": {"x": x, "y": y}}
        original_data = getattr(stategraph.nodes[node].runnable, "flowgram_data", {})
        typ = getattr(stategraph.nodes[node].runnable, "flowgram_type", "basic")
        nodes.append({"id": node, "type": typ, "data": original_data, "meta": meta})

    for edge in stategraph.edges:
        source, target = edge
        source_id = id_map[source]
        target_id = id_map[target] if target != END else [n["id"] for n in nodes if n["type"] == "end"][0]
        edges.append({"sourceNodeID": source_id, "targetNodeID": target_id})

    for node, branches in stategraph.branches.items():
        source_id = id_map[node]
        for branch_name, branch_obj in branches.items():
            if branch_obj.ends:
                for key, target_node in branch_obj.ends.items():
                    target_id = id_map[target_node]
                    edges.append({"sourceNodeID": source_id, "targetNodeID": target_id, "sourcePortID": key})

    # 3. Placement: after nodes/edges are all gathered
    placements = place_nodes(list(id_map.keys()), edges)
    for node in stategraph.nodes:
        x, y = placements[node]
        meta = {"position": {"x": x, "y": y}}
        original_data = getattr(stategraph.nodes[node].runnable, "flowgram_data", {})
        typ = getattr(stategraph.nodes[node].runnable, "flowgram_type", "basic")
        nodes.append({"id": node, "type": typ, "data": original_data, "meta": meta})

    return json.dumps({"nodes": nodes, "edges": edges}, indent=2)

