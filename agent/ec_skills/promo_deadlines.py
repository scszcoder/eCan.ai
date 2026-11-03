"""营销工具到期提醒: the store's coupons and discounts that end within N days. Read only.

抖店   back-office list APIs, called from a short-lived BACKGROUND tab on a back-office
       page (fxg.jinritemai.com; the chat page is another origin, and the coupon list
       only answers requests signed by that page's own SDK -- KEN 11-04):
         coupons     GET  /marketing/coupons/v1/list?favoured_type=0 (0 = every type)
                     -> expire_time, status, credit/threshold (fen), goods_count
                        (0 = whole store), renew_result.renew_switch_on (auto-renew)
         限时限量购  POST /marketing/app/v1/time_buy/list {status: 1 not started | 2 running}
         限时折扣    GET  /marketing/promotion/v1/listFlashWithTimeLimit?campaign_status=1|2
         满减        GET  /marketing/activity/v1/query_full_discount_activity?activity_status=1|2
       The three activity lists were empty on the test store, so their items are read
       with generic name/end-time keys and an item without an end time is reported.
拼多多 the chat page's allCouponList (same generic keys). 限时折扣 not read yet.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import re
import threading
from typing import Any, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

DAYS = 3
CN = dt.timezone(dt.timedelta(hours=8))   # both platforms show China time
BACKOFFICE = {"douyin": "https://fxg.jinritemai.com/ffa/g/excel"}

_DOUYIN_JS = r"""(async () => {
  const q = '_bid=ecom_market_shop&appid=1';
  const get = async p => (await fetch(p + (p.includes('?') ? '&' : '?') + q, {credentials: 'include'})).json();
  const post = async (p, b) => (await fetch(p + '?' + q, {method: 'POST', credentials: 'include',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(b)})).json();
  const out = {coupon: [], time_buy: [], flash: [], full_discount: [], errors: []};
  let j;
  for (let k = 0; k < 40; k++) {   // the page's request signer may still be loading
    j = await get('/marketing/coupons/v1/list?page=1&size=50&favoured_type=0');
    if (j.code === 0) break;
    await new Promise(r => setTimeout(r, 500));
  }
  for (let page = 1; page <= 20 && j.code === 0; page++) {
    if (page > 1) j = await get('/marketing/coupons/v1/list?size=50&favoured_type=0&page=' + page);
    const items = Array.isArray(j.data) ? j.data : [];
    out.coupon.push(...items);
    if (items.length < 50) break;
  }
  if (j.code !== 0) out.errors.push('coupon ' + j.code + ' ' + (j.msg || ''));
  const list = d => Array.isArray(d) ? d : (d && (d.data || d.list || d.flash_list || d.activity_list)) || [];
  for (const st of [1, 2]) {
    try { const t = await post('/marketing/app/v1/time_buy/list', {page: 1, pageSize: 100, status: st});
          if (t.code) out.errors.push('time_buy ' + t.code + ' ' + (t.msg || '')); else out.time_buy.push(...list(t.data)); }
    catch (e) { out.errors.push('time_buy ' + e); }
    try { const f = await get('/marketing/promotion/v1/listFlashWithTimeLimit?page=1&pageSize=100&campaign_status=' + st);
          if (f.code) out.errors.push('flash ' + f.code + ' ' + (f.msg || '')); else out.flash.push(...list(f.data)); }
    catch (e) { out.errors.push('flash ' + e); }
    try { const m = await get('/marketing/activity/v1/query_full_discount_activity?page=1&pageSize=100&activity_status=' + st);
          if (m.code) out.errors.push('full_discount ' + m.code + ' ' + (m.msg || '')); else out.full_discount.push(...list(m.data)); }
    catch (e) { out.errors.push('full_discount ' + e); }
  }
  return JSON.stringify(out);
})()"""
_PDD_JS = r"""(async () => {
  const j = await (await fetch('/latitude/coupon/allCouponList', {method: 'POST', credentials: 'include',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify({uid: '0'})})).json();
  const r = j.result || {}, coupon = [];
  for (const [k, v] of Object.entries(r)) if (Array.isArray(v)) coupon.push(...v.map(c => Object.assign({_list: k}, c)));
  return JSON.stringify({coupon, errors: j.success === false ? ['coupon ' + (j.errorMsg || '')] : []});
})()"""

KINDS = {"coupon": "优惠券", "time_buy": "限时限量购", "flash": "限时折扣", "full_discount": "满减"}
_NAME = ("coupon_name", "activity_name", "campaign_name", "title", "name", "couponName", "batchName", "batch_name")
_END = ("expire_time", "end_apply_time", "end_time", "activity_end_time", "endTime", "end_at",
        "batchEndTime", "batch_end_time", "validEndTime", "expireTime", "couponEndTime")
_START = ("start_time", "start_apply_time", "begin_time", "activity_start_time", "startTime",
          "batchStartTime", "validStartTime")
_ID = ("coupon_meta_id", "activity_id", "campaign_id", "id", "batchId", "batch_id", "couponId")
_GOODS = ("goods_count", "product_count", "product_num", "goods_num", "productCount")


def _first(item: Dict[str, Any], keys) -> Any:
    for k in keys:
        if item.get(k) not in (None, ""):
            return item[k]
    return None


def _when(v: Any) -> Optional[dt.datetime]:
    """Unix seconds or ms, or a date string -> naive China-time datetime."""
    if v in (None, "", 0, "0"):
        return None
    try:
        n = float(v)
        return dt.datetime.fromtimestamp(n / 1000 if n > 1e11 else n, CN).replace(tzinfo=None)
    except (TypeError, ValueError):
        m = re.match(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?", str(v))
        if not m:
            return None
        return dt.datetime(*[int(x) for x in m.groups() if x is not None])


def normalize(kind: str, item: Dict[str, Any]) -> Dict[str, Any]:
    renew = (item.get("renew_result") or {}).get("renew_switch_on") if isinstance(item.get("renew_result"), dict) else None
    goods = _first(item, _GOODS)
    p = {"kind": KINDS.get(kind, kind), "name": str(_first(item, _NAME) or ""), "id": str(_first(item, _ID) or ""),
         "start": _when(_first(item, _START)), "end": _when(_first(item, _END)),
         "status": item.get("status", item.get("campaign_status", item.get("activity_status", ""))),
         "auto_renew": bool(renew), "goods": "全店" if goods in (0, "0") and kind == "coupon" else (goods or "")}
    if kind == "coupon":
        amount = item.get("credit", item.get("discount"))       # fen on both platforms
        threshold = item.get("threshold", item.get("minAmount", item.get("min_amount")))
        if amount not in (None, ""):
            try:
                a, t = float(amount) / 100, float(threshold or 0) / 100
                p["detail"] = (f"满{t:g}减{a:g}" if t else f"立减{a:g}")
            except (TypeError, ValueError):
                pass
    return p


def china_now() -> dt.datetime:
    return dt.datetime.now(CN).replace(tzinfo=None)


def due(promos: List[Dict[str, Any]], days: int = DAYS, now: Optional[dt.datetime] = None) -> List[Dict[str, Any]]:
    """Promos still live that end within *days* (soonest first), plus any without an end time."""
    now = now or china_now()
    out = []
    for p in promos:
        if p["end"] is None:
            out.append(dict(p, left="没读到结束时间"))
        elif now < p["end"] <= now + dt.timedelta(days=days):
            hours = (p["end"] - now).total_seconds() / 3600
            out.append(dict(p, left=f"{hours:.0f}小时" if hours < 48 else f"{hours / 24:.1f}天"))
    return sorted(out, key=lambda p: p["end"] or now)


def summary(rows: List[Dict[str, Any]], live: int, store: str, days: int, errors: List[str]) -> str:
    head = f"营销到期提醒（{store}）：在用/待开始的营销 {live} 个，"
    if not rows:
        text = head + f"{days} 天内没有要到期的。"
    else:
        manual = [r for r in rows if not r["auto_renew"]]
        text = head + f"{days} 天内到期 {len(rows)} 个" + (f"（其中 {len(rows) - len(manual)} 个会自动续期）" if len(manual) < len(rows) else "") + "："
        for r in rows[:10]:
            end = r["end"].strftime("%m-%d %H:%M") if r["end"] else ""
            text += f"\n- {r['kind']}「{r['name']}」{r.get('detail', '')} {end} 结束（还剩{r['left']}）" + ("，会自动续期" if r["auto_renew"] else "")
        if len(rows) > 10:
            text += f"\n…另有 {len(rows) - 10} 个，见结果表"
    if errors:
        text += "\n没读全：" + "；".join(errors[:3])
    return text


COLUMNS = [("类型", "kind"), ("名称", "name"), ("优惠", "detail"), ("开始", "start"), ("结束", "end"),
           ("还剩", "left"), ("自动续期", "auto_renew"), ("商品", "goods"), ("状态", "status"), ("ID", "id")]


def write_xlsx(rows: List[Dict[str, Any]], path: str) -> str:
    import openpyxl
    os.makedirs(os.path.dirname(path), exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "到期提醒"
    ws.append([c for c, _ in COLUMNS])
    for r in rows:
        ws.append([("是" if r.get(k) else "") if k == "auto_renew" else
                   (r[k].strftime("%Y-%m-%d %H:%M") if isinstance(r.get(k), dt.datetime) else r.get(k, ""))
                   for _, k in COLUMNS])
    wb.save(path)
    return path


async def _douyin(tab: Dict[str, str]) -> Dict[str, Any]:
    from agent.ec_skills.browser_use_extension import store_page
    return await store_page.evaluate_in_background_tab(tab["ws"], BACKOFFICE["douyin"], _DOUYIN_JS, timeout=90.0)


async def _pdd(tab: Dict[str, str]) -> Dict[str, Any]:
    from agent.ec_skills.browser_use_extension import store_page
    return await store_page.evaluate(tab["ws"], _PDD_JS, timeout=60.0)


def read_store_promos(platform: str, store_id: str = "", timeout_s: float = 180.0) -> Dict[str, Any]:
    """{"promos": [normalized], "errors": [...]} for the open store(s) of *platform*, from any thread."""
    from agent.ec_skills.browser_use_extension import store_page
    box: Dict[str, Any] = {}

    async def go():
        promos, errors = [], []
        tabs = [t for t in store_page.store_tabs(platform) if not store_id or t.get("store_id") == store_id]
        if not tabs:
            raise RuntimeError("没有打开这个店铺的聊天页（店铺浏览器没启动或没登录）")
        for tab in tabs:
            raw = await (_douyin(tab) if platform == "douyin" else _pdd(tab))
            errors += raw.get("errors") or []
            for kind in KINDS:
                promos += [normalize(kind, i) for i in raw.get(kind) or [] if isinstance(i, dict)]
        return {"promos": promos, "errors": errors}

    def run():
        try:
            box["out"] = asyncio.run(go())
        except Exception as exc:
            box["error"] = f"{type(exc).__name__}: {exc}"
    t = threading.Thread(target=run, name=f"promo-deadlines-{platform}", daemon=True)
    t.start()
    t.join(timeout_s)
    if "out" not in box:
        raise RuntimeError(box.get("error") or "timed out")
    return box["out"]


def run_for_store(store_id: str, platform: str, folder: str, days: int = DAYS) -> Dict[str, Any]:
    """Read the store's promos, write <folder>/结果/营销到期_<time>.xlsx, return a summary."""
    data = read_store_promos(platform, store_id)
    now = china_now()
    live = [p for p in data["promos"] if p["end"] is None or p["end"] > now]
    rows = due(live, days, now)
    path = ""
    if rows:
        path = write_xlsx(rows, os.path.join(folder, "结果", now.strftime("营销到期_%Y%m%d_%H%M.xlsx")))
    if data["errors"]:
        logger.warning(f"[promo-deadlines] {store_id}: {data['errors']}")
    return {"summary": summary(rows, len(live), store_id or platform, days, data["errors"]), "path": path,
            "due": len(rows), "live": len(live), "errors": data["errors"]}
