"""Own-data store reports (wave B): computed from the store's own orders (store_orders),
SKUs and stock (store_prices) and promotions (promo_deadlines). Read only.

run_for_store(report, store_id, folder, **opts) -> {summary, path, ...}; the result
Excel goes to <folder>/结果/<报告名>_<time>.xlsx. Reports:

  goods_health   货盘诊断    every product: sales, stock, days of stock, 动销/滞销/断货/积压
  sabc           商品分层    S/A/B/C by share of sales, with what to do per tier
  daily_patrol   店铺日巡检  yesterday vs the 7 days before; refunds; low stock; promos ending
  weekly_goods   商品周巡检  each product, last 7 days vs the 7 before; refund rate
  promo_review   营销复盘    a window (start/end, default last 7 days) vs the same length before
  bundle         搭配购      items bought together (same order, or same buyer same day)
  repeat         复购老客    repeat / lapsed buyers (only where the platform gives a buyer key)
  buyer_profile  下单画像    price bands, hours, weekdays, specs, quantities
  tool_effect    优惠效果    discounted vs full-price orders, discount cost, units per order

Numbers come only from the merchant's own pages; traffic and conversion are not read
(reader R6), so tiers and drops are by sales, and each summary says so where it matters.
"""
from __future__ import annotations

import datetime as dt
import os
import re
from collections import Counter, defaultdict
from typing import Any, Callable, Dict, List, Optional, Tuple

from utils.logger_helper import logger_helper as logger

CN = dt.timezone(dt.timedelta(hours=8))
NAMES = {"goods_health": "货盘诊断", "sabc": "商品分层", "daily_patrol": "店铺日巡检", "weekly_goods": "商品周巡检",
         "promo_review": "营销复盘", "bundle": "搭配购", "repeat": "复购老客", "buyer_profile": "下单画像",
         "tool_effect": "优惠效果"}
DAYS = {"repeat": 90, "bundle": 90, "daily_patrol": 8, "weekly_goods": 14}


def china_now() -> dt.datetime:
    return dt.datetime.now(CN).replace(tzinfo=None)


def platform_of_store(store_id: str) -> str:
    """'pinduoduo-小店二号' -> 'pdd'; 'tmall-…'/'taobao-…' -> 'tmall'; '' if unknown."""
    head = str(store_id or "").split("-", 1)[0].lower()
    if head in ("tmall", "taobao", "qianniu", "tb"):
        return "tmall"
    from agent.ec_skills.browser_use_extension.store_page import platform_of
    return platform_of(head)


# ---------- small helpers ----------

def _pct(a: float, b: float) -> str:
    return f"{a / b * 100:.0f}%" if b else "-"


def _chg(new: float, old: float) -> str:
    if not old:
        return "新增" if new else "-"
    return f"{(new - old) / old * 100:+.0f}%"


def _y(v: float) -> str:
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.2f}"


def _int(v: Any) -> Optional[int]:
    try:
        return int(float(str(v).replace(",", "").strip()))
    except (TypeError, ValueError):
        return None


def _orders(lines: List[Dict[str, Any]]) -> int:
    return len({l["order_id"] for l in lines})


def _gmv(lines: List[Dict[str, Any]]) -> float:
    return round(sum(l["paid"] for l in lines), 2)


def _units(lines: List[Dict[str, Any]]) -> int:
    return sum(l["qty"] for l in lines)


def _refunds(lines: List[Dict[str, Any]]) -> int:
    return len({l["order_id"] for l in lines if l["refund"]})


def _between(lines, start: dt.datetime, end: dt.datetime):
    return [l for l in lines if l["time"] and start <= l["time"] < end]


def _by_product(lines) -> Dict[str, List[Dict[str, Any]]]:
    g: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for l in lines:
        g[l["product_id"] or l["title"]].append(l)
    return g


def _title(lines, skus=None) -> str:
    return (lines[0]["title"] if lines else (skus or [{}])[0].get("title", ""))[:40]


def _summ(lines) -> Dict[str, Any]:
    o = _orders(lines)
    return {"订单": o, "件数": _units(lines), "销售额": _gmv(lines), "客单价": round(_gmv(lines) / o, 2) if o else 0,
            "退款订单": _refunds(lines), "退款率": _pct(_refunds(lines), o)}


# ---------- reports: each returns (summary, {sheet: rows}) ----------

def goods_health(lines, skus, now, opts) -> Tuple[str, Dict[str, list]]:
    days = opts["days"]
    sold = _by_product(lines)
    by_sku_product: Dict[str, List[dict]] = defaultdict(list)
    for s in skus:
        by_sku_product[str(s.get("product_id") or "")].append(s)
    rows = []
    for pid in sorted(set(sold) | set(by_sku_product)):
        ls, ss = sold.get(pid, []), by_sku_product.get(pid, [])
        units = _units(ls)
        known = [_int(s.get("stock")) for s in ss if _int(s.get("stock")) is not None]
        # 淘宝 shows one stock per item (repeated on each SKU), the others one per SKU
        stock = (max(known) if opts.get("platform") == "tmall" else sum(known)) if known else None
        daily = units / days
        cover = round(stock / daily) if stock is not None and daily else None
        last = max((l["time"] for l in ls if l["time"]), default=None)
        prices = [float(s["price"]) for s in ss if s.get("price") not in (None, "")]
        tags = []
        if not units:
            tags.append("滞销")
        if stock is not None and units and cover is not None and cover < 7:
            tags.append("断货风险")
        if cover is not None and cover > 90:
            tags.append("积压")
        out_specs = [s for s in ss if _int(s.get("stock")) == 0] if opts.get("platform") != "tmall" else []
        if out_specs and units:
            tags.append(f"{len(out_specs)}个规格缺货")
        rows.append({"状态": "、".join(tags) or "动销", "商品ID": pid, "商品": _title(ls, ss), "在售规格": len(ss) or "",
                     "价格带": (f"{min(prices):g}-{max(prices):g}" if prices else ""), "库存": "" if stock is None else stock,
                     f"{days}天件数": units, f"{days}天销售额": _gmv(ls), "日均件数": round(daily, 1),
                     "可售天数": "" if cover is None else cover, "最后成交": last.strftime("%m-%d") if last else "",
                     "退款率": _pct(_refunds(ls), _orders(ls)) if ls else ""})
    rows.sort(key=lambda r: -r[f"{days}天销售额"])
    c = Counter(t.split("个规格")[0] if "规格缺货" in t else t for r in rows for t in r["状态"].split("、"))
    moving = sum(1 for r in rows if r[f"{days}天件数"])
    text = (f"共 {len(rows)} 个商品，{days} 天内有成交 {moving} 个（动销率 {_pct(moving, len(rows))}）；"
            f"滞销 {c.get('滞销', 0)}，断货风险 {c.get('断货风险', 0)}，积压 {c.get('积压', 0)}。")
    for tag in ("断货风险", "滞销", "积压"):
        hit = [r for r in rows if tag in r["状态"]][:3]
        if hit:
            text += f"\n- {tag}：" + "；".join(f"{r['商品'][:16]}（库存{r['库存']}，{days}天{r[f'{days}天件数']}件）" for r in hit)
    if not skus:
        text += "\n（没读到店铺商品和库存，只按订单算；滞销/积压看不出来）"
    return text, {"货盘": rows}


TIERS = [("S", 0.30, "主推：保库存、保价格，广告和活动优先给它"), ("A", 0.70, "稳住：看转化和评价，跟着做活动"),
         ("B", 0.90, "培养：优化主图标题，试小额推广或搭配"), ("C", 1.01, "观察：考虑清库存、合并或下架")]


def sabc(lines, skus, now, opts):
    sold = _by_product(lines)
    total = _gmv(lines) or 1
    ranked = sorted(sold.items(), key=lambda kv: -_gmv(kv[1]))
    rows, cum = [], 0.0
    for pid, ls in ranked:
        share = _gmv(ls) / total
        tier = next(t for t, cap, _ in TIERS if round(cum, 6) < cap)
        cum += share
        rows.append({"层级": tier, "商品ID": pid, "商品": _title(ls), "销售额": _gmv(ls), "占比": f"{share * 100:.1f}%",
                     "件数": _units(ls), "订单": _orders(ls), "退款率": _pct(_refunds(ls), _orders(ls)),
                     "建议": next(a for t, _, a in TIERS if t == tier)})
    listed = {str(s.get("product_id")) for s in skus} - set(sold)
    for pid in sorted(listed):
        t = next((s.get("title", "") for s in skus if str(s.get("product_id")) == pid), "")
        rows.append({"层级": "C", "商品ID": pid, "商品": t[:40], "销售额": 0, "占比": "0%", "件数": 0, "订单": 0,
                     "退款率": "", "建议": "没有成交：" + TIERS[3][2]})
    c = Counter(r["层级"] for r in rows)
    text = (f"按 {opts['days']} 天销售额分层（S 占前30%、A 到70%、B 到90%、C 其余；没有流量和转化数据，只按成交）："
            f"S {c.get('S', 0)} 个，A {c.get('A', 0)}，B {c.get('B', 0)}，C {c.get('C', 0)}。")
    for r in rows[:5]:
        text += f"\n- {r['层级']} {r['商品'][:18]}：销售额 {_y(r['销售额'])}（{r['占比']}）"
    return text, {"分层": rows}


def daily_patrol(lines, skus, now, opts):
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    y0 = today - dt.timedelta(days=1)
    yday = _between(lines, y0, today)
    before = _between(lines, y0 - dt.timedelta(days=7), y0)
    cur, avg = _summ(yday), {k: v / 7 for k, v in _summ(before).items() if isinstance(v, (int, float))}
    flags = []
    if avg.get("销售额") and cur["销售额"] < avg["销售额"] * 0.7:
        flags.append(f"销售额比前7天日均低 {_chg(cur['销售额'], avg['销售额'])}")
    if cur["订单"] and cur["退款订单"] / cur["订单"] >= 0.1:
        flags.append(f"退款订单占 {cur['退款率']}")
    recent = {l["product_id"] for l in before + yday}
    low = [s for s in skus if _int(s.get("stock")) is not None and _int(s.get("stock")) <= int(opts.get("low_stock") or 5)
           and str(s.get("product_id")) in recent]
    if low:
        flags.append(f"{len(low)} 个在卖规格库存≤{opts.get('low_stock') or 5}")
    due = opts.get("promos_due") or []
    if due:
        flags.append(f"{len(due)} 个营销 3 天内到期")
    rows = [{"项目": k, "昨天": cur[k], "前7天日均": round(avg.get(k, 0), 2) if k in avg else "",
             "变化": _chg(cur[k], avg.get(k, 0)) if k in avg else ""} for k in cur]
    text = (f"昨天（{y0:%m-%d}）：订单 {cur['订单']}，销售额 {_y(cur['销售额'])}（前7天日均 {_y(avg.get('销售额', 0))}，"
            f"{_chg(cur['销售额'], avg.get('销售额', 0))}），退款订单 {cur['退款订单']}。")
    text += ("\n要注意：" + "；".join(flags)) if flags else "\n没有异常。"
    for s in low[:5]:
        text += f"\n- 库存低：{str(s.get('title', ''))[:16]} {'/'.join(str(v) for v in (s.get('spec') or {}).values())} 剩 {s.get('stock')}"
    for p in due[:5]:
        text += f"\n- 到期：{p.get('kind')}「{p.get('name')}」{p['end']:%m-%d %H:%M}" if p.get("end") else ""
    low_rows = [{"商品": s.get("title", ""), "规格": "/".join(str(v) for v in (s.get("spec") or {}).values()),
                 "库存": s.get("stock")} for s in low]
    return text, {"昨天": rows, "库存低": low_rows}


def weekly_goods(lines, skus, now, opts):
    w0 = now - dt.timedelta(days=7)
    this, last = _by_product(_between(lines, w0, now)), _by_product(_between(lines, w0 - dt.timedelta(days=7), w0))
    rows = []
    for pid in set(this) | set(last):
        a, b = this.get(pid, []), last.get(pid, [])
        flags = []
        if _units(b) >= 5 and _units(a) <= _units(b) * 0.7:
            flags.append("销量下滑")
        if _units(a) >= 5 and _units(b) and _units(a) >= _units(b) * 1.5:
            flags.append("增长")
        if _orders(a) >= 5 and _refunds(a) / _orders(a) >= 0.1:
            flags.append("退款偏高")
        if b and not a:
            flags.append("本周没卖出")
        rows.append({"提示": "、".join(flags), "商品ID": pid, "商品": _title(a or b), "本周件数": _units(a), "上周件数": _units(b),
                     "件数变化": _chg(_units(a), _units(b)), "本周销售额": _gmv(a), "上周销售额": _gmv(b),
                     "本周退款率": _pct(_refunds(a), _orders(a))})
    rows.sort(key=lambda r: (not r["提示"], -r["本周销售额"]))
    t, l = _summ(_between(lines, w0, now)), _summ(_between(lines, w0 - dt.timedelta(days=7), w0))
    text = (f"近7天：销售额 {_y(t['销售额'])}（上周 {_y(l['销售额'])}，{_chg(t['销售额'], l['销售额'])}），订单 {t['订单']}，"
            f"退款率 {t['退款率']}。")
    for r in [r for r in rows if r["提示"]][:8]:
        text += f"\n- {r['商品'][:18]}：{r['提示']}（本周{r['本周件数']}件，上周{r['上周件数']}件，退款率{r['本周退款率']}）"
    if not any(r["提示"] for r in rows):
        text += "\n各商品没有明显异常（只看成交和退款；流量和广告没读）。"
    return text, {"商品周巡检": rows}


def _parse_day(v: Any) -> Optional[dt.datetime]:
    try:
        return dt.datetime.strptime(str(v).strip()[:10], "%Y-%m-%d")
    except ValueError:
        return None


def promo_review(lines, skus, now, opts):
    start, end = _parse_day(opts.get("start")), _parse_day(opts.get("end"))
    if start and end:
        end = end + dt.timedelta(days=1)
    else:
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - dt.timedelta(days=7)
    span = end - start
    cur, prev = _between(lines, start, end), _between(lines, start - span, start)
    a, b = _summ(cur), _summ(prev)
    disc = lambda ls: round(sum(l["merchant_discount"] for l in ls), 2)
    gross = lambda ls: sum(l["amount"] for l in ls) or 1
    rows = [{"指标": k, "活动期": a[k], "活动前": b[k], "变化": _chg(a[k], b[k]) if isinstance(a[k], (int, float)) else ""}
            for k in a]
    rows += [{"指标": "商家优惠金额", "活动期": disc(cur), "活动前": disc(prev), "变化": _chg(disc(cur), disc(prev))},
             {"指标": "优惠占原价", "活动期": _pct(disc(cur), gross(cur)), "活动前": _pct(disc(prev), gross(prev)), "变化": ""}]
    days = []
    d = start
    while d < end:
        ls = _between(lines, d, d + dt.timedelta(days=1))
        days.append(dict({"日期": d.strftime("%Y-%m-%d")}, **_summ(ls)))
        d += dt.timedelta(days=1)
    top = sorted(_by_product(cur).items(), key=lambda kv: -_gmv(kv[1]))[:10]
    goods = [{"商品": _title(ls), "活动期件数": _units(ls), "活动期销售额": _gmv(ls),
              "活动前件数": _units(_by_product(prev).get(pid, []))} for pid, ls in top]
    roi = (a["销售额"] - b["销售额"]) / disc(cur) if disc(cur) else None
    text = (f"{start:%m-%d}~{(end - dt.timedelta(days=1)):%m-%d} 对比之前同样 {span.days} 天：销售额 {_y(a['销售额'])}"
            f"（{_chg(a['销售额'], b['销售额'])}），订单 {a['订单']}（{_chg(a['订单'], b['订单'])}），客单价 {a['客单价']}"
            f"（{_chg(a['客单价'], b['客单价'])}），商家优惠 {_y(disc(cur))}，占原价 {_pct(disc(cur), gross(cur))}，退款率 {a['退款率']}。")
    if roi is not None:
        text += f"\n每 1 元优惠多带来 {roi:.1f} 元销售额（按与之前的差额算，粗略）。"
    return text, {"对比": rows, "每天": days, "商品": goods}


def bundle(lines, skus, now, opts):
    baskets: Dict[str, set] = defaultdict(set)
    for l in lines:
        baskets[f"o:{l['order_id']}"].add(l["product_id"])
        if l["buyer"] and l["time"]:
            baskets[f"b:{l['buyer']}:{l['time']:%Y%m%d}"].add(l["product_id"])
    multi = [b for b in baskets.values() if len(b) > 1]
    names = {l["product_id"]: l["title"] for l in lines}
    single = Counter(p for b in multi for p in b)
    pairs = Counter()
    for b in multi:
        items = sorted(b)
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                pairs[(items[i], items[j])] += 1
    rows = [{"商品A": names.get(x, x)[:30], "商品B": names.get(y, y)[:30], "一起买的次数": n,
             "买A的也买B": _pct(n, single[x]), "买B的也买A": _pct(n, single[y])} for (x, y), n in pairs.most_common(30)]
    if not rows:
        why = ("这个平台的订单一单一个商品，买家也看不到是谁（拼多多），所以算不出连带。"
               if not any(l["buyer"] for l in lines) else "这段时间没有一起买的记录。")
        units = [l["qty"] for l in lines]
        multi_qty = sum(1 for q in units if q > 1)
        return (f"{opts['days']} 天 {_orders(lines)} 单里没有找到一起买的商品：{why}"
                f"\n一单多件的有 {multi_qty} 单（{_pct(multi_qty, len(units))}），可以考虑第二件优惠/多件折。"), {}
    text = f"{opts['days']} 天里一起买的组合 {len(pairs)} 种，最常见："
    for r in rows[:5]:
        text += f"\n- {r['商品A'][:14]} + {r['商品B'][:14]}：{r['一起买的次数']} 次（买A的有{r['买A的也买B']}也买B）"
    return text, {"搭配": rows}


def repeat(lines, skus, now, opts):
    keyed = [l for l in lines if l["buyer"]]
    if not keyed:
        return ("这个平台的订单里看不到买家是谁（昵称已打码），复购只能在平台自己的客户数据里看；"
                f"本店 {opts['days']} 天 {_orders(lines)} 单。"), {}
    by_buyer: Dict[str, List[dict]] = defaultdict(list)
    for l in keyed:
        by_buyer[l["buyer"]].append(l)
    half = now - dt.timedelta(days=opts["days"] / 2)
    rep = {b: ls for b, ls in by_buyer.items() if _orders(ls) >= 2}
    lapsed = [b for b, ls in by_buyer.items() if all(l["time"] and l["time"] < half for l in ls) and _orders(ls) >= 2]
    rebuy = Counter(l["product_id"] for ls in rep.values() for l in ls)
    names = {l["product_id"]: l["title"] for l in lines}
    rows = [{"商品": names.get(p, p)[:40], "老客买的件次": n} for p, n in rebuy.most_common(20)]
    text = (f"{opts['days']} 天买家 {len(by_buyer)} 个，买过 2 次及以上 {len(rep)} 个（复购率 {_pct(len(rep), len(by_buyer))}），"
            f"老客贡献销售额 {_pct(sum(_gmv(ls) for ls in rep.values()), _gmv(keyed))}；"
            f"前半段买过多次、后半段没再来的 {len(lapsed)} 个。")
    for r in rows[:5]:
        text += f"\n- 老客常买：{r['商品'][:20]}（{r['老客买的件次']}）"
    return text, {"老客常买": rows}


_BANDS = [0, 20, 50, 100, 200, 500, 1000, 10 ** 9]


def buyer_profile(lines, skus, now, opts):
    per_order: Dict[str, float] = defaultdict(float)
    for l in lines:
        per_order[l["order_id"]] += l["paid"]
    band = Counter()
    for v in per_order.values():
        i = next(i for i in range(len(_BANDS) - 1) if v < _BANDS[i + 1])
        band[f"{_BANDS[i]}-{_BANDS[i + 1]}" if _BANDS[i + 1] < 10 ** 9 else f"{_BANDS[i]}以上"] += 1
    hours = Counter(l["time"].hour for l in lines if l["time"])
    week = Counter("一二三四五六日"[l["time"].weekday()] for l in lines if l["time"])
    specs = Counter(p.strip() for l in lines for p in re.split(r"[,;，；]", l["spec"]) if p.strip())
    qty = Counter(min(l["qty"], 5) for l in lines)
    n = len(per_order) or 1
    text = (f"{opts['days']} 天 {len(per_order)} 单：客单价主要在 {band.most_common(1)[0][0] if band else '-'} 元；"
            f"下单最多的时段 {', '.join(f'{h}点' for h, _ in hours.most_common(3))}；"
            f"星期{''.join(d for d, _ in week.most_common(2))}最多；"
            f"热门规格 {', '.join(s for s, _ in specs.most_common(5))}；一单多件占 {_pct(sum(v for k, v in qty.items() if k > 1), n)}。")
    if not any(l["buyer"] for l in lines):
        text += "\n（平台不给买家身份，分不出新客/老客，这里是全部订单的画像）"
    return text, {"价格带": [{"实付(元)": k, "订单": v} for k, v in sorted(band.items(), key=lambda kv: int(re.match(r"\d+", kv[0]).group()))],
                  "时段": [{"小时": h, "件次": hours[h]} for h in range(24)],
                  "星期": [{"星期": d, "件次": week[d]} for d in "一二三四五六日"],
                  "规格": [{"规格": s, "件次": c} for s, c in specs.most_common(50)],
                  "件数": [{"一单件数": f"{k}{'+' if k == 5 else ''}", "单数": v} for k, v in sorted(qty.items())]}


def tool_effect(lines, skus, now, opts):
    with_d = [l for l in lines if l["merchant_discount"] > 0]
    without = [l for l in lines if l["merchant_discount"] <= 0]
    a, b = _summ(with_d), _summ(without)
    upo = lambda ls: round(_units(ls) / _orders(ls), 2) if _orders(ls) else 0
    cost = round(sum(l["merchant_discount"] for l in lines), 2)
    rows = [{"指标": k, "用了商家优惠": a[k], "没用": b[k]} for k in a]
    rows.append({"指标": "每单件数(连带)", "用了商家优惠": upo(with_d), "没用": upo(without)})
    goods = []
    for pid, ls in sorted(_by_product(lines).items(), key=lambda kv: -_gmv(kv[1])):
        d = [l for l in ls if l["merchant_discount"] > 0]
        goods.append({"商品": _title(ls), "订单": _orders(ls), "用优惠的订单": _orders(d),
                      "优惠金额": round(sum(l["merchant_discount"] for l in ls), 2),
                      "平均优惠力度": _pct(sum(l["merchant_discount"] for l in d), sum(l["amount"] for l in d))})
    text = (f"{opts['days']} 天 {_orders(lines)} 单里用了商家优惠的 {a['订单']} 单（{_pct(a['订单'], _orders(lines))}），"
            f"优惠共 {_y(cost)} 元，占销售额 {_pct(cost, _gmv(lines))}；"
            f"用优惠的客单价 {a['客单价']}，没用的 {b['客单价']}；每单件数 {upo(with_d)} vs {upo(without)}。"
            "\n（平台不分是哪张券/哪个活动，这里按订单上的“商家优惠”合计）")
    return text, {"对比": rows, "商品": goods}


REPORTS: Dict[str, Callable] = {"goods_health": goods_health, "sabc": sabc, "daily_patrol": daily_patrol,
                                "weekly_goods": weekly_goods, "promo_review": promo_review, "bundle": bundle,
                                "repeat": repeat, "buyer_profile": buyer_profile, "tool_effect": tool_effect}
NEEDS_SKUS = {"goods_health", "sabc", "daily_patrol"}


def write_xlsx(sheets: Dict[str, list], path: str) -> str:
    import openpyxl
    os.makedirs(os.path.dirname(path), exist_ok=True)
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name[:30])
        if rows:
            cols = list(rows[0].keys())
            ws.append(cols)
            for r in rows:
                ws.append([r.get(c, "") for c in cols])
    wb.save(path)
    return path


def run_for_store(report: str, store_id: str, folder: str, platform: str = "", **opts) -> Dict[str, Any]:
    """Read the store's own data, compute *report*, write the Excel, return a summary."""
    if report not in REPORTS:
        raise ValueError(f"unknown report {report!r}; one of {', '.join(REPORTS)}")
    platform = platform or platform_of_store(store_id)
    if not platform:
        raise ValueError(f"看不出店铺 {store_id!r} 是哪个平台")
    days = int(opts.get("days") or DAYS.get(report, 30))
    if report == "promo_review" and opts.get("start"):
        start = _parse_day(opts["start"])
        if start:
            days = max(days, (china_now() - start).days * 2 + 2)
    opts = dict(opts, days=days, platform=platform)
    from agent.ec_skills.store_orders import read_orders
    data = read_orders(platform, store_id, days)
    errors = list(data["errors"])
    skus: List[Dict[str, Any]] = []
    if report in NEEDS_SKUS:
        try:
            from agent.ec_skills.store_prices import read_store_skus
            skus = [s for s in read_store_skus(platform, store_id=store_id)[0]
                    if not s.get("store_id") or not store_id or s.get("store_id") == store_id]
        except Exception as exc:
            errors.append(f"商品和库存没读到：{exc}")
    if report == "daily_patrol":
        try:
            from agent.ec_skills import promo_deadlines as pd
            promos = pd.read_store_promos(platform, store_id)["promos"]
            opts["promos_due"] = pd.due([p for p in promos if p["end"] is None or p["end"] > china_now()])
            opts["promos_due"] = [p for p in opts["promos_due"] if p.get("end")]
        except Exception as exc:
            errors.append(f"营销没读到：{exc}")
    now = china_now()
    lines = [l for l in data["orders"] if not l.get("cancelled")]
    cancelled = _orders([l for l in data["orders"] if l.get("cancelled")])
    text, sheets = REPORTS[report](lines, skus, now, opts)
    deep = _orders([l for l in lines if l["amount"] and l["paid"] < l["amount"] * 0.3])
    if deep and report in ("buyer_profile", "tool_effect", "promo_review", "sabc"):
        text += (f"\n注意：有 {deep} 单实付不到原价的3成（多半是平台活动或特殊订单），"
                 "客单价和优惠力度会被拉低，请对照平台的活动记录看。")
    if cancelled:
        text += f"\n（已取消/关闭的 {cancelled} 单不算在内）"
    name = NAMES[report]
    head = f"{name}（{store_id or platform}）：" if lines or report == "daily_patrol" else f"{name}（{store_id or platform}）：{days} 天内没有成交订单。"
    summary = head + ("\n" if lines or report == "daily_patrol" else "") + (text if lines or report in ("goods_health", "daily_patrol") else "")
    path = ""
    if any(sheets.values()):
        path = write_xlsx(sheets, os.path.join(folder, "结果", now.strftime(f"{name}_%Y%m%d_%H%M.xlsx")))
    if errors:
        summary += "\n没读全：" + "；".join(errors[:3])
        logger.warning(f"[store-reports] {report} {store_id}: {errors}")
    logger.info(f"[store-reports] {report} {store_id} orders={len(data['orders'])} skus={len(skus)} path={bool(path)}")
    return {"summary": summary, "path": path, "orders": len(data["orders"]), "errors": errors}
