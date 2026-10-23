"""lookup_order: the buyer's orders, read from the store's own chat page.

After-sales must act only on an order that the platform itself ties to the
buyer in THIS conversation -- a pasted order number or a screenshot is a hint,
never proof (scams, and leaking one buyer's order to another).

How: the store's chat page is already logged in, and its customer panel lists
"this buyer's orders" through the platform's own back-office API. This tool
runs that same READ request inside the page (Chrome DevTools Protocol on the
store browser eCan launched), keyed by the conversation's buyer:

* 抖店 (飞鸽 workstation): POST pigeon.jinritemai.com/backstage/cmpoent/order/query
  {security_user_id, search_words, ...}; security_user_id == the conversation's
  security id == the buyer's inbound security_sender_id (ws_session.buyer_key_for).
  An empty buyer is refused by the platform ("参数错误") -- there is no store-wide
  search here, by design of the platform.
* 拼多多 (chat-merchant): POST /latitude/order/userAllOrder {uid, pageNo, pageSize,
  showHistory}; the conversation's customer id IS the buyer uid.

``verified`` is true only when the given order number is in THIS buyer's list.
Only allowlisted read endpoints are ever called. Personal data (receiver name,
phone, address, ID numbers) is removed before anything reaches the model.

Field names of a returned order were not observable on the test stores (their
test buyers had no orders, 2026-10-23); orders are summarised generically by
key name and the raw key list is returned so the mapping can be tightened from
the first real lookup.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from mcp.types import TextContent

from utils.logger_helper import logger_helper as logger

from agent.ec_skills.browser_use_extension import store_page

_DOUYIN_JS = r"""(async (key, words) => {
  const qs = 'biz_type=4&PIGEON_BIZ_TYPE=2&_pms=1&device_platform=web&FUSION=true';
  const body = {security_user_id: key, page_no: 0, page_size: 20, search_words: words || '',
                is_init_tab: 1, tab_type: 1, biz_type: 2, open_params: {},
                workstation_opt_version: 'v2', service_entity_id: '', version: '1.0'};
  const r = await fetch('https://pigeon.jinritemai.com/backstage/cmpoent/order/query?' + qs,
                        {method: 'POST', credentials: 'include',
                         headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  const j = await r.json();
  return JSON.stringify({http: r.status, code: j.code, msg: j.msg || '', total: j.total,
                         orders: Array.isArray(j.data) ? j.data : (j.data && j.data.list) || []});
})(%s, %s)"""

_PDD_JS = r"""(async (uid) => {
  const r = await fetch('/latitude/order/userAllOrder',
                        {method: 'POST', credentials: 'include', headers: {'Content-Type': 'application/json'},
                         body: JSON.stringify({pageNo: 1, pageSize: 30, showHistory: true, uid})});
  const j = await r.json();
  const res = j.result || {};
  return JSON.stringify({http: r.status, code: j.errorCode, msg: j.errorMsg || '', success: j.success,
                         total: res.total, orders: res.orders || []});
})(%s)"""

# Personal data: never handed to the model.
_PII_KEY = re.compile(r"(receiver|receive_?(name|mobile|phone|tel|addr|user|info|man)|post_?(tel|receiver|addr)|"
                      r"consignee|addr|address|mobile|phone|tel(?!e)|id_?card|identity|"
                      r"post_?code|zip|real_?name|buyer_?name|nick|avatar|province|city|district|"
                      r"town|street|detail_?address|encrypt|mask)", re.I)
# What an order summary may carry.
_KEEP_KEY = re.compile(r"(order|sn|status|state|goods|product|item|sku|spec|title|name|num|count|"
                       r"quantity|amount|price|pay|total|freight|refund|after_?sale|logistic|"
                       r"express|shipping|ship|deliver|sign|receive|confirm|time|date|create|"
                       r"promise|remark|type|desc|text)", re.I)
_ORDER_ID_KEY = re.compile(r"^(order_?(id|sn|no)|orderSn|orderId|order_id_str|p_order_id|parent_order_id|"
                           r"shop_order_id|main_order_id)$", re.I)


def _clean(value: Any, depth: int = 0) -> Any:
    """Allowlisted, PII-free copy of an order (or part of one)."""
    if depth > 5:
        return None
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            name = str(k)
            if _PII_KEY.search(name) and not _ORDER_ID_KEY.match(name):
                continue
            if isinstance(v, (dict, list)):
                sub = _clean(v, depth + 1)
                if sub not in (None, {}, []):
                    out[name] = sub
            elif _KEEP_KEY.search(name) and v not in (None, ""):
                out[name] = v if not isinstance(v, str) else v[:300]
        return out
    if isinstance(value, list):
        return [x for x in (_clean(v, depth + 1) for v in value[:20]) if x not in (None, {}, [])]
    return value


def _order_ids(order: Any) -> List[str]:
    """Every order-number-looking value in one order (any depth)."""
    ids: List[str] = []

    def walk(o, depth=0):
        if depth > 4:
            return
        if isinstance(o, dict):
            for k, v in o.items():
                if _ORDER_ID_KEY.match(str(k)) and isinstance(v, (str, int)) and str(v).strip():
                    ids.append(str(v).strip())
                elif isinstance(v, (dict, list)):
                    walk(v, depth + 1)
        elif isinstance(o, list):
            for v in o:
                walk(v, depth + 1)
    walk(order)
    return ids


def _norm_sn(s: str) -> str:
    return re.sub(r"[\s\-_#]", "", str(s or ""))


def _buyer_key(platform: str, customer_id: str) -> str:
    c = str(customer_id or "").strip()
    if platform == "pdd":
        return c[len("uid:"):] if c.startswith("uid:") else c
    from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import ws_session
    return ws_session.buyer_key_for(c)


def _out(data) -> list:
    return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False, default=str))]


async def lookup_order(mainwin, args):
    inp = args.get("input", args) if isinstance(args, dict) else {}
    platform = store_page.platform_of(inp.get("platform") or "")
    customer_id = str(inp.get("customer_id") or "").strip()
    order_sn = str(inp.get("order_id") or "").strip()
    if not platform:
        return _out({"ok": False, "error": "platform must be one of: douyin (抖店), pdd (拼多多)"})
    if not customer_id:
        return _out({"ok": False, "error": "customer_id (the buyer in this conversation) is required"})
    key = _buyer_key(platform, customer_id)
    if not key:
        return _out({"ok": False, "verified": False,
                     "error": "this conversation's buyer is not identified yet; ask the buyer for the "
                              "order number and try again after their next message"})
    tabs = store_page.store_tabs(platform)
    if not tabs:
        return _out({"ok": False, "verified": False,
                     "error": f"no open {platform} chat page in this app's store browsers"})
    orders: List[Any] = []
    errors = []
    for tab in tabs:
        try:
            if platform == "douyin":
                js = _DOUYIN_JS % (json.dumps(key), json.dumps(order_sn))
            else:
                js = _PDD_JS % json.dumps(key)
            res = await store_page.evaluate(tab["ws"], js)
            if platform == "douyin" and res.get("code") not in (0, None):
                errors.append(f"{tab['profile']}: {res.get('msg') or res.get('code')}")
                continue
            if platform == "pdd" and res.get("success") is False:
                errors.append(f"{tab['profile']}: {res.get('msg') or res.get('code')}")
                continue
            orders.extend(res.get("orders") or [])
        except Exception as exc:
            errors.append(f"{tab['profile']}: {type(exc).__name__}: {exc}")
    want = _norm_sn(order_sn)
    match = [o for o in orders if want and any(_norm_sn(i) == want for i in _order_ids(o))]
    raw_keys = sorted({k for o in orders[:3] if isinstance(o, dict) for k in o.keys()})
    logger.info(f"[lookup_order] {platform} buyer=...{key[-6:]} order={'given' if order_sn else 'none'} "
                f"orders={len(orders)} verified={bool(match)} tabs={len(tabs)} errors={len(errors)}")
    result = {
        "ok": not (errors and not orders),
        "platform": platform,
        "verified": bool(match),
        "order": _clean(match[0]) if match else None,
        "buyer_order_count": len(orders),
        # Without an order number: this buyer's recent orders, so the buyer can be
        # asked "which one?" -- never another buyer's.
        "recent_orders": [] if match else [_clean(o) for o in orders[:5]],
        "raw_keys": raw_keys,
    }
    if order_sn and not match:
        result["note"] = ("This order number is NOT among this buyer's orders in this store. Do not act on "
                          "it or say anything about it; ask the buyer to check the number.")
    if errors:
        result["errors"] = errors[:3]
    return _out(result)


def add_order_lookup_tool_schema(tool_schemas):
    import mcp.types as types
    tool_schemas.append(types.Tool(
        _meta={"run_in_cloud": False},
        name="lookup_order",
        description=(
            "<category>AfterSales</category><sub-category>Order</sub-category>"
            "Look up the buyer's order in the store's own records (抖店 / 拼多多), read-only. "
            "Returns verified=true ONLY when order_id is one of THIS conversation's buyer's orders, "
            "with its status, goods, specs, quantities, amounts and dates (no personal data). "
            "Without order_id it returns this buyer's recent orders. Use it before ANY after-sales "
            "action (refund, return, resend, wrong / missing / damaged item); never act on an order "
            "that is not verified, and never reveal anything about it."),
        inputSchema={"type": "object", "required": ["input"], "properties": {"input": {
            "type": "object", "required": ["platform", "customer_id"],
            "properties": {
                "platform": {"type": "string", "description": "douyin (抖店/飞鸽) or pdd (拼多多)"},
                "customer_id": {"type": "string",
                                "description": "The buyer's customer_id exactly as in the turn's input"},
                "order_id": {"type": "string",
                             "description": "The order number (订单号) the buyer gave or an order card showed"},
            }}}}))
