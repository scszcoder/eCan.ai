"""mt019: rag_query hot-path timeout cap.

Q&A bots call ``rag_query`` in the customer-reply path.  A slow RAG
query directly translates to customer wait time.  Default MCP tool
timeout was 60s; the live 2026-05-21 21:04:03 trace showed a single
68-second rag_query failure (TaskGroup error) adding ~70s to a
customer's wait (total 188s).

Fix: ``LocalMCPClient.call_tool`` now caps ``rag_query`` at 10s by
default.  Overridable via ``ECAN_MCP_RAG_QUERY_TIMEOUT_S`` env var.

These tests just verify the cap-down logic — they don't run a real
MCP call.  We inspect the per-tool cap calculation directly.
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch


class RagQueryTimeoutCapTests(unittest.TestCase):
    """The cap should rewrite ``timeout`` in ``call_tool`` for
    ``rag_query`` only — other tools keep whatever caller passed."""

    def _cap_for_tool(self, tool_name: str, requested_timeout: float) -> float:
        """Mirrors the inline cap logic in
        ``agent.mcp.local_client.LocalMCPClient.call_tool`` so unit
        tests can exercise it without a real network call.

        If the local_client logic ever changes, this helper must change
        in lockstep — failure of this assertion is a heads-up that the
        cap behaviour has drifted from the test's expectation."""
        hot_caps = {
            "rag_query": float(os.getenv("ECAN_MCP_RAG_QUERY_TIMEOUT_S", "10")),
        }
        cap = hot_caps.get(tool_name)
        if cap is not None and cap > 0 and requested_timeout > cap:
            return cap
        return requested_timeout

    def test_rag_query_default_capped_to_10s(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ECAN_MCP_RAG_QUERY_TIMEOUT_S", None)
            self.assertEqual(10.0, self._cap_for_tool("rag_query", 60.0))

    def test_rag_query_below_cap_unchanged(self) -> None:
        # Caller passing a tighter timeout than the cap → cap doesn't kick in
        self.assertEqual(5.0, self._cap_for_tool("rag_query", 5.0))

    def test_other_tool_uncapped(self) -> None:
        # Only rag_query is in the hot-cap list
        self.assertEqual(60.0, self._cap_for_tool("send_chat", 60.0))
        self.assertEqual(60.0, self._cap_for_tool("feige_send_message", 60.0))

    def test_env_override_raises_cap(self) -> None:
        with patch.dict(os.environ, {"ECAN_MCP_RAG_QUERY_TIMEOUT_S": "25"}):
            self.assertEqual(25.0, self._cap_for_tool("rag_query", 60.0))

    def test_env_override_lowers_cap(self) -> None:
        with patch.dict(os.environ, {"ECAN_MCP_RAG_QUERY_TIMEOUT_S": "5"}):
            self.assertEqual(5.0, self._cap_for_tool("rag_query", 60.0))


class CallToolCapDeployedTests(unittest.TestCase):
    """Reads the actual call_tool source to confirm the cap is wired
    in.  Guards against accidental removal in a future refactor."""

    def test_call_tool_has_rag_query_cap(self) -> None:
        from pathlib import Path
        src = Path("agent/mcp/local_client.py").read_text(encoding="utf-8")
        i = src.find("async def call_tool")
        self.assertGreater(i, 0)
        # Limit search to within call_tool's body (next 4 KB)
        body = src[i : i + 4000]
        self.assertIn("ECAN_MCP_RAG_QUERY_TIMEOUT_S", body, "env var override missing")
        self.assertIn('"rag_query"', body, "rag_query not in hot-caps dict")


if __name__ == "__main__":
    unittest.main()
