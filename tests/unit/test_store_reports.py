import datetime as dt

from agent.ec_skills import store_orders as so
from agent.ec_skills import store_reports as sr

NOW = dt.datetime(2026, 11, 4, 10, 0)


def _line(oid, days_ago, pid="1", qty=1, paid=100.0, amount=100.0, disc=0.0, refund="", buyer="", title="睡衣",
          spec="红色,M"):
    return {"order_id": oid, "time": NOW - dt.timedelta(days=days_ago), "status": "已收货", "cancelled": False,
            "product_id": pid, "title": title, "spec": spec, "sku_code": "", "code": "", "qty": qty, "amount": amount,
            "paid": paid, "merchant_discount": disc, "platform_discount": 0.0, "refund": refund, "buyer": buyer}


def test_pdd_rows_map_to_lines_in_yuan_with_list_price_and_no_buyer():
    rows = [{"order_sn": "260000-1", "created_at": 1786430068, "order_status_str": "已收货", "goods_id": 9,
             "goods_name": "睡衣", "goods_price": 13955, "goods_number": 1, "goods_amount": 1396, "order_amount": 1396,
             "spec": "蓝色,L/", "merchant_discount": 0, "after_sales_id": None},
            {"order_sn": "260000-2", "created_at": 1786430068, "order_status_str": "已取消", "goods_id": 9,
             "goods_price": 6990, "goods_number": 1, "order_amount": 5390, "merchant_discount": 1600,
             "after_sales_id": 5, "after_sales_status": 10}]
    a, b = so._mark(so.pdd_lines(rows))
    assert a["amount"] == 139.55 and a["paid"] == 13.96 and a["spec"] == "蓝色,L" and a["buyer"] == ""
    assert a["time"] == dt.datetime(2026, 8, 11, 14, 34, 28) and not a["cancelled"]
    assert b["cancelled"] and b["merchant_discount"] == 16.0 and b["refund"] == "10"


def test_tmall_rows_split_the_paid_amount_over_sub_orders_and_hash_the_buyer():
    rows = [{"id": "1", "createTime": "2026-11-01 12:00:00", "status": "交易成功", "actualFee": "90.00", "buyerId": "777",
             "subOrders": [{"itemInfo": {"id": "11", "title": "A", "skuText": [{"name": "颜色", "value": "红"}]},
                            "priceInfo": {"original": "60", "realTotal": "50"}, "quantity": 1},
                           {"itemInfo": {"id": "12", "title": "B"}, "priceInfo": {"realTotal": "50"}, "quantity": 1}]}]
    a, b = so.tmall_lines(rows)
    assert a["paid"] == 45.0 and b["paid"] == 45.0 and a["merchant_discount"] == 10.0 and a["spec"] == "红"
    assert a["buyer"] and a["buyer"] != "777" and a["buyer"] == b["buyer"]


def test_store_id_names_the_platform():
    assert sr.platform_of_store("pinduoduo-小店二号") == "pdd"
    assert sr.platform_of_store("tmall-小店三号") == "tmall"
    assert sr.platform_of_store("douyin-小店一号") == "douyin"


def test_goods_health_tags_unsold_overstocked_and_running_out():
    lines = [_line(f"o{i}", i % 30, pid="1", qty=2) for i in range(30)]   # 60 units / 30 days = 2 a day
    skus = [{"product_id": "1", "title": "睡衣", "price": 100, "stock": 10, "spec": {}},
            {"product_id": "2", "title": "拖鞋", "price": 30, "stock": 500, "spec": {}},
            {"product_id": "3", "title": "袜子", "price": 9, "stock": 0, "spec": {}}]
    text, sheets = sr.goods_health(lines, skus, NOW, {"days": 30, "platform": "pdd"})
    rows = {r["商品ID"]: r for r in sheets["货盘"]}
    assert rows["1"]["状态"] == "断货风险" and rows["1"]["可售天数"] == 5
    assert rows["2"]["状态"] == "滞销" and rows["3"]["状态"] == "滞销"
    assert "动销率 33%" in text


def test_sabc_tiers_by_cumulative_sales_and_lists_unsold_products_as_c():
    lines = [_line("a", 1, pid="1", paid=600), _line("b", 1, pid="2", paid=300), _line("c", 1, pid="3", paid=100)]
    _, sheets = sr.sabc(lines, [{"product_id": "9", "title": "x"}], NOW, {"days": 30})
    assert [(r["商品ID"], r["层级"]) for r in sheets["分层"]] == [("1", "S"), ("2", "A"), ("3", "C"), ("9", "C")]


def test_weekly_goods_flags_drops_and_refunds():
    lines = [_line(f"p{i}", 9, pid="1") for i in range(10)] + [_line("n1", 2, pid="1")]
    lines += [_line(f"r{i}", 1, pid="2", refund="退款中" if i < 2 else "") for i in range(6)]
    _, sheets = sr.weekly_goods(lines, [], NOW, {"days": 14})
    rows = {r["商品ID"]: r for r in sheets["商品周巡检"]}
    assert "销量下滑" in rows["1"]["提示"] and "退款偏高" in rows["2"]["提示"]


def test_promo_review_compares_the_window_with_the_same_length_before():
    lines = [_line("a", 2, paid=200, disc=20), _line("b", 3, paid=100), _line("c", 5, paid=100), _line("d", 12, paid=999)]
    text, sheets = sr.promo_review(lines, [], NOW, {"start": "2026-11-01", "end": "2026-11-03"})
    first = sheets["对比"][2]
    assert first["指标"] == "销售额" and first["活动期"] == 300 and first["活动前"] == 100
    assert "11-01~11-03" in text and len(sheets["每天"]) == 3


def test_bundle_pairs_from_one_order_or_one_buyer_on_one_day():
    lines = [_line("1", 1, pid="A", title="上衣"), _line("1", 1, pid="B", title="裤子"),
             _line("2", 1, pid="A", title="上衣", buyer="u1"), _line("3", 1, pid="B", title="裤子", buyer="u1")]
    _, sheets = sr.bundle(lines, [], NOW, {"days": 90})
    assert sheets["搭配"][0]["一起买的次数"] == 2


def test_repeat_needs_a_buyer_key():
    text, sheets = sr.repeat([_line("1", 1)], [], NOW, {"days": 90})
    assert "看不到买家" in text and sheets == {}
    lines = [_line("1", 80, buyer="u1"), _line("2", 70, buyer="u1"), _line("3", 5, buyer="u2")]
    text, _ = sr.repeat(lines, [], NOW, {"days": 90})
    assert "复购率 50%" in text and "没再来的 1 个" in text


def test_run_for_store_drops_cancelled_orders_and_writes_the_excel(tmp_path, monkeypatch):
    lines = [_line("1", 1), dict(_line("2", 1), cancelled=True)]
    monkeypatch.setattr(so, "read_orders", lambda p, s, d: {"orders": lines, "errors": []})
    out = sr.run_for_store("tool_effect", "pinduoduo-小店二号", str(tmp_path))
    assert out["path"].endswith(".xlsx") and "1 单不算在内" in out["summary"] and "30 天 1 单" in out["summary"]


def test_pdd_reviews_map_scores_specs_and_reported_reviews():
    rows = [{"id": "1", "goods_id": 9, "goods": "睡衣", "score": 2, "logistics": 3, "service": 4, "comment": "起球",
             "time": 1792929254, "specs": '[{"spec_key":"颜色","spec_value":"蓝"},{"spec_key":"尺码","spec_value":"2XL"}]',
             "pictures": 1, "replied": False, "excluded": True}]
    (r,) = so.pdd_reviews(rows)
    assert r["spec"] == "蓝/2XL" and r["score"] == 2 and r["excluded"] and r["product_id"] == "9"


def test_reviews_report_lists_bad_reviews_and_the_daily_patrol_counts_yesterdays():
    rv = [dict(id="1", product_id="9", title="睡衣", score=1, logistics=5, service=5, comment="起球", spec="蓝/2XL",
               pictures=0, replied=False, excluded=False, time=NOW - dt.timedelta(hours=20)),
          dict(id="2", product_id="9", title="睡衣", score=5, logistics=5, service=5, comment="好", spec="蓝/L",
               pictures=0, replied=False, excluded=False, time=NOW - dt.timedelta(days=3))]
    text, sheets = sr.reviews([], [], NOW, {"days": 30, "reviews": rv})
    assert "差评(1-2星) 1（50%）" in text and "计入考核又没回复的 1 条" in text and sheets["差评"][0]["评价"] == "起球"
    text, _ = sr.daily_patrol([], [], NOW, {"days": 8, "reviews": rv, "unreplied_bad": 3})
    assert "昨天 1 条差评" in text and "3 条差评还没回复" in text
