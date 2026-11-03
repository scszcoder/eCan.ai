"""Every SKU of the stores open in this app, with its price, for 价格核验 (price_check).

Read only, from the store pages' own read requests (the same ones the product
export uses, see knowledge/ks/store_images.py):

抖店   pigeon get_product_list: per SKU effective_price (after a running
       discount; coupons are NOT in it -- only the product's discount_min_price
       has them, KEN 11-03), specs; the product's 货号 from its attributes;
       coupons from the product's marketing labels (value, 满X condition).
拼多多 getMallChatGoodsList + skuSelectorForMall per product: per SKU groupPrice
       (拼单价, after a running 限时折扣), normalPrice, outSkuSn (SKU 商家编码),
       specs; outGoodsSn (货号). Coupons: allCouponList.

A SKU: {platform, store_id, product_id, code, title, sku_id, sku_code, spec,
price, stock}; a coupon: {product_id ("" = any product), threshold, amount}. Yuan.
"""
from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, Dict, List, Tuple

from utils.logger_helper import logger_helper as logger

MAX_PAGES = 30
_DOUYIN_JS = r"""(async (page) => {
  const r = await fetch('https://pigeon.jinritemai.com/backstage/workstation/get_product_list?PIGEON_BIZ_TYPE=2&_pms=1',
    {method: 'POST', credentials: 'include', headers: {'Content-Type': 'application/json'},
     body: JSON.stringify({security_user_id: '', presale_biz_scene: 'b_product_list', page_size: 100,
                           page, service_entity_id: ''})});
  const j = await r.json();
  const name = p => ((p || {}).Property || {}).PropertyName || '';
  const skus = [], coupons = [];
  for (const x of (Array.isArray(j.data) ? j.data : [])) {
    const pi = x.product_item || {}, b = pi.product_base_info || {};
    if (!b.product_id) continue;
    const attrs = {};
    for (const p of b.property_value_pair || []) attrs[name(p)] = (p.Values || []).map(v => v.ValueName).join('/');
    const si = pi.sku_info || {}, stock = si.sku_stock_info || {}, mk = si.sku_marketing_info || {};
    for (const l of (pi.marketing_info || {}).makreting_label || []) {
      if (l.type !== 'coupon') continue;
      let e = {}; try { e = JSON.parse(l.extra || '{}'); } catch (err) {}
      const m = String(e.condition_desc || '').match(/满\s*(\d+(?:\.\d+)?)/);
      coupons.push({product_id: String(b.product_id), threshold: m ? Number(m[1]) : 0,
                    amount: Number(e.value || 0), name: e.name || e.coupon_head || ''});
    }
    for (const k of b.skus || []) {
      const spec = {};
      for (const p of k.sale_property_value_pair || []) spec[name(p)] = (p.Value || {}).ValueName || '';
      const m = mk[String(k.id)] || {}, s = stock[String(k.id)] || {};
      skus.push({product_id: String(b.product_id), code: attrs['货号'] || '', title: b.title || '',
        sku_id: String(k.id), sku_code: '', spec, price: m.effective_price || m.origin_price,
        stock: (s.normal_stock_num_sum || 0) + (s.campaign_now_stock_num || 0)});
    }
  }
  return JSON.stringify({code: j.code, msg: j.msg || '', skus, coupons});
})(%d)"""
_PDD_LIST_JS = r"""(async (page) => {
  const r = await fetch('/latitude/goods/getMallChatGoodsList', {method: 'POST', credentials: 'include',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify({uid: '0', pageNum: page, pageSize: 50})});
  const j = await r.json();
  return JSON.stringify({ok: j.success, msg: j.errorMsg || '',
    ids: (((j.result || {}).goodsList) || []).filter(g => g.goodsId).map(g => String(g.goodsId))});
})(%d)"""
_PDD_SKU_JS = r"""(async (ids) => {
  const clean = v => String(v || '').replace(/^\/+|\/+$/g, '').trim();
  const out = [];
  for (const id of ids) {
    try {
      const j = await (await fetch('/latitude/goods/skuSelectorForMall', {method: 'POST', credentials: 'include',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify({goodsId: Number(id), uid: '0'})})).json();
      const g = j.result || {};
      for (const k of g.sku || []) {
        if (k.isOnsale === 0) continue;
        const spec = {};
        for (const sp of k.specs || []) if (sp.specKey) spec[sp.specKey] = clean(sp.specValue);
        out.push({product_id: id, code: g.outGoodsSn || '', title: g.goodsName || '', sku_id: String(k.skuId),
          sku_code: k.outSkuSn || '', spec, price: k.groupPrice, single_price: k.normalPrice, stock: k.quantity});
      }
    } catch (e) { out.push({product_id: id, error: String(e).slice(0, 120)}); }
  }
  return JSON.stringify(out);
})(%s)"""
_PDD_COUPONS_JS = r"""(async () => {
  const j = await (await fetch('/latitude/coupon/allCouponList', {method: 'POST', credentials: 'include',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify({uid: '0'})})).json();
  return JSON.stringify({ok: j.success, msg: j.errorMsg || '', result: j.result || {}});
})()"""
DETAIL_BATCH = 20


def _yuan(fen: Any) -> Any:
    try:
        return round(int(fen) / 100, 2)
    except (TypeError, ValueError):
        return None


def pdd_coupons(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """allCouponList's result -> [{product_id?, threshold, amount}] in yuan."""
    out = []
    for key in ("allMallCouponList", "mallCoupons", "allGoodsCouponList", "goodsCoupons"):
        for c in result.get(key) or []:
            if not isinstance(c, dict):
                continue
            amount = _yuan(c.get("discount") or c.get("discountAmount") or c.get("discount_amount"))
            if not amount:
                continue
            gid = (c.get("goodsId") or c.get("goods_id")) if "oods" in key else ""
            out.append({"product_id": str(gid or ""), "threshold": _yuan(c.get("minAmount") or c.get("min_amount")
                                                                          or c.get("threshold")) or 0,
                        "amount": amount, "name": str(c.get("couponName") or c.get("name") or "")})
    return out


async def douyin_skus() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    from agent.ec_skills.browser_use_extension import store_page
    skus: Dict[str, Dict[str, Any]] = {}
    coupons: List[Dict[str, Any]] = []
    for tab in store_page.store_tabs("douyin"):
        for page in range(MAX_PAGES):
            res = await store_page.evaluate(tab["ws"], _DOUYIN_JS % page, timeout=60.0)
            if res.get("code") not in (0, None):
                raise RuntimeError(f"抖店 product list: {res.get('msg') or res.get('code')}")
            new = [s for s in res.get("skus") or [] if s["sku_id"] not in skus]
            for s in new:
                skus[s["sku_id"]] = {**s, "platform": "douyin", "store_id": tab.get("store_id", ""),
                                     "price": _yuan(s.get("price"))}
            coupons += [dict(c, store_id=tab.get("store_id", "")) for c in res.get("coupons") or []]
            if not new:
                break
    return list(skus.values()), coupons


async def pdd_skus() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    from agent.ec_skills.browser_use_extension import store_page
    skus: List[Dict[str, Any]] = []
    coupons: List[Dict[str, Any]] = []
    for tab in store_page.store_tabs("pdd"):
        ids: List[str] = []
        for page in range(1, MAX_PAGES + 1):
            res = await store_page.evaluate(tab["ws"], _PDD_LIST_JS % page)
            if res.get("ok") is False:
                raise RuntimeError(f"拼多多 goods list: {res.get('msg')}")
            new = [i for i in res.get("ids") or [] if i not in ids]
            ids += new
            if not new:
                break
        for i in range(0, len(ids), DETAIL_BATCH):
            for s in await store_page.evaluate(tab["ws"], _PDD_SKU_JS % json.dumps(ids[i:i + DETAIL_BATCH]), timeout=90.0) or []:
                if s.get("error"):
                    logger.warning(f"[price-check] 拼多多 {s['product_id']}: {s['error']}")
                    continue
                skus.append({**s, "platform": "pdd", "store_id": tab.get("store_id", ""),
                             "price": _yuan(s.get("price")), "single_price": _yuan(s.get("single_price"))})
        res = await store_page.evaluate(tab["ws"], _PDD_COUPONS_JS)
        coupons += [dict(c, store_id=tab.get("store_id", "")) for c in pdd_coupons(res.get("result") or {})]
    return skus, coupons


def read_store_skus(platform: str, timeout_s: float = 300.0) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """(skus, coupons) of every open store of *platform* ("douyin" | "pdd"), from any thread."""
    fn = {"douyin": douyin_skus, "pdd": pdd_skus}[platform]
    box: Dict[str, Any] = {}

    def run():
        try:
            box["out"] = asyncio.run(fn())
        except Exception as exc:
            box["error"] = f"{type(exc).__name__}: {exc}"
    t = threading.Thread(target=run, name=f"price-check-{platform}", daemon=True)
    t.start()
    t.join(timeout_s)
    if "out" not in box:
        raise RuntimeError(box.get("error") or "timed out")
    return box["out"]
