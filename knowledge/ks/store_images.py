"""The store's own product list as a knowledge source: every on-sale product
gets at least its title, attributes, variants and main picture (主图) in the
knowledge base, and existing products get their pictures -- so a merchant
never has to supply images, and a new install is not empty.

抖店: the 飞鸽 workstation's own product panel request (read-only), run in the
store's logged-in chat page (store_page.py):
    POST pigeon.jinritemai.com/backstage/workstation/get_product_list
    {security_user_id: '', presale_biz_scene: 'b_product_list', page_size, page}
    -> data[i].product_item.product_base_info {product_id, title, main_img,
       property_value_pair (attributes incl. 货号), skus[].sale_property_value_pair}
The `page` field did not page on the test store (2026-10-23), so pages are
asked for until no new product appears.

拼多多: the chat page's 帮下单 goods list (read-only), which lists the whole
store's goods but needs any buyer uid (one this app answered recently):
    POST /latitude/goods/getMallChatGoodsList {uid, pageNum, pageSize}
    -> result.goodsList[i] {goodsId, goodsName, thumbUrl}

A store product is matched to a knowledge-base product by its 商品ID listing
(the 抖店 export imports it), else by 货号 = product code, else by a unique
exact title; a match only gets the picture (and the 商品ID listing) -- what
the merchant wrote is never overwritten. An unmatched product is added
(source "store"). Price is not stored (like the importer: it changes).
Pictures are stored and described by product_images.py.
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
  const pairs = l => (l || []).map(p => [(p.Property || {}).PropertyName || '',
                                         (p.Values || []).map(v => v.ValueName).filter(Boolean).join('/')])
                               .filter(([k, v]) => k && v);
  const items = (Array.isArray(j.data) ? j.data : []).map(x => (x.product_item || {}).product_base_info || {})
      .filter(b => b.product_id).map(b => ({id: String(b.product_id), title: b.title || '', image: b.main_img || '',
        attributes: Object.fromEntries(pairs(b.property_value_pair)),
        variants: (b.skus || []).map(k => Object.fromEntries(pairs(k.sale_property_value_pair)))}));
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


async def douyin_products() -> List[Dict[str, Any]]:
    """[{id, title, image, attributes, variants, store_id}] for every 抖店 store open in this app."""
    from agent.ec_skills.browser_use_extension import store_page
    seen: Dict[str, Dict[str, Any]] = {}
    for tab in store_page.store_tabs("douyin"):
        for page in range(MAX_PAGES):
            res = await store_page.evaluate(tab["ws"], _DOUYIN_JS % page)
            if res.get("code") not in (0, None):
                raise RuntimeError(f"抖店 product list: {res.get('msg') or res.get('code')}")
            new = [it for it in res.get("items") or [] if it["id"] not in seen]
            for it in new:
                seen[it["id"]] = {**it, "store_id": tab.get("store_id", ""), "platform": "douyin"}
            if not new:
                break
    return list(seen.values())


async def pdd_products() -> List[Dict[str, Any]]:
    """[{id, title, image, store_id}] for every 拼多多 store open in this app; [] until it has answered a buyer."""
    from agent.ec_skills.browser_use_extension import store_page
    from agent.ec_skills.browser_use_extension.hooks.external.pdd_chat import ws_observer
    uids = list(ws_observer._ECHOES)
    seen: Dict[str, Dict[str, Any]] = {}
    for tab in store_page.store_tabs("pdd") if uids else []:
        for page in range(1, MAX_PAGES + 1):
            res = await store_page.evaluate(tab["ws"], _PDD_JS % (json.dumps(uids[-1]), page))
            if res.get("ok") is False:
                raise RuntimeError(f"拼多多 goods list: {res.get('msg')}")
            new = [it for it in res.get("items") or [] if it["id"] not in seen]
            for it in new:
                seen[it["id"]] = {**it, "store_id": tab.get("store_id", ""), "platform": "pdd"}
            if not new:
                break
    return list(seen.values())


def _ks_store(svc, tid: str, store_id: str, platform: str, cache: Dict[str, str]) -> str:
    """The knowledge-base store for eCan store *store_id* (created when missing)."""
    if not store_id:
        return ""
    if store_id not in cache:
        st = svc.store.find_store(tid, store_id) or svc.store.upsert_store(
            tid, name=store_id, platform=platform, ecan_store_id=store_id)
        cache[store_id] = st["id"]
    return cache[store_id]


def attach(svc, items: List[Dict[str, Any]], tenant_id: str = "") -> Dict[str, int]:
    """Bring the store's products into the knowledge base: pictures for the
    ones already there, new products for the rest. Returns counts."""
    from knowledge.ks import product_images
    from knowledge.ks.text import clean_text
    tid = svc.tenant_id(tenant_id or None)
    by_title: Dict[str, List[str]] = {}
    by_code: Dict[str, str] = {}
    for p in svc.store.list_products(tid, limit=100000)["items"]:
        by_title.setdefault(p.get("title", ""), []).append(p["id"])
        by_code[p.get("code", "")] = p["id"]
    stores: Dict[str, str] = {}
    stats = {"store_products": len(items), "matched": 0, "added": 0, "pictures": 0, "described": 0}
    for it in items:
        title = clean_text(it.get("title"))
        if not title:
            continue
        attrs = {k: v for k, v in (it.get("attributes") or {}).items() if k and v}
        code = attrs.get("货号") or it["id"]
        ks_store = _ks_store(svc, tid, it.get("store_id", ""), it.get("platform", ""), stores)
        pid = svc.store.resolve_item(tid, it["id"])
        listed = bool(pid)
        if not pid:
            pid = by_code.get(code) or (by_title[title][0] if len(by_title.get(title, [])) == 1 else None)
        if pid:
            prod = svc.store.get_product(pid)
            have = product_images.normalize(prod.get("images")) if prod else []
            if any(e.get("src") == it.get("image") for e in have):
                images = []               # this picture is already there
            else:
                images = product_images.prepare([{"src": it["image"], "from": "store"}]) if it.get("image") else []
        else:
            prod, have = None, []
            images = product_images.prepare([{"src": it["image"], "from": "store"}]) if it.get("image") else []
        stats["described"] += product_images.describe(images)
        if not pid:
            variants = [tuple(sorted(v.items())) for v in it.get("variants") or [] if v]
            svc.save_product({
                "code": code, "title": title, "attributes": attrs,
                "variants": [dict(v) for v in dict.fromkeys(variants)],
                "images": images, "source": "store",
                "listings": [{"store_id": ks_store, "platform_item_id": it["id"]}] if ks_store else []},
                tenant_id=tid)
            stats["added"] += 1
            continue
        stats["matched"] += 1
        if ks_store and not listed:
            svc.store.add_listing(pid, ks_store, it["id"])
        if not prod or not images or any(e.get("sha") == images[0].get("sha") for e in have):
            continue
        saved, changed = svc.store.upsert_product(prod["tenant_id"], prod["kb_id"],
                                                  {**prod, "images": images + have})
        if changed:
            svc._index_product(saved)
            stats["pictures"] += 1
    return stats


def sync_open_stores(svc=None) -> Dict[str, Any]:
    """Read the products of the 抖店 / 拼多多 stores open in this app into the
    knowledge base (attach). Safe from any thread; never raises."""
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
            logger.warning(f"[KS] store products: could not read the {name} product list ({out[name]['error']})")
            continue
        if not box["items"]:
            continue
        try:
            if svc is None:                 # opened only when there is something to write
                from knowledge.ks.service import get_service
                svc = get_service()
            out[name] = attach(svc, box["items"])
        except Exception as exc:
            out[name] = {"error": str(exc)}
            logger.warning(f"[KS] store products ({name}): {type(exc).__name__}: {exc}")
            continue
        logger.info(f"[KS] store products ({name}): {json.dumps(out[name], ensure_ascii=False)}")
    return out


def sync_in_background(svc=None) -> None:
    threading.Thread(target=sync_open_stores, args=(svc,), name="ks-store-images-sync", daemon=True).start()


_SYNC_EVERY_S = 12 * 3600
_last_sync = 0.0
_sync_lock = threading.Lock()


def maybe_sync() -> None:
    """Called when a store chat sends a reply: sync at most every 12 h, so a
    store whose catalog was never imported still gets its products (and
    拼多多 has the buyer uid its list needs). Cheap; never raises."""
    global _last_sync
    import time
    with _sync_lock:
        if time.time() - _last_sync < _SYNC_EVERY_S:
            return
        _last_sync = time.time()
    try:
        sync_in_background()
    except Exception as exc:
        logger.warning(f"[KS] store products: background sync not started ({exc})")
