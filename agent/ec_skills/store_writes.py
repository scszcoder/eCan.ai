"""Store changes the person confirms first (wave D): propose -> the person says yes -> the
platform's own form, filled by a fill flow (agent/ec_skills/fill) -> read back.

Two steps, two skill runs, so nothing changes without a person's yes:

  propose(kind, platform, store_id, folder)   reads the merchant's request table (newest
      .xlsx/.csv in <folder>, e.g. <ks>/营销设置/<店铺>/), checks every row, writes
      <folder>/待确认.json and returns what would be created. Changes nothing.
  execute(kind, platform, store_id, folder, flow)   runs only that pending plan (made in the
      last 24 h, never twice), one row at a time through the platform's form, then reads the
      store back to confirm each one exists; results to <folder>/结果/, the plan moves to
      已执行_<time>.json.

Kinds: coupon (优惠券: 满减 / 立减 / 折扣; 全店 or the listed 商品ID). Flows so far: 抖店.
A flow's guards keep every other publish/sign-up button out of reach (fill engine).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from utils.logger_helper import logger_helper as logger

CN = dt.timezone(dt.timedelta(hours=8))
PLAN = "待确认.json"
PLAN_TTL_H = 24
FILL_TIMEOUT_S = 300.0
KINDS = {"coupon": "优惠券"}
FLOWS = {("coupon", "douyin")}

ALIAS = {"name": ("名称", "券名称", "优惠券名称", "名字"), "kind": ("类型", "优惠方式", "券类型"),
         "threshold": ("门槛", "满", "满多少", "使用门槛"), "amount": ("面额", "减", "减多少", "金额", "优惠金额"),
         "discount": ("折扣", "几折"), "start": ("开始", "开始时间", "领取开始", "开始日期"),
         "end": ("结束", "结束时间", "领取结束", "结束日期"), "quantity": ("发放量", "数量", "张数"),
         "product_ids": ("商品ID", "商品", "商品id", "适用商品")}


def china_now() -> dt.datetime:
    return dt.datetime.now(CN).replace(tzinfo=None)


def _norm(h: Any) -> str:
    return re.sub(r"[\s（）()：:*]", "", str(h or ""))


def _day(v: Any) -> Optional[dt.date]:
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    m = re.match(r"\s*(\d{4})\D(\d{1,2})\D(\d{1,2})", str(v or ""))
    try:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None
    except ValueError:
        return None


def _num(v: Any) -> Optional[float]:
    try:
        return float(str(v).replace("¥", "").replace("元", "").replace("折", "").strip())
    except (TypeError, ValueError):
        return None


def read_rows(path: str) -> List[Dict[str, Any]]:
    """Rows of a request table with known headers (the header row may be under a title row)."""
    if path.lower().endswith(".csv"):
        import csv
        raw = open(path, "rb").read()
        text = next((raw.decode(e) for e in ("utf-8-sig", "gb18030") if _decodes(raw, e)), raw.decode("utf-8", "replace"))
        table = [r for r in csv.reader(text.splitlines())]
    else:
        import openpyxl
        ws = openpyxl.load_workbook(path, data_only=True).active
        table = [list(r) for r in ws.iter_rows(values_only=True)]
    names = {_norm(a): k for k, al in ALIAS.items() for a in al}
    for i, row in enumerate(table[:5]):
        cols = {j: names[_norm(c)] for j, c in enumerate(row) if _norm(c) in names}
        if "name" in cols.values() or "amount" in cols.values():
            out = []
            for r in table[i + 1:]:
                d = {k: r[j] for j, k in cols.items() if j < len(r) and r[j] not in (None, "")}
                if d:
                    out.append(d)
            return out
    return []


def _decodes(raw: bytes, enc: str) -> bool:
    try:
        raw.decode(enc)
        return True
    except UnicodeDecodeError:
        return False


def check_coupon(r: Dict[str, Any], today: dt.date) -> Tuple[Dict[str, Any], List[str]]:
    """(the coupon as the flow wants it, problems). A row with problems is not proposed."""
    bad = []
    kind = str(r.get("kind") or "").strip() or ("折扣" if r.get("discount") else "满减" if r.get("threshold") else "立减")
    kind = "满减" if "满" in kind else "折扣" if "折" in kind else "立减" if "减" in kind or "立" in kind else kind
    if kind not in ("满减", "立减", "折扣"):
        bad.append(f"类型「{kind}」不认识（满减/立减/折扣）")
    name = str(r.get("name") or "").strip() or "优惠券"
    if len(name) > 25:
        bad.append("名称超过 25 个字")
    threshold, amount, discount = _num(r.get("threshold")) or 0, _num(r.get("amount")), _num(r.get("discount"))
    if kind == "折扣":
        if not discount or not 0.1 <= discount <= 9.9:
            bad.append("折扣要在 0.1 到 9.9 折之间")
    elif not amount or amount <= 0:
        bad.append("面额要大于 0")
    elif kind == "满减" and threshold <= amount:
        bad.append("满减的门槛要大于面额")
    start, end = _day(r.get("start")) or today, _day(r.get("end"))
    if not end:
        bad.append("没有结束日期")
    elif start < today:
        bad.append("开始日期早于今天")
    elif end < start or (end - start).days > 180:
        bad.append("结束日期要在开始之后、180 天以内")
    ids = [x for x in re.split(r"[,，;；\s]+", str(r.get("product_ids") or "")) if x]
    if any(not x.isdigit() for x in ids):
        bad.append("商品ID要是数字")
    qty = int(_num(r.get("quantity")) or 0)
    c = {"name": name, "kind": kind, "threshold": threshold, "amount": amount or 0, "discount": discount or 0,
         "start": f"{start:%Y/%m/%d} 00:00:00", "end": f"{end:%Y/%m/%d} 23:59:59" if end else "",
         "quantity": qty, "auto_renew": False, "scope": "商品" if ids else "全店", "product_ids": ids}
    return c, bad


def describe(c: Dict[str, Any]) -> str:
    off = (f"满{c['threshold']:g}减{c['amount']:g}" if c["kind"] == "满减" else
           f"立减{c['amount']:g}" if c["kind"] == "立减" else f"{c['discount']:g}折")
    scope = "全店" if c["scope"] == "全店" else f"商品 {','.join(c['product_ids'])}"
    return (f"「{c['name']}」{off}，{c['start'][:10]} ~ {c['end'][:10]}，"
            f"{'不限量' if not c['quantity'] else str(c['quantity']) + ' 张'}，{scope}")


def _newest_table(folder: str) -> str:
    files = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith((".xlsx", ".csv"))
             and not f.startswith(("~$", "结果"))] if os.path.isdir(folder) else []
    return max(files, key=os.path.getmtime) if files else ""


def propose(kind: str, platform: str, store_id: str, folder: str) -> Dict[str, Any]:
    """Check the newest request table and write the plan to confirm. Changes nothing on the store."""
    label = KINDS[kind]
    if (kind, platform) not in FLOWS:
        return {"summary": f"{label}创建：这个平台还不支持（目前只有抖店）。", "items": 0}
    table = _newest_table(folder)
    if not table:
        return {"summary": f"{label}创建：{folder} 里还没有申请表（.xlsx/.csv：名称、类型、门槛、面额、折扣、开始、结束、发放量、商品ID）。",
                "items": 0}
    today = china_now().date()
    items, problems = [], []
    for i, r in enumerate(read_rows(table), 1):
        c, bad = check_coupon(r, today)
        (problems.append(f"第{i}行 {c['name']}：{'；'.join(bad)}") if bad else items.append(c))
    plan = {"kind": kind, "platform": platform, "store_id": store_id, "table": os.path.basename(table),
            "created": china_now().strftime("%Y-%m-%d %H:%M:%S"), "items": items}
    if items:
        with open(os.path.join(folder, PLAN), "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=1)
    text = f"{label}创建（{store_id}）——还没有改店铺，等你确认：\n"
    text += "\n".join(f"{n}. {describe(c)}" for n, c in enumerate(items, 1)) or "没有可以创建的。"
    if problems:
        text += "\n这些行有问题，不会创建：\n" + "\n".join(f"- {p}" for p in problems[:10])
    if items:
        text += f"\n确认就运行「{label}创建（确认执行）」（或对助手说“确认创建{label}”）；{PLAN_TTL_H} 小时内有效。"
    return {"summary": text, "items": len(items), "problems": problems}


def load_plan(folder: str, kind: str, store_id: str) -> Tuple[Optional[Dict[str, Any]], str]:
    path = os.path.join(folder, PLAN)
    try:
        with open(path, encoding="utf-8") as f:
            plan = json.load(f)
    except (OSError, ValueError):
        return None, "没有待确认的申请（先运行“提议”那一步）"
    age = china_now() - dt.datetime.strptime(plan.get("created", "2000-01-01 00:00:00"), "%Y-%m-%d %H:%M:%S")
    if plan.get("kind") != kind or plan.get("store_id") != store_id:
        return None, "待确认的申请不是这个店铺/这类改动的"
    if age > dt.timedelta(hours=PLAN_TTL_H):
        return None, f"待确认的申请已经超过 {PLAN_TTL_H} 小时，请重新提议"
    return plan, ""


def verify_coupons(platform: str, store_id: str, names: List[str]) -> Dict[str, bool]:
    """Which coupon names the store now lists (promo_deadlines reader)."""
    from agent.ec_skills.promo_deadlines import read_store_promos
    have = {p["name"] for p in read_store_promos(platform, store_id)["promos"] if p.get("kind") == "优惠券"}
    return {n: n in have for n in names}


def execute(kind: str, platform: str, store_id: str, folder: str, flow: Dict[str, Any],
            profile_id: str = "") -> Dict[str, Any]:
    """Run the pending plan through *flow* (publish), then read the store back."""
    from agent.ec_skills.fill.node import _open_and_run, _port, _run_sync
    label = KINDS[kind]
    plan, why = load_plan(folder, kind, store_id)
    if not plan:
        return {"summary": f"{label}创建：{why}。", "done": 0}
    # taken before running, so a second run can never repeat it
    stamp = china_now().strftime("%Y%m%d_%H%M%S")
    os.replace(os.path.join(folder, PLAN), os.path.join(folder, f"已执行_{stamp}.json"))
    port = _port(store_id, flow, profile_id)
    guards = dict(flow.get("guards") or {})
    steps = {k: v for k, v in flow.items() if k != "guards"}
    rows = []
    for c in plan["items"]:
        if not port:
            rows.append(dict(c, 结果="没执行", 原因="店铺浏览器没启动"))
            continue
        out = _run_sync(lambda: _open_and_run(port, steps, guards, c, {}, {}, "publish", {}), FILL_TIMEOUT_S)
        rows.append(dict(c, 结果="已提交" if out.get("ok") else "失败",
                         原因="" if out.get("ok") else f"{out.get('stage')}: {str(out.get('error') or '')[:200]}"))
        logger.info(f"[store-writes] {kind} {store_id} {c['name']!r}: ok={out.get('ok')} stage={out.get('stage')} "
                    f"blocked={out.get('blocked')}")
    sent = [r["name"] for r in rows if r["结果"] == "已提交"]
    if sent:
        try:
            seen = verify_coupons(platform, store_id, sent)
            for r in rows:
                if r["name"] in seen:
                    r["结果"] = "已创建" if seen[r["name"]] else "已提交，店铺列表里还没看到"
        except Exception as exc:
            logger.warning(f"[store-writes] read-back failed: {exc}")
    path = _write(rows, os.path.join(folder, "结果", f"{label}创建_{stamp}.xlsx"))
    ok = sum(1 for r in rows if r["结果"] == "已创建")
    text = f"{label}创建（{store_id}）：{len(rows)} 个里创建成功 {ok} 个。"
    for r in rows:
        text += f"\n- {describe(r)}：{r['结果']}" + (f"（{r['原因']}）" if r.get("原因") else "")
    return {"summary": text, "done": ok, "path": path}


def _write(rows: List[Dict[str, Any]], path: str) -> str:
    import openpyxl
    os.makedirs(os.path.dirname(path), exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    cols = ["结果", "原因", "name", "kind", "threshold", "amount", "discount", "start", "end", "quantity", "scope", "product_ids"]
    ws.append(cols)
    for r in rows:
        ws.append([",".join(r[c]) if isinstance(r.get(c), list) else r.get(c, "") for c in cols])
    wb.save(path)
    return path
