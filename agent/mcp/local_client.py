from agent.mcp.config import mcp_http_base
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.session import ClientSession
from agent.mcp.streamablehttp_manager import Streamable_HTTP_Manager

import asyncio
import traceback
from utils.logger_helper import logger_helper as logger
from agent.ec_skills.system_proxy import create_mcp_httpx_client



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
            async with streamablehttp_client(url, httpx_client_factory=create_mcp_httpx_client) as streams:
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

    async def call_tool(self, url, tool_name, arguments, timeout: float = 60.0):
        """Calls a tool on an MCP server with robust session handling.
        
        Args:
            url: MCP server URL
            tool_name: Name of the tool to call
            arguments: Tool arguments
            timeout: Timeout in seconds (default 60s)
        """
        result = None
        try:
            # First, try using a persistent session for efficiency
            try:
                mgr = Streamable_HTTP_Manager.get(url)
                session = await asyncio.wait_for(mgr.session(), timeout=timeout)
                result = await asyncio.wait_for(
                    session.call_tool(tool_name, arguments),
                    timeout=timeout
                )
                logger.debug(f"Tool call via persistent session succeeded for '{tool_name}'")
                return result
            except asyncio.TimeoutError:
                logger.warning(f"Persistent session timed out for '{tool_name}', falling back to ephemeral")
            except BaseException as mgr_err:
                logger.warning(f"Persistent session failed, falling back to ephemeral: {mgr_err}")
            
            # Fallback to a temporary (ephemeral) session
            async with streamablehttp_client(url, terminate_on_close=False, httpx_client_factory=create_mcp_httpx_client) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await asyncio.wait_for(session.initialize(), timeout=timeout)
                    result = await asyncio.wait_for(
                        session.call_tool(tool_name, arguments),
                        timeout=timeout
                    )
                    # Allow a brief moment for server-side cleanup before closing
                    await asyncio.sleep(0.05)
        except asyncio.TimeoutError:
            logger.error(f"Tool call timed out for '{tool_name}' after {timeout}s")
            raise
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
        except (RuntimeError, Exception) as e:
            # Handle both RuntimeError from task group issues and other exceptions
            if "cancel scope" in str(e) or "different task" in str(e):
                logger.debug(f"MCP client session close: Task group exit error (expected during shutdown): {e}")
            else:
                logger.warning(f"MCP client session close: Unexpected error: {e}")
            # Don't re-raise to avoid breaking the shutdown process



# Create a singleton instance for managing MCP client operations
mcp_client_manager = MCPClientManager()

async def mcp_call_tool(tool_name, args, timeout: float = 60.0):
    """Public function to call a tool, using the client manager.
    
    Args:
        tool_name: Name of the MCP tool to call
        args: Tool arguments
        timeout: Timeout in seconds (default 60s). Caller should specify appropriate
                 timeout based on the tool's expected execution time.
    """
    logger.debug(f"MCP client calling tool: {tool_name} with args: {args}, timeout: {timeout}s")
    response = None
    try:
        url = mcp_http_base()
        response = await mcp_client_manager.call_tool(url, tool_name, args, timeout=timeout)
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