"""
Private-data guard for the agent harness (docs/RAG_ENTERPRISE_PLAN.md §2.4).

When a retrieval result marked ``private`` enters a run's state, every later
LLM call in that run must go to a private model: an endpoint on this machine,
on the customer's network, or one the admin listed. Calls to anything else
are blocked before any text leaves the machine.

  ECAN_KS_TAINT_GUARD=0          disable (not recommended)
  ECAN_PRIVATE_LLM_HOSTS=a,b     extra hosts treated as private
"""
from __future__ import annotations

import ipaddress
import os
from typing import Any, Optional
from urllib.parse import urlparse

TAINT_KEY = "_ks_sensitivity"


class PrivateDataBlocked(RuntimeError):
    """Raised instead of sending private knowledge to a non-private model."""


def enabled() -> bool:
    return (os.getenv("ECAN_KS_TAINT_GUARD") or "1").strip().lower() not in ("0", "false", "no", "off")


def _attrs(state: Any) -> Optional[dict]:
    if not isinstance(state, dict):
        return None
    attrs = state.get("attributes")
    if not isinstance(attrs, dict):
        attrs = {}
        state["attributes"] = attrs
    return attrs


def mark(state: Any, sensitivity: str) -> None:
    """Record the most sensitive knowledge a run has seen.

    Kept in ``state["attributes"]``: skills run as a typed LangGraph StateGraph
    (NodeState), which DROPS top-level keys it does not declare between nodes
    -- a top-level mark never reached the next LLM node, so the guard never
    fired (rag-enterprise review, 2026-10-10)."""
    attrs = _attrs(state)
    if attrs is None or not sensitivity:
        return
    if sensitivity == "private" or attrs.get(TAINT_KEY) != "private":
        attrs[TAINT_KEY] = sensitivity


def is_tainted(state: Any) -> bool:
    if not isinstance(state, dict):
        return False
    attrs = state.get("attributes")
    return (isinstance(attrs, dict) and attrs.get(TAINT_KEY) == "private") or state.get(TAINT_KEY) == "private"


def _extra_hosts() -> set:
    return {h.strip().lower() for h in (os.getenv("ECAN_PRIVATE_LLM_HOSTS") or "").split(",") if h.strip()}


def is_private_host(host: str) -> bool:
    host = (host or "").strip().lower().strip("[]")
    if not host:
        return False
    if host in ("localhost",) or host.endswith((".local", ".lan", ".internal", ".corp")) or host in _extra_hosts():
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_loopback or ip.is_private or ip.is_link_local
    except ValueError:
        return False


def llm_endpoint(llm: Any) -> Optional[str]:
    """Best-effort base URL of a langchain chat model (unwraps bind_tools)."""
    seen = 0
    obj = llm
    while obj is not None and seen < 4:
        for attr in ("openai_api_base", "base_url", "api_base", "endpoint", "azure_endpoint", "base_url_"):
            val = getattr(obj, attr, None)
            if val:
                return str(val)
        client = getattr(obj, "client", None) or getattr(obj, "_client", None)
        val = getattr(client, "base_url", None) if client is not None else None
        if val:
            return str(val)
        # bind_tools -> .bound; with_fallbacks -> .runnable; other wrappers -> .llm / .model
        obj = next((getattr(obj, a) for a in ("bound", "runnable", "llm", "model")
                    if getattr(obj, a, None) is not None and not isinstance(getattr(obj, a), str)), None)
        seen += 1
    return None


def check_llm(state: Any, llm: Any, provider: str = "", node: str = "") -> None:
    """Raise PrivateDataBlocked if a tainted run would call a non-private model."""
    if not enabled() or not is_tainted(state):
        return
    endpoint = llm_endpoint(llm)
    host = urlparse(endpoint).hostname if endpoint and "://" in endpoint else endpoint
    if is_private_host(host or ""):
        return
    raise PrivateDataBlocked(
        f"Node '{node}' would send private knowledge to {provider or 'a model'} at "
        f"{endpoint or 'an unknown/cloud endpoint'}. Use a model on your private server for this skill, "
        f"or list its host in ECAN_PRIVATE_LLM_HOSTS.")
