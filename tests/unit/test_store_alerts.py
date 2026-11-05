import datetime as dt

from agent.ec_skills import store_alerts as sa

NOW = dt.datetime(2026, 11, 4, 10, 0)


def _line(oid, ship_by=None, shipped=None, urged=False, memo=False, refund="", paid=100.0, pid="1", spec="红色"):
    return {"order_id": oid, "time": NOW - dt.timedelta(days=1), "status": "待发货", "product_id": pid, "title": "睡衣",
            "spec": spec, "qty": 1, "amount": 100.0, "paid": paid, "refund": refund, "ship_by": ship_by,
            "shipped": shipped, "urged": urged, "memo": memo}


def test_order_alerts_flag_late_near_hurried_and_cheap_orders():
    lines = [_line("a", ship_by=NOW - dt.timedelta(hours=1)), _line("b", ship_by=NOW + dt.timedelta(hours=3), memo=True),
             _line("c", ship_by=NOW + dt.timedelta(days=2), urged=True), _line("d", ship_by=NOW - dt.timedelta(hours=1),
                                                                             shipped=NOW), _line("e", paid=10)]
    text, sheets = sa.order_alerts(lines, [], NOW, {"platform": "pdd", "days": 15})
    got = {r["订单号"]: r["问题"] for r in sheets["订单"]}
    assert got == {"a": "已超时未发货", "b": "12小时内要发货、有买家留言，发货前看一下", "c": "买家催发货", "e": "实付不到原价3成"}
    assert "已超时未发货 1，12小时内要发货 1" in text and "1 单实付不到原价3成" in text


def test_douyin_order_counts_come_from_the_platform():
    counts = {"orders": {"ship_delay": 2, "exp_ship": 0, "stock_up": 5}}
    text, sheets = sa.order_alerts([], [], NOW, {"platform": "douyin", "counts": counts})
    assert text.startswith("要紧：已超时未发货 2。") and [r["事项"] for r in sheets["待办"]] == ["已超时未发货", "待发货"]


def test_after_sales_lists_what_waits_for_the_shop_and_refund_rate_per_product():
    counts = {"after_sales": {"expireIn24HoursWaitHandle": 1, "waitSellerHandle": 3, "waitBuyerHandle": 2}}
    lines = [_line(f"o{i}", refund="退款中" if i < 2 else "", spec="蓝色" if i == 0 else "红色") for i in range(4)]
    text, sheets = sa.after_sales(lines, [], NOW, {"platform": "pdd", "days": 30, "counts": counts})
    assert "要处理：24小时内到期、要处理的售后 1，等商家处理的售后 3。" in text and "等买家操作" not in text
    assert sheets["商品售后率"][0]["售后率"] == "50%" and sheets["商品售后率"][0]["售后多的规格"] == "红色、蓝色"
    assert "4 单里有售后的 2 单" in text and "不会替你同意" in text
