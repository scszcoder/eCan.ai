"""Built-in "store" vendor for query_price / query_inventories / query_order:
the store's own back office, read-only, in the logged-in chat page.

It is the default when no merchant stock/ERP connector is configured
(ECAN_CUSTOMER_DATA_VENDOR unset). Before 2026-10-24 that default was the
development "mock" vendor, which told buyers "暂无库存记录" for products the
store had 600 of (KEN photo evals).

Stock and price come from the store's live product list (store_images.py:
抖店 get_product_list / 拼多多 getMallChatGoodsList). The model passes the
knowledge-base product code as "sku"; it is mapped through the product's
商品ID listing, else taken as a 商品ID, else matched by title.
Orders: lookup_order, which checks the order belongs to this buyer.
"""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

_CACHE_S = 60.0
_cache: Dict[str, Any] = {"at": 0.0, "items": []}
_lock = threading.Lock()


def _live_products() -> List[Dict[str, Any]]:
    """Both platforms' current product lists (cached for a minute)."""
    with _lock:
        if time.time() - _cache["at"] < _CACHE_S:
            return _cache["items"]
    from knowledge.ks import store_images
    box: Dict[str, Any] = {}

    def run():
        items: List[Dict[str, Any]] = []
        for fetch in (store_images.douyin_products, store_images.pdd_products):
            try:
                items.extend(asyncio.run(fetch()))
            except Exception as exc:
                logger.warning(f"[store-vendor] product list not read: {type(exc).__name__}: {exc}")
        box["items"] = items
    t = threading.Thread(target=run, name="store-vendor", daemon=True)
    t.start()
    t.join(60)
    items = box.get("items") or []
    with _lock:
        _cache.update(at=time.time(), items=items)
    return items


def _item_ids(ref: str) -> List[str]:
    """商品IDs for *ref*: a knowledge-base product code's listings, else ref itself."""
    ids = [ref]
    try:
        from knowledge.ks.service import get_service
        svc = get_service()
        p = svc.store.find_product_by_code(svc.tenant_id(None), ref)
        if p:
            ids = [l["platform_item_id"] for l in p.get("listings") or [] if l.get("platform_item_id")] + [ref]
            ids.append("title:" + p.get("title", ""))
    except Exception:
        pass
    return ids


def find(ref: str) -> Optional[Dict[str, Any]]:
    ref = str(ref or "").strip()
    if not ref:
        return None
    items = _live_products()
    ids = _item_ids(ref)
    for it in items:
        if it.get("id") in ids:
            return it
    titles = [i[len("title:"):] for i in ids if i.startswith("title:")] + [ref]
    for it in items:
        t = it.get("title") or ""
        if any(x and (x == t or (len(x) >= 6 and x in t)) for x in titles):
            return it
    return None


def _not_found(ref: str) -> Dict[str, Any]:
    return {"sku": ref, "found": False,
            "note": "店铺后台商品列表里没有找到这个商品（不代表没货）。不要说没货；请顾客发商品链接或确认是哪款。"}


def inventory(input_data: Dict[str, Any]) -> Dict[str, Any]:
    ref = str(input_data.get("sku") or "").strip()
    it = find(ref)
    if not it:
        return _not_found(ref)
    stock = it.get("stock")
    return {"sku": ref, "found": True, "title": it.get("title"), "in_stock": bool(stock and stock > 0),
            "stock_total": stock, "source": "店铺后台实时商品列表",
            "note": "按规格的库存以下单页为准" if stock else "店铺后台显示该商品当前无可售库存"}


def price(input_data: Dict[str, Any]) -> Dict[str, Any]:
    ref = str(input_data.get("sku") or "").strip()
    it = find(ref)
    if not it:
        return _not_found(ref)
    fen = it.get("price_fen") or 0
    return {"sku": ref, "found": bool(fen), "title": it.get("title"),
            "price_yuan_from": round(fen / 100, 2) if fen else None, "source": "店铺后台实时商品列表",
            "note": "最低规格价；优惠以下单页为准" if fen else "后台未显示价格，请以商品页为准"}


def order(input_data: Dict[str, Any]) -> Dict[str, Any]:
    return {"order_id": input_data.get("order_id"), "found": None,
            "note": "请改用 lookup_order（平台 + 本会话顾客 + 订单号）核对订单；它只返回属于这位顾客的订单。"}
