import json
from langgraph.graph import StateGraph, START, END
from agent.ec_skills.build_node import *
import importlib
from agent.ec_skills.llm_utils.llm_utils import node_maker
from gui.LoginoutGUI import Login
from utils.logger_helper import logger_helper as logger
import traceback
from app_context import AppContext


# Simulated function registry to map node types to actual Python functions.
# You need to populate this in your real implementation
function_registry = {
    "llm": build_llm_node,
    "basic": build_basic_node,
    "api": build_api_node,
    "loop": build_loop_node,
    "condition": build_condition_node,
    "tool": build_mcp_tool_calling_node,
    "group": build_group_node,
    "default": build_debug_node,
}

def evaluate_condition(state, conditions):
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

def make_condition_func(node_id, conditions, port_map):
    def condition_func(state):
        result = evaluate_condition(state, conditions)
        return list(port_map.keys())[0] if result else list(port_map.keys())[1]
    condition_func.__name__ = node_id
    return condition_func

def process_blocks(workflow, blocks, node_map, id_to_node, skill_name, owner, bp_manager, edges_in_block):
    # Process all blocks (nodes) within the group/loop
    for block in blocks:
        block_id = block["id"]
        node_map[block_id] = block_id
        id_to_node[block_id] = block

        node_type = block.get("type", "default")
        node_data = block.get("data", {})

        # Get the appropriate builder function from the registry
        builder_func = function_registry.get(node_type, build_debug_node)

        # Call the builder function with the node's data to get the final callable
        node_callable = builder_func(node_data, block_id, skill_name, owner, bp_manager)

        # Add the constructed node to the workflow
        workflow.add_node(block_id, node_callable)

        # Recursively process nested blocks if any
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
    flow = json.loads(flowgram_json) if isinstance(flowgram_json, str) else flowgram_json
    workflow = StateGraph(dict)
    node_map = {}
    id_to_node = {}

    skill_name = flowgram_json["name"]
    owner = flowgram_json["owner"]
    # find breakpoint manager of the dev task, since it will always be that.
    login: Login = AppContext.login
    tester = next((agent for agent in login.main_win.agents if "test engineer" in agent.card.title.lower()), None)

    bp_manager = tester.runner.bp_manager

    for node in flow["nodes"]:
        node_id = node["id"]
        node_type = node.get("type", "default")
        node_data = node.get("data", {})

        node_map[node_id] = node_id
        id_to_node[node_id] = node

        # Get the appropriate builder function from the registry
        builder_func = function_registry.get(node_type, build_debug_node)

        # Call the builder function with the node's data to get the final callable
        node_callable = builder_func(node_data, node_id, skill_name, owner, bp_manager)

        # Add the constructed node to the workflow
        workflow.add_node(node_id, node_callable)

        if node_type == "start":
            workflow.set_entry_point(node_id)
        if node_type in ["loop", "group"] and "blocks" in node:
            edges_in_block = node.get("edges", [])
            process_blocks(workflow, node["blocks"], node_map, id_to_node, skill_name, owner, bp_manager, edges_in_block)
    # Add edges
    for edge in flow["edges"]:
        source = node_map[edge["sourceNodeID"]]
        target = node_map[edge["targetNodeID"]]
        if target == "end":
            workflow.add_edge(source, END)
        else:
            workflow.add_edge(source, target)
    # Add conditional edges
    for node in flow["nodes"]:
        if node["type"] == "condition":
            node_id = node["id"]
            conditions = node["data"].get("conditions", [])
            outgoing_edges = [e for e in flow["edges"] if e["sourceNodeID"] == node_id]
            port_map = {}
            for edge in outgoing_edges:
                port = edge.get("sourcePortID")
                if port:
                    port_map[port] = edge["targetNodeID"]
            workflow.add_conditional_edges(
                node_id,
                make_condition_func(node_id, conditions, port_map),
                path_map=port_map
            )
    return workflow

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
