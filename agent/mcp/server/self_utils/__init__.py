"""
Self Utils Module - Tools for agent self-introspection and management.

This module provides MCP tools for:
- describe_self: Get structured agent description (agents, skills, tasks, tools, knowledge_base, prompts, llm, network, diagnostics)
- diagnose_llm: Run LLM connection diagnostic test
- create_agent: Create a new agent
- delete_agent: Delete an existing agent
- find_skill: Search for skills (local + market)
- open_channel: Open a communication channel
- close_channel: Close a communication channel

Task management tools have been moved to agent/ec_tasks/task_mcp_tools.py.
"""

from .self_tools import (
    describe_self,
    diagnose_llm,
    create_agent,
    delete_agent,
    find_skill,
    open_channel,
    close_channel,
    add_describe_self_tool_schema,
    add_diagnose_llm_tool_schema,
    add_create_agent_tool_schema,
    add_delete_agent_tool_schema,
    add_find_skill_tool_schema,
    add_open_channel_tool_schema,
    add_close_channel_tool_schema,
    async_describe_self,
    async_diagnose_llm,
    async_create_agent,
    async_delete_agent,
    async_find_skill,
    async_open_channel,
    async_close_channel,
)

__all__ = [
    "describe_self",
    "diagnose_llm",
    "create_agent",
    "delete_agent",
    "find_skill",
    "open_channel",
    "close_channel",
    "add_describe_self_tool_schema",
    "add_diagnose_llm_tool_schema",
    "add_create_agent_tool_schema",
    "add_delete_agent_tool_schema",
    "add_find_skill_tool_schema",
    "add_open_channel_tool_schema",
    "add_close_channel_tool_schema",
    "async_describe_self",
    "async_diagnose_llm",
    "async_create_agent",
    "async_delete_agent",
    "async_find_skill",
    "async_open_channel",
    "async_close_channel",
]
