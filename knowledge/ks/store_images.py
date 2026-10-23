"""Product main pictures (主图) straight from the store, so a merchant never has
to supply images by hand.

抖店: the 飞鸽 workstation's own product panel request (read-only), run in the
store's logged-in chat page (store_page.py):
    POST pigeon.jinritemai.com/backstage/workstation/get_product_list
    {security_user_id: '', presale_biz_scene: 'b_product_list', page_size, page}
    -> data[i].product_item.product_base_info {product_id, title, main_img}
The `page` field did not page on the test store (2026-10-23), so pages are
asked for until no new product appears.

拼多多: the chat page's 帮下单 goods list (read-only), which lists the whole
store's goods but needs any buyer uid (one this app answered recently):
    POST /latitude/goods/getMallChatGoodsList {uid, pageNum, pageSize}
    -> result.goodsList[i] {goodsId, goodsName, thumbUrl}

A store product is matched to a knowledge-base product by its 商品ID listing
(the 抖店 export imports it), else by exact title. Matched products get the
picture stored and described (product_images.py) and are re-indexed.
"""
from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, Dict, List

from utils.logger_helper import logger_helper as logger

_DOUYIN_JS = r"""(async (page) => {
  const r = await fetch('https://pigeon.jinritemai.com/backstage/workstation/get_product_list?PIGEON_BIZ_TYPE=2&_pms=1',
    {method: 'POST', credentials: 'include', headers: {'Content-Type': 'application/json'},
     body: JSON.stringify({security_user_id: '', presale_biz_scene: 'b_product_list', page_size: 100,
                           page, service_entity_id: ''})});
  const j = await r.json();
  const items = (Array.isArray(j.data) ? j.data : []).map(x => (x.product_item || {}).product_base_info || {})
      .filter(b => b.product_id).map(b => ({id: String(b.product_id), title: b.title || '', image: b.main_img || ''}));
  return JSON.stringify({code: j.code, msg: j.msg || '', items});
})(%d)"""
_PDD_JS = r"""(async (uid, page) => {
  const r = await fetch('/latitude/goods/getMallChatGoodsList', {method: 'POST', credentials: 'include',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify({uid, pageNum: page, pageSize: 50})});
  const j = await r.json();
  const items = (((j.result || {}).goodsList) || []).filter(g => g.goodsId)
      .map(g => ({id: String(g.goodsId), title: g.goodsName || '', image: g.thumbUrl || ''}));
  return JSON.stringify({ok: j.success, msg: j.errorMsg || '', items});
})(%s, %d)"""
MAX_PAGES = 30


async def douyin_products() -> List[Dict[str, str]]:
    """[{id, title, image}] for every 抖店 store open in this app (all stores together)."""
    from agent.ec_skills.browser_use_extension import store_page
    seen: Dict[str, Dict[str, str]] = {}
    for tab in store_page.store_tabs("douyin"):
        for page in range(MAX_PAGES):
            res = await store_page.evaluate(tab["ws"], _DOUYIN_JS % page)
            if res.get("code") not in (0, None):
                raise RuntimeError(f"抖店 product list: {res.get('msg') or res.get('code')}")
            new = [it for it in res.get("items") or [] if it["id"] not in seen]
            for it in new:
                seen[it["id"]] = it
            if not new:
                break
    return list(seen.values())


async def pdd_products() -> List[Dict[str, str]]:
    """[{id, title, image}] for every 拼多多 store open in this app; [] until it has answered a buyer."""
    from agent.ec_skills.browser_use_extension import store_page
    from agent.ec_skills.browser_use_extension.hooks.external.pdd_chat import ws_observer
    uids = list(ws_observer._ECHOES)
    seen: Dict[str, Dict[str, str]] = {}
    for tab in store_page.store_tabs("pdd") if uids else []:
        for page in range(1, MAX_PAGES + 1):
            res = await store_page.evaluate(tab["ws"], _PDD_JS % (json.dumps(uids[-1]), page))
            if res.get("ok") is False:
                raise RuntimeError(f"拼多多 goods list: {res.get('msg')}")
            new = [it for it in res.get("items") or [] if it["id"] not in seen]
            for it in new:
                seen[it["id"]] = it
            if not new:
                break
    return list(seen.values())


def attach(svc, items: List[Dict[str, str]], tenant_id: str = "") -> Dict[str, int]:
    """Give knowledge-base products their store pictures. Returns counts."""
    from knowledge.ks import product_images
    tid = svc.tenant_id(tenant_id or None)
    by_title: Dict[str, List[str]] = {}
    for p in svc.store.list_products(tid, limit=100000)["items"]:
        by_title.setdefault(p.get("title", ""), []).append(p["id"])
    stats = {"store_products": len(items), "matched": 0, "updated": 0, "described": 0}
    for it in items:
        if not it.get("image"):
            continue
        pid = svc.store.resolve_item(tid, it["id"])
        if not pid and len(by_title.get(it.get("title", ""), [])) == 1:
            pid = by_title[it["title"]][0]
        if not pid:
            continue
        stats["matched"] += 1
        prod = svc.store.get_product(pid)
        if not prod:
            continue
        images = product_images.normalize(prod.get("images"))
        if any(e.get("src") == it["image"] for e in images):
            continue
        images = product_images.prepare([{"src": it["image"], "from": "store"}] + images)
        stats["described"] += product_images.describe(images)
        saved, changed = svc.store.upsert_product(prod["tenant_id"], prod["kb_id"], {**prod, "images": images})
        if changed:
            svc._index_product(saved)
            stats["updated"] += 1
    return stats


def sync_open_stores(svc=None) -> Dict[str, Any]:
    """Fetch the products of the 抖店 / 拼多多 stores open in this app and attach
    their main pictures. Safe from any thread; never raises."""
    if svc is None:
        from knowledge.ks.service import get_service
        svc = get_service()
    out: Dict[str, Any] = {}
    for name, fetch in (("抖店", douyin_products), ("拼多多", pdd_products)):
        box: Dict[str, Any] = {}

        def run():
            try:
                box["items"] = asyncio.run(fetch())
            except Exception as exc:
                box["error"] = f"{type(exc).__name__}: {exc}"
        t = threading.Thread(target=run, name="ks-store-images", daemon=True)
        t.start()
        t.join(180)
        if "items" not in box:
            out[name] = {"error": box.get("error") or "timed out"}
            logger.warning(f"[KS] store pictures: could not read the {name} product list ({out[name]['error']})")
            continue
        if not box["items"]:
            continue
        try:
            out[name] = attach(svc, box["items"])
        except Exception as exc:
            out[name] = {"error": str(exc)}
            logger.warning(f"[KS] store pictures ({name}): {type(exc).__name__}: {exc}")
            continue
        logger.info(f"[KS] store pictures ({name}): {json.dumps(out[name], ensure_ascii=False)}")
    return out


def sync_in_background(svc=None) -> None:
    threading.Thread(target=sync_open_stores, args=(svc,), name="ks-store-images-sync", daemon=True).start()
