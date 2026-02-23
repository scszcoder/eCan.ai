"""
Self Utils Module - Tools for agent self-introspection.

This module provides MCP tools for:
- describe_self: Get structured agent description (skills, tasks)

Task management tools have been moved to agent/ec_tasks/task_mcp_tools.py.
"""

from .self_tools import (
    describe_self,
    add_describe_self_tool_schema,
    async_describe_self,
)

__all__ = [
    "describe_self",
    "add_describe_self_tool_schema",
    "async_describe_self",
]
