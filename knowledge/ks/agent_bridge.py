"""
Bridge between the LangGraph agents and the Knowledge Service.

``rag_query`` (the MCP tool every Q&A skill already calls) asks this module
first. When the merchant has product knowledge and the question can be scoped
to a store or a product card, path A answers in milliseconds with facts from
the product record; otherwise ``rag_query`` falls through to LightRAG as
before. No skill data needs to change.

Scope is never chosen by the LLM: the store comes from the task's ``store_id``
variable and the product from the buyer's product card (``商品ID:<id>``),
both read from the graph state by the harness.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, Optional

from knowledge.ks._log import logger

_ITEM_ID_RE = re.compile(r"商品ID[:：]\s*(\d{4,})")
_STATE_KEYS = ("attributes", "messages", "input", "prompt_refs", "metadata")
_MAX_SCAN_CHARS = 60000
_STATS_TTL_S = 30.0
_stats_cache: Dict[str, Any] = {"at": 0.0, "has_data": False, "key": None}


def enabled() -> bool:
    return (os.getenv("ECAN_KS_PRODUCT_QA") or "1").strip().lower() not in ("0", "false", "no", "off")


def extract_item_id(text: str) -> str:
    """The most recent platform item id in a product-card text."""
    found = _ITEM_ID_RE.findall(text or "")
    return found[-1] if found else ""


def _state_text(state: Any) -> str:
    parts = []
    total = 0
    if not isinstance(state, dict):
        return ""
    for key in _STATE_KEYS:
        if key not in state:
            continue
        try:
            chunk = json.dumps(state[key], ensure_ascii=False, default=str)
        except Exception:
            chunk = str(state[key])
        parts.append(chunk[-_MAX_SCAN_CHARS:])
        total += len(parts[-1])
        if total > _MAX_SCAN_CHARS * 2:
            break
    return "\n".join(parts)


def scope_from_state(state: Any) -> Dict[str, str]:
    """Store id (task variable) and product-card item id from the graph state."""
    scope = {"store_id": "", "platform_item_id": ""}
    try:
        from agent.ec_skills.prompt_variable_providers import resolve_store_id
        scope["store_id"] = resolve_store_id(state) or ""
    except Exception:
        pass
    scope["platform_item_id"] = extract_item_id(_state_text(state))
    return scope


def _has_product_knowledge(svc) -> bool:
    now = time.monotonic()
    key = id(svc)
    if _stats_cache["key"] == key and now - _stats_cache["at"] < _STATS_TTL_S:
        return _stats_cache["has_data"]
    stats = svc.store.stats(svc.tenant_id())
    has = bool(stats["products"] or stats["policies"])
    _stats_cache.update({"at": now, "has_data": has, "key": key})
    return has


def _confidence_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    score = float(result.get("confidence") or 0.0)
    level = "high" if score >= 0.8 else "medium" if score >= 0.5 else "low"
    return {
        "overall_score": round(score, 3),
        "confidence_level": level,
        "explanation": f"product_knowledge tier {result.get('tier')}",
        "decision": {"should_answer": bool(result.get("should_answer"))},
        "retrieval": {"score_source": "product_knowledge", "tier": result.get("tier"),
                      "timings_ms": result.get("timings_ms")},
    }


def _references(result: Dict[str, Any]) -> list:
    refs = []
    if result.get("product"):
        p = result["product"]
        refs.append({"reference_id": p["id"], "file_path": f"商品:{p['title']}", "content": "; ".join(
            f"{f['key']}:{f['value']}" for f in result.get("facts") or [])})
    for i, faq in enumerate(result.get("faq") or [], start=1):
        refs.append({"reference_id": f"faq{i}", "file_path": "常见问题", "content": f"{faq['question']} {faq['answer']}",
                     "score": faq.get("score")})
    for pol in result.get("policies") or []:
        refs.append({"reference_id": pol["id"], "file_path": f"店铺规则:{pol['topic']}", "content": pol["text"]})
    for i, c in enumerate(result.get("chunks") or [], start=1):
        refs.append({"reference_id": f"chunk{i}", "file_path": c.get("doc_type"), "content": c["text"], "score": c.get("score")})
    return refs


def _configured_store_count(main_window) -> int:
    """Stores set up in eCan (the Stores page / 快速生成), imported or not."""
    try:
        svc = getattr(getattr(main_window, "ec_db_mgr", None), "store_service", None)
        return len(svc.list_stores() or []) if svc is not None else 0
    except Exception:
        return 0


def _no_store_knowledge(main_window, store_ref: str, why: str) -> Optional[Dict[str, Any]]:
    """With several stores, a turn scoped to *store_ref* must not fall through to
    LightRAG: that knowledge base is one per account and mixes the stores'
    material (2026-10-19: the 牙线 store answered "这边主营童装" from the other
    store's documents). Say this store has no product information instead.
    None (fall through, as before) for a single store or an unscoped turn."""
    if not store_ref or _configured_store_count(main_window) < 2:
        return None
    logger.info(f"[KS] store={store_ref!r}: {why}; several stores configured -- not using the "
                f"shared knowledge base (it mixes stores)")
    text = (f"【店铺 {store_ref} 的商品知识库中没有与此问题相关的资料】"
            f"不要使用或猜测其他店铺的商品信息；如实告诉买家需要核实后再回复。")
    return {
        "status": "success",
        "data": {
            "response": text,
            "references": [],
            "confidence": {"overall_score": 0.0, "confidence_level": "low",
                           "explanation": f"no product knowledge for store {store_ref}",
                           "decision": {"should_answer": False},
                           "retrieval": {"score_source": "product_knowledge", "tier": "none"}},
            "source": "product_knowledge",
            "product_knowledge": {"tier": "none", "store": store_ref, "reason": why},
        },
    }


def try_product_answer(main_window, input_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Answer a rag_query from product knowledge, or return None to fall
    through to LightRAG. The returned dict is the rag_query meta payload."""
    if not enabled():
        logger.info("[KS] product knowledge off -- using LightRAG")
        return None
    query = str(input_data.get("query") or "").strip()
    if not query:
        return None
    # A query pinned to a LightRAG workspace keeps that tenant isolation: the
    # merchant-wide product catalog must not answer it (review 2026-10-10).
    if str(input_data.get("workspace") or "").strip():
        return None
    # The run's own scope (task store, or the store a front desk dispatched the
    # turn for, + the buyer's product card) wins over anything in the LLM's
    # tool arguments, which a buyer can steer: inside a run the arguments
    # never name the store.
    has_scope = "_ks_scope" in input_data
    scope = input_data.get("_ks_scope") or {}
    store_ref = str(scope.get("store_id") or ("" if has_scope else input_data.get("store_id")) or "").strip()
    item_id = str(scope.get("platform_item_id") or input_data.get("platform_item_id") or "").strip()
    if not item_id:
        item_id = extract_item_id(" ".join(str(v) for v in input_data.values() if isinstance(v, str)))
    try:
        from knowledge.ks.service import get_router, get_service
        svc = get_service(main_window)
        router = get_router(main_window)
        has_remote = any(c.get("enabled", True) for c in router.all_connections())
        if not has_remote and not _has_product_knowledge(svc):
            logger.info(f"[KS] store={store_ref!r}: no products imported yet")
            return _no_store_knowledge(main_window, store_ref, "no products imported yet")
        if has_remote:
            result = router.search(query, store=store_ref, platform_item_id=item_id)
        else:
            result = svc.search(query, store_ref=store_ref, platform_item_id=item_id)
    except Exception as e:
        logger.warning(f"[KS] product knowledge lookup failed, using LightRAG: {e}")
        return None
    if not result.get("should_answer"):
        logger.info(f"[KS] store={store_ref!r}: no confident answer (tier={result.get('tier')})")
        return _no_store_knowledge(main_window, store_ref, f"no confident answer (tier={result.get('tier')})")
    logger.info(f"[KS] store={store_ref!r} answered from product knowledge tier={result['tier']} "
                f"product={(result.get('product') or {}).get('code')} in {result['timings_ms'].get('total')}ms")
    return {
        "status": "success",
        "data": {
            "response": result["context"],
            "references": _references(result),
            "confidence": _confidence_payload(result),
            "source": "product_knowledge",
            "sensitivity": result.get("sensitivity", "internal"),
            "plane": result.get("plane", "local"),
            "product_knowledge": {k: result.get(k) for k in ("tier", "product", "store", "facts", "faq", "policies",
                                                             "candidates", "timings_ms", "confidence")},
        },
    }
