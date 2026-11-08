"""Read a listed product back from the platform itself, read-only, for checks.

A browser agent asked to "read the product page" described another product
(拼多多 run 73, KEN 11-01: eight SKU codes from some other goods), and a product
id taken from the agent's report can be wrong (抖店 run 72 reported 79676396 for
3851450341539316685). This reads the platform's own back-office APIs in a tab
of the store's logged-in browser -- the same read-only calls the confirm-listing
actions make -- and returns one shape for every platform:

    {"found": bool, "product_id": str, "title": str,
     "skus": [{"spec": ["颜色", "尺码"], "code": str, "price": float, "stock": int}]}

抖店 can also find the newest product by 货号 (outer id) or exact title when the
id is missing or wrong; 拼多多's read needs the goods id.
"""
from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, Dict

from utils.logger_helper import logger_helper as logger

TABS = {"douyin": r"fxg\.jinritemai\.com", "pdd": r"mms\.pinduoduo\.com"}
HOME = {"douyin": "https://fxg.jinritemai.com/ffa/g/list", "pdd": "https://mms.pinduoduo.com/goods/goods_list"}

_DOUYIN_JS = r"""(async (want, outer, title) => {
  const get = async u => (await fetch(u, {credentials: 'include'})).json();
  let row = null, newest = null;
  for (let page = 0; page < 10 && !row; page++) {
    const rows = (await get('/product/tproduct/list?page=' + page + '&pageSize=100&tab=all&business_type=4&appid=1')).data || [];
    row = want ? rows.find(p => String(p.product_id) === want) || null : null;
    for (const p of rows) {
      const hit = (outer && String(p.out_product_id || '') === outer) || (title && String(p.name || '') === title);
      if (hit && !Number(p.delete_time) && (!newest || String(p.create_time) > String(newest.create_time))) newest = p;
    }
    if (!rows.length) break;
  }
  row = row || newest;
  if (!row) return JSON.stringify({found: false});
  const pid = String(row.product_id);
  const s = await (await fetch('/product/tproduct/getSchema?appid=1', {method: 'POST', credentials: 'include',
    headers: {'content-type': 'application/json'}, body: JSON.stringify({context: {product_id: pid}})})).json();
  const m = (s.data || {}).model || {};
  const names = {};
  const groups = ((m.spec_detail || {}).value || ((m.spec_detail || {}).additions || {}).origin_value || []);
  for (const g of groups) for (const v of g.spec_values || []) names[String(v.id)] = v.name;
  const skus = ((m.sku_detail || {}).value || []).map(k => ({
    spec: (k.spec_detail_ids || []).map(i => names[String(i)] || String(i)), code: String(k.code || ''),
    price: Number(k.price), stock: Number((k.stock_info || {}).stock_num ?? k.self_sell_stock)}));
  return JSON.stringify({found: true, product_id: pid, title: String((m.title || {}).value || row.name || ''),
    published: Number(row.publish_time) > 0 && Number(row.draft_status) !== 1 && !Number(row.delete_time), skus});
})(%s, %s, %s)"""

_PDD_JS = r"""(async (want) => {
  const r = await (await fetch('/latitude/goods/skuSelectorForMall', {method: 'POST', credentials: 'include',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify({goodsId: Number(want), uid: '0'})})).json();
  const g = r.success ? (r.result || {}) : null;
  if (!g || String(g.goodsId || '') !== want) return JSON.stringify({found: false, msg: r.errorMsg || ''});
  return JSON.stringify({found: true, product_id: String(g.goodsId), title: g.goodsName || '',
    published: Number(g.isOnsale) === 1,
    skus: (g.sku || []).map(k => ({spec: (k.specs || []).map(s => s.specValue || ''), code: String(k.outSkuSn || ''),
      price: Number(k.groupPrice) / 100, stock: Number(k.quantity)}))});
})(%s)"""


async def readback(platform: str, store_id: str, product_id: str = "", outer_id: str = "",
                   title: str = "") -> Dict[str, Any]:
    from agent.ec_skills.explorer.page import PageSession, browser_port
    if platform not in TABS:
        return {"found": False, "error": f"no read-back for platform {platform!r}"}
    want = "".join(ch for ch in str(product_id or "") if ch.isdigit())
    if platform == "pdd" and not want:
        return {"found": False, "error": "拼多多 needs the goods id"}
    port = browser_port(store_id)
    if not port:
        return {"found": False, "error": f"no running browser for store {store_id}"}
    js = (_DOUYIN_JS % (json.dumps(want), json.dumps(outer_id or ""), json.dumps(title or ""))
          if platform == "douyin" else _PDD_JS % json.dumps(want))
    page = await PageSession.open(port, HOME[platform], TABS[platform])   # an open back-office tab, else ours
    try:
        raw = await page.evaluate(js, 60)
    finally:
        await page.close()
    try:
        out = json.loads(raw)
    except Exception:
        return {"found": False, "error": f"unreadable answer: {str(raw)[:200]}"}
    logger.info(f"[listing-readback] {platform} want={want or '-'} outer={outer_id or '-'} -> found={out.get('found')} "
                f"id={out.get('product_id')} skus={len(out.get('skus') or [])}")
    return out


def readback_sync(platform: str, store_id: str, **kwargs) -> Dict[str, Any]:
    """``readback`` from synchronous code (a skill's code node), in its own loop and thread."""
    box: Dict[str, Any] = {}

    def run():
        try:
            box["out"] = asyncio.run(readback(platform, store_id, **kwargs))
        except Exception as exc:
            logger.warning(f"[listing-readback] failed: {type(exc).__name__}: {exc}")
            box["out"] = {"found": False, "error": f"{type(exc).__name__}: {exc}"}
    th = threading.Thread(target=run, name="listing-readback", daemon=True)
    th.start()
    th.join(120)
    return box.get("out") or {"found": False, "error": "timed out"}
