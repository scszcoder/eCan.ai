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
store's goods; any uid works, "0" included (2026-10-24 KEN: 12 of 12 with "0",
none with ""), so no buyer has to have been answered first:
    POST /latitude/goods/getMallChatGoodsList {uid, pageNum, pageSize}
    -> result.goodsList[i] {goodsId, goodsName, thumbUrl}
and per product, from the same page:
    POST /latitude/goods/goodsProperties {goodsId} -> result.properties[{name, values}]
    POST /latitude/goods/skuSelectorForMall {goodsId, uid} -> result.sku[{specs[{specKey, specValue}]}]
(the 商品列表 page's own /vodka/.../goodsList API wants a signed anti-content
header and answers 54001 操作太过频繁 to a plain request).

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
  const items = (Array.isArray(j.data) ? j.data : []).map(x => x.product_item || {})
      .filter(pi => (pi.product_base_info || {}).product_id).map(pi => {
        const b = pi.product_base_info, ss = ((pi.sku_info || {}).sku_stock_info) || {};
        const price = ((pi.marketing_info || {}).price) || {};
        return {id: String(b.product_id), title: b.title || '', image: b.main_img || '',
          attributes: Object.fromEntries(pairs(b.property_value_pair)),
          variants: (b.skus || []).map(k => Object.fromEntries(pairs(k.sale_property_value_pair))),
          stock: Object.values(ss).reduce((n, s) => n + (s.normal_stock_num_sum || 0) + (s.campaign_now_stock_num || 0), 0),
          price_fen: price.effective_min_price || price.origin_price || 0};
      });
  return JSON.stringify({code: j.code, msg: j.msg || '', items});
})(%d)"""
_PDD_JS = r"""(async (uid, page) => {
  const r = await fetch('/latitude/goods/getMallChatGoodsList', {method: 'POST', credentials: 'include',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify({uid, pageNum: page, pageSize: 50})});
  const j = await r.json();
  const items = (((j.result || {}).goodsList) || []).filter(g => g.goodsId)
      .map(g => ({id: String(g.goodsId), title: g.goodsName || '', image: g.thumbUrl || '',
                  stock: g.quantity, price_fen: g.minOnSaleGroupPriceOriginal || 0}));
  return JSON.stringify({ok: j.success, msg: j.errorMsg || '', items});
})(%s, %d)"""
# Attributes and SKU specs of the given goods ids, one product at a time.
_PDD_DETAIL_JS = r"""(async (uid, ids) => {
  const post = async (ep, body) => {
    const j = await (await fetch(ep, {method: 'POST', credentials: 'include',
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})).json();
    return j.success ? (j.result || {}) : null;
  };
  const clean = v => String(v || '').replace(/^\/+|\/+$/g, '').trim();
  const out = {};
  for (const id of ids) {
    const d = {attributes: {}, variants: []};
    try {
      const p = await post('/latitude/goods/goodsProperties', {goodsId: Number(id)});
      for (const pr of (p && p.properties) || []) {
        const v = (pr.values || []).map(clean).filter(Boolean).join('、');
        if (pr.name && v) d.attributes[pr.name] = v;
      }
      const k = await post('/latitude/goods/skuSelectorForMall', {goodsId: Number(id), uid});
      for (const sku of (k && k.sku) || []) {
        if (sku.isOnsale === 0) continue;
        const v = {};
        for (const sp of sku.specs || []) if (sp.specKey && clean(sp.specValue)) v[sp.specKey] = clean(sp.specValue);
        if (Object.keys(v).length) d.variants.push(v);
      }
    } catch (e) { d.error = String(e).slice(0, 120); }
    out[id] = d;
  }
  return JSON.stringify(out);
})(%s, %s)"""
MAX_PAGES = 30
DETAIL_BATCH = 20                    # products per in-page call (two small requests each)


async def douyin_products() -> List[Dict[str, Any]]:
    """[{id, title, image, attributes, variants, store_id}] for every 抖店 store open in this app."""
    from agent.ec_skills.browser_use_extension import store_page
    seen: Dict[str, Dict[str, Any]] = {}
    for tab in store_page.store_tabs("douyin"):
        for page in range(MAX_PAGES):
            res = await store_page.evaluate(tab["ws"], _DOUYIN_JS % page)
            if res.get("code") not in (0, None):
                raise RuntimeError(f"抖店 product list: {res.get('msg') or res.get('code')}")
            store_page.note_signed_in(profile_id=tab.get("profile", ""), proof="抖店 product list")
            new = [it for it in res.get("items") or [] if it["id"] not in seen]
            for it in new:
                seen[it["id"]] = {**it, "store_id": tab.get("store_id", ""), "platform": "douyin"}
            if not new:
                break
    return list(seen.values())


async def pdd_products() -> List[Dict[str, Any]]:
    """[{id, title, image, attributes, variants, store_id}] for every 拼多多 store open in this app."""
    from agent.ec_skills.browser_use_extension import store_page
    from agent.ec_skills.browser_use_extension.hooks.external.pdd_chat import ws_observer
    uids = list(ws_observer._ECHOES)
    uid = json.dumps(uids[-1] if uids else "0")
    seen: Dict[str, Dict[str, Any]] = {}
    for tab in store_page.store_tabs("pdd"):
        found = []
        for page in range(1, MAX_PAGES + 1):
            res = await store_page.evaluate(tab["ws"], _PDD_JS % (uid, page))
            if res.get("ok") is False:
                raise RuntimeError(f"拼多多 goods list: {res.get('msg')}")
            store_page.note_signed_in(profile_id=tab.get("profile", ""), proof="拼多多 goods list")
            new = [it for it in res.get("items") or [] if it["id"] not in seen]
            for it in new:
                seen[it["id"]] = {**it, "store_id": tab.get("store_id", ""), "platform": "pdd"}
                found.append(it["id"])
            if not new:
                break
        for i in range(0, len(found), DETAIL_BATCH):
            ids = found[i:i + DETAIL_BATCH]
            details = await store_page.evaluate(tab["ws"], _PDD_DETAIL_JS % (uid, json.dumps(ids)), timeout=60.0)
            for gid, d in (details or {}).items():
                if gid in seen and isinstance(d, dict):
                    seen[gid].update(attributes=d.get("attributes") or {}, variants=d.get("variants") or [])
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
    stats = {"store_products": len(items), "matched": 0, "added": 0, "pictures": 0, "described": 0, "failed": 0}
    for it in items:
        try:
            _attach_one(svc, tid, it, by_code, by_title, stores, stats)
        except Exception as exc:          # one bad product never stops the rest
            stats["failed"] += 1
            logger.warning(f"[KS] store product {it.get('id')} not saved: {type(exc).__name__}: {str(exc)[:200]}")
    return stats


def _attach_one(svc, tid: str, it: Dict[str, Any], by_code: Dict[str, str],
                by_title: Dict[str, List[str]], stores: Dict[str, str], stats: Dict[str, int]) -> None:
    from knowledge.ks import product_images
    from knowledge.ks.text import clean_text
    title = clean_text(it.get("title"))
    if not title:
        return
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
        return
    stats["matched"] += 1
    if ks_store and not listed:
        svc.store.add_listing(pid, ks_store, it["id"])
    if not prod:
        return
    update = {}
    if images and not any(e.get("sha") == images[0].get("sha") for e in have):
        update["images"] = images + have
    # A product this sync added (never one the merchant wrote) takes the
    # store's current attributes and specs: an earlier sync may have had none.
    if prod.get("source") == "store":
        variants = [dict(v) for v in dict.fromkeys(tuple(sorted(v.items())) for v in it.get("variants") or [] if v)]
        if attrs and attrs != (prod.get("attributes") or {}):
            update["attributes"] = attrs
        if variants and variants != (prod.get("variants") or []):
            update["variants"] = variants
    if not update:
        return
    saved, changed = svc.store.upsert_product(prod["tenant_id"], prod["kb_id"], {**prod, **update})
    if changed:
        svc._index_product(saved)
        if "images" in update:
            stats["pictures"] += 1
        if "attributes" in update or "variants" in update:
            stats["details"] = stats.get("details", 0) + 1


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


# 拼多多 coupons, read-only from the chat page (any uid works, as for the goods list).
_PDD_COUPONS_JS = r"""(async (uid) => {
  const r = await fetch('/latitude/coupon/allCouponList', {method: 'POST', credentials: 'include',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify({uid})});
  const j = await r.json();
  return JSON.stringify({ok: j.success, msg: j.errorMsg || '', result: j.result || {}});
})(%s)"""


def _yuan(fen: Any) -> str:
    try:
        v = int(fen) / 100
    except (TypeError, ValueError):
        return ""
    return f"{v:g}" if v else ""


def pdd_coupon_text(result: Dict[str, Any]) -> str:
    """One line for the [当前活动] snapshot from allCouponList's result. Only
    coupons are readable this way, so with none the line says so and points to
    the product page -- never "当前无活动" (a 限时折扣 may still be running)."""
    lines, seen = [], set()
    for key, scope in (("allMallCouponList", "店铺券"), ("mallCoupons", "店铺券"),
                       ("allGoodsCouponList", "商品券"), ("goodsCoupons", "商品券")):
        for c in result.get(key) or []:
            if not isinstance(c, dict):
                continue
            off = _yuan(c.get("discount") or c.get("discountAmount") or c.get("discount_amount"))
            floor = _yuan(c.get("minAmount") or c.get("min_amount") or c.get("threshold"))
            name = str(c.get("couponName") or c.get("name") or c.get("title") or "").strip()
            text = (f"{scope}满{floor}减{off}" if floor and off else f"{scope}立减{off}元" if off else
                    f"{scope}{name}" if name else "")
            if text and text not in seen:
                seen.add(text)
                lines.append(text)
    return "；".join(lines) if lines else "店铺暂无优惠券；其他活动（如限时折扣、多件优惠）以商品页显示为准"


async def pdd_promotions() -> Dict[str, str]:
    """{eCan store id: one-line promotions summary} for every 拼多多 store open in this app."""
    from agent.ec_skills.browser_use_extension import store_page
    from agent.ec_skills.browser_use_extension.hooks.external.pdd_chat import ws_observer
    uids = list(ws_observer._ECHOES)
    uid = json.dumps(uids[-1] if uids else "0")
    out: Dict[str, str] = {}
    for tab in store_page.store_tabs("pdd"):
        res = await store_page.evaluate(tab["ws"], _PDD_COUPONS_JS % uid)
        if res.get("ok") is False:
            raise RuntimeError(f"拼多多 coupons: {res.get('msg')}")
        out[tab.get("store_id", "")] = pdd_coupon_text(res.get("result") or {})
    return out


def read_pdd_promotions(timeout_s: float = 60.0) -> Dict[str, str]:
    """pdd_promotions() from any thread (a skill's code step)."""
    box: Dict[str, Any] = {}

    def run():
        try:
            box["out"] = asyncio.run(pdd_promotions())
        except Exception as exc:
            box["error"] = f"{type(exc).__name__}: {exc}"
    t = threading.Thread(target=run, name="ks-pdd-promos", daemon=True)
    t.start()
    t.join(timeout_s)
    if "out" not in box:
        raise RuntimeError(box.get("error") or "timed out")
    return box["out"]
