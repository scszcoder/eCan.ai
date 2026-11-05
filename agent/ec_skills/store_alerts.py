"""异常订单 and 售后巡检: what needs doing today, from the platform's own to-do counts
(store_orders.read_counts) and the store's own order lines. Read only: nothing is shipped,
refunded or answered; each item says where in the back office to act.

  order_alerts  异常订单  orders past or near their ship-by time, orders the buyer asked to hurry,
                          unshipped orders with a buyer note, deeply discounted orders
  after_sales   售后巡检  after-sales waiting for the shop (and those due within 24 h), returns to
                          receive, disputes needing evidence; refund rate per product over N days
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Any, Dict, List, Tuple

SOON_H = 12
# platform count key -> (label, urgent, what to do)
ORDER_COUNTS = {"douyin": {"ship_delay": ("已超时未发货", True, "马上发货，超时会被罚/影响体验分"),
                           "exp_ship": ("快超时未发货", True, "今天内发货"),
                           "ship_and_logistics_delay": ("发货/揽收超时", True, "催快递揽收或换快递"),
                           "stock_up": ("待发货", False, "按时发货"),
                           "in_aftersale": ("售后中的订单", False, "看售后巡检")}}
AFTER_COUNTS = {
    "pdd": {"expireIn24HoursWaitHandle": ("24小时内到期、要处理的售后", True, "今天处理，超时平台会自动退款"),
            "expireIn24HoursWaitSellerProof": ("24小时内到期、要举证的", True, "今天上传凭证"),
            "waitSellerHandle": ("等商家处理的售后", True, "售后工作台处理"),
            "waitSellerProof": ("等商家举证的", True, "上传凭证"),
            "returnedWaitHandle": ("买家已退货、等收货处理", True, "验货后退款或拒绝"),
            "remindRefund": ("买家催退款", True, "尽快处理"),
            "complainWarning": ("投诉预警", True, "联系买家，先沟通"),
            "expireIn24HoursWaitMerchantHelpReturn": ("24小时内到期、要协助退货的", True, "今天处理"),
            "waitMerchantHelpReturn": ("要协助退货的", False, "处理"),
            "platformHandling": ("平台介入中", False, "关注结果"),
            "waitBuyerHandle": ("等买家操作", False, "不用管"),
            "refundedByPlatformLast24Hours": ("24小时内被平台直接退款", False, "看是不是超时没处理")},
    "douyin": {"approaching_deadline_audit": ("快超时的售后", True, "今天审核，超时会自动同意"),
               "audit_ddl_in_one_day": ("一天内到期的售后", True, "今天审核"),
               "all_audit": ("待审核的售后", True, "售后工作台审核"),
               "refund_audit": ("仅退款待审核", False, ""), "return_audit": ("退货待审核", False, ""),
               "exchange_audit": ("换货待审核", False, ""),
               "return_receive": ("退货待收货确认", True, "验货后确认收货/退款"),
               "arbitrate_shop_evidence": ("平台仲裁、等商家举证", True, "上传凭证"),
               "arbitrate_pending": ("平台仲裁中", False, "关注结果"),
               "urge_audit": ("买家催审核", True, "尽快审核"),
               "logistics_abnormal": ("退货物流异常", True, "查物流"),
               "suspected_violation": ("疑似违规", True, "看平台提示")}}


def _when(t) -> str:
    return t.strftime("%m-%d %H:%M") if t else ""


def _num(v: Any) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def count_rows(counts: Dict[str, Any], table: Dict[str, Tuple[str, bool, str]]) -> List[Dict[str, Any]]:
    return [{"事项": label, "数量": _num(counts[k]), "要紧": "是" if urgent else "", "怎么办": todo}
            for k, (label, urgent, todo) in table.items() if _num(counts.get(k))]


def order_alerts(lines, skus, now, opts) -> Tuple[str, Dict[str, list]]:
    platform = opts.get("platform", "")
    counts = (opts.get("counts") or {}).get("orders") or {}
    crows = count_rows(counts, ORDER_COUNTS.get(platform, {}))
    soon = now + dt.timedelta(hours=SOON_H)
    rows: Dict[str, Dict[str, Any]] = {}
    for l in lines:
        if l.get("refund"):
            continue
        tags = []
        unshipped = not l.get("shipped")
        if unshipped and l.get("ship_by"):
            if l["ship_by"] <= now:
                tags.append("已超时未发货")
            elif l["ship_by"] <= soon:
                tags.append(f"{SOON_H}小时内要发货")
        if unshipped and l.get("urged"):
            tags.append("买家催发货")
        if unshipped and l.get("memo") and l.get("ship_by"):
            tags.append("有买家留言，发货前看一下")
        if l["amount"] and l["paid"] < l["amount"] * 0.3:
            tags.append("实付不到原价3成")
        if not tags:
            continue
        r = rows.setdefault(l["order_id"], {"订单号": l["order_id"], "下单": _when(l["time"]), "最晚发货": _when(l.get("ship_by")),
                                            "商品": l["title"][:40], "规格": l["spec"], "实付": l["paid"], "问题": []})
        r["问题"] += [t for t in tags if t not in r["问题"]]
    order_rows = sorted(rows.values(), key=lambda r: (r["最晚发货"] or "99"))
    for r in order_rows:
        r["问题"] = "、".join(r["问题"])
    late = sum(1 for r in order_rows if "已超时" in r["问题"])
    near = sum(1 for r in order_rows if "小时内要发货" in r["问题"])
    head = [f"{r['事项']} {r['数量']}" for r in crows if r["要紧"]]
    if not head and (late or near):
        head = [f"已超时未发货 {late}", f"{SOON_H}小时内要发货 {near}"]
    text = ("要紧：" + "，".join(head) + "。") if head else "没有超时或快超时的订单。"
    for r in [r for r in order_rows if "发货" in r["问题"]][:5]:
        text += f"\n- {r['订单号'][-6:]} {r['商品'][:16]} 最晚 {r['最晚发货']}：{r['问题']}"
    deep = sum(1 for r in order_rows if "3成" in r["问题"])
    if deep:
        text += f"\n另有 {deep} 单实付不到原价3成，看是不是活动价设错了。"
    if not counts and platform != "pdd":
        text += "\n（这个平台没读到平台自己的待发货统计）"
    return text, {"待办": crows, "订单": order_rows}


def after_sales(lines, skus, now, opts) -> Tuple[str, Dict[str, list]]:
    platform = opts.get("platform", "")
    counts = (opts.get("counts") or {}).get("after_sales") or {}
    crows = count_rows(counts, AFTER_COUNTS.get(platform, {}))
    by: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for l in lines:
        by[l["product_id"] or l["title"]].append(l)
    goods = []
    for pid, ls in by.items():
        orders = {l["order_id"] for l in ls}
        ref = {l["order_id"] for l in ls if l["refund"]}
        if ref:
            goods.append({"商品ID": pid, "商品": ls[0]["title"][:40], "订单": len(orders), "有售后的订单": len(ref),
                          "售后率": f"{len(ref) * 100 // len(orders)}%",
                          "售后多的规格": "、".join(sorted({l["spec"] for l in ls if l["refund"] and l["spec"]})[:3])})
    goods.sort(key=lambda g: (-g["有售后的订单"], g["商品"]))
    urgent = [r for r in crows if r["要紧"]]
    text = ("要处理：" + "，".join(f"{r['事项']} {r['数量']}" for r in urgent) + "。") if urgent else "现在没有要商家处理的售后。"
    for r in urgent[:4]:
        if r["怎么办"]:
            text += f"\n- {r['事项']}：{r['怎么办']}"
    all_orders = len({l["order_id"] for l in lines})
    refunded = len({l["order_id"] for l in lines if l["refund"]})
    text += f"\n{opts['days']} 天 {all_orders} 单里有售后的 {refunded} 单（{refunded * 100 // max(1, all_orders)}%）。"
    for g in [g for g in goods if g["订单"] >= 3][:3]:
        text += f"\n- 售后多：{g['商品'][:18]} {g['有售后的订单']}/{g['订单']} 单（{g['售后率']}）"
    if not counts:
        text += "\n（没读到平台的售后待办数）" if platform in AFTER_COUNTS else "\n（这个平台的售后待办数还没接上）"
    text += "\n不会替你同意或拒绝售后：请在店铺后台的售后工作台处理。"
    return text, {"待办": crows, "商品售后率": goods}
