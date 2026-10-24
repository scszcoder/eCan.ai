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
    desc = _turn_picture_desc(state)
    if desc:
        scope["image_desc"] = desc
    return scope


def _turn_picture_uri(state: Any) -> tuple:
    """(data URI, where) of the picture in this turn, or ("", "")."""
    from agent.ec_skills.llm_utils.llm_utils import _resolve_attachment_data_uri
    for key in ("input", "current_invocation_input"):
        raw = state.get(key)
        try:
            turn = json.loads(raw) if isinstance(raw, str) and raw.strip().startswith("{") else raw
        except Exception:
            turn = None
        for a in (turn or {}).get("latest_message_attachments") or [] if isinstance(turn, dict) else []:
            uri = _resolve_attachment_data_uri(a) if isinstance(a, dict) else ""
            if uri.startswith("data:image/"):
                return uri, key
    # The answering node's own multimodal message (the picture as an image_url part).
    for m in reversed(state.get("messages") or []):
        content = getattr(m, "content", None)
        if type(m).__name__ == "HumanMessage" and isinstance(content, list):
            for part in content:
                url = ((part or {}).get("image_url") or {}) if isinstance(part, dict) else {}
                url = url.get("url") if isinstance(url, dict) else url
                if isinstance(url, str) and url.startswith("data:image/"):
                    return url, "messages"
    for att in state.get("attachments") or []:
        data = att.get("file_data") if isinstance(att, dict) else None
        if isinstance(data, str) and data.startswith("data:image/"):
            return data, "attachments"
    return "", ""


# A picture "matches" a product when its best candidate scores at least
# PICTURE_MATCH_MIN and leads the next by PICTURE_MATCH_LEAD (tentative values,
# 2026-10-24: tune from the logged scores).
PICTURE_MATCH_MIN = 0.55
PICTURE_SIMILAR_MIN = 0.6
PICTURE_MATCH_LEAD = 0.05


def _picture_note(result: Dict[str, Any], note: str) -> Dict[str, Any]:
    """Put *note* first in the answer and let the answering model use it: what
    the picture comparison found is an answer in itself ("没有同款" included)."""
    out = dict(result)
    out["context"] = note + "\n" + (result.get("context") or "")
    out["should_answer"] = True
    out["confidence"] = max(float(result.get("confidence") or 0.0), 0.6)
    return out


def _focus_on_picture_match(svc, query: str, store_ref: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """The buyer sent a photo. A clear match: answer as if they had shared that
    product's card (its colours, sizes, facts), labelled as a picture match the
    answering model confirms against the photo it sees. No clear match: say so,
    naming the closest products only as similar ones -- never as the same item."""
    cands = result.get("candidates") or []
    scores = ", ".join(f"{c['title'][:14]}={c['score']}" for c in cands[:4]) or "none"
    lead = cands[0]["score"] - cands[1]["score"] if len(cands) > 1 else 1.0
    if not cands or cands[0]["score"] < PICTURE_MATCH_MIN or lead < PICTURE_MATCH_LEAD:
        logger.info(f"[KS] buyer picture: no clear match ({scores})")
        # Only look-alikes are worth naming: below PICTURE_SIMILAR_MIN the "closest"
        # items are just other products (a pajama photo got jeans shorts suggested).
        near = "、".join(c["title"][:30] for c in cands[:3] if c["score"] >= PICTURE_SIMILAR_MIN)
        return _picture_note(result, "[图片匹配] 本店没有找到与顾客图片明显一致的商品"
                             + (f"；外观最接近的是：{near}（只能作为相似款推荐，不要说成同款）" if near else "")
                             + "。请结合图片回答，不确定就请顾客发商品链接。")
    try:
        focused = svc.search(query, store_ref=store_ref, product_id=cands[0]["id"])
    except Exception as e:
        logger.warning(f"[KS] picture-match lookup failed: {e}")
        return result
    others = "、".join(c["title"][:30] for c in cands[1:3])
    out = _picture_note(focused, f"[图片匹配] 顾客图片最像本店的「{cands[0]['title']}」（按外观匹配，请结合图片确认是否同款"
                        + (f"；相近的还有：{others}" if others else "") + "）")
    out["candidates"] = cands
    logger.info(f"[KS] buyer picture matched {cands[0]['title'][:30]} ({scores})")
    return out


_LATEST_RE = re.compile(r'"latest_message"\s*:\s*"((?:[^"\\]|\\.)*)"')
_CUSTOMER_RE = re.compile(r'"customer_id"\s*:\s*"([^"]+)"')
_DATA_URI_RE = re.compile(r"data:image/[A-Za-z0-9.+-]+;base64,[A-Za-z0-9+/=]{100,}")


def _unwrap_turn_query(query: str) -> tuple:
    """(search text, picture data URI) for a rag_query whose query is the whole
    turn payload -- the skill's auto-selected rag_query passes the front desk's
    JSON (2026-10-23 KEN: a 155,912-char query, the photo's base64 included).
    Search with what the buyer wrote; the picture is described separately."""
    if '"latest_message' not in query:
        return query, ""
    turn, how = None, "json"
    try:
        turn = json.loads(query)
    except Exception:
        how = "pattern"
    if not isinstance(turn, dict):
        turn, how = {}, "pattern"
        m = _LATEST_RE.search(query)
        if m:
            try:
                turn["latest_message"] = json.loads(f'"{m.group(1)}"')
            except Exception:
                turn["latest_message"] = m.group(1)
    text = str(turn.get("latest_message") or "").strip()
    if text in ("[图片]", "[视频]", "[image]"):
        text = ""
    uri, keys = "", []
    try:
        from agent.ec_skills.llm_utils.llm_utils import _resolve_attachment_data_uri
        for a in turn.get("latest_message_attachments") or []:
            keys.append(sorted(a) if isinstance(a, dict) else type(a).__name__)
            uri = _resolve_attachment_data_uri(a) if isinstance(a, dict) else ""
            if uri.startswith("data:image/"):
                break
            uri = ""
    except Exception:
        uri = ""
    if not uri:
        m = _DATA_URI_RE.search(query)
        uri = m.group(0) if m else ""
    where = "query"
    if not uri:
        # The query was written from the turn text with the picture stripped:
        # the answering node remembered the buyer's picture (turn_pictures.py).
        cid = turn.get("customer_id") if isinstance(turn, dict) else ""
        if not cid:
            m = _CUSTOMER_RE.search(query)
            cid = m.group(1) if m else ""
        try:
            from agent.ec_skills.turn_pictures import recent
            uri = recent(cid)
            where = "this buyer's turn"
        except Exception:
            uri = ""
    logger.info(f"[KS] turn payload as the query ({how}): text={text[:30]!r} "
                f"picture={('from ' + where) if uri else 'no'} "
                f"attachments={keys}")
    if not text and not uri:
        return query, ""
    return (text or "顾客发来一张图片"), uri


def _describe_uri(uri: str, where: str) -> str:
    try:
        import base64
        from knowledge.ks.product_images import describe_bytes
        desc = describe_bytes(base64.b64decode(uri.split(",", 1)[1]))
        logger.info(f"[KS] buyer picture (from {where}): {desc[:60] or 'not described'}")
        return desc
    except Exception as e:
        logger.warning(f"[KS] buyer picture not described: {type(e).__name__}: {e}")
        return ""


def _turn_picture_desc(state: Any) -> str:
    """What the picture in this turn shows, in the words the product pictures
    were described with (product_images.describe_bytes), or ""."""
    if not isinstance(state, dict):
        return ""
    try:
        uri, where = _turn_picture_uri(state)
        if not uri or "," not in uri:
            return ""
        import base64
        from knowledge.ks.product_images import describe_bytes
        desc = describe_bytes(base64.b64decode(uri.split(",", 1)[1]))
        logger.info(f"[KS] buyer picture (from {where}): {desc[:60] or 'not described'}")
        return desc
    except Exception as e:
        logger.warning(f"[KS] buyer picture not described: {type(e).__name__}: {e}")
    return ""


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


_DEFAULT_POLICIES: Optional[Dict[str, str]] = None


def default_policies() -> Dict[str, str]:
    """topic -> the standard store policy text (the 店铺规则 page's 载入标准模板;
    knowledge/ks/default_policies_zh.json, kept identical to the frontend's)."""
    global _DEFAULT_POLICIES
    if _DEFAULT_POLICIES is None:
        import json
        import os
        path = os.path.join(os.path.dirname(__file__), "default_policies_zh.json")
        try:
            with open(path, encoding="utf-8") as f:
                _DEFAULT_POLICIES = {k: v for k, v in json.load(f).items() if isinstance(v, str) and v.strip()}
        except Exception as e:
            logger.warning(f"[KS] standard store policies unavailable: {e}")
            _DEFAULT_POLICIES = {}
    return _DEFAULT_POLICIES


def _default_policy_answer(query: str, store_ref: str, saved: list, why: str) -> Optional[Dict[str, Any]]:
    """A policy question (退换/发货/发票/售后/付款/优惠) the store has no saved rule
    for is answered from the standard template instead of "need to verify" every
    time (alpha 2026-10-20: an empty 商品知识 made every 七天无理由/运费险 question a
    placeholder). The store's own saved rule wins per topic. None when the
    question is not about a policy topic, or nothing is left to add."""
    from knowledge.ks.text import POLICY_TOPIC_LABELS, detect_topics
    topics = detect_topics(query)
    if not topics:
        return None
    have = {p.get("topic"): p for p in saved or [] if p.get("text")}
    defaults = default_policies()
    used = [t for t in topics if t not in have and t in defaults]
    if not used:
        return None
    parts = [f"{POLICY_TOPIC_LABELS.get(t, t)}：{have[t]['text']}" for t in topics if t in have]
    parts += [f"{POLICY_TOPIC_LABELS.get(t, t)}（店铺标准规则）：{defaults[t]}" for t in used]
    text = ("【店铺规则】以下为本店规则；标注「店铺标准规则」的是通用标准规则（店铺未单独设置），"
            "回答时用“一般情况下”的口吻，具体以商品页和订单为准；商品本身的信息（材质、尺码等）如无资料仍需核实。\n"
            + "\n".join(parts))
    logger.info(f"[KS] store={store_ref!r}: {why}; policy topics {used} answered from the standard "
                f"template (the store has no saved rule for them)")
    return {
        "status": "success",
        "data": {
            "response": text,
            "references": [{"reference_id": f"default_policy_{t}", "file_path": f"店铺标准规则:{t}",
                            "content": defaults[t]} for t in used],
            "confidence": {"overall_score": 0.6, "confidence_level": "medium",
                           "explanation": f"standard store policy for {used}",
                           "decision": {"should_answer": True},
                           "retrieval": {"score_source": "default_policies", "tier": "default_policy"}},
            "source": "default_policies",
            "product_knowledge": {"tier": "default_policy", "store": store_ref, "topics": used, "reason": why},
        },
    }


def try_product_answer(main_window, input_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Answer a rag_query from product knowledge, or return None to fall
    through to LightRAG. The returned dict is the rag_query meta payload."""
    if not enabled():
        logger.info("[KS] product knowledge off -- using LightRAG")
        return None
    query = str(input_data.get("query") or "").strip()
    query, turn_picture = _unwrap_turn_query(query)
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
    if turn_picture and not scope.get("image_desc"):
        scope = {**scope, "image_desc": _describe_uri(turn_picture, "query")}
    if scope.get("image_desc"):
        # The buyer sent a picture: search by what it shows too (同款 / 相似款).
        query = f"{query}（顾客图片：{scope['image_desc']}）"
        logger.info(f"[KS] searching with the buyer's picture: {scope['image_desc'][:60]}")
    if not item_id:
        item_id = extract_item_id(" ".join(str(v) for v in input_data.values() if isinstance(v, str)))
    try:
        from knowledge.ks.service import get_router, get_service
        svc = get_service(main_window)
        router = get_router(main_window)
        has_remote = any(c.get("enabled", True) for c in router.all_connections())
        if not has_remote and not _has_product_knowledge(svc):
            logger.info(f"[KS] store={store_ref!r}: no products imported yet")
            return (_default_policy_answer(query, store_ref, [], "no products or rules imported yet")
                    or _no_store_knowledge(main_window, store_ref, "no products imported yet"))
        if has_remote:
            result = router.search(query, store=store_ref, platform_item_id=item_id)
        else:
            result = svc.search(query, store_ref=store_ref, platform_item_id=item_id)
            if scope.get("image_desc") and not item_id:
                try:
                    result["candidates"] = (svc.picture_candidates(scope["image_desc"], store_ref)
                                            or result.get("candidates") or [])
                except Exception as e:
                    logger.warning(f"[KS] picture ranking failed: {e}")
                result = _focus_on_picture_match(svc, query, store_ref, result)
    except Exception as e:
        logger.warning(f"[KS] product knowledge lookup failed, using LightRAG: {e}")
        return None
    if not result.get("should_answer"):
        logger.info(f"[KS] store={store_ref!r}: no confident answer (tier={result.get('tier')})")
        return (_default_policy_answer(query, store_ref, result.get("policies") or [],
                                       f"no confident answer (tier={result.get('tier')})")
                or _no_store_knowledge(main_window, store_ref, f"no confident answer (tier={result.get('tier')})"))
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
