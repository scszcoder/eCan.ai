import os
import sys
import traceback
import httpx
import json

from agent.mcp.server.server import handle_sse, sse_handle_messages, meca_mcp_server, meca_sse, handle_streamable_http, lifespan
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
                    "url": "http://localhost:4668/sse/",
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
    # await mcp_client.connect_to_server_via_sse("http://localhost:4668/sse/")
    # async with mcp_client.session("E-Commerce Agents Service") as session:
    #     tools = await load_mcp_tools(session)
    #     print("mcp client created................")
    # return mcp_client
@asynccontextmanager
async def create_sse_client():
    async with sse_client("http://localhost:4668/sse/") as (read_stream, write_stream):
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
    # "http://localhost:4668/mcp/"
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
    # "http://localhost:4668/mcp/"
    tools = {}
    async with streamablehttp_client(url) as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()
            tools = await session.list_tools()
            # await session.complete()
            return tools

async def local_mcp_call_tool(url, tool_name, arguments):
    # "http://localhost:4668/mcp/"
    result = {}
    async with streamablehttp_client(url) as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            # await session.complete()
            return result