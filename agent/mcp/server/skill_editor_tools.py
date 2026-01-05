"""
Skill Editor MCP Tools

MCP tool definitions for AI-assisted flowgram editing.
These tools allow the LLM agent to control the skill editor canvas.
"""

import mcp.types as types
from typing import List


def get_skill_editor_tool_schemas() -> List[types.Tool]:
    """Return all skill editor MCP tool schemas"""
    return [
        # Canvas State
        types.Tool(
            name="canvas_get_state",
            description="Get the current state of the skill editor canvas, including all nodes and edges.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        
        # Node Operations
        types.Tool(
            name="canvas_add_node",
            description="Add a new node to the skill editor canvas. Available node types: llm, code, http, condition, loop, variable, start, end, mcp, human_input.",
            inputSchema={
                "type": "object",
                "properties": {
                    "nodeType": {
                        "type": "string",
                        "description": "Type of node to add (e.g., 'llm', 'code', 'http', 'condition', 'loop', 'variable', 'start', 'end', 'mcp', 'human_input')"
                    },
                    "position": {
                        "type": "object",
                        "description": "Position on the canvas",
                        "properties": {
                            "x": {"type": "number", "description": "X coordinate"},
                            "y": {"type": "number", "description": "Y coordinate"}
                        },
                        "required": ["x", "y"]
                    },
                    "label": {
                        "type": "string",
                        "description": "Display label for the node"
                    },
                    "config": {
                        "type": "object",
                        "description": "Node-specific configuration (varies by node type)"
                    }
                },
                "required": ["nodeType", "position"]
            }
        ),
        
        types.Tool(
            name="canvas_remove_node",
            description="Remove a node from the canvas by its ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "nodeId": {
                        "type": "string",
                        "description": "ID of the node to remove"
                    }
                },
                "required": ["nodeId"]
            }
        ),
        
        types.Tool(
            name="canvas_update_node",
            description="Update an existing node's configuration or position.",
            inputSchema={
                "type": "object",
                "properties": {
                    "nodeId": {
                        "type": "string",
                        "description": "ID of the node to update"
                    },
                    "label": {
                        "type": "string",
                        "description": "New display label"
                    },
                    "position": {
                        "type": "object",
                        "description": "New position",
                        "properties": {
                            "x": {"type": "number"},
                            "y": {"type": "number"}
                        }
                    },
                    "config": {
                        "type": "object",
                        "description": "Updated configuration"
                    }
                },
                "required": ["nodeId"]
            }
        ),
        
        # Edge Operations
        types.Tool(
            name="canvas_add_edge",
            description="Add an edge (connection) between two nodes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "sourceNodeId": {
                        "type": "string",
                        "description": "ID of the source node"
                    },
                    "targetNodeId": {
                        "type": "string",
                        "description": "ID of the target node"
                    },
                    "sourceHandle": {
                        "type": "string",
                        "description": "Source port/handle ID (optional)"
                    },
                    "targetHandle": {
                        "type": "string",
                        "description": "Target port/handle ID (optional)"
                    },
                    "label": {
                        "type": "string",
                        "description": "Edge label (optional, useful for condition branches)"
                    }
                },
                "required": ["sourceNodeId", "targetNodeId"]
            }
        ),
        
        types.Tool(
            name="canvas_remove_edge",
            description="Remove an edge from the canvas by its ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "edgeId": {
                        "type": "string",
                        "description": "ID of the edge to remove"
                    }
                },
                "required": ["edgeId"]
            }
        ),
        
        # Flowgram Operations
        types.Tool(
            name="canvas_create_flowgram",
            description="Create a new empty flowgram with the given name.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name for the new flowgram"
                    },
                    "description": {
                        "type": "string",
                        "description": "Description of what the flowgram does"
                    }
                },
                "required": ["name"]
            }
        ),
        
        types.Tool(
            name="canvas_clear",
            description="Clear all nodes and edges from the canvas. Use with caution.",
            inputSchema={
                "type": "object",
                "properties": {
                    "confirm": {
                        "type": "boolean",
                        "description": "Must be true to confirm clearing"
                    }
                },
                "required": ["confirm"]
            }
        ),
        
        # Run Controls
        types.Tool(
            name="flowgram_run",
            description="Start running the current flowgram.",
            inputSchema={
                "type": "object",
                "properties": {
                    "input": {
                        "type": "object",
                        "description": "Input data for the flowgram run"
                    }
                },
                "required": []
            }
        ),
        
        types.Tool(
            name="flowgram_step",
            description="Execute a single step in the flowgram (step debugging).",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        
        types.Tool(
            name="flowgram_pause",
            description="Pause the currently running flowgram.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        
        types.Tool(
            name="flowgram_resume",
            description="Resume a paused flowgram.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        
        types.Tool(
            name="flowgram_stop",
            description="Stop the currently running flowgram.",
            inputSchema={
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Reason for stopping"
                    }
                },
                "required": []
            }
        ),
    ]


# Tool name to handler mapping (to be implemented)
SKILL_EDITOR_TOOL_HANDLERS = {
    "canvas_get_state": "handle_canvas_get_state",
    "canvas_add_node": "handle_canvas_add_node",
    "canvas_remove_node": "handle_canvas_remove_node",
    "canvas_update_node": "handle_canvas_update_node",
    "canvas_add_edge": "handle_canvas_add_edge",
    "canvas_remove_edge": "handle_canvas_remove_edge",
    "canvas_create_flowgram": "handle_canvas_create_flowgram",
    "canvas_clear": "handle_canvas_clear",
    "flowgram_run": "handle_flowgram_run",
    "flowgram_step": "handle_flowgram_step",
    "flowgram_pause": "handle_flowgram_pause",
    "flowgram_resume": "handle_flowgram_resume",
    "flowgram_stop": "handle_flowgram_stop",
}
