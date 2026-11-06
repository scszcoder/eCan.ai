"""活动报名提醒: the platform campaigns a store could sign up for, with their sign-up windows.
READ ONLY -- it never signs up (报名 is the merchant's decision, made on the platform's page).

抖店  活动广场 list, called from a short-lived background tab on the back office (the page's own
      SDK signs the request, as for the coupon list -- KEN 11-05):
        POST /mmc/activity/seller_activity_feed
             {page, page_size, condition: {participate_tab: 0 (all; 1 = can sign up, 2.. = others),
              is_collection: false, intro_industry_items: [], keyword_ids: [], activity_name: '',
              act_time_period: {end_time_lower: now}, apply_time_period: {start_time_upper: now}}}
        -> data.total, data.data[]: feed_act.main_act.{can_apply, access_rule_check_pass,
           main_act.{name, act_marketing_type, start_time, end_time}}, sub_acts[]: {name,
           scene_label.name, apply_start_time/apply_end_time, activity_start_time/activity_end_time,
           can_apply, access_rule_check_pass, apply_status, apply_success_item_num} (unix seconds)
      The test 个人店 sees 16 campaigns and may join none (can_apply false everywhere).
拼多多 from the chat page (same origin as the back office; the page's request signer goes in
      the Anti-Content header, as for orders -- KEN 11-05, 106 activities):
        POST /leekmms/activityLabelAudit/query/activityListV3 {order_by: 'updated_at', sort_by: 'desc',
             page_size: 20, page_number, query_source: 1, sort_tab: 1, all_activity_type: true, ...}
        -> result.page_result.{total, result[]: activity_id, activity_name, activity_type_desc,
           enroll_start_time/enroll_end_time, activity_start_time/activity_end_time (ms),
           label_info.label_name (免费活动...), no_pass_rule_keys (why the store can't join)}
淘宝/天猫: not read yet.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import os
import threading
from typing import Any, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

CN = dt.timezone(dt.timedelta(hours=8))
DAYS = 3
BACKOFFICE = {"douyin": "https://fxg.jinritemai.com/ffa/g/excel"}
TYPES = {0: "大促活动", 1: "超值购", 2: "低价秒杀", 4: "行业活动", 5: "营销IP活动", 6: "商城频道活动", 7: "抖音月付",
         8: "抖音支付", 11: "直播间活动", 12: "平台商家混资", 13: "节盟计划", 14: "国家补贴", 15: "领航计划", 16: "精选联盟"}

_DOUYIN_JS = r"""(async () => {
  const now = Math.floor(Date.now() / 1000), out = {items: [], errors: [], total: 0};
  for (let page = 1; page <= 10; page++) {
    let j = null;
    for (let k = 0; k < 40; k++) {   // the page's request signer may still be loading
      j = await (await fetch('/mmc/activity/seller_activity_feed', {method: 'POST', credentials: 'include',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({page, page_size: 20, condition: {participate_tab: 0, is_collection: false,
          intro_industry_items: [], keyword_ids: [], activity_name: '', act_time_period: {end_time_lower: now},
          apply_time_period: {start_time_upper: now}}})})).json();
      if (j.code === 0 || page > 1) break;
      await new Promise(r => setTimeout(r, 500));
    }
    if (j.code !== 0) { out.errors.push('campaigns ' + j.code + ' ' + (j.msg || '')); break; }
    const d = j.data || {}, items = d.data || [];
    out.total = d.total || 0;
    out.items.push(...items);
    if (items.length < 20 || out.items.length >= out.total) break;
  }
  return JSON.stringify(out);
})()"""


_PDD_JS = r"""(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  for (let k = 0; k < 120 && !window.riskControlCrawler; k++) await sleep(500);
  if (!window.riskControlCrawler) return JSON.stringify({items: [], errors: ['拼多多客服页还没准备好（1 分钟内没有加载完），稍后再试']});
  const out = {items: [], errors: [], total: 0};
  for (let page = 1; page <= 10; page++) {
    const h = {'Content-Type': 'application/json', 'Anti-Content': await window.riskControlCrawler.messagePack()};
    const j = await (await fetch('/leekmms/activityLabelAudit/query/activityListV3', {method: 'POST', credentials: 'include', headers: h,
      body: JSON.stringify({order_by: 'updated_at', need_mms_activity_type: false, sort_by: 'desc', page_size: 20,
        page_number: page, query_source: 1, sort_tab: 1, all_activity_type: true, iris_context_env: 'shouYeGaiBan'})})).json();
    if (!j.success) { out.errors.push('activities ' + (j.error_msg || j.error_code)); break; }
    const p = (j.result || {}).page_result || {}, items = p.result || [];
    out.total = p.total || 0;
    out.items.push(...items);
    if (items.length < 20 || out.items.length >= out.total) break;
    await sleep(800);
  }
  return JSON.stringify(out);
})()"""


def pdd_rows(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for a in items:
        # the list says why a store can't join only when it checked (null = not said; KEN 11-05: always null)
        why = [str(x) for x in a.get("no_pass_rule_keys") or []] if a.get("no_pass_rule_keys") is not None else None
        rows.append({
            "campaign": str(a.get("activity_name") or ""), "type": str(a.get("activity_type_desc") or "其他"),
            "signup": "", "scene": str((a.get("label_info") or {}).get("label_name") or ""),
            "apply_start": _when(a.get("enroll_start_time")), "apply_end": _when(a.get("enroll_end_time")),
            "start": _when(a.get("activity_start_time")), "end": _when(a.get("activity_end_time")),
            "can_apply": None if why is None else not why, "why_not": "、".join(why)[:120] if why else "",
            "applied": None, "applied_items": 0, "id": str(a.get("activity_id") or ""),
        })
    return rows


def china_now() -> dt.datetime:
    return dt.datetime.now(CN).replace(tzinfo=None)


def _when(v: Any) -> Optional[dt.datetime]:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    return dt.datetime.fromtimestamp(n / 1000 if n > 1e11 else n, CN).replace(tzinfo=None)


def douyin_rows(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One row per sign-up (sub-activity) of each campaign."""
    rows = []
    for it in items:
        head = ((it.get("feed_act") or {}).get("main_act") or {})
        main = head.get("main_act") or {}
        subs = it.get("sub_acts") or [{}]
        for s in subs:
            can = bool(s.get("can_apply", head.get("can_apply")))
            rule_ok = s.get("access_rule_check_pass", head.get("access_rule_check_pass"))
            done = int(s.get("apply_success_item_num") or 0)
            rows.append({
                "campaign": str(main.get("name") or ""),
                "type": TYPES.get(main.get("act_marketing_type"), "其他"),
                "signup": str(s.get("name") or ""),
                "scene": str((s.get("scene_label") or {}).get("name") or ""),
                "apply_start": _when(s.get("apply_start_time")), "apply_end": _when(s.get("apply_end_time")),
                "start": _when(s.get("activity_start_time") or main.get("start_time")),
                "end": _when(s.get("activity_end_time") or main.get("end_time")),
                "can_apply": can,
                "why_not": "" if can else ("店铺不满足报名条件" if rule_ok is False else "现在不能报名"),
                "applied": done > 0 or bool(s.get("apply_status")),
                "applied_items": done,
                "id": str(s.get("id") or main.get("main_activity_id") or ""),
            })
    return rows


def open_now(rows: List[Dict[str, Any]], now: dt.datetime) -> List[Dict[str, Any]]:
    return [r for r in rows if (r["apply_start"] or now) <= now and (r["apply_end"] is None or now <= r["apply_end"])]


def summary(rows: List[Dict[str, Any]], store: str, days: int, now: dt.datetime, errors: List[str]) -> str:
    live = open_now(rows, now)
    said = [r for r in live if r["can_apply"] is not None]      # 拼多多's list does not say
    maybe = [r for r in live if r["can_apply"] is not False]
    soon = sorted([r for r in maybe if r["apply_end"] and r["apply_end"] <= now + dt.timedelta(days=days) and not r["applied"]],
                  key=lambda r: r["apply_end"])
    n = lambda rs: len({r["campaign"] for r in rs})   # noqa: E731 -- campaigns, not their sign-up items
    text = f"活动报名提醒（{store}）：正在报名的平台活动 {n(live)} 个（{len(live)} 个报名项）"
    if said:
        text += (f"，这个店能报的 {sum(1 for r in live if r['can_apply'])} 项，"
                 f"已报名 {sum(1 for r in live if r['applied'])} 项。")
    else:
        text += "。列表不说这个店能不能报、报过没有，以活动页为准。"
    if soon:
        text += f"\n{days} 天内截止" + ("、还没报的：" if said else "的：")
        for r in soon[:10]:
            text += f"\n- {r['type']}「{r['campaign']}」{r['signup']}：{r['apply_end']:%m-%d %H:%M} 截止报名"
    elif maybe:
        text += f"\n{'能报的活动' if said else '这些活动'} {days} 天内都不截止。"
    if live and not maybe:
        reasons = sorted({r["why_not"] for r in live})
        text += f"\n现在一个都报不了（{'；'.join(reasons)}）。"
    text += "\n只是提醒，不会替你报名；要报名请在店铺后台的活动页自己操作。"
    if errors:
        text += "\n没读全：" + "；".join(errors[:3])
    return text


COLUMNS = [("活动", "campaign"), ("类型", "type"), ("报名项", "signup"), ("场景", "scene"), ("报名开始", "apply_start"),
           ("报名截止", "apply_end"), ("活动开始", "start"), ("活动结束", "end"), ("能报名", "can_apply"),
           ("不能报的原因", "why_not"), ("已报名", "applied"), ("已报商品数", "applied_items"), ("ID", "id")]


def write_xlsx(rows: List[Dict[str, Any]], path: str) -> str:
    import openpyxl
    os.makedirs(os.path.dirname(path), exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "活动报名"
    ws.append([c for c, _ in COLUMNS])
    for r in rows:
        ws.append([("是" if r.get(k) else "") if isinstance(r.get(k), bool) else
                   (r[k].strftime("%Y-%m-%d %H:%M") if isinstance(r.get(k), dt.datetime) else r.get(k, ""))
                   for _, k in COLUMNS])
    wb.save(path)
    return path


def read_campaigns(platform: str, store_id: str = "", timeout_s: float = 180.0) -> Dict[str, Any]:
    """{"rows": [...], "errors": [...]} from the store's back office, from any thread."""
    import json
    from agent.ec_skills.browser_use_extension import store_page
    if platform not in ("douyin", "pdd"):
        return {"rows": [], "errors": ["这个平台的活动列表还没接上"]}
    box: Dict[str, Any] = {}

    async def go():
        tabs = (store_page.backoffice_tabs(platform, store_id) if platform == "douyin" else
                [t for t in store_page.store_tabs(platform) if not store_id or t.get("store_id") == store_id])
        if not tabs:
            raise RuntimeError("没有打开这个店铺的后台页（店铺浏览器没启动或没登录）")
        rows, errors = [], []
        for tab in tabs:
            if platform == "douyin":
                raw = await store_page.evaluate_in_background_tab(tab["ws"], BACKOFFICE[platform], _DOUYIN_JS, timeout=90.0)
            else:
                raw = await store_page.evaluate(tab["ws"], _PDD_JS, timeout=120.0)
            raw = json.loads(raw) if isinstance(raw, str) else (raw or {})
            errors += raw.get("errors") or []
            items = [i for i in raw.get("items") or [] if isinstance(i, dict)]
            rows += douyin_rows(items) if platform == "douyin" else pdd_rows(items)
        return {"rows": rows, "errors": errors}

    def run():
        try:
            box["out"] = asyncio.run(go())
        except Exception as exc:
            box["error"] = f"{type(exc).__name__}: {exc}"
    t = threading.Thread(target=run, name=f"campaigns-{platform}", daemon=True)
    t.start()
    t.join(timeout_s)
    if "out" not in box:
        raise RuntimeError(box.get("error") or "timed out")
    return box["out"]


def run_for_store(store_id: str, platform: str, folder: str, days: int = DAYS) -> Dict[str, Any]:
    """Read the campaigns, write <folder>/结果/活动报名_<time>.xlsx, return a summary."""
    data = read_campaigns(platform, store_id)
    now = china_now()
    rows = sorted(data["rows"], key=lambda r: (not r["can_apply"], r["apply_end"] or now))
    path = write_xlsx(rows, os.path.join(folder, "结果", now.strftime("活动报名_%Y%m%d_%H%M.xlsx"))) if rows else ""
    if data["errors"]:
        logger.warning(f"[campaigns] {store_id}: {data['errors']}")
    return {"summary": summary(rows, store_id or platform, days, now, data["errors"]), "path": path,
            "rows": len(rows), "errors": data["errors"]}
