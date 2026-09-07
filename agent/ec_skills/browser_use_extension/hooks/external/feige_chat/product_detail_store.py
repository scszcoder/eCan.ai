"""ws186: authoritative product-card detail from the CAPTURED backstage JSON.

The cold-start post-mortem's design lesson #1 applied to response quality:
the page's own ``getTemplateCardDataV2`` / ``get_consulting_products`` /
``get_product_list`` responses carry everything the customer can see on a
product card — 券后价/原价, 优惠券, 已售, 发货/保障 texts, product_id —
while the WS frame gives only title+goods_id and the ws101 DOM span scrape
recovers just 价格/券/发货 *when the card has painted* (25-44s lag on cold
reopens, ≤4 retries, misses under load). event_monitor already fetched these
response bodies (ECAN_FEIGE_PRODUCT_DETAIL_CAPTURE, log-only); ws186 parses
them into a per-goods store that:

- seeds ws101's ``_CARD_DETAIL_CACHE`` (pre_dispatch_enrich) so the enrich
  path prefers the JSON detail and skips the paint-dependent scrape retries;
- enriches ws184-parked card dispatches at dispatch time (``enrich_card_text``)
  so even the direct-QA lane carries 价格/券/发货 without any DOM wait.

Keys: product_id (== the WS frame's 商品ID) and exact product_name (fallback
join when id formats ever diverge). Tolerant parser: targeted field extraction
plus a keyword harvest over all strings (发货/退款/运费/无理由), so partial or
truncated schemas still yield a useful detail line. Kill: ECAN_FEIGE_CARD_JSON=0.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time

# CN builds name the app logger "eCan.cn" (propagate=False) — a bare
# getLogger("eCan") record never reaches its handlers, silencing this
# module's entire log output in packaged CN apps (v0.9.95u incident:
# the WS reader looked dead because none of its lines could land).
from utils.logger_helper import logger_helper as logger

_lock = threading.Lock()
_by_goods: dict[str, tuple[float, str]] = {}    # product_id -> (ts, detail)
_by_title: dict[str, tuple[float, str]] = {}    # exact product_name -> (ts, detail)
# ws195: product ATTRIBUTES kept in a SEPARATE store — they arrive on a
# different body (get_product_list, data=list) than the price/发货 detail
# (getTemplateCardDataV2), so a shared key would let one body's write clobber
# the other's. detail_for() merges the two at read time.
_by_goods_attrs: dict[str, tuple[float, str]] = {}   # product_id -> (ts, attr_line)
_by_title_attrs: dict[str, tuple[float, str]] = {}   # exact product_name -> (ts, attr_line)
_MAX_ENTRIES = 200

_HARVEST_RE = re.compile(r"(发货|退款|退货|运费|无理由|包邮)")
_GOODS_ID_RE = re.compile(r"商品ID[:：]\s*(\d+)")

# ws195: CS-relevant product attributes to surface in the QA card context.
# Kept TIGHT (project_qa_token_bloat): customer factual questions cluster on
# material (掉色/起球/舒适), size/age fit, function and season — NOT the full
# 15-attribute taxonomy (which reinflates the prompt and adds RAG-style noise).
# Without material the QA agent fobs off "会不会掉色" with "稍后回复您" (the
# 2026-09-07 customer report) even though the card JSON carries 面料材质.
_ATTR_WHITELIST = ("面料材质", "材质", "里料材质", "适用年龄", "尺码", "功能",
                   "适用季节", "裤长", "领型", "版型")
_ATTR_MAX = 5           # at most N whitelisted attributes
_ATTR_LINE_MAX = 160    # chars cap on the whole 属性 segment


def enabled() -> bool:
    import os
    return os.environ.get("ECAN_FEIGE_CARD_JSON", "1") != "0"


def _trim(store: dict) -> None:
    while len(store) > _MAX_ENTRIES:
        store.pop(next(iter(store)))


def _walk_strings(obj, out: list, depth: int = 0) -> None:
    """Collect guarantee/shipping-ish display strings anywhere in the JSON."""
    if depth > 8 or len(out) >= 6:
        return
    if isinstance(obj, dict):
        for v in obj.values():
            _walk_strings(v, out, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            _walk_strings(v, out, depth + 1)
    elif isinstance(obj, str):
        s = obj.strip()
        # display text, not urls/ids/json blobs
        if (2 <= len(s) <= 30 and _HARVEST_RE.search(s)
                and "http" not in s and "{" not in s and s not in out):
            out.append(s)


def _coupon_texts(data: dict) -> list:
    out = []
    for act in (data.get("b_activities") or []):
        if not isinstance(act, dict):
            continue
        pre = (((act.get("prefix") or {}).get("text_content")) or "").strip()
        suf = (((act.get("suffix") or {}).get("text_content")) or "").strip()
        joined = (pre + suf).strip()
        if joined and joined not in out:
            out.append(joined)
    return out


def _detail_from_goods(g: dict, coupons: list, harvest: list) -> tuple[str, str, str]:
    """Return (product_id, product_name, detail_str) for one goods entry."""
    pid = str(g.get("product_id") or g.get("goods_id") or "").strip()
    name = str(g.get("product_name") or g.get("name") or "").strip()
    parts = []
    cur = g.get("current_price") or g.get("discount_price") or {}
    cur_price = str((cur or {}).get("price") or "").strip() if isinstance(cur, dict) else ""
    cur_suffix = str((cur or {}).get("suffix") or (cur or {}).get("prefix") or "").strip() \
        if isinstance(cur, dict) else ""
    origin = str(g.get("price") or g.get("origin_price") or "").strip()
    if cur_price:
        parts.append(f"价格:￥{cur_price}" + (f"({cur_suffix})" if "券" in cur_suffix else ""))
        if origin and origin != cur_price:
            parts.append(f"原价:￥{origin}")
    elif origin:
        parts.append(f"价格:￥{origin}")
    if coupons:
        parts.append("优惠:" + "/".join(coupons[:3]))
    sell = str(g.get("sell_num_desc") or "").strip()
    if sell:
        parts.append(sell)
    if harvest:
        parts.append("发货/保障:" + "/".join(harvest))
    status = str(g.get("product_status") or "").strip()
    if status:
        parts.append(f"状态:{status}")
    if pid:
        parts.append(f"商品ID:{pid}")
    return pid, name, " ".join(parts)


def _resolve_pid_name(g: dict) -> "tuple[str, str]":
    """product_id + name for a goods entry, checking the nested
    product_item.product_base_info too — get_product_list entries carry the
    real ids/title there, not at the top level (top-level product_id is '')."""
    pid = str(g.get("product_id") or g.get("goods_id") or "").strip()
    name = str(g.get("product_name") or g.get("name") or "").strip()
    pi = g.get("product_item")
    if isinstance(pi, dict):
        pbi = pi.get("product_base_info")
        if isinstance(pbi, dict):
            pid = pid or str(pbi.get("product_id") or "").strip()
            name = name or str(pbi.get("title") or "").strip()
    return pid, name


def _attrs_from_goods(g: dict) -> str:
    """Compact, whitelisted 属性 line from a goods entry's
    ``property_value_pair`` (present on get_product_list / some card bodies).

    Answers the attribute questions the price/发货 detail can't — e.g.
    '会不会掉色' needs 面料材质. Empty when no whitelisted attribute is present.
    Capped for token budget (project_qa_token_bloat)."""
    base = g
    try:
        pi = g.get("product_item")
        if isinstance(pi, dict):
            pbi = pi.get("product_base_info")
            if isinstance(pbi, dict) and isinstance(pbi.get("property_value_pair"), list):
                base = pbi
    except Exception:
        base = g
    pvp = base.get("property_value_pair")
    if not isinstance(pvp, list):
        return ""
    picked = []
    for entry in pvp:
        if not isinstance(entry, dict):
            continue
        pname = str(((entry.get("Property") or {}) or {}).get("PropertyName") or "").strip()
        if not pname or not any(w in pname for w in _ATTR_WHITELIST):
            continue
        vals = []
        for v in (entry.get("Values") or []):
            if isinstance(v, dict):
                vn = str(v.get("ValueName") or "").strip()
                if vn:
                    vals.append(vn)
        if vals:
            picked.append(f"{pname}={'/'.join(vals[:3])}")
        if len(picked) >= _ATTR_MAX:
            break
    line = " ".join(picked)
    return line[:_ATTR_LINE_MAX] if line else ""


def note_detail_body(url: str, body: str) -> int:
    """Parse one captured product/card response body; returns entries stored."""
    if not enabled() or not body:
        return 0
    # Runs on the dedicated capture client's loop (never the CDP handler loop
    # or renderer), so a slow parse can only delay further capture — but bound
    # it anyway: a pathological multi-MB body isn't a product card.
    if len(body) > 512 * 1024:
        return 0
    try:
        obj = json.loads(body)
    except Exception:
        return 0
    if not isinstance(obj, dict):
        return 0
    data = obj.get("data")
    # ws195: get_product_list returns ``data`` as a LIST of goods (the body that
    # carries the full property_value_pair attributes) — it was dropped by the
    # dict-only guard, so attributes never reached the store. Accept both shapes.
    goods_lists = []
    if isinstance(data, list) and data:
        goods_lists.append(data)
    elif isinstance(data, dict):
        for key in ("b_goods", "consulting_product", "product_list", "products", "goods"):
            v = data.get(key)
            if isinstance(v, list) and v:
                goods_lists.append(v)
    else:
        return 0
    if not goods_lists:
        return 0
    coupons = _coupon_texts(data) if isinstance(data, dict) else []
    harvest: list = []
    _walk_strings(data, harvest)
    stored = 0
    stored_attrs = 0
    now = time.time()
    for lst in goods_lists:
        for g in lst[:10]:
            if not isinstance(g, dict):
                continue
            # ws195: attributes (面料材质/尺码/功能…) — stored independently of
            # the price guard below, since the get_product_list body carries
            # attributes but no card-shaped price. Nested-aware pid/name.
            attrs = _attrs_from_goods(g)
            if attrs:
                apid, aname = _resolve_pid_name(g)
                with _lock:
                    if apid:
                        _by_goods_attrs[apid] = (now, attrs)
                        _trim(_by_goods_attrs)
                    if aname:
                        _by_title_attrs[aname] = (now, attrs)
                        _trim(_by_title_attrs)
                if apid or aname:
                    stored_attrs += 1
                    logger.info(
                        f"[FEIGE-CARD-JSON] stored attrs goods={apid or '?'} "
                        f"name={aname[:24]!r} attrs={attrs[:120]!r}")
            pid, name, detail = _detail_from_goods(g, coupons, harvest)
            # a detail line with no price/coupon/shipping content is useless
            if not detail or not re.search(r"[￥券]|发货", detail):
                continue
            with _lock:
                if pid:
                    _by_goods[pid] = (now, detail)
                    _trim(_by_goods)
                if name:
                    _by_title[name] = (now, detail)
                    _trim(_by_title)
            stored += 1
            logger.info(
                f"[FEIGE-CARD-JSON] stored detail goods={pid or '?'} "
                f"name={name[:24]!r} detail={detail[:120]!r} "
                f"(src={'card' if 'TemplateCard' in url else 'workstation'})")
    return stored + stored_attrs


def detail_for(goods_id: str = "", title: str = "") -> str:
    """Authoritative detail string for a card, by product_id or exact title.

    ws195: merges the price/发货 detail with the separately-stored 属性 line
    (面料材质/尺码/功能…) so the QA context can answer attribute questions
    ('会不会掉色' → 面料材质) instead of fobbing the customer off. Either half
    may be missing; returns whatever is available (never fabricated)."""
    if not enabled():
        return ""
    gid = str(goods_id or "").strip()
    ttl = str(title or "").strip()
    with _lock:
        hit = _by_goods.get(gid) if gid else None
        if hit is None and ttl:
            hit = _by_title.get(ttl)
        ahit = _by_goods_attrs.get(gid) if gid else None
        if ahit is None and ttl:
            ahit = _by_title_attrs.get(ttl)
    price = hit[1] if hit else ""
    attrs = ahit[1] if ahit else ""
    if price and attrs:
        return f"{price} 属性:{attrs}"
    if attrs:
        return f"属性:{attrs}"
    return price


# Markers that begin the price/coupon/shipping tail of a card text, i.e. where
# the clean product title ends. Used to recover the title from a slim DOM card
# ("[商品卡片] <title> ￥38.00 (券:立减10元) …") so the authoritative detail can
# be looked up by title when the slim card carries no 商品ID.
_TITLE_TAIL_RE = re.compile(r"\s*(?:商品ID[:：]|[￥¥]|[（(]?券|未发货|已发货|[（(]服务|发货|价格[:：])")


def enrich_card_text(text: str) -> str:
    """ws186/ws191: make a '[商品卡片] …' text carry the AUTHORITATIVE
    getTemplateCardDataV2 detail (券后价/原价/优惠/发货).

    Two cases:
      * bare card, no price markers yet → append the detail (original ws186).
      * slim DOM card that ALREADY shows an ambiguous price
        ("￥38.00 (券:立减10元)") → REPLACE it with the authoritative detail
        when we have it, so the two dispatch lanes never disagree on price
        (live 2026-09-05: same product answered 券后28元 on the slim card and
        券后38元 on the authoritative card). When no authoritative detail is
        stored, the text is returned unchanged (never fabricated)."""
    t = str(text or "")
    if not t.startswith("[商品卡片]"):
        return t
    body = t[len("[商品卡片]"):].strip()
    m = _GOODS_ID_RE.search(t)
    gid = m.group(1) if m else ""
    # Clean title = body up to the first price/id/coupon/shipping marker.
    title = _TITLE_TAIL_RE.split(body, 1)[0].strip().rstrip(":：|").strip()
    detail = detail_for(gid, title)
    if not detail:
        # No authoritative detail: preserve prior behaviour exactly — only the
        # already-priced card is left untouched; a bare card gets nothing to add.
        return t
    canonical = "[商品卡片] " + title
    if gid:
        canonical += f" 商品ID:{gid}"
    return f"{canonical} | {detail}"
