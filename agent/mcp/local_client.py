import os
import sys
import traceback
import httpx
import json

from agent.mcp.server.server import handle_sse, sse_handle_messages, meca_mcp_server, meca_sse, handle_streamable_http, lifespan
from agent.mcp.config import mcp_http_base, mcp_sse_url
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.session import ClientSession
from contextlib import asynccontextmanager


# ============================= now create global client ===========================
async def create_mcp_client():
    mcp_client = MultiServerMCPClient(
            {
                "E-Commerce Agents Service": {
                    # make sure you start your weather server on port 8000
                    "url": mcp_sse_url(),
                    "transport": "sse",
                }
            }
    )

    try:
        # NotImplementedError: As of langchain - mcp - adapters0.1.0, MultiServerMCPClient
        # cannot be used as a context manager(e.g., async with MultiServerMCPClient(...)).
        # Instead, you can do one of the following:
        # 1.
        # client = MultiServerMCPClient(...)
        # tools = await client.get_tools()
        # 2.
        # client = MultiServerMCPClient(...)
        # async with client.session(server_name) as session:
        # tools = await load_mcp_tools(session)

        # CORRECTED LINE: Pass server_name as a keyword argument
        # tools = await mcp_client.get_tools(server_name="E-Commerce Agents Service")
        # print("MCP client created and tools loaded successfully for E-Commerce Agents Service.")
        #
        # # You might want to store the loaded tools on the client object if they're needed later
        # mcp_client._loaded_tools = tools
        # tools = await mcp_client.get_tools()
        # print("MCP client created and tools loaded successfully.", tools)

        async with mcp_client.session("E-Commerce Agents Service") as session:
            print("MCP client session initing................")
            await session.initialize()
            # tools = await load_mcp_tools(session)
            print("MCP client created................")
            tools = await mcp_client.get_tools()
            print("MCP client created and tools loaded successfully.", tools)
            # return mcp_client

        return mcp_client

    except Exception as e:
        print(f"Error creating MCP client or loading tools: {e}")
        # Depending on your needs, you might re-raise the exception or return None
        raise
    # await mcp_client.__aenter__()
    # await mcp_client.connect_to_server_via_sse("http://127.0.0.1:4668/sse")
    # async with mcp_client.session("E-Commerce Agents Service") as session:
    #     tools = await load_mcp_tools(session)
    #     print("mcp client created................")
    # return mcp_client
@asynccontextmanager
async def create_sse_client():
    async with sse_client(mcp_sse_url()) as (read_stream, write_stream):
        # Add debug prints to check stream types
        print(f"Read stream type: {type(read_stream).__name__}")  # Should be MemoryObjectReceiveStream
        print(f"Write stream type: {type(write_stream).__name__}")  # Should be MemoryObjectSendStream
        print("before ClientSession  ", id(read_stream), id(write_stream))

        async with ClientSession(read_stream, write_stream) as session:
        # async with ClientSession(streams[0], streams[1]) as session:
            print("SSE client session initing................")
            await session.initialize()
            print("SSE client created................")
            yield session


@asynccontextmanager
async def create_streamable_http_client(url):
    # mcp_http_base()
    async with streamablehttp_client(url) as (read_stream, write_stream):
        # Add debug prints to check stream types
        print(f"Read stream type: {type(read_stream).__name__}")  # Should be MemoryObjectReceiveStream
        print(f"Write stream type: {type(write_stream).__name__}")  # Should be MemoryObjectSendStream
        print("before ClientSession  ", id(read_stream), id(write_stream))

        async with ClientSession(read_stream, write_stream) as session:
        # async with ClientSession(streams[0], streams[1]) as session:
            print("SSE client session initing................")
            await session.initialize()
            print("SSE client created................")
            yield session


async def local_mcp_list_tools(url):
    """
    获取MCP工具列表

    Args:
        url: MCP服务器URL，例如 mcp_http_base()

    Returns:
        ListToolsResult对象，包含tools属性

    Raises:
        Exception: 连接或获取工具列表失败
    """
    from utils.logger_helper import logger_helper as logger

    try:
        logger.debug(f"Connecting to MCP server at {url}")
        async with streamablehttp_client(url) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                logger.debug("Initializing MCP session...")
                await session.initialize()

                logger.debug("Listing tools...")
                tools_result = await session.list_tools()

                # 记录结果信息
                if hasattr(tools_result, 'tools'):
                    logger.debug(f"Retrieved {len(tools_result.tools)} tools")
                    if tools_result.tools:
                        logger.debug(f"First tool: {tools_result.tools[0].name if hasattr(tools_result.tools[0], 'name') else 'Unknown'}")
                else:
                    logger.debug(f"Tools result type: {type(tools_result)}")

                return tools_result

    except Exception as e:
        logger.error(f"Failed to list MCP tools from {url}: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise

async def local_mcp_call_tool(url, tool_name, arguments):
    # mcp_http_base()
    result = {}
    async with streamablehttp_client(url) as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()
            tools = await session.list_tools()
            result = await session.call_tool(tool_name, arguments)
            # await session.complete()
            return result


async def mcp_call_tool(tool_name, args):
    # async with mcp_client.session("E-Commerce Agents Service") as session:
    print(f"MCP client calling tool: {tool_name} with args: {args}")
    try:
        # Call the tool and get the raw response
        # response = await mcp_client.call_tool(tool_name, args)
        url = mcp_http_base()
        response = await local_mcp_call_tool(url,tool_name, args)
        print(f"Raw response type: {type(response)}")
        print(f"Raw response Err: {response.isError}   {response.content[0].text}")
        # print("response meta:", response.content[0].meta)

        # If the response is a CallToolResult with an error, return the error
        return response

    except Exception as e:
        error_msg = f"Error calling {tool_name}: {str(e)}"
        print(error_msg)
        return {"content": [{"type": "text", "text": error_msg}], "isError": True}