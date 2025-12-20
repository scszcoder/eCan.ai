"""
Chat Utils Module - MCP tools for inter-agent and agent-human communication.

This module provides MCP tools for:
- send_chat: Send a chat message to another agent or agent group
- list_chat_agents: List available agents for chat
- get_chat_history: Get chat history for a conversation

These tools enable agents to communicate with each other as part of
workflow design or when instructed by prompts.
"""

from agent.mcp.server.chat_utils.chat_tools import (
    send_chat,
    list_chat_agents,
    get_chat_history,
    add_send_chat_tool_schema,
    add_list_chat_agents_tool_schema,
    add_get_chat_history_tool_schema,
    async_send_chat,
    async_list_chat_agents,
    async_get_chat_history,
)

__all__ = [
    "send_chat",
    "list_chat_agents",
    "get_chat_history",
    "add_send_chat_tool_schema",
    "add_list_chat_agents_tool_schema",
    "add_get_chat_history_tool_schema",
    "async_send_chat",
    "async_list_chat_agents",
    "async_get_chat_history",
]
