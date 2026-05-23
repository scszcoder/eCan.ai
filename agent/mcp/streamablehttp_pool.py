"""Bounded pool of persistent MCP streamable-HTTP sessions for hot-path tools.

The existing :class:`agent.mcp.streamablehttp_manager.Streamable_HTTP_Manager`
is a singleton with **one** persistent session, so concurrent ``rag_query``
callers head-of-line block on each other (mt019 added rag_query to
``_NO_PERSISTENT_SESSION`` to fall back to ephemeral).  Ephemeral pays
~400 ms streams_open + ~1.7 s initialize per call, which adds up across
8 concurrent bots.

This pool uses a **producer / consumer with N workers** model.  Each
worker keeps its own ephemeral session ALIVE for the duration of one
call, then re-opens on the next call (or on failure).  This avoids the
fragile "persistent task group across asyncio boundaries" problem the
mt027 first-cut pool ran into (live 2026-05-22 13:46 trace:
``ClosedResourceError`` after 3 successful hits, 52% pool hit rate).

The trade-off: each call still pays the init overhead because the
session is single-use per call.  BUT a future enhancement (deferred,
see TODO at end of file) can make a worker hold its session across
multiple calls if no error fires, recovering the init savings.

Sizing
------
``ECAN_MCP_RAG_POOL_SIZE`` (env) or ``max(ECAN_FEIGE_TAB_COUNT, 4)``.

Observability
-------------
``[MCP-RAG-POOL]`` log lines for create, hit (with wait_ms / call_ms),
and worker-error events.
"""
from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Optional

from mcp.client.streamable_http import streamablehttp_client
from mcp.client.session import ClientSession
from utils.logger_helper import logger_helper as logger
from agent.ec_skills.system_proxy import create_mcp_httpx_client


POOL_TOOLS: frozenset[str] = frozenset({"rag_query"})


def _default_pool_size() -> int:
    explicit = os.getenv("ECAN_MCP_RAG_POOL_SIZE")
    if explicit:
        try:
            n = int(explicit)
            if n > 0:
                return n
        except ValueError:
            pass
    tabs = os.getenv("ECAN_FEIGE_TAB_COUNT")
    if tabs:
        try:
            return max(int(tabs), 4)
        except ValueError:
            pass
    return 4


@dataclass
class _Request:
    """One call request handed to a worker via the request queue."""
    tool_name: str
    arguments: dict
    timeout: float
    future: "asyncio.Future"


class Streamable_HTTP_Pool:
    """Worker-pool for one MCP server URL.

    On startup, lazily spawns ``size`` worker tasks.  Each worker:
      1. Opens a fresh ephemeral session (`streamablehttp_client` +
         `ClientSession.__aenter__` + `initialize`).
      2. Pulls one :class:`_Request` from the shared queue.
      3. Runs ``call_tool`` against the session, sets the request's
         future.
      4. Closes the session.
      5. Loops back to step 1.

    A worker that hits an exception in its open/init/close cycle backs
    off briefly and retries.  This makes the pool self-healing — no
    persistent task group state to leak across asyncio task boundaries.

    Concurrency bound: at most ``size`` requests are processed at once.
    Additional requests queue and observe their wait time in
    ``[MCP-RAG-POOL] hit wait_ms=N``.
    """

    _pools: dict[str, "Streamable_HTTP_Pool"] = {}

    def __init__(self, url: str, size: int) -> None:
        self.url = url
        self.size = size
        # asyncio.Queue() requires a running event loop to construct in
        # Python 3.10+.  Create lazily inside the running loop in
        # _ensure_workers_started.
        self._queue: Optional["asyncio.Queue[_Request]"] = None
        self._workers: list[asyncio.Task] = []
        self._workers_started = False
        self._calls_total = 0
        self._calls_success = 0
        self._calls_failed = 0

    @classmethod
    def get(cls, url: str, size: Optional[int] = None) -> "Streamable_HTTP_Pool":
        existing = cls._pools.get(url)
        if existing is not None:
            return existing
        pool = cls(url, size if size is not None else _default_pool_size())
        cls._pools[url] = pool
        logger.info(
            f"[MCP-RAG-POOL] created pool url={url!r} size={pool.size}"
        )
        return pool

    @classmethod
    async def close_all(cls) -> None:
        for pool in list(cls._pools.values()):
            for task in pool._workers:
                task.cancel()
            pool._workers.clear()
        cls._pools.clear()

    def _ensure_workers_started(self) -> None:
        if self._workers_started:
            return
        self._workers_started = True
        loop = asyncio.get_running_loop()
        if self._queue is None:
            self._queue = asyncio.Queue()
        for i in range(self.size):
            task = loop.create_task(self._worker_loop(i))
            self._workers.append(task)
        logger.info(
            f"[MCP-RAG-POOL] spawned {self.size} workers for url={self.url!r}"
        )

    async def _worker_loop(self, worker_id: int) -> None:
        """One worker: open session → serve one request → close → loop.

        Errors in any phase log + back off + retry.  Cancellation
        (event loop shutdown) breaks the loop cleanly.
        """
        backoff = 0.5
        while True:
            req: Optional[_Request] = None
            try:
                # Pull next request BEFORE opening session — saves
                # opening a session when queue is empty.
                req = await self._queue.get()
                t_call_start = time.perf_counter()
                try:
                    async with streamablehttp_client(
                        self.url,
                        terminate_on_close=False,
                        httpx_client_factory=create_mcp_httpx_client,
                    ) as streams:
                        async with ClientSession(streams[0], streams[1]) as session:
                            await asyncio.wait_for(
                                session.initialize(), timeout=10.0
                            )
                            result = await asyncio.wait_for(
                                session.call_tool(req.tool_name, req.arguments),
                                timeout=req.timeout,
                            )
                            call_ms = int((time.perf_counter() - t_call_start) * 1000)
                            self._calls_success += 1
                            logger.info(
                                f"[MCP-RAG-POOL] hit tool={req.tool_name} "
                                f"worker={worker_id} call_ms={call_ms} "
                                f"queued={self._queue.qsize()} "
                                f"success={self._calls_success} "
                                f"failed={self._calls_failed}"
                            )
                            if not req.future.done():
                                req.future.set_result(result)
                            backoff = 0.5  # reset on success
                except asyncio.CancelledError:
                    if req is not None and not req.future.done():
                        req.future.cancel()
                    raise
                except Exception as exc:
                    self._calls_failed += 1
                    logger.warning(
                        f"[MCP-RAG-POOL] worker={worker_id} call failed "
                        f"({type(exc).__name__}: {exc}); request escalated to caller"
                    )
                    if req is not None and not req.future.done():
                        req.future.set_exception(exc)
                    # Brief back-off so a flapping server doesn't cause
                    # a tight retry loop across all workers.
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 10.0)
            except asyncio.CancelledError:
                logger.info(f"[MCP-RAG-POOL] worker={worker_id} cancelled")
                return
            except Exception as exc:
                logger.error(
                    f"[MCP-RAG-POOL] worker={worker_id} loop fatal "
                    f"({type(exc).__name__}: {exc}); restarting"
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 10.0)

    async def call_tool(self, tool_name: str, arguments: dict, timeout: float):
        """Submit a call to the worker pool.  Blocks the caller until
        a worker picks it up and returns a result (or raises)."""
        self._ensure_workers_started()
        loop = asyncio.get_running_loop()
        fut: "asyncio.Future" = loop.create_future()
        req = _Request(
            tool_name=tool_name,
            arguments=arguments,
            timeout=timeout,
            future=fut,
        )
        t_submit = time.perf_counter()
        await self._queue.put(req)
        self._calls_total += 1
        # The worker enforces its own per-request timeout and resolves
        # the future.  Add a hard cap of timeout + 30 s here for the
        # "all workers stuck" pathological case.
        try:
            result = await asyncio.wait_for(fut, timeout=timeout + 30.0)
            wait_ms = int((time.perf_counter() - t_submit) * 1000)
            if wait_ms > 100:
                logger.info(
                    f"[MCP-RAG-POOL] tool={tool_name} queue_wait_ms={wait_ms} "
                    f"queue_depth_at_submit={self._queue.qsize()}"
                )
            return result
        except asyncio.TimeoutError:
            fut.cancel()
            raise


__all__ = [
    "POOL_TOOLS",
    "Streamable_HTTP_Pool",
]
