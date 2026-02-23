"""
Self Tools - MCP tools for agent self-introspection.

Tools:
- describe_self: Returns structured JSON of agent description (skills, tasks)

Task management tools have been moved to agent/ec_tasks/task_mcp_tools.py.
Naming convention follows server.py and tool_schemas.py patterns.
"""

import json
import time
from typing import Any, Dict, List, Optional

import mcp.types as types
from mcp.types import TextContent

from agent.agent_service import get_agent_by_id
from app_context import AppContext
from utils.logger_helper import logger_helper as logger, get_traceback


# ==================== Tool Implementations ====================

def describe_self(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a structured JSON description of the agent including all skills and tasks.
    
    Args:
        mainwin: Main window instance
        config: Configuration dict with optional 'agent_id'
        
    Returns:
        Structured dict with agent description:
        {
            "agent_id": str,
            "agent_name": str,
            "agent_description": str,
            "skills": [
                {
                    "id": str,
                    "name": str,
                    "description": str,
                    "type": str,
                    "enabled": bool
                }
            ],
            "tasks": {
                "running": [...],
                "pending": [...],
                "completed": [...],
                "failed": [...]
            },
            "status": str,
            "timestamp": int
        }
    """
    try:
        agent_id = config.get("agent_id", "")
        
        # Get agent by ID or use first available agent
        agent = None
        if agent_id:
            agent = get_agent_by_id(agent_id)
        else:
            # Try to get from mainwin
            if hasattr(mainwin, 'agents') and mainwin.agents:
                agent = mainwin.agents[0]
                agent_id = getattr(getattr(agent, 'card', None), 'id', 'unknown')
        
        if not agent:
            return {
                "error": f"Agent not found: {agent_id}",
                "timestamp": int(time.time() * 1000)
            }
        
        # Build agent description
        result = {
            "agent_id": agent_id,
            "agent_name": getattr(getattr(agent, 'card', None), 'name', 'Unknown'),
            "agent_description": getattr(getattr(agent, 'card', None), 'description', ''),
            "skills": [],
            "tasks": {
                "running": [],
                "pending": [],
                "completed": [],
                "failed": []
            },
            "status": getattr(agent, 'status', 'unknown'),
            "timestamp": int(time.time() * 1000)
        }
        
        # Collect skills information
        skills = getattr(agent, 'skills', []) or []
        for skill in skills:
            skill_info = {
                "id": getattr(skill, 'id', '') or getattr(skill, 'name', 'unknown'),
                "name": getattr(skill, 'name', 'Unknown'),
                "description": getattr(skill, 'description', ''),
                "type": getattr(skill, 'type', 'unknown'),
                "enabled": getattr(skill, 'enabled', True)
            }
            # Add skill tags if available
            if hasattr(skill, 'tags') and skill.tags:
                skill_info["tags"] = skill.tags
            result["skills"].append(skill_info)
        
        # Collect tasks information
        tasks = getattr(agent, 'tasks', []) or []
        for task in tasks:
            task_info = {
                "id": getattr(task, 'id', 'unknown'),
                "name": getattr(task, 'name', 'Unknown'),
                "skill_name": getattr(getattr(task, 'skill', None), 'name', 'unknown'),
                "state": "unknown",
                "created_at": None,
                "run_id": getattr(task, 'run_id', None)
            }
            
            # Get task state
            task_status = getattr(task, 'status', None)
            if task_status:
                state = getattr(task_status, 'state', None)
                if state:
                    task_info["state"] = state.value if hasattr(state, 'value') else str(state)
            
            # Get schedule info if available
            schedule = getattr(task, 'schedule', None)
            if schedule:
                task_info["schedule"] = {
                    "next_run": getattr(schedule, 'next_run', None),
                    "repeat_type": getattr(schedule, 'repeat_type', None)
                }
            
            # Categorize task by state
            state_str = task_info["state"].lower() if task_info["state"] else "unknown"
            if state_str in ("working", "running", "in_progress"):
                result["tasks"]["running"].append(task_info)
            elif state_str in ("pending", "scheduled", "queued", "unknown"):
                result["tasks"]["pending"].append(task_info)
            elif state_str in ("completed", "done", "success"):
                result["tasks"]["completed"].append(task_info)
            elif state_str in ("failed", "error", "canceled"):
                result["tasks"]["failed"].append(task_info)
            else:
                result["tasks"]["pending"].append(task_info)
        
        logger.info(f"[describe_self] Agent {agent_id}: {len(result['skills'])} skills, "
                   f"{len(result['tasks']['running'])} running tasks")
        return result
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorDescribeSelf")
        logger.error(err_trace)
        return {
            "error": err_trace,
            "timestamp": int(time.time() * 1000)
        }


# ==================== Tool Schema Functions ====================

def add_describe_self_tool_schema(tool_schemas: List[types.Tool]) -> None:
    """Add describe_self tool schema to the tool schemas list."""
    tool_schema = types.Tool(_meta={"run_in_cloud": False},
        name="describe_self",
        description=(
            "<category>Agent</category><sub-category>Self</sub-category>"
            "Get a structured JSON description of the agent including all skills (with descriptions) "
            "and all tasks (running, pending, completed, failed). Useful for agent self-introspection "
            "and capability discovery."
        ),
        inputSchema={
            "type": "object",
            "required": [],
            "properties": {
                "input": {
                    "type": "object",
                    "required": [],
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "Agent ID to describe. If not provided, uses the first available agent."
                        }
                    }
                }
            }
        }
    )
    tool_schemas.append(tool_schema)


# ==================== Async Wrappers for Server ====================

async def async_describe_self(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for describe_self tool."""
    try:
        input_config = args.get('input', {})
        result = describe_self(mainwin, input_config)
        
        msg = f"Agent description retrieved successfully"
        if "error" in result:
            msg = f"Error: {result['error']}"
        
        text_result = TextContent(type="text", text=msg)
        text_result.meta = {"agent_description": result}
        return [text_result]
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncDescribeSelf")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]
