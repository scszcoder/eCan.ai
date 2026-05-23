from agent.mcp.config import mcp_http_base
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.session import ClientSession
from agent.mcp.streamablehttp_manager import Streamable_HTTP_Manager

import asyncio
import time as _time
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
            timeout: Timeout in seconds (default 60s). Caller can specify longer
                     timeout for slow operations like API queries.
        """
        # 2026-05-21 mt019 — per-tool fast-fail caps for hot-path tools.
        # Q&A bots calling ``rag_query`` block the customer's reply on
        # that single network call.  A 60s wait is unacceptable — the
        # customer has moved on by then.  Cap rag_query at 10s by
        # default (override via env ECAN_MCP_RAG_QUERY_TIMEOUT_S).  On
        # timeout the caller gets an empty rag_answer and the LLM
        # synthesises a generic reply from product context + history
        # — better UX than the customer waiting 60s for nothing.
        # Live trace (2026-05-21 21:04:03): a single 68s rag_query
        # failure added ~70s to one customer's wait.  Customer was
        # waiting 188s total.
        try:
            import os as _os
            _hot_caps = {
                "rag_query": float(_os.getenv("ECAN_MCP_RAG_QUERY_TIMEOUT_S", "10")),
            }
            _cap = _hot_caps.get(tool_name)
            if _cap is not None and _cap > 0 and timeout > _cap:
                timeout = _cap
        except Exception:
            pass
        result = None
        # Use shorter timeout only for getting persistent session (not for the actual call)
        persistent_session_timeout = min(5.0, timeout)
        
        try:
            # First, try using a persistent session for efficiency.
            # Hot-path tools that fan out concurrently (one call per customer)
            # are excluded — the shared streamable-HTTP ClientSession serializes
            # in-flight responses and stalls all-but-one caller until the 60s
            # timeout fires, even though each individual call only needs ~2s.
            # Confirmed in 22:39 / 00:10 multi-customer runs: 2 of 3 concurrent
            # rag_query calls timed out, then completed in ~2s via ephemeral.
            #
            # 2026-05-23 mt028 — DISABLED Tier 2 pool routing.  Live
            # trace 2026-05-22 14:33 showed the pool's workers spawn on
            # the FIRST caller's event loop, get cancelled when that
            # transient loop ends, and every subsequent call times out
            # via pool then falls back to ephemeral (doubles latency,
            # cascades into bot failures).  Re-enabling requires a
            # loop-aware pool (one pool per running loop, or detect
            # cancelled workers and re-spawn on the current loop).
            #
            # The pool code in ``agent/mcp/streamablehttp_pool.py`` is
            # kept intact and unit-tested; just the routing here is
            # commented out so production rag_query uses the
            # ephemeral path that mt019 hardened with the 10 s cap.
            #
            # from agent.mcp.streamablehttp_pool import (
            #     Streamable_HTTP_Pool as _RagPool,
            #     POOL_TOOLS as _POOL_TOOLS,
            # )
            # if tool_name in _POOL_TOOLS:
            #     try:
            #         pool = _RagPool.get(url)
            #         return await pool.call_tool(tool_name, arguments, timeout)
            #     except asyncio.TimeoutError:
            #         logger.warning(
            #             f"[MCP-RAG-POOL] tool={tool_name} timed out via pool, "
            #             f"falling back to ephemeral"
            #         )
            #     except Exception as pool_err:
            #         logger.warning(
            #             f"[MCP-RAG-POOL] tool={tool_name} pool path raised "
            #             f"({type(pool_err).__name__}: {pool_err}); falling "
            #             f"back to ephemeral"
            #         )
            _NO_PERSISTENT_SESSION = {"send_chat", "rag_query"}
            use_persistent_session = tool_name not in _NO_PERSISTENT_SESSION
            if use_persistent_session:
                try:
                    mgr = Streamable_HTTP_Manager.get(url)
                    # Quick check if persistent session is available
                    logger.debug(f"[MCP] Getting persistent session for '{tool_name}'...")
                    session = await asyncio.wait_for(mgr.session(), timeout=persistent_session_timeout)
                    logger.debug(f"[MCP] Got persistent session, calling tool '{tool_name}'...")
                    # Use full timeout for the actual tool call
                    result = await asyncio.wait_for(
                        session.call_tool(tool_name, arguments),
                        timeout=timeout
                    )
                    logger.debug(f"Tool call via persistent session succeeded for '{tool_name}'")
                    return result
                except asyncio.TimeoutError:
                    logger.warning(f"Persistent session timed out for '{tool_name}', falling back to ephemeral")
                    # Reset persistent session so next call can try to recreate it
                    Streamable_HTTP_Manager.reset()
                except BaseException as mgr_err:
                    logger.warning(f"Persistent session failed, falling back to ephemeral: {mgr_err}")
                    # Reset persistent session so next call can try to recreate it
                    Streamable_HTTP_Manager.reset()
            else:
                logger.debug(
                    f"[MCP] Skipping persistent session for hot-path '{tool_name}'; "
                    "using isolated ephemeral session"
                )
            
            # Fallback to a temporary (ephemeral) session
            # 2026-05-19: instrumented to break down the ~4 s mcp→lightrag
            # transport gap and ~2.8 s lightrag→result gap seen in customer
            # flood-test logs.  rag_query uses ephemeral because the persistent
            # session serialized concurrent fan-out calls under load (see
            # comment above).  Logging each ephemeral phase reveals whether
            # the cost is the streamablehttp_client open, MCP handshake
            # (session.initialize), the actual call_tool, or teardown.
            try:
                _t_ephem_start = _time.perf_counter()
                async with streamablehttp_client(
                    url,
                    terminate_on_close=False,
                    httpx_client_factory=create_mcp_httpx_client,
                ) as streams:
                    _t_streams_open = _time.perf_counter()
                    async with ClientSession(streams[0], streams[1]) as session:
                        _t_session_ctx = _time.perf_counter()
                        await asyncio.wait_for(session.initialize(), timeout=timeout)
                        _t_init_done = _time.perf_counter()
                        result = await asyncio.wait_for(
                            session.call_tool(tool_name, arguments),
                            timeout=timeout,
                        )
                        _t_call_done = _time.perf_counter()
                        # Allow a brief moment for server-side cleanup before closing
                        await asyncio.sleep(0.05)
                        _t_after_sleep = _time.perf_counter()
                    _t_session_closed = _time.perf_counter()
                _t_streams_closed = _time.perf_counter()
                logger.info(
                    f"[PERF][MCP-EPHEM] tool={tool_name} "
                    f"streams_open_ms={int((_t_streams_open - _t_ephem_start) * 1000)} "
                    f"session_ctx_ms={int((_t_session_ctx - _t_streams_open) * 1000)} "
                    f"initialize_ms={int((_t_init_done - _t_session_ctx) * 1000)} "
                    f"call_tool_ms={int((_t_call_done - _t_init_done) * 1000)} "
                    f"post_sleep_ms={int((_t_after_sleep - _t_call_done) * 1000)} "
                    f"session_close_ms={int((_t_session_closed - _t_after_sleep) * 1000)} "
                    f"streams_close_ms={int((_t_streams_closed - _t_session_closed) * 1000)} "
                    f"total_ms={int((_t_streams_closed - _t_ephem_start) * 1000)}"
                )
            except asyncio.TimeoutError:
                logger.error(f"Ephemeral session timed out for '{tool_name}' after {timeout}s")
                raise
            except BaseException as cleanup_err:
                # If we got a result but cleanup failed, log and return the result
                if result is not None:
                    # Check if it's a TaskGroup error during cleanup
                    if "TaskGroup" in str(cleanup_err) or "cancel scope" in str(cleanup_err):
                        logger.debug(f"Ephemeral session cleanup error (result obtained, ignoring): {cleanup_err}")
                    else:
                        logger.warning(f"Ephemeral session cleanup error (result obtained): {cleanup_err}")
                    # Return the result anyway since we got it successfully
                    return result
                else:
                    # No result obtained, this is a real error
                    logger.error(f"Ephemeral session tool call failed for '{tool_name}': {cleanup_err}")
                    raise
        except asyncio.TimeoutError:
            logger.error(f"Tool call timed out for '{tool_name}' after {timeout}s")
            raise
        except BaseException as e:
            # This should not be reached if the inner try-except handles everything correctly
            # But keep it as a safety net
            if result is not None:
                logger.warning(f"Suppressed outer teardown error after tool result: {e}")
            else:
                logger.error(f"Outer exception for '{tool_name}': {e}")
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

# Flag to track if persistent session needs warmup
_needs_warmup = False
_session_warmed_up = False

def mark_needs_warmup():
    """Mark that MCP session needs warmup on first call."""
    global _needs_warmup
    _needs_warmup = True

async def warmup_mcp_session():
    """Pre-initialize the persistent MCP session.
    
    This should be called from the same event loop where MCP calls will be made.
    """
    global _session_warmed_up, _needs_warmup
    if _session_warmed_up:
        logger.debug("MCP session already warmed up, skipping")
        return True
    
    _needs_warmup = False  # Clear the flag
    
    try:
        url = mcp_http_base()
        logger.info(f"Warming up MCP persistent session to {url}...")
        mgr = Streamable_HTTP_Manager.get(url)
        # Try to establish session with a reasonable timeout
        session = await asyncio.wait_for(mgr.session(), timeout=15.0)
        if session is not None:
            _session_warmed_up = True
            logger.info("✅ MCP persistent session warmed up successfully")
            return True
        else:
            logger.warning("MCP session warmup: session is None")
            return False
    except asyncio.TimeoutError:
        logger.warning("MCP session warmup timed out after 15s, will use ephemeral sessions")
        return False
    except Exception as e:
        logger.warning(f"MCP session warmup failed: {e}, will use ephemeral sessions")
        return False

async def mcp_call_tool(tool_name, args, timeout: float = 60.0):
    """Public function to call a tool, using the client manager.
    
    Args:
        tool_name: Name of the MCP tool to call
        args: Tool arguments
        timeout: Timeout in seconds (default 60s). Caller should specify longer
                 timeout for slow operations like cloud API queries.
    """
    global _needs_warmup
    
    # Warmup on first call if needed (in the correct event loop)
    if _needs_warmup and not _session_warmed_up:
        logger.info("[MCP] First call - warming up persistent session...")
        await warmup_mcp_session()
    
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
