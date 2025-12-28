"""
Azure Utils MCP Tools

Provides MCP tools for Azure cost monitoring and emergency shutdown.
"""

from agent.mcp.server.azure_utils.azure_tools import (
    azure_read_billing,
    azure_shutdown,
    add_azure_read_billing_tool_schema,
    add_azure_shutdown_tool_schema,
)

__all__ = [
    'azure_read_billing',
    'azure_shutdown',
    'add_azure_read_billing_tool_schema',
    'add_azure_shutdown_tool_schema',
]
