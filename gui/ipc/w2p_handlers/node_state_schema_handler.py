import traceback
from typing import Any, Optional, Dict

from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from utils.logger_helper import logger_helper as logger

# Minimal JSON Schema for NodeState (Draft-07 compatible)
NODE_STATE_JSON_SCHEMA: Dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "urn:ecan:node-state-schema:v1",
    "title": "NodeState",
    "type": "object",
    "properties": {
        "input": {"type": "string"},
        "attachments": {"type": "array", "items": {"type": "object"}},
        "prompts": {"type": "array", "items": {"type": "object"}},
        "prompt_refs": {"type": "object"},
        "history": {"type": "array", "items": {"type": "object"}},
        "messages": {"type": "array", "items": {"type": "object"}},
        "threads": {"type": "array", "items": {"type": "object"}},
        "metadata": {"type": "object", "additionalProperties": True},
        "this_node": {"type": "string"},
        "attributes": {"type": "object", "additionalProperties": True},
        "result": {"type": "object"},
        "tool_input": {"type": "object"},
        "tool_result": {"type": "object"},
        "error": {"type": "string"},
        "retries": {"type": "integer"},
        "condition": {"type": "boolean"},
        "case": {"type": "string"},
        "goals": {"type": "array", "items": {"type": "object"}},
        "breakpoint": {"type": "boolean"}
    },
    "required": [],
    "additionalProperties": True,
}


@IPCHandlerRegistry.handler('skill_editor.get_node_state_schema')
def handle_get_node_state_schema(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Return the NodeState JSON Schema to the GUI.

    In future this can be made pluggable per project via params or environment.
    """
    try:
        logger.debug("[node_state_schema_handler] get_node_state_schema called")
        resp = {
            "schemaVersion": "1.0.0",
            "schema": NODE_STATE_JSON_SCHEMA,
            "uiSchema": {},
            "defaults": {}
        }
        return create_success_response(request, resp)
    except Exception as e:
        logger.error(f"[node_state_schema_handler] error: {e} {traceback.format_exc()}")
        return create_error_response(request, 'NODE_STATE_SCHEMA_ERROR', str(e))
