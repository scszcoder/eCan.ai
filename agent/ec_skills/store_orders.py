"""Store-wide orders (reader R3) and reviews (R5) of the last N days, for the store reports. Read only.

Each platform's own order-list request, run inside the store's logged-in pages:

拼多多 POST mms /mangkhut/mms/recentOrderList {groupStartTime, groupEndTime, pageNumber,
       pageSize, ...} from the chat page (same origin). Needs the page's own risk header
       (window.riskControlCrawler.messagePack() as Anti-Content; without it: 40002
       "操作太过频繁"). One row per order (one goods line); money in fen; buyer nick and
       province come masked, so there is no buyer key (KEN 11-04, 434 orders / 90 days).
抖店   GET fxg /api/order/searchlist?order=desc&order_by=create_time&page&pageSize&tab=all
       in a background fxg tab (the page signs its own requests). Test store had 0 orders,
       so the row fields are mapped tolerantly from several known names.
淘宝   POST trade.taobao.com/trade/itemlist/asyncSold.htm (form, action=itemlist/SoldQueryAction,
       pageNum) from a background 千牛 tab; mainOrders[].subOrders[]. Test store had 0 orders.

Reviews: 拼多多 POST mms /saturn/reviews/list {startTime (a day start, <= ~90 days back, else
"仅支持查看近2000条评价"), endTime, pageNo, pageSize 20}, same risk header. 抖店/淘宝: not yet.

A line: {order_id, time (China time), status, cancelled, product_id, title, spec, sku_code, qty,
amount (goods total before discounts), paid, merchant_discount, platform_discount,
refund ("" or the after-sales state), buyer ("" or a one-way hash, never a name)}. Yuan.
Personal data (names, phones, addresses) is never copied out of the page.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import re
import threading
from typing import Any, Dict, List

from utils.logger_helper import logger_helper as logger

CN = dt.timezone(dt.timedelta(hours=8))
MAX_PAGES = 40
BACKOFFICE = {"douyin": "https://fxg.jinritemai.com/ffa/morder/order/list",
              "tmall": "https://qn.taobao.com/home.htm/trade-platform/tp/sold"}

_PDD_JS = r"""(async (days, maxPages) => {
  const c = window.riskControlCrawler;
  if (!c) return JSON.stringify({rows: [], errors: ['页面的风控签名没加载（请刷新拼多多客服页）']});
  const end = Math.floor(Date.now() / 1000), start = end - days * 86400;
  const keep = ['order_sn', 'created_at', 'order_status_str', 'after_sales_status', 'after_sales_id', 'goods_id',
                'goods_name', 'goods_price', 'spec', 'out_sku_sn', 'out_goods_sn', 'goods_number', 'goods_amount', 'order_amount',
                'merchant_discount', 'platform_discount', 'duoduo_pay_discount'];
  const rows = [], errors = [];
  for (let page = 1; page <= maxPages; page++) {
    c.updateServerTime && c.updateServerTime(Date.now());
    let j;
    try {
      j = await (await fetch('/mangkhut/mms/recentOrderList', {method: 'POST', credentials: 'include',
        headers: {'Content-Type': 'application/json', 'Anti-Content': c.messagePack()},
        body: JSON.stringify({orderType: 0, afterSaleType: 0, remarkStatus: -1, urgeShippingStatus: -1,
          groupStartTime: start, groupEndTime: end, pageNumber: page, pageSize: 50, sortType: 10, mobile: ''})})).json();
    } catch (e) { errors.push('订单 ' + e); break; }
    if (!j.success) { errors.push('订单 ' + (j.errorMsg || j.error_msg || j.errorCode || j.error_code)); break; }
    const items = (j.result || {}).pageItems || [];
    for (const o of items) { const x = {}; for (const k of keep) x[k] = o[k]; rows.push(x); }
    if (!items.length || items.length < 50 || rows.length >= Number((j.result || {}).totalItemNum || 0)) break;
    if (page === maxPages) errors.push('订单太多，只读了前 ' + rows.length + ' 条');
    await new Promise(r => setTimeout(r, 400));
  }
  return JSON.stringify({rows, errors});
})(%d, %d)"""

_DOUYIN_JS = r"""(async (days, maxPages) => {
  const since = Math.floor(Date.now() / 1000) - days * 86400;
  const rows = [], errors = [];
  let j;
  for (let page = 0; page < maxPages; page++) {
    for (let k = 0; k < 40; k++) {   // the page's request signer may still be loading
      j = await (await fetch('/api/order/searchlist?order=desc&order_by=create_time&pageSize=50&tab=all' +
        '&source=shop_order_view_upgrade&appid=1&page=' + page, {credentials: 'include'})).json();
      if (j.code === 0 || page > 0) break;
      await new Promise(r => setTimeout(r, 500));
    }
    if (j.code !== 0) { errors.push('订单 ' + j.code + ' ' + (j.msg || '')); break; }
    const items = Array.isArray(j.data) ? j.data : [];
    let old = false;
    for (const o of items) {
      if (Number(o.create_time || 0) && Number(o.create_time) < since) { old = true; continue; }
      rows.push(o);
    }
    if (old || items.length < 50) break;
  }
  return JSON.stringify({rows, errors});
})(%d, %d)"""

_TMALL_JS = r"""(async (days, maxPages) => {
  const since = Date.now() - days * 86400000;
  const rows = [], errors = [];
  for (let page = 1; page <= maxPages; page++) {
    const body = 'isQnNew=true&isHideNick=true&prePageNo=' + Math.max(1, page - 1) + '&sifg=0' +
      '&action=itemlist%2FSoldQueryAction&close=0&pageNum=' + page + '&pageSize=50&orderStatus=&rateStatus=&queryMore=false';
    let j;
    try {
      const t = await (await fetch('https://trade.taobao.com/trade/itemlist/asyncSold.htm?event_submit_do_query=1&_input_charset=utf8',
        {method: 'POST', credentials: 'include',
         headers: {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}, body})).text();
      j = JSON.parse(t);
    } catch (e) { errors.push('订单 ' + e); break; }
    if (j.error) { errors.push('订单 ' + JSON.stringify(j.error).slice(0, 100)); break; }
    const items = j.mainOrders || [];
    let old = false;
    for (const o of items) {
      const t = Date.parse(String(((o.orderInfo || {}).createTime) || '').replace(' ', 'T') + '+08:00');
      if (t && t < since) { old = true; continue; }
      rows.push({id: o.id, createTime: (o.orderInfo || {}).createTime, status: (o.statusInfo || {}).text,
        actualFee: (o.payInfo || {}).actualFee, buyerId: (o.buyer || {}).id || '',
        subOrders: (o.subOrders || []).map(s => ({itemInfo: {id: (s.itemInfo || {}).id || (s.itemInfo || {}).itemId,
          title: (s.itemInfo || {}).title, skuText: (s.itemInfo || {}).skuText, extra: (s.itemInfo || {}).extra},
          priceInfo: s.priceInfo, quantity: s.quantity, refund: ((s.operations || []).find(x => /退款/.test(x.text || '')) || {}).text || ''}))});
    }
    const pg = j.page || {};
    if (old || !items.length || page >= (pg.totalPage || 0)) break;
  }
  return JSON.stringify({rows, errors});
})(%d, %d)"""


def _num(v: Any) -> float:
    try:
        return float(str(v).replace("¥", "").replace(",", "").strip() or 0)
    except (TypeError, ValueError):
        return 0.0


def _time(v: Any) -> Any:
    """Seconds, milliseconds or 'YYYY-MM-DD HH:MM:SS' -> naive China time (None if unknown)."""
    if v in (None, "", 0):
        return None
    if isinstance(v, (int, float)) or str(v).isdigit():
        n = float(v)
        return dt.datetime.fromtimestamp(n / 1000 if n > 1e11 else n, CN).replace(tzinfo=None)
    try:
        return dt.datetime.strptime(str(v)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _buyer(v: Any) -> str:
    v = str(v or "").strip()
    return hashlib.sha1(v.encode("utf-8")).hexdigest()[:12] if v and "*" not in v else ""


def _first(d: Dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if d.get(k) not in (None, ""):
            return d[k]
    return None


def _spec_text(v: Any) -> str:
    if isinstance(v, list):
        return "/".join(str(x.get("value") or x.get("Value") or x.get("name") or "") if isinstance(x, dict) else str(x)
                        for x in v)
    return str(v or "").strip().strip(",/")


def pdd_lines(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for o in rows:
        out.append({"order_id": str(o.get("order_sn") or ""), "time": _time(o.get("created_at")),
                    "status": str(o.get("order_status_str") or ""), "product_id": str(o.get("goods_id") or ""),
                    "title": str(o.get("goods_name") or ""), "spec": _spec_text(o.get("spec")),
                    "sku_code": str(o.get("out_sku_sn") or ""), "code": str(o.get("out_goods_sn") or ""),
                    "qty": int(o.get("goods_number") or 1),
                    # list price x qty: goods_amount is already reduced on some orders (biz_type 2002)
                    "amount": (_num(o.get("goods_price")) * int(o.get("goods_number") or 1)
                               or _num(o.get("goods_amount"))) / 100,
                    "paid": _num(o.get("order_amount")) / 100,
                    "merchant_discount": _num(o.get("merchant_discount")) / 100,
                    "platform_discount": (_num(o.get("platform_discount")) + _num(o.get("duoduo_pay_discount"))) / 100,
                    "refund": str(o.get("after_sales_status") or "") if o.get("after_sales_id") else "",
                    "buyer": ""})
    return out


def douyin_lines(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """抖店 web order rows (fen). Field names vary by page version; unknown ones stay empty."""
    out = []
    for o in rows:
        status = o.get("order_status_info") if isinstance(o.get("order_status_info"), dict) else {}
        subs = _first(o, "product_item", "sku_order_list", "child_order_list") or [o]
        total_paid = _num(_first(o, "pay_amount", "order_amount")) / 100
        for s in subs if isinstance(subs, list) else [o]:
            amount = _num(_first(s, "total_amount", "goods_amount", "origin_amount", "price")) / 100
            out.append({"order_id": str(_first(o, "shop_order_id", "order_id", "p_order_id") or ""),
                        "time": _time(_first(o, "create_time", "order_create_time")),
                        "status": str(_first(status, "order_status_desc", "desc") or _first(o, "order_status_desc", "main_status_desc") or ""),
                        "product_id": str(_first(s, "product_id", "item_id") or ""),
                        "title": str(_first(s, "product_name", "goods_name", "title") or ""),
                        "spec": _spec_text(_first(s, "sku_spec", "spec", "sku_desc")),
                        "sku_code": str(_first(s, "out_sku_id", "sku_code", "code") or ""), "code": "",
                        "qty": int(_num(_first(s, "combo_num", "item_num", "goods_number")) or 1),
                        "amount": amount,
                        "paid": (_num(_first(s, "pay_amount")) / 100) if s is not o and s.get("pay_amount") is not None
                        else total_paid if len(subs) == 1 else amount,
                        "merchant_discount": _num(_first(s, "shop_discount_amount", "promotion_shop_amount")) / 100,
                        "platform_discount": _num(_first(s, "platform_discount_amount", "promotion_platform_amount")) / 100,
                        "refund": str(_first(s.get("after_sale_info") or {}, "after_sale_status_desc", "after_sale_status") or ""),
                        "buyer": _buyer(_first(o, "doudian_open_id", "user_id", "buyer_id"))})
    return out


def tmall_lines(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for o in rows:
        subs = o.get("subOrders") or []
        paid_total = _num(o.get("actualFee"))
        gross = sum(_num((s.get("priceInfo") or {}).get("realTotal")) * int(s.get("quantity") or 1) for s in subs) or 1
        for s in subs:
            it, pr = s.get("itemInfo") or {}, s.get("priceInfo") or {}
            qty = int(_num(s.get("quantity")) or 1)
            original = _num(pr.get("original") or pr.get("realTotal")) * qty
            real = _num(pr.get("realTotal")) * qty
            out.append({"order_id": str(o.get("id") or ""), "time": _time(o.get("createTime")),
                        "status": str(o.get("status") or ""), "product_id": str(it.get("id") or ""),
                        "title": str(it.get("title") or ""), "spec": _spec_text(it.get("skuText")),
                        "sku_code": "", "code": "", "qty": qty, "amount": original,
                        "paid": round(paid_total * real / gross, 2) if len(subs) > 1 else paid_total,
                        "merchant_discount": max(0.0, original - real), "platform_discount": 0.0,
                        "refund": str(s.get("refund") or ""), "buyer": _buyer(o.get("buyerId"))})
    return out


_PDD_REVIEWS_JS = r"""(async (days) => {
  const c = window.riskControlCrawler;
  if (!c) return JSON.stringify({rows: [], errors: ['页面的风控签名没加载（请刷新拼多多客服页）']});
  const end = Math.floor(Date.now() / 1000);
  const day0 = new Date(); day0.setHours(0, 0, 0, 0);   // the page asks from a day start, at most ~90 days back
  const start = Math.floor(day0.getTime() / 1000) - Math.min(days, 89) * 86400;
  const rows = [], errors = [];
  let unreplied = null;
  for (let page = 1; page <= 50; page++) {
    c.updateServerTime && c.updateServerTime(Date.now());
    let j;
    try {
      j = await (await fetch('/saturn/reviews/list', {method: 'POST', credentials: 'include',
        headers: {'Content-Type': 'application/json', 'Anti-Content': c.messagePack()},
        body: JSON.stringify({startTime: start, endTime: end, pageNo: page, pageSize: 20, orderSn: ''})})).json();
    } catch (e) { errors.push('评价 ' + e); break; }
    if (!j.success) { errors.push('评价 ' + (j.errorMsg || j.errorCode)); break; }
    const res = j.result || {}, items = res.data || [];
    if (unreplied === null) unreplied = res.negNoReplyReviewNum;
    for (const x of items) rows.push({id: x.reviewId, goods_id: x.goodsId, goods: x.goodsName, score: x.descScore,
      logistics: x.logisticsScore, service: x.serviceScore, comment: x.comment, time: x.createTime, specs: x.specs,
      pictures: (() => { try { return JSON.parse(x.pictures || '[]').length; } catch (e) { return 0; } })(),
      replied: !!x.replyStatus, excluded: /不计入/.test(JSON.stringify(x.reportResult || ''))});
    if (items.length < 20) break;
    await new Promise(r => setTimeout(r, 400));
  }
  return JSON.stringify({rows, errors, unreplied_bad: unreplied});
})(%d)"""


def pdd_reviews(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """A review: {id, product_id, title, score (1-5, description), logistics, service, comment, time, spec,
    pictures, replied, excluded (reported, not counted by the platform)}. No buyer data."""
    out = []
    for r in rows:
        try:
            spec = "/".join(str(x.get("spec_value") or "") for x in json.loads(r.get("specs") or "[]"))
        except (TypeError, ValueError):
            spec = ""
        out.append({"id": str(r.get("id") or ""), "product_id": str(r.get("goods_id") or ""),
                    "title": str(r.get("goods") or ""), "score": int(r.get("score") or 0),
                    "logistics": int(r.get("logistics") or 0), "service": int(r.get("service") or 0),
                    "comment": str(r.get("comment") or "")[:300], "time": _time(r.get("time")), "spec": spec,
                    "pictures": int(r.get("pictures") or 0), "replied": bool(r.get("replied")),
                    "excluded": bool(r.get("excluded"))})
    return out


_LINES = {"pdd": pdd_lines, "douyin": douyin_lines, "tmall": tmall_lines}
_CANCELLED = re.compile(r"取消|关闭|未付款|待付款|待支付")


def _mark(lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for l in lines:
        l["cancelled"] = bool(_CANCELLED.search(l["status"]))
    return lines


async def _read(platform: str, store_id: str, days: int, kind: str = "orders") -> Dict[str, Any]:
    from agent.ec_skills.browser_use_extension import store_page
    tabs = (store_page.backoffice_tabs(platform, store_id) if platform in store_page.BACKOFFICE_TABS else
            [t for t in store_page.store_tabs(platform) if not store_id or t.get("store_id") == store_id])
    if not tabs:
        raise RuntimeError("没有打开这个店铺的后台页（店铺浏览器没启动或没登录）")
    tab = tabs[0]
    if kind == "reviews":
        if platform != "pdd":
            return {"reviews": [], "errors": ["这个平台的评价还没接上（目前只有拼多多）"], "unreplied_bad": None}
        raw = await store_page.evaluate(tab["ws"], _PDD_REVIEWS_JS % days, timeout=240.0)
        return {"reviews": pdd_reviews(raw.get("rows") or []), "errors": raw.get("errors") or [],
                "unreplied_bad": raw.get("unreplied_bad")}
    if platform == "pdd":
        raw = await store_page.evaluate(tab["ws"], _PDD_JS % (days, MAX_PAGES), timeout=240.0)
    else:
        js = (_DOUYIN_JS if platform == "douyin" else _TMALL_JS) % (days, MAX_PAGES)
        raw = await store_page.evaluate_in_background_tab(tab["ws"], BACKOFFICE[platform], js, timeout=240.0)
    rows, errors = raw.get("rows") or [], raw.get("errors") or []
    if platform == "douyin" and rows:
        logger.info(f"[store-orders] douyin row keys: {sorted(rows[0].keys())[:60]}")
    return {"orders": _mark(_LINES[platform](rows)), "errors": errors}


def _in_thread(platform: str, store_id: str, days: int, kind: str, timeout_s: float) -> Dict[str, Any]:
    box: Dict[str, Any] = {}

    def run():
        try:
            box["out"] = asyncio.run(_read(platform, store_id, days, kind))
        except Exception as exc:
            box["error"] = f"{type(exc).__name__}: {exc}"
    t = threading.Thread(target=run, name=f"store-{kind}-{platform}", daemon=True)
    t.start()
    t.join(timeout_s)
    if "out" not in box:
        raise RuntimeError(box.get("error") or "timed out")
    return box["out"]


def read_orders(platform: str, store_id: str = "", days: int = 30, timeout_s: float = 300.0) -> Dict[str, Any]:
    """{"orders": [lines], "errors": [...]} of the last *days* days, from any thread."""
    return _in_thread(platform, store_id, days, "orders", timeout_s)


def read_reviews(platform: str, store_id: str = "", days: int = 30, timeout_s: float = 300.0) -> Dict[str, Any]:
    """{"reviews": [...], "errors": [...], "unreplied_bad": n|None} of the last *days* days (拼多多 for now)."""
    return _in_thread(platform, store_id, days, "reviews", timeout_s)
