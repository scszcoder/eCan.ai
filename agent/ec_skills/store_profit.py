"""利润核算: profit per SKU, product and day from the store's own orders and the merchant's cost table.

The cost table is the newest .xlsx/.csv in the report folder whose name has 成本 in it
(e.g. <ks>/reports/<店铺>/成本表.xlsx). Headers are matched loosely:

  编码   规格编码/SKU编码/商家编码 | 货号/款号 | 商品ID      (at least one)
  规格   optional; a row without one covers every spec of the product
  成本   单件成本/进价/采购价/成本价 (yuan per piece; required)
  包装   optional, per piece
  运费   optional, per order (the first one found is used for every order)

Task vars: fee_rate (平台扣点, e.g. 0.05 or 5 = 5%; default 0, the summary says so),
ship_cost (per order; overrides the table). Refunded lines are left out of revenue and
counted apart (a partial refund counts as a whole one: the order list has no amounts).
Read only: nothing in the store is changed.
"""
from __future__ import annotations

import datetime as dt
import os
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from agent.ec_skills import price_check as pc

COST_HEADERS = {
    "sku_code": ["规格编码", "SKU编码", "sku编码", "商家编码", "外部编码", "条码"],
    "code": ["货号", "款号", "商品编码", "商品编号", "型号"],
    "product_id": ["商品ID", "商品id", "宝贝ID", "宝贝id", "产品ID"],
    "spec": ["规格", "SKU", "sku", "销售属性"],
    "title": ["商品名称", "商品标题", "宝贝标题", "标题", "名称"],
    "pack": ["包装", "耗材"],
    "ship": ["运费", "快递费", "物流费"],
    "cost": ["单件成本", "成本价", "进价", "采购价", "成本", "拿货价"],
}


def _columns(head: List[str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    used = set()
    for field, words in COST_HEADERS.items():
        for w in words:
            hit = next((i for i, h in enumerate(head) if i not in used and w.lower() in h.lower()), None)
            if hit is not None:
                out[field] = hit
                used.add(hit)
                break
    return out


def find_table(folder: str) -> str:
    names = [n for n in (os.listdir(folder) if os.path.isdir(folder) else [])
             if "成本" in n and n.lower().endswith((".xlsx", ".csv")) and not n.startswith("~$")]
    return max((os.path.join(folder, n) for n in names), key=os.path.getmtime, default="")


def read_costs(path: str) -> List[Dict[str, Any]]:
    """[{sku_code?, code?, product_id?, spec?, cost, pack, ship}] -- rows with a key and a cost."""
    rows: List[Dict[str, Any]] = []
    for grid in pc._sheets(path):
        for h, head in enumerate(grid[:10]):
            cols = _columns([str(x or "").strip() for x in head])
            if ({"sku_code", "code", "product_id"} & set(cols)) and "cost" in cols:
                break
        else:
            continue
        for r in grid[h + 1:]:
            get = lambda f: r[cols[f]] if f in cols and cols[f] < len(r) else None
            row = {f: str(get(f)).strip() for f in ("sku_code", "code", "product_id", "spec", "title")
                   if get(f) not in (None, "")}
            row["cost"] = pc._num(get("cost"))
            row["pack"], row["ship"] = pc._num(get("pack")) or 0.0, pc._num(get("ship"))
            if (row.get("sku_code") or row.get("code") or row.get("product_id")) and row["cost"] is not None:
                rows.append(row)
    return rows


def _parts(spec: str) -> List[str]:
    return [pc._norm(p) for p in re.split(r"[/;；,，:：\s]+", str(spec or "")) if p.strip()]


def cost_of(line: Dict[str, Any], costs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The cost row for an order line: by SKU code, else by product (code or ID) + spec, else product."""
    if line.get("sku_code"):
        hit = next((c for c in costs if c.get("sku_code") and pc._norm(c["sku_code"]) == pc._norm(line["sku_code"])), None)
        if hit:
            return hit
    keys = {pc._norm(line.get(k)) for k in ("product_id", "code", "sku_code") if line.get(k)}
    prod = [c for c in costs if keys & {pc._norm(c.get(k)) for k in ("product_id", "code", "sku_code") if c.get(k)}]
    have = _parts(line.get("spec"))
    for c in prod:
        want = _parts(c.get("spec"))
        if want and all(w in have for w in want):
            return c
    return next((c for c in prod if not c.get("spec")), None)


def _rate(v: Any) -> float:
    r = pc._num(v) or 0.0
    return r / 100 if r >= 1 else r


def _money(v: float) -> float:
    return round(v, 2)


def profit(lines, skus, now, opts) -> Tuple[str, Dict[str, list]]:
    costs = opts.get("costs") or []
    if not costs:
        return (f"还没有成本表：把成本表（文件名带“成本”，.xlsx 或 .csv，含 编码 和 成本 两列，可加 包装、运费）"
                f"放进 {opts.get('folder') or '报告文件夹'}，再运行一次。"), {}
    fee = _rate(opts.get("fee_rate"))
    ship = pc._num(opts.get("ship_cost"))
    if ship is None:
        ship = next((c["ship"] for c in costs if c.get("ship") is not None), 0.0)
    kept = [l for l in lines if not l["refund"]]
    refunded = [l for l in lines if l["refund"]]
    per_order = defaultdict(int)
    for l in kept:
        per_order[l["order_id"]] += 1
    by_sku: Dict[Tuple[str, str], Dict[str, Any]] = {}
    by_day: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    missing: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for l in kept:
        c = cost_of(l, costs)
        key = (l["product_id"] or l["title"], l["spec"])
        if c is None:
            m = missing.setdefault(key, {"商品ID": l["product_id"], "商品": l["title"][:40], "规格": l["spec"],
                                         "SKU编码": l.get("sku_code", ""), "件数": 0, "销售额": 0.0})
            m["件数"] += l["qty"]
            m["销售额"] = _money(m["销售额"] + l["paid"])
            continue
        goods = l["qty"] * (c["cost"] + c["pack"])
        p = l["paid"] - goods - l["paid"] * fee - ship / per_order[l["order_id"]]
        r = by_sku.setdefault(key, {"商品ID": l["product_id"], "商品": l["title"][:40], "规格": l["spec"],
                                    "单件成本": c["cost"] + c["pack"], "件数": 0, "销售额": 0.0, "商品成本": 0.0,
                                    "扣点": 0.0, "运费": 0.0, "利润": 0.0})
        r["件数"] += l["qty"]
        for k, v in (("销售额", l["paid"]), ("商品成本", goods), ("扣点", l["paid"] * fee),
                     ("运费", ship / per_order[l["order_id"]]), ("利润", p)):
            r[k] = _money(r[k] + v)
        day = by_day[l["time"].strftime("%Y-%m-%d") if l["time"] else "?"]
        day["销售额"] += l["paid"]
        day["利润"] += p
        day["件数"] += l["qty"]
    rows = sorted(by_sku.values(), key=lambda r: -r["利润"])
    for r in rows:
        r["利润率"] = f"{r['利润'] / r['销售额'] * 100:.0f}%" if r["销售额"] else "-"
    goods_rows: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        g = goods_rows.setdefault(r["商品ID"] or r["商品"], {"商品ID": r["商品ID"], "商品": r["商品"], "件数": 0,
                                                            "销售额": 0.0, "利润": 0.0})
        g["件数"] += r["件数"]
        g["销售额"], g["利润"] = _money(g["销售额"] + r["销售额"]), _money(g["利润"] + r["利润"])
    goods = sorted(goods_rows.values(), key=lambda g: -g["利润"])
    for g in goods:
        g["利润率"] = f"{g['利润'] / g['销售额'] * 100:.0f}%" if g["销售额"] else "-"
    days = [{"日期": d, "件数": int(v["件数"]), "销售额": _money(v["销售额"]), "利润": _money(v["利润"])}
            for d, v in sorted(by_day.items())]
    rev, prof = sum(r["销售额"] for r in rows), sum(r["利润"] for r in rows)
    text = (f"{opts['days']} 天（有成本的部分）：销售额 {rev:,.2f}，商品成本 {sum(r['商品成本'] for r in rows):,.2f}，"
            f"扣点 {sum(r['扣点'] for r in rows):,.2f}，运费 {sum(r['运费'] for r in rows):,.2f}，"
            f"利润 {prof:,.2f}（利润率 {prof / rev * 100:.0f}%）。" if rev else
            f"{opts['days']} 天的成交里没有一单能对上成本表。")
    for g in [g for g in goods if g["利润"] > 0][:3]:
        text += f"\n- 赚得多：{g['商品'][:18]} 利润 {g['利润']:,.2f}（{g['利润率']}）"
    for g in [g for g in goods if g["利润"] < 0][-3:]:
        text += f"\n- 亏钱：{g['商品'][:18]} 利润 {g['利润']:,.2f}（{g['件数']} 件）"
    if missing:
        text += (f"\n{len(missing)} 个规格在成本表里没找到（销售额 {sum(m['销售额'] for m in missing.values()):,.2f}，"
                 "没算进利润），见结果表“没成本”。")
    if refunded:
        text += f"\n有售后/退款的 {len({l['order_id'] for l in refunded})} 单没算进销售额。"
    notes = []
    if not fee:
        notes.append("没扣平台扣点（任务变量 fee_rate 填，如 0.05）")
    if not ship:
        notes.append("没算运费（成本表加“运费”列或任务变量 ship_cost）")
    notes.append("没算推广费和平台活动补贴")
    text += "\n（" + "；".join(notes) + "）"
    return text, {"按规格": rows, "按商品": goods, "按天": days, "没成本": list(missing.values())}
