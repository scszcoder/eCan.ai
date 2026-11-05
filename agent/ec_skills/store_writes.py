"""Store changes the person confirms first (wave D): propose -> the person says yes -> the
platform's own form, filled by a fill flow (agent/ec_skills/fill) -> read back.

Two steps, two skill runs, so nothing changes without a person's yes:

  propose(kind, platform, store_id, folder)   reads the merchant's request table (newest
      .xlsx/.csv in <folder>, e.g. <ks>/营销设置/<店铺>/), checks every row, writes
      <folder>/待确认.json and returns what would be changed. Changes nothing.
  execute(kind, platform, store_id, folder, flow)   runs only that pending plan (made in the
      last 24 h, never twice), one item at a time through the platform's form, then reads the
      store back where it can; results to <folder>/结果/, the plan moves to 已执行_<time>.json.
      Items with a later 生效时间 stay in the plan for a later run.

Kinds (flows so far: 抖店; tested live on KEN 11-05):
  coupon     优惠券: 满减 / 立减 / 折扣; 全店 or the listed 商品ID
  price_cut  单品直降 (普通降价促销): one 一口价 per product; rows with the same 名称 = one activity
  main_pic   主图替换: one main picture of one product, from a picture file in <folder>; optional
             生效时间 (the change waits for a run after that time; the platform reviews it)
  goods_edit 商品修改: new 价格 and/or 库存 per SKU (规格 or SKU ID; no 规格 = every SKU of the product),
             through the 商品列表 编辑价格 / 编辑库存 dialogs; the plan shows old -> new
  shelf      上下架: 上架 or 下架 per 商品ID (下架 asks for a new review before it can go back on sale)
A flow's guards keep every other publish/sign-up button out of reach (fill engine).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from utils.logger_helper import logger_helper as logger

CN = dt.timezone(dt.timedelta(hours=8))
PLAN = "待确认.json"
PLAN_TTL_H = 24
FILL_TIMEOUT_S = 300.0
VERIFY_TRIES, VERIFY_WAIT_S = 4, 5.0
KINDS = {"coupon": "优惠券", "price_cut": "单品直降", "main_pic": "主图替换", "goods_edit": "商品修改", "shelf": "上下架"}
FLOWS = {("coupon", "douyin"), ("price_cut", "douyin"), ("main_pic", "douyin"), ("goods_edit", "douyin"), ("shelf", "douyin")}
PICS = (".png", ".jpg", ".jpeg", ".webp")

ALIAS = {
    "coupon": {"name": ("名称", "券名称", "优惠券名称", "名字"), "kind": ("类型", "优惠方式", "券类型"),
               "threshold": ("门槛", "满", "满多少", "使用门槛"), "amount": ("面额", "减", "减多少", "金额", "优惠金额"),
               "discount": ("折扣", "几折"), "start": ("开始", "开始时间", "领取开始", "开始日期"),
               "end": ("结束", "结束时间", "领取结束", "结束日期"), "quantity": ("发放量", "数量", "张数"),
               "product_ids": ("商品ID", "商品", "商品id", "适用商品")},
    "price_cut": {"name": ("名称", "活动名称"), "product_id": ("商品ID", "商品id", "商品"),
                  "price": ("活动价", "一口价", "直降价", "价格"), "start": ("开始", "开始时间", "开始日期"),
                  "end": ("结束", "结束时间", "结束日期")},
    "main_pic": {"product_id": ("商品ID", "商品id", "商品"), "slot": ("第几张", "位置", "主图位置", "第几张主图"),
                 "picture": ("图片", "新图", "图片文件", "文件名"), "when": ("生效时间", "替换时间", "时间")},
    "goods_edit": {"product_id": ("商品ID", "商品id", "商品"), "sku": ("规格", "SKU", "SKU ID", "SKUID", "规格ID", "sku"),
                   "price": ("价格", "新价格", "售价", "一口价", "改后价格"), "stock": ("库存", "新库存", "改后库存", "数量")},
    "shelf": {"product_id": ("商品ID", "商品id", "商品"), "action": ("操作", "上下架", "动作", "上架下架")},
}
KEYS = {"coupon": ("name", "amount"), "price_cut": ("product_id", "price"), "main_pic": ("product_id", "picture"),
        "goods_edit": ("product_id",), "shelf": ("product_id", "action")}


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


def _moment(v: Any) -> Optional[dt.datetime]:
    """A date with an optional time ("2026/11/06 20:00"); a bare date is its midnight."""
    if isinstance(v, dt.datetime):
        return v
    m = re.match(r"\s*(\d{4})\D(\d{1,2})\D(\d{1,2})(?:\D+(\d{1,2})[:：](\d{2}))?", str(v or ""))
    try:
        return dt.datetime(*[int(x) for x in m.groups() if x is not None]) if m else None
    except ValueError:
        return None


def _num(v: Any) -> Optional[float]:
    try:
        return float(str(v).replace("¥", "").replace("元", "").replace("折", "").strip())
    except (TypeError, ValueError):
        return None


def _id(v: Any) -> str:
    s = str(v if v is not None else "").strip()
    return s[:-2] if s.endswith(".0") else s


def read_rows(path: str, kind: str = "coupon") -> List[Dict[str, Any]]:
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
    names = {_norm(a): k for k, al in ALIAS[kind].items() for a in al}
    for i, row in enumerate(table[:5]):
        cols = {j: names[_norm(c)] for j, c in enumerate(row) if _norm(c) in names}
        if any(k in cols.values() for k in KEYS[kind]):
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


# ---- 优惠券 -------------------------------------------------------------------------------

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
    bad += _date_problems(start, end, today, 180)
    ids = [x for x in re.split(r"[,，;；\s]+", _id(r.get("product_ids"))) if x]
    if any(not x.isdigit() for x in ids):
        bad.append("商品ID要是数字")
    qty = int(_num(r.get("quantity")) or 0)
    c = {"name": name, "kind": kind, "threshold": threshold, "amount": amount or 0, "discount": discount or 0,
         "start": f"{start:%Y/%m/%d} 00:00:00", "end": f"{end:%Y/%m/%d} 23:59:59" if end else "",
         "quantity": qty, "auto_renew": False, "scope": "商品" if ids else "全店", "product_ids": ids}
    return c, bad


def _date_problems(start: dt.date, end: Optional[dt.date], today: dt.date, max_days: int) -> List[str]:
    if not end:
        return ["没有结束日期"]
    if start < today:
        return ["开始日期早于今天"]
    if end < start or (end - start).days > max_days:
        return [f"结束日期要在开始之后、{max_days} 天以内"]
    return []


def describe(c: Dict[str, Any]) -> str:
    off = (f"满{c['threshold']:g}减{c['amount']:g}" if c["kind"] == "满减" else
           f"立减{c['amount']:g}" if c["kind"] == "立减" else f"{c['discount']:g}折")
    scope = "全店" if c["scope"] == "全店" else f"商品 {','.join(c['product_ids'])}"
    return (f"「{c['name']}」{off}，{c['start'][:10]} ~ {c['end'][:10]}，"
            f"{'不限量' if not c['quantity'] else str(c['quantity']) + ' 张'}，{scope}")


def _plan_coupon(rows: List[Dict[str, Any]], folder: str, today: dt.date):
    items, problems = [], []
    for i, r in enumerate(rows, 1):
        c, bad = check_coupon(r, today)
        (problems.append(f"第{i}行 {c['name']}：{'；'.join(bad)}") if bad else items.append(c))
    return items, problems


# ---- 单品直降 ------------------------------------------------------------------------------

def _plan_price_cut(rows: List[Dict[str, Any]], folder: str, today: dt.date):
    """One activity per 名称 (a row without one is its own); each product once, with its 一口价."""
    groups: Dict[str, Dict[str, Any]] = {}
    problems = []
    for i, r in enumerate(rows, 1):
        bad = []
        pid, price = _id(r.get("product_id")), _num(r.get("price"))
        if not pid.isdigit():
            bad.append("商品ID要是数字")
        if not price or price <= 0:
            bad.append("活动价要大于 0")
        start, end = _day(r.get("start")) or today, _day(r.get("end"))
        bad += _date_problems(start, end, today, 365)
        name = str(r.get("name") or "").strip() or f"单品直降 {pid}"
        if len(name) > 25:
            bad.append("名称超过 25 个字")
        if bad:
            problems.append(f"第{i}行 {name}：{'；'.join(bad)}")
            continue
        g = groups.setdefault(name, {"name": name, "start": f"{start:%Y/%m/%d} 00:00:00",
                                     "end": f"{end:%Y/%m/%d} 23:59:59", "items": []})
        if g["start"][:10] != f"{start:%Y/%m/%d}" or g["end"][:10] != f"{end:%Y/%m/%d}":
            problems.append(f"第{i}行 {name}：同一个活动的开始/结束要一样")
        elif any(x["product_id"] == pid for x in g["items"]):
            problems.append(f"第{i}行 {name}：商品 {pid} 重复")
        else:
            g["items"].append({"product_id": pid, "price": price})
    return [g for g in groups.values() if g["items"]], problems


def describe_price_cut(c: Dict[str, Any]) -> str:
    goods = "，".join(f"{x['product_id']} 一口价 {x['price']:g} 元" for x in c["items"])
    return f"「{c['name']}」{c['start'][:10]} ~ {c['end'][:10]}，{goods}（普通降价促销，不限购）"


# ---- 主图替换 ------------------------------------------------------------------------------

def _plan_main_pic(rows: List[Dict[str, Any]], folder: str, today: dt.date):
    items, problems = [], []
    now = china_now()
    for i, r in enumerate(rows, 1):
        bad = []
        pid = _id(r.get("product_id"))
        if not pid.isdigit():
            bad.append("商品ID要是数字")
        slot = int(_num(r.get("slot")) or 1)
        if not 1 <= slot <= 5:
            bad.append("第几张要在 1 到 5 之间")
        pic = str(r.get("picture") or "").strip()
        path = os.path.join(folder, pic) if pic else ""
        if not pic or not os.path.isfile(path):
            bad.append(f"图片「{pic}」不在 {folder} 里")
        elif not pic.lower().endswith(PICS):
            bad.append("图片要是 png/jpg/webp")
        when = _moment(r.get("when")) if r.get("when") else None
        if r.get("when") and not when:
            bad.append("生效时间看不懂（例：2026/11/20 08:00）")
        elif when and when < now - dt.timedelta(minutes=5):
            bad.append("生效时间已经过了")
        if bad:
            problems.append(f"第{i}行 商品 {pid}：{'；'.join(bad)}")
            continue
        items.append({"product_id": pid, "slot": slot, "picture": pic,
                      "when": when.strftime("%Y-%m-%d %H:%M") if when else ""})
    return items, problems


def describe_main_pic(c: Dict[str, Any]) -> str:
    return (f"商品 {c['product_id']} 第 {c['slot']} 张主图换成「{c['picture']}」"
            + (f"，{c['when']} 以后替换" if c.get("when") else "，马上替换") + "（平台审核后生效）")


# ---- 商品修改 ------------------------------------------------------------------------------

BIG_CHANGE = 0.5


def _spec_label(spec: Dict[str, Any]) -> str:
    return "/".join(str(v) for v in (spec or {}).values())


def _plan_goods_edit(rows: List[Dict[str, Any]], folder: str, today: dt.date, skus: Optional[List[Dict[str, Any]]] = None):
    """One item per product: the SKUs to change, old -> new, from the store's live SKUs."""
    from agent.ec_skills.price_check import _spec_match
    by: Dict[str, Dict[str, Any]] = {}
    problems = []
    for i, r in enumerate(rows, 1):
        pid = _id(r.get("product_id"))
        price = _num(r.get("price")) if r.get("price") not in (None, "") else None
        stock = _num(r.get("stock")) if r.get("stock") not in (None, "") else None
        bad = []
        if not pid.isdigit():
            bad.append("商品ID要是数字")
        if price is None and stock is None:
            bad.append("价格和库存都没填")
        if price is not None and price <= 0:
            bad.append("价格要大于 0")
        if stock is not None and (stock < 0 or stock != int(stock)):
            bad.append("库存要是 0 或正整数")
        mine = [s for s in skus or [] if str(s.get("product_id")) == pid]
        if pid.isdigit() and not mine:
            bad.append("店铺在售商品里没有这个商品ID")
        want = str(r.get("sku") or "").strip()
        hit = ([s for s in mine if str(s.get("sku_id")) == _id(want)] or [s for s in mine if _spec_match(want, s.get("spec") or {})]
               if want else mine)
        if mine and not hit:
            bad.append(f"商品里没有规格「{want}」")
        if bad:
            problems.append(f"第{i}行 商品 {pid}：{'；'.join(bad)}")
            continue
        item = by.setdefault(pid, {"product_id": pid, "title": str(mine[0].get("title") or "")[:30], "changes": []})
        for sk in hit:
            c = next((c for c in item["changes"] if c["sku_id"] == str(sk["sku_id"])), None)
            if c is None:
                c = {"sku_id": str(sk["sku_id"]), "label": _spec_label(sk.get("spec")), "old_price": sk.get("price"),
                     "old_stock": sk.get("stock")}
                item["changes"].append(c)
            if price is not None:
                c["price"] = round(price, 2)
            if stock is not None:
                c["stock"] = int(stock)
    return [i for i in by.values() if i["changes"]], problems


def describe_goods_edit(c: Dict[str, Any]) -> str:
    parts = []
    for x in c["changes"][:8]:
        bits = []
        if x.get("price") is not None:
            old = x.get("old_price")
            warn = (f"（变动 {abs(x['price'] - float(old)) / float(old):.0%}，请看清楚）"
                    if old and abs(x["price"] - float(old)) / float(old) > BIG_CHANGE else "")
            bits.append(f"价格 {old if old is not None else '?'}→{x['price']:g}{warn}")
        if x.get("stock") is not None:
            bits.append(f"库存 {x.get('old_stock', '?')}→{x['stock']}")
        parts.append(f"{x['label'] or x['sku_id']} " + "，".join(bits))
    more = f" 等 {len(c['changes'])} 个规格" if len(c["changes"]) > 8 else ""
    return f"商品 {c['product_id']}「{c.get('title', '')}」：" + "；".join(parts) + more


# ---- 上下架 --------------------------------------------------------------------------------

def _plan_shelf(rows: List[Dict[str, Any]], folder: str, today: dt.date):
    items, problems, seen = [], [], set()
    for i, r in enumerate(rows, 1):
        pid, act = _id(r.get("product_id")), str(r.get("action") or "").strip()
        bad = []
        if not pid.isdigit():
            bad.append("商品ID要是数字")
        if act not in ("上架", "下架"):
            bad.append("操作要写 上架 或 下架")
        if pid in seen:
            bad.append("商品重复")
        if bad:
            problems.append(f"第{i}行 商品 {pid}：{'；'.join(bad)}")
            continue
        seen.add(pid)
        items.append({"product_id": pid, "action": act})
    return items, problems


def describe_shelf(c: Dict[str, Any]) -> str:
    return f"商品 {c['product_id']} {c['action']}" + ("（下架后再上架要重新审核）" if c["action"] == "下架" else "")


SPECS: Dict[str, Dict[str, Callable]] = {
    "coupon": {"plan": _plan_coupon, "describe": describe},
    "price_cut": {"plan": _plan_price_cut, "describe": describe_price_cut},
    "main_pic": {"plan": _plan_main_pic, "describe": describe_main_pic},
    "goods_edit": {"plan": _plan_goods_edit, "describe": describe_goods_edit},
    "shelf": {"plan": _plan_shelf, "describe": describe_shelf},
}
HEADERS = {"coupon": "名称、类型、门槛、面额、折扣、开始、结束、发放量、商品ID",
           "price_cut": "名称、商品ID、活动价、开始、结束",
           "main_pic": "商品ID、第几张、图片（放在这个文件夹里的图片文件名）、生效时间（可空）",
           "goods_edit": "商品ID、规格（或 SKU ID，空=这个商品的全部规格）、价格、库存（价格和库存填一个就行）",
           "shelf": "商品ID、操作（上架 或 下架）"}


def _newest_table(folder: str) -> str:
    files = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith((".xlsx", ".csv"))
             and not f.startswith(("~$", "结果"))] if os.path.isdir(folder) else []
    return max(files, key=os.path.getmtime) if files else ""


def propose(kind: str, platform: str, store_id: str, folder: str) -> Dict[str, Any]:
    """Check the newest request table and write the plan to confirm. Changes nothing on the store."""
    label = KINDS[kind]
    if (kind, platform) not in FLOWS:
        return {"summary": f"{label}：这个平台还不支持（目前只有抖店）。", "items": 0}
    table = _newest_table(folder)
    if not table:
        return {"summary": f"{label}：{folder} 里还没有申请表（.xlsx/.csv：{HEADERS[kind]}）。", "items": 0}
    today = china_now().date()
    if kind == "goods_edit":   # old -> new needs the store's live SKUs
        from agent.ec_skills.store_prices import read_store_skus
        skus = [s for s in read_store_skus(platform, store_id=store_id)[0]
                if not store_id or not s.get("store_id") or s.get("store_id") == store_id]
        items, problems = _plan_goods_edit(read_rows(table, kind), folder, today, skus)
    else:
        items, problems = SPECS[kind]["plan"](read_rows(table, kind), folder, today)
    plan = {"kind": kind, "platform": platform, "store_id": store_id, "table": os.path.basename(table),
            "created": china_now().strftime("%Y-%m-%d %H:%M:%S"), "items": items}
    whens = [c["when"] for c in items if c.get("when")]
    if whens:   # a scheduled change keeps its plan until a little after its time
        plan["valid_until"] = max(max(whens) + ":00", plan["created"])
    if items:
        with open(os.path.join(folder, PLAN), "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=1)
    desc = SPECS[kind]["describe"]
    text = f"{label}（{store_id}）——还没有改店铺，等你确认：\n"
    text += "\n".join(f"{n}. {desc(c)}" for n, c in enumerate(items, 1)) or "没有可以执行的。"
    if problems:
        text += "\n这些行有问题，不会执行：\n" + "\n".join(f"- {p}" for p in problems[:10])
    if items:
        text += f"\n确认就运行「{label}（确认执行）」（或对助手说“确认{label}”）；{PLAN_TTL_H} 小时内有效。"
        if whens:
            text += "定了生效时间的，要在那个时间以后再运行一次确认执行（可以给它设一个定时）。"
    return {"summary": text, "items": len(items), "problems": problems}


def load_plan(folder: str, kind: str, store_id: str) -> Tuple[Optional[Dict[str, Any]], str]:
    path = os.path.join(folder, PLAN)
    try:
        with open(path, encoding="utf-8") as f:
            plan = json.load(f)
    except (OSError, ValueError):
        return None, "没有待确认的申请（先运行“提议”那一步）"
    if plan.get("kind") != kind or plan.get("store_id") != store_id:
        return None, "待确认的申请不是这个店铺/这类改动的"
    created = dt.datetime.strptime(plan.get("created", "2000-01-01 00:00:00"), "%Y-%m-%d %H:%M:%S")
    until = created + dt.timedelta(hours=PLAN_TTL_H)
    if plan.get("valid_until"):
        until = max(until, dt.datetime.strptime(plan["valid_until"], "%Y-%m-%d %H:%M:%S") + dt.timedelta(hours=PLAN_TTL_H))
    if china_now() > until:
        return None, f"待确认的申请已经超过有效期（{PLAN_TTL_H} 小时），请重新提议"
    return plan, ""


def verify_coupons(platform: str, store_id: str, names: List[str]) -> Dict[str, bool]:
    """Which coupon names the store now lists (promo_deadlines reader)."""
    return _promo_names(platform, store_id, names, "优惠券")


def _promo_names(platform: str, store_id: str, names: List[str], kind: str = "") -> Dict[str, bool]:
    from agent.ec_skills.promo_deadlines import read_store_promos
    have = {p["name"] for p in read_store_promos(platform, store_id)["promos"] if not kind or p.get("kind") == kind}
    return {n: n in have for n in names}


def _verify_goods(platform: str, store_id: str, sent: List[Dict[str, Any]]) -> Dict[int, str]:
    from agent.ec_skills.store_prices import read_store_skus
    now = {str(s.get("sku_id")): s for s in read_store_skus(platform, store_id=store_id)[0]}
    out = {}
    for i, c in enumerate(sent):
        off = []
        for x in c["changes"]:
            sk = now.get(x["sku_id"]) or {}
            if x.get("stock") is not None and sk.get("stock") != x["stock"]:
                off.append(f"{x['label']} 库存现在是 {sk.get('stock')}")
            if x.get("price") is not None and sk.get("price") is not None and abs(float(sk["price"]) - x["price"]) > 0.005:
                off.append(f"{x['label']} 价格现在是 {sk['price']}（有活动时显示的是活动价）")
        out[i] = "已改好" if not off else "已保存，" + "；".join(off[:3])
    return out


def _verify_shelf(platform: str, store_id: str, sent: List[Dict[str, Any]]) -> Dict[int, str]:
    from agent.ec_skills.store_quality import read_status
    now = read_status(store_id)
    out = {}
    for i, c in enumerate(sent):
        st = (now.get(c["product_id"]) or {}).get("status", "")
        if c["action"] == "下架":
            out[i] = "已下架" if st == "已下架" else f"已提交，现在是 {st or '没读到'}"
        else:
            out[i] = "已上架" if st == "在售" else ("已提交，等平台审核" if st == "审核中或其他" else f"已提交，现在是 {st or '没读到'}")
    return out


def _verify(kind: str, platform: str, store_id: str, sent: List[Dict[str, Any]]) -> Dict[int, str]:
    """Row index -> result after reading the store back (nothing for kinds the readers can't see)."""
    if kind == "goods_edit":
        return _verify_goods(platform, store_id, sent)
    if kind == "shelf":
        return _verify_shelf(platform, store_id, sent)
    if kind not in ("coupon", "price_cut"):
        return {}
    names = [c["name"] for c in sent]
    for attempt in range(VERIFY_TRIES):   # a new coupon shows in the list some seconds later (KEN 11-05)
        seen = (verify_coupons(platform, store_id, names) if kind == "coupon" else
                _promo_names(platform, store_id, names))                # 抖店 lists 单品直降 as 限时折扣
        if all(seen.values()) or attempt == VERIFY_TRIES - 1:
            break
        time.sleep(VERIFY_WAIT_S)
    return {i: "已创建" if seen.get(c["name"]) else "已提交，店铺列表里还没看到" for i, c in enumerate(sent)}


def execute(kind: str, platform: str, store_id: str, folder: str, flow: Dict[str, Any],
            profile_id: str = "") -> Dict[str, Any]:
    """Run the pending plan through *flow* (publish), then read the store back."""
    from agent.ec_skills.fill.node import _open_and_run, _port, _run_sync
    label = KINDS[kind]
    plan, why = load_plan(folder, kind, store_id)
    if not plan:
        return {"summary": f"{label}：{why}。", "done": 0}
    now = china_now()
    due = [c for c in plan["items"] if not c.get("when") or c["when"] <= now.strftime("%Y-%m-%d %H:%M")]
    later = [c for c in plan["items"] if c not in due]
    if not due:
        return {"summary": f"{label}：还没到生效时间（最早 {min(c['when'] for c in later)}），这次没有改店铺。", "done": 0}
    # taken before running, so a second run can never repeat it; later items stay pending
    stamp = now.strftime("%Y%m%d_%H%M%S")
    os.replace(os.path.join(folder, PLAN), os.path.join(folder, f"已执行_{stamp}.json"))
    if later:
        with open(os.path.join(folder, PLAN), "w", encoding="utf-8") as f:
            json.dump(dict(plan, items=later), f, ensure_ascii=False, indent=1)
    port = _port(store_id, flow, profile_id)
    guards = dict(flow.get("guards") or {})
    steps = {k: v for k, v in flow.items() if k != "guards"}
    rows = []
    for c in due:
        if not port:
            rows.append(dict(c, 结果="没执行", 原因="店铺浏览器没启动"))
            continue
        roles, paths = {}, {}
        if kind == "main_pic":
            roles, paths = {"main_new": [c["picture"]]}, {c["picture"]: os.path.join(folder, c["picture"])}
        out = _run_sync(lambda: _open_and_run(port, steps, guards, c, roles, paths, "publish", {}), FILL_TIMEOUT_S)
        rows.append(dict(c, 结果=("已提交，平台审核后生效" if kind == "main_pic" else "已提交") if out.get("ok") else "失败",
                         原因="" if out.get("ok") else f"{out.get('stage')}: {str(out.get('error') or '')[:200]}"))
        logger.info(f"[store-writes] {kind} {store_id} {c.get('name') or c.get('product_id')!r}: ok={out.get('ok')} "
                    f"stage={out.get('stage')} blocked={out.get('blocked')}")
    sent = [r for r in rows if r["结果"] == "已提交"]
    if sent:
        try:
            for i, res in _verify(kind, platform, store_id, sent).items():
                sent[i]["结果"] = res
        except Exception as exc:
            logger.warning(f"[store-writes] read-back failed: {exc}")
    path = _write(rows, os.path.join(folder, "结果", f"{label}_{stamp}.xlsx"))
    ok = sum(1 for r in rows if r["结果"].startswith(("已创建", "已提交", "已改好", "已保存", "已下架", "已上架")))
    text = f"{label}（{store_id}）：{len(rows)} 个里成功 {ok} 个。"
    desc = SPECS[kind]["describe"]
    for r in rows:
        text += f"\n- {desc(r)}：{r['结果']}" + (f"（{r['原因']}）" if r.get("原因") else "")
    if later:
        text += f"\n还有 {len(later)} 个没到生效时间，留在待确认里。"
    return {"summary": text, "done": ok, "path": path}


def _write(rows: List[Dict[str, Any]], path: str) -> str:
    import openpyxl
    os.makedirs(os.path.dirname(path), exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    cols = ["结果", "原因"] + [k for k in rows[0] if k not in ("结果", "原因")] if rows else ["结果", "原因"]
    ws.append(cols)
    for r in rows:
        ws.append([_cell(r.get(c, "")) for c in cols])
    wb.save(path)
    return path


def _cell(v: Any) -> Any:
    if isinstance(v, list):
        return ", ".join(f"{x['product_id']}:{x['price']:g}" if isinstance(x, dict) and "product_id" in x else
                         f"{x.get('label') or x.get('sku_id')}:" + "/".join(f"{k}{x[k]}" for k in ("price", "stock") if x.get(k) is not None)
                         if isinstance(x, dict) else str(x) for x in v)
    return v
