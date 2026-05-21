"""mt020: ECAN_RAG_QUERY_DEFAULT_MODE tunable.

The default rag_query mode is now operator-configurable via env var.
Default unchanged ('mix') for backwards compat; the env var lets a
deployment that's seeing slow keyword-extraction LLM calls switch to
'naive' (pure vector search, no keyword LLM) without changing any
bot prompts or other code.

Mirrors the inline logic in
``agent.ec_skills.rag.local_rag_mcp.rag_query`` so unit tests can
exercise it without booting the MCP server.
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch


def resolve_mode(input_mode: str | None) -> str:
    """Mirror of the mt020 resolution inside ``rag_query``."""
    env_default_mode = (os.getenv("ECAN_RAG_QUERY_DEFAULT_MODE") or "mix").strip().lower()
    if env_default_mode not in ["local", "global", "hybrid", "naive", "mix", "bypass"]:
        env_default_mode = "mix"
    mode = input_mode or env_default_mode
    if mode in ["local", "global", "hybrid", "naive", "mix", "bypass"]:
        return mode
    return env_default_mode


class RagQueryDefaultModeTests(unittest.TestCase):
    def setUp(self) -> None:
        # Make sure env is clean per test
        os.environ.pop("ECAN_RAG_QUERY_DEFAULT_MODE", None)

    def tearDown(self) -> None:
        os.environ.pop("ECAN_RAG_QUERY_DEFAULT_MODE", None)

    def test_default_remains_mix(self) -> None:
        self.assertEqual("mix", resolve_mode(None))
        self.assertEqual("mix", resolve_mode(""))

    def test_caller_override_wins(self) -> None:
        # Bot prompts that explicitly set mode keep working
        self.assertEqual("naive", resolve_mode("naive"))
        self.assertEqual("hybrid", resolve_mode("hybrid"))

    def test_env_changes_default(self) -> None:
        with patch.dict(os.environ, {"ECAN_RAG_QUERY_DEFAULT_MODE": "naive"}):
            self.assertEqual("naive", resolve_mode(None))
            # Caller-provided mode still overrides env
            self.assertEqual("hybrid", resolve_mode("hybrid"))

    def test_env_validation_falls_back_to_mix(self) -> None:
        with patch.dict(os.environ, {"ECAN_RAG_QUERY_DEFAULT_MODE": "garbage"}):
            self.assertEqual("mix", resolve_mode(None))

    def test_caller_invalid_mode_falls_back_to_env(self) -> None:
        with patch.dict(os.environ, {"ECAN_RAG_QUERY_DEFAULT_MODE": "naive"}):
            # Bad caller mode → fall back to env default
            self.assertEqual("naive", resolve_mode("not_a_mode"))


class CallSiteWiredCorrectlyTests(unittest.TestCase):
    """Confirm the env-default + caller-override pattern is wired in
    the actual rag_query implementation."""

    def test_env_var_referenced(self) -> None:
        from pathlib import Path
        src = Path("agent/ec_skills/rag/local_rag_mcp.py").read_text(encoding="utf-8")
        self.assertIn("ECAN_RAG_QUERY_DEFAULT_MODE", src)

    def test_default_modes_still_validated(self) -> None:
        from pathlib import Path
        src = Path("agent/ec_skills/rag/local_rag_mcp.py").read_text(encoding="utf-8")
        # The valid-mode whitelist must still be present
        for mode in ["local", "global", "hybrid", "naive", "mix", "bypass"]:
            self.assertIn(f'"{mode}"', src)


if __name__ == "__main__":
    unittest.main()
