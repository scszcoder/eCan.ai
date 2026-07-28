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

logger = logging.getLogger("eCan")

_lock = threading.Lock()
_by_goods: dict[str, tuple[float, str]] = {}    # product_id -> (ts, detail)
_by_title: dict[str, tuple[float, str]] = {}    # exact product_name -> (ts, detail)
_MAX_ENTRIES = 200

_HARVEST_RE = re.compile(r"(发货|退款|退货|运费|无理由|包邮)")
_GOODS_ID_RE = re.compile(r"商品ID[:：]\s*(\d+)")


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
    if not isinstance(data, dict):
        return 0
    goods_lists = []
    for key in ("b_goods", "consulting_product", "product_list", "products", "goods"):
        v = data.get(key)
        if isinstance(v, list) and v:
            goods_lists.append(v)
    if not goods_lists:
        return 0
    coupons = _coupon_texts(data)
    harvest: list = []
    _walk_strings(data, harvest)
    stored = 0
    now = time.time()
    for lst in goods_lists:
        for g in lst[:10]:
            if not isinstance(g, dict):
                continue
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
    return stored


def detail_for(goods_id: str = "", title: str = "") -> str:
    """Authoritative detail string for a card, by product_id or exact title."""
    if not enabled():
        return ""
    with _lock:
        hit = _by_goods.get(str(goods_id or "").strip()) if goods_id else None
        if hit is None and title:
            hit = _by_title.get(str(title or "").strip())
    return hit[1] if hit else ""


def enrich_card_text(text: str) -> str:
    """ws186: append the JSON detail to a '[商品卡片] <title> 商品ID:<id>' text
    when we have it and the text doesn't already carry detail markers. Used by
    the ws184 park dispatch (direct-QA lane never passes through ws101)."""
    t = str(text or "")
    if not t.startswith("[商品卡片]") or any(m in t for m in ("￥", "¥", "券", "发货")):
        return t
    m = _GOODS_ID_RE.search(t)
    gid = m.group(1) if m else ""
    title = t[len("[商品卡片]"):].strip()
    if gid and f"商品ID:{gid}" in title:
        title = title.split("商品ID", 1)[0].strip().rstrip(":：")
    detail = detail_for(gid, title)
    if not detail:
        return t
    return f"{t} | {detail}"
