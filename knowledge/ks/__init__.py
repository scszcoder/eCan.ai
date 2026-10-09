"""
eCan Knowledge Service (KS).

Owns tenants, knowledge bases, the product catalog (products, store listings,
store policies), document metadata, retrieval scoping and long-running jobs.
LightRAG stays the engine for deep document search; KS's own path A answers
e-commerce product questions with structured lookups plus filtered hybrid
search and no LLM calls inside retrieval.

See docs/RAG_ENTERPRISE_PLAN.md.
"""
