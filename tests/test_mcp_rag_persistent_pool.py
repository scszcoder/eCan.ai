"""mt028 — Streamable_HTTP_Pool worker-pattern rewrite (Fix 2).

The mt027 first-cut pool used a per-slot anyio task group held alive
via ``sleep_forever``.  Live trace 2026-05-22 13:46 showed this is
fragile — 3 successful hits then ``ClosedResourceError`` (the task
group's streams got closed by asyncio cancellation propagation across
task boundaries).  Hit rate ended at 52%.

mt028 rewrites the pool as N producer/consumer worker tasks.  Each
worker:
  * Opens a fresh ephemeral session (no persistent task group)
  * Serves ONE call_tool from the queue
  * Closes session
  * Loops

No persistent state to leak — workers self-heal on error.  Concurrency
bound still ``size``; observable via queue_wait_ms log marker.

Trade-off: each call pays init overhead again.  Future enhancement
(TODO in source) can keep the session alive across multiple calls if
no error fires.
"""
from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import patch

from agent.mcp import streamablehttp_pool as pool_mod
from agent.mcp.streamablehttp_pool import (
    POOL_TOOLS,
    Streamable_HTTP_Pool,
    _default_pool_size,
)


class DefaultPoolSizeTests(unittest.TestCase):
    def setUp(self) -> None:
        for k in ("ECAN_MCP_RAG_POOL_SIZE", "ECAN_FEIGE_TAB_COUNT"):
            os.environ.pop(k, None)

    def tearDown(self) -> None:
        for k in ("ECAN_MCP_RAG_POOL_SIZE", "ECAN_FEIGE_TAB_COUNT"):
            os.environ.pop(k, None)

    def test_default_is_4(self) -> None:
        self.assertEqual(4, _default_pool_size())

    def test_explicit_overrides_tabs(self) -> None:
        with patch.dict(os.environ, {
            "ECAN_MCP_RAG_POOL_SIZE": "10",
            "ECAN_FEIGE_TAB_COUNT": "3",
        }):
            self.assertEqual(10, _default_pool_size())

    def test_tab_count_used_when_explicit_missing(self) -> None:
        with patch.dict(os.environ, {"ECAN_FEIGE_TAB_COUNT": "8"}):
            self.assertEqual(8, _default_pool_size())

    def test_tab_count_clamped_to_min_4(self) -> None:
        with patch.dict(os.environ, {"ECAN_FEIGE_TAB_COUNT": "2"}):
            self.assertEqual(4, _default_pool_size())

    def test_invalid_env_falls_back_to_default(self) -> None:
        with patch.dict(os.environ, {"ECAN_MCP_RAG_POOL_SIZE": "garbage"}):
            self.assertEqual(4, _default_pool_size())


class PoolSingletonTests(unittest.TestCase):
    def setUp(self) -> None:
        Streamable_HTTP_Pool._pools.clear()

    def tearDown(self) -> None:
        Streamable_HTTP_Pool._pools.clear()

    def test_pool_size_matches_constructor_arg(self) -> None:
        p = Streamable_HTTP_Pool.get("http://test/mcp", size=6)
        self.assertEqual(6, p.size)
        self.assertEqual(0, len(p._workers))  # workers spawn lazily on first call

    def test_get_is_url_scoped_singleton(self) -> None:
        p1 = Streamable_HTTP_Pool.get("http://a/mcp", size=4)
        p2 = Streamable_HTTP_Pool.get("http://a/mcp", size=99)  # size ignored
        p3 = Streamable_HTTP_Pool.get("http://b/mcp", size=4)
        self.assertIs(p1, p2)
        self.assertIsNot(p1, p3)


class WorkerSelfHealTests(unittest.IsolatedAsyncioTestCase):
    """Worker survives transient call_tool errors by re-opening the
    ephemeral session on the NEXT request.  Without this, the mt027
    first-cut pool's persistent task group leaked ClosedResourceError
    after 3 hits."""

    def setUp(self) -> None:
        Streamable_HTTP_Pool._pools.clear()

    def tearDown(self) -> None:
        Streamable_HTTP_Pool._pools.clear()

    async def test_pool_tools_registry(self) -> None:
        self.assertIn("rag_query", POOL_TOOLS)

    async def test_ensure_workers_started_idempotent(self) -> None:
        p = Streamable_HTTP_Pool.get("http://test/mcp", size=3)
        # Stub the worker loop so it doesn't try to open real connections
        async def _stub_worker(self_, worker_id):
            try:
                while True:
                    req = await self_._queue.get()
                    if not req.future.done():
                        req.future.set_result(f"stubbed-{worker_id}")
            except asyncio.CancelledError:
                return

        with patch.object(Streamable_HTTP_Pool, "_worker_loop", _stub_worker):
            p._ensure_workers_started()
            self.assertEqual(3, len(p._workers))
            # Calling again must NOT spawn more
            p._ensure_workers_started()
            self.assertEqual(3, len(p._workers))
            # Clean up
            for task in p._workers:
                task.cancel()

    async def test_worker_resolves_request_future(self) -> None:
        """One call through the pool with a stubbed worker resolves
        the request future."""
        p = Streamable_HTTP_Pool.get("http://test/mcp", size=2)

        async def _stub_worker(self_, worker_id):
            try:
                while True:
                    req = await self_._queue.get()
                    if not req.future.done():
                        req.future.set_result({"ok": True, "worker": worker_id})
            except asyncio.CancelledError:
                return

        with patch.object(Streamable_HTTP_Pool, "_worker_loop", _stub_worker):
            result = await p.call_tool("rag_query", {"q": "test"}, timeout=5.0)
            self.assertEqual(True, result["ok"])
            for task in p._workers:
                task.cancel()

    async def test_worker_failure_propagates_to_future(self) -> None:
        """When a worker's call raises, the caller sees the exception
        (not a hang)."""
        p = Streamable_HTTP_Pool.get("http://test/mcp", size=1)

        async def _failing_worker(self_, worker_id):
            try:
                while True:
                    req = await self_._queue.get()
                    if not req.future.done():
                        req.future.set_exception(RuntimeError("boom"))
            except asyncio.CancelledError:
                return

        with patch.object(Streamable_HTTP_Pool, "_worker_loop", _failing_worker):
            with self.assertRaises(RuntimeError) as ctx:
                await p.call_tool("rag_query", {"q": "test"}, timeout=5.0)
            self.assertIn("boom", str(ctx.exception))
            for task in p._workers:
                task.cancel()


class LocalClientWiringTests(unittest.TestCase):
    """The pool routing in local_client.py was disabled in mt028
    because workers die when their spawning event loop ends.  The pool
    code itself is kept for future re-enable.  These tests confirm the
    routing IS disabled."""

    def test_pool_routing_is_commented_out(self) -> None:
        from pathlib import Path
        src = Path("agent/mcp/local_client.py").read_text(encoding="utf-8")
        # The pool import + routing block must be commented out
        # (the disable note is a load-bearing safety guard)
        self.assertIn("DISABLED Tier 2 pool routing", src)
        # Verify the active code path (uncommented) does NOT invoke
        # the pool's call_tool
        # Find the call_tool function body
        idx = src.find("async def call_tool")
        self.assertGreater(idx, 0)
        body = src[idx : idx + 6000]
        # No uncommented "pool.call_tool" line in the body
        for line in body.split("\n"):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            self.assertNotIn(
                "pool.call_tool",
                stripped,
                msg=f"Pool routing leaked back in: {stripped!r}",
            )


if __name__ == "__main__":
    unittest.main()
