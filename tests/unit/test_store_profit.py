import datetime as dt

import openpyxl

from agent.ec_skills import store_profit as sp

NOW = dt.datetime(2026, 11, 4, 10, 0)


def _line(oid, pid="1", qty=1, paid=100.0, spec="红色,M", sku_code="", refund=""):
    return {"order_id": oid, "time": NOW - dt.timedelta(days=1), "status": "已收货", "cancelled": False,
            "product_id": pid, "title": "睡衣", "spec": spec, "sku_code": sku_code, "code": "", "qty": qty,
            "amount": paid, "paid": paid, "merchant_discount": 0.0, "platform_discount": 0.0, "refund": refund,
            "buyer": ""}


def test_cost_table_is_read_loosely_and_matched_by_code_then_product_and_spec(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["我的成本"])
    ws.append(["商品ID", "规格", "进价", "包装费", "运费"])
    ws.append(["1", "红色", 30, 2, 5])
    ws.append(["1", "", 40, 0, None])
    ws.append(["", "", 10, 0, None])        # no key: skipped
    path = tmp_path / "成本表.xlsx"
    wb.save(path)
    assert sp.find_table(str(tmp_path)) == str(path)
    costs = sp.read_costs(str(path))
    assert len(costs) == 2 and costs[0]["cost"] == 30 and costs[0]["pack"] == 2 and costs[0]["ship"] == 5
    assert sp.cost_of(_line("a", spec="红色,M"), costs)["cost"] == 30
    assert sp.cost_of(_line("a", spec="蓝色,M"), costs)["cost"] == 40
    assert sp.cost_of(_line("a", pid="2"), costs) is None
    assert sp.cost_of(_line("a", pid="2", sku_code="X1"), [{"sku_code": "x1", "cost": 7, "pack": 0}])["cost"] == 7


def test_profit_takes_off_cost_fee_and_shipping_and_leaves_refunds_and_unknown_skus_out():
    costs = [{"product_id": "1", "cost": 30.0, "pack": 0.0, "ship": None}]
    lines = [_line("a", qty=2, paid=100), _line("a", qty=1, paid=50, spec="蓝色,L"),   # one order, 2 lines
             _line("b", paid=100, refund="退款中"), _line("c", pid="9", paid=80)]
    text, sheets = sp.profit(lines, [], NOW, {"days": 30, "costs": costs, "fee_rate": 5, "ship_cost": 6})
    # 150 - 3*30 - 7.5 fee - 6 ship = 46.5
    assert round(sum(r["利润"] for r in sheets["按规格"]), 2) == 46.5
    assert sheets["按商品"][0]["利润"] == 46.5 and sheets["按天"][0]["销售额"] == 150
    assert sheets["没成本"][0]["商品ID"] == "9" and "1 个规格在成本表里没找到" in text
    assert "售后/退款的 1 单" in text and "fee_rate" not in text


def test_no_cost_table_says_where_to_put_it():
    text, sheets = sp.profit([_line("a")], [], NOW, {"days": 30, "folder": "D:/ks/reports/店"})
    assert "还没有成本表" in text and "D:/ks/reports/店" in text and sheets == {}
