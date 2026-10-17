"""KB-mining MCP tools — the read side of the self-learning knowledge base.

``query_qa_history`` returns the raw resolved Q&A turns captured by
``agent/ec_skills/qa_capture.py`` that have not yet been mined. A mining skill
feeds these to an LLM to cluster + dedup them and propose candidate KB entries;
the merchant approves candidates (by email notification + in-app review) before
anything is written to the knowledge base — nothing is ever auto-published.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from mcp.types import TextContent

from utils.logger_helper import get_traceback
from utils.logger_helper import logger_helper as logger


def _db_mgr(mainwin):
    return getattr(mainwin, "ec_db_mgr", None) if mainwin is not None else None


def _owner(mainwin) -> str:
    """Best-effort current account owner (used to scope candidates)."""
    for attr in ("auth_manager", "authManager", "login"):
        am = getattr(mainwin, attr, None)
        getter = getattr(am, "get_current_user", None) if am else None
        if callable(getter):
            try:
                v = getter()
                if v:
                    return str(v).strip()
            except Exception:
                pass
    return ""


async def query_qa_history(mainwin, args):
    """Return captured Q&A turns in a mining-lifecycle state (default 'new').

    ``args == {"input": {"status"?, "store_id"?, "owner"?, "limit"?}}``.
    """
    try:
        input_data = (args or {}).get("input", {}) or {}
        if not isinstance(input_data, dict):
            return [TextContent(type="text", text="Error: input must be an object")]

        status = (input_data.get("status") or "new").strip() or "new"
        store_id = (input_data.get("store_id") or "").strip() or None
        owner = (input_data.get("owner") or "").strip() or None
        try:
            limit = int(input_data.get("limit") or 500)
        except (TypeError, ValueError):
            limit = 500

        mgr = _db_mgr(mainwin)
        svc = getattr(mgr, "qa_history_service", None) if mgr else None
        if svc is None:
            msg = "qa_history service not available (no running DB in this context)"
            result = TextContent(type="text", text=msg)
            result.meta = {"status": "not_available", "message": msg}
            return [result]

        rows = svc.list_by_status(status=status, store_id=store_id, owner=owner, limit=limit)
        # Trim to the fields the miner needs (keep the payload small).
        slim = [
            {
                "id": r.get("id"),
                "store_id": r.get("store_id"),
                "product_id": r.get("product_id"),
                "platform": r.get("platform"),
                "question": r.get("question"),
                "answer": r.get("answer"),
                "created_at": r.get("created_at"),
            }
            for r in rows
        ]
        payload = {"status": status, "count": len(slim), "rows": slim}
        logger.info(f"[kb_mining] query_qa_history status={status!r} store={store_id!r} -> {len(slim)} rows")
        result = TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, default=str))
        # payload carries its own 'status' (the lifecycle filter) — keep the
        # tool-call status authoritative by merging it last.
        result.meta = {**payload, "status": "success"}
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorQueryQaHistory")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def propose_kb_candidate(mainwin, args):
    """Write ONE mined Q&A candidate for the merchant to approve in-app.

    ``args == {"input": {"question", "answer", "rationale"?, "confidence"?,
    "store_id"?, "product_id"?, "source_ids"?}}``. ``source_ids`` are the
    qa_history row ids this candidate was mined from; they are marked 'mined'
    so they are not re-processed. Nothing enters the KB here — a candidate is
    created in 'pending' state only.
    """
    try:
        input_data = (args or {}).get("input", {}) or {}
        if not isinstance(input_data, dict):
            return [TextContent(type="text", text="Error: input must be an object")]

        question = str(input_data.get("question") or "").strip()
        answer = str(input_data.get("answer") or "").strip()
        if not question or not answer:
            result = TextContent(type="text", text="Error: question and answer are required")
            result.meta = {"status": "error", "message": "question and answer are required"}
            return [result]

        mgr = _db_mgr(mainwin)
        svc = getattr(mgr, "kb_candidate_service", None) if mgr else None
        if svc is None:
            msg = "kb_candidate service not available (no running DB in this context)"
            result = TextContent(type="text", text=msg)
            result.meta = {"status": "not_available", "message": msg}
            return [result]

        source_ids = input_data.get("source_ids") or []
        store_id = str(input_data.get("store_id") or "").strip() or None
        res = svc.add_candidate(
            owner=_owner(mainwin) or None,
            store_id=store_id,
            product_id=str(input_data.get("product_id") or "").strip() or None,
            platform=(store_id.split("-", 1)[0] if store_id and "-" in store_id else None),
            question=question,
            answer=answer,
            rationale=str(input_data.get("rationale") or "").strip() or None,
            examples=list(source_ids) if isinstance(source_ids, list) else None,
            confidence=input_data.get("confidence"),
            status="pending",
        )
        # Retire the source turns so they are not mined again.
        qa_svc = getattr(mgr, "qa_history_service", None)
        if qa_svc is not None and isinstance(source_ids, list) and source_ids:
            try:
                qa_svc.mark_status([str(i) for i in source_ids], "mined")
            except Exception as e:
                logger.debug(f"[kb_mining] mark source turns mined failed: {e}")

        payload = {"candidate_id": res.get("id"), "ok": bool(res.get("success")),
                   "error": res.get("error")}
        logger.info(f"[kb_mining] propose_kb_candidate ok={payload['ok']} id={payload['candidate_id']}")
        result = TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, default=str))
        result.meta = {"status": "success" if payload["ok"] else "error", **payload}
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorProposeKbCandidate")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


def add_query_qa_history_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schemas.append(types.Tool(
        _meta={"run_in_cloud": False},
        name="query_qa_history",
        description=(
            "<category>Knowledge Base</category><sub-category>Mining</sub-category>"
            "Return captured customer Q&A turns that have not yet been mined into "
            "the knowledge base (status='new' by default). Use this to gather raw "
            "question/answer history so you can cluster similar questions, drop "
            "duplicates and ones the KB already answers, and propose NEW candidate "
            "Q&A entries for the merchant to approve. Returns JSON: "
            "{status, count, rows:[{id, store_id, product_id, platform, question, "
            "answer, created_at}]}."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "description": "Lifecycle state to read (default 'new').",
                        },
                        "store_id": {
                            "type": "string",
                            "description": "Optional: only this store's turns.",
                        },
                        "owner": {
                            "type": "string",
                            "description": "Optional: only this account owner's turns.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max rows (default 500).",
                        },
                    },
                }
            },
        },
    ))


def add_propose_kb_candidate_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schemas.append(types.Tool(
        _meta={"run_in_cloud": False},
        name="propose_kb_candidate",
        description=(
            "<category>Knowledge Base</category><sub-category>Mining</sub-category>"
            "Propose ONE new Q&A entry for the knowledge base, for the merchant "
            "to approve. Call this after clustering the captured history, for each "
            "distinct question the KB does not already answer well. The candidate "
            "is saved as 'pending' and the merchant is notified; it does NOT enter "
            "the KB until they approve. Pass source_ids (the qa_history row ids the "
            "candidate was mined from) so those turns are not re-processed. Returns "
            "{candidate_id, ok}."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["question", "answer"],
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "The canonical customer question (clustered).",
                        },
                        "answer": {
                            "type": "string",
                            "description": "The proposed answer to add to the KB.",
                        },
                        "rationale": {
                            "type": "string",
                            "description": "Why this is worth adding / what gap it fills.",
                        },
                        "confidence": {
                            "type": "number",
                            "description": "Miner confidence 0..1.",
                        },
                        "store_id": {
                            "type": "string",
                            "description": "Store this Q&A pertains to, if store-specific.",
                        },
                        "product_id": {
                            "type": "string",
                            "description": "商品ID this Q&A pertains to, if product-specific.",
                        },
                        "source_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "qa_history row ids this candidate was mined from.",
                        },
                    },
                }
            },
        },
    ))
