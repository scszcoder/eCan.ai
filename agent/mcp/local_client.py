from agent.mcp.config import mcp_http_base
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.session import ClientSession
from agent.mcp.streamablehttp_manager import Streamable_HTTP_Manager

import asyncio
import traceback
from utils.logger_helper import logger_helper as logger



class MCPClientManager:
    """Manages MCP client sessions and tool interactions."""

    def __init__(self):
        pass

    async def list_tools(self, url):
        """
        Lists available tools from an MCP server.

        Args:
            url: The URL of the MCP server (e.g., mcp_http_base()).

        Returns:
            A ListToolsResult object containing the 'tools' attribute.

        Raises:
            Exception: If connecting or listing tools fails.
        """
        try:
            logger.debug(f"Connecting to MCP server at {url} to list tools")
            async with streamablehttp_client(url) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    logger.debug("Initializing MCP session...")
                    await session.initialize()
                    logger.debug("Listing tools...")
                    tools_result = await session.list_tools()

                    if hasattr(tools_result, 'tools'):
                        logger.debug(f"Retrieved {len(tools_result.tools)} tools")
                    return tools_result
        except Exception as e:
            logger.error(f"Failed to list MCP tools from {url}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    async def call_tool(self, url, tool_name, arguments):
        """Calls a tool on an MCP server with robust session handling."""
        result = None
        try:
            # First, try using a persistent session for efficiency
            try:
                mgr = Streamable_HTTP_Manager.get(url)
                session = await mgr.session()
                result = await session.call_tool(tool_name, arguments)
                logger.debug(f"Tool call via persistent session succeeded for '{tool_name}'")
                return result
            except BaseException as mgr_err:
                logger.warning(f"Persistent session failed, falling back to ephemeral: {mgr_err}")
                # Fallback to a temporary (ephemeral) session
                async with streamablehttp_client(url, terminate_on_close=False) as streams:
                    async with ClientSession(streams[0], streams[1]) as session:
                        await session.initialize()
                        result = await session.call_tool(tool_name, arguments)
                        # Allow a brief moment for server-side cleanup before closing
                        await asyncio.sleep(0.05)
        except BaseException as e:
            # If a result was obtained but an error occurred during cleanup, prioritize the result
            if result is not None:
                logger.warning(f"Suppressed teardown error after tool result: {e}")
            else:
                logger.error(f"Ephemeral session tool call failed for '{tool_name}': {e}")
                raise
        return result
    
    async def close(self):
        """Closes the underlying persistent HTTP session manager."""
        logger.info("Closing persistent MCP client session...")
        try:
            # The manager is a singleton; get the instance and close it.
            url = mcp_http_base()
            manager_instance = Streamable_HTTP_Manager.get(url)
            await manager_instance.close()
            logger.info("✅ MCP client session closed successfully.")
        except Exception as e:
            logger.error(f"❌ Failed to close MCP client session: {e}")



# Create a singleton instance for managing MCP client operations
mcp_client_manager = MCPClientManager()

async def mcp_call_tool(tool_name, args):
    """Public function to call a tool, using the client manager."""
    logger.debug(f"MCP client calling tool: {tool_name} with args: {args}")
    response = None
    try:
        url = mcp_http_base()
        response = await mcp_client_manager.call_tool(url, tool_name, args)
        logger.debug(f"Raw response type: {type(response)}")
        return response
    except BaseException as e:
        if response is not None:
            # If a result was obtained but an error occurred during cleanup, prioritize the result
            logger.warning(f"Suppressed teardown error after successful tool call: {e}")
            return response

        # No response was obtained, so the error is critical
        error_msg = f"Error calling tool '{tool_name}': {e}"
        logger.error(error_msg)
        # Return a structured error message compatible with MCP tool results
        return {"content": [{"type": "text", "text": error_msg}], "isError": True}