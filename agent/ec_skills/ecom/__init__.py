"""E-commerce operations foundation: the deterministic layer (L1) the store skills share.

Every number and every rule threshold lives here, never in an LLM prompt. Skills reach it
through the ``ec_*`` MCP tools (``agent/mcp/server/ecom_tools.py``).

Nothing in this package names a store, product, account or URL: those come from the
seller's own KB records (``kb.py``), discovered at onboarding or given in chat.
"""
