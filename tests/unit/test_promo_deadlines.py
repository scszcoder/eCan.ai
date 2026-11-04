import datetime as dt

from agent.ec_skills import promo_deadlines as pd

NOW = dt.datetime(2026, 11, 18, 12, 0)
# a 抖店 coupon as /marketing/coupons/v1/list returns it (KEN 11-04): fen, unix seconds
COUPON = {"coupon_meta_id": "769", "coupon_name": "全店优惠券", "start_time": 1792512000, "expire_time": 1795190399,
          "credit": 1000, "threshold": 0, "status": 3, "goods_count": 0,
          "renew_result": {"renew_switch_on": True, "activity_renew_status": 1}}


def test_a_douyin_coupon_reads_in_china_time_with_its_offer_and_renewal():
    p = pd.normalize("coupon", COUPON)
    assert p["end"] == dt.datetime(2026, 11, 20, 23, 59, 59)          # 15:59:59Z
    assert (p["kind"], p["detail"], p["goods"], p["auto_renew"]) == ("优惠券", "立减10", "全店", True)
    q = pd.normalize("coupon", dict(COUPON, threshold=5000, renew_result={"renew_switch_on": False}))
    assert q["detail"] == "满50减10" and q["auto_renew"] is False
    # a product coupon also says goods_count 0; support_type 1 marks it (5 = whole store)
    assert pd.normalize("coupon", dict(COUPON, support_type=1))["goods"] == "指定商品"
    assert pd.normalize("coupon", dict(COUPON, support_type=5))["goods"] == "全店"


def test_activities_and_pdd_coupons_use_generic_keys():
    a = pd.normalize("time_buy", {"activity_name": "双11直降", "end_time": "2026-11-19 10:00:00", "activity_id": 5})
    assert (a["kind"], a["name"], a["end"], a["id"]) == ("限时限量购", "双11直降", dt.datetime(2026, 11, 19, 10, 0), "5")
    c = pd.normalize("coupon", {"batchName": "店铺券", "batchEndTime": 1795190399000, "discount": 300, "minAmount": 9900})
    assert c["end"] == dt.datetime(2026, 11, 20, 23, 59, 59) and c["detail"] == "满99减3"


def test_a_pdd_activity_row_names_its_product_and_discount_range():
    # one row of /libra-backend/mms/activity/marketing/query (KEN 11-04, trimmed)
    row = {"activity_id": 90000000000001, "activity_name": "全站营销TEST", "activity_type": 3,
           "goods_id": 800000000001, "goods_name": "测试款珊瑚绒加厚保暖家居服套装男士冬季款",
           "start_time": 1792851893, "end_time": 1795190399, "status": 2,
           "price_info": [{"discount": 0, "discount_range": "3.6-5.2", "pattern": 11}]}
    p = pd.normalize("time_buy", row)
    assert (p["kind"], p["name"], p["detail"], p["status"], p["id"]) == ("限时限量购", "全站营销TEST", "3.6-5.2折", 2, "90000000000001")
    assert p["end"] == dt.datetime(2026, 11, 20, 23, 59, 59) and p["goods"].startswith("测试款珊瑚绒")
    text = pd.summary(pd.due([p], 3, NOW), 1, "小店二号", 3, [])
    assert "「全站营销TEST」（测试款珊瑚绒加厚保暖家居服套装男）3.6-5.2折" in text


def test_due_keeps_live_promos_ending_inside_the_window_and_ones_without_an_end():
    soon = pd.normalize("coupon", COUPON)                                   # 2.5 days left
    later = dict(soon, name="later", end=NOW + dt.timedelta(days=10))
    ended = dict(soon, name="ended", end=NOW - dt.timedelta(hours=1))
    blind = pd.normalize("flash", {"title": "限时折扣A"})
    rows = pd.due([later, soon, ended, blind], 3, NOW)
    assert [r["name"] for r in rows] == ["限时折扣A", "全店优惠券"]
    assert rows[0]["left"] == "没读到结束时间" and rows[1]["left"] == "2.5天"


def test_summary_and_excel(tmp_path):
    rows = pd.due([pd.normalize("coupon", COUPON)], 3, NOW)
    text = pd.summary(rows, 1, "小店一号", 3, [])
    assert "3 天内到期 1 个（其中 1 个会自动续期）" in text and "11-20 23:59" in text
    assert "没有要到期的" in pd.summary([], 4, "小店一号", 3, ["flash 500 busy"]) and "没读全" in pd.summary([], 4, "s", 3, ["x"])
    import openpyxl
    ws = openpyxl.load_workbook(pd.write_xlsx(rows, str(tmp_path / "r" / "到期.xlsx"))).active
    assert [c.value for c in ws[1]][:3] == ["类型", "名称", "优惠"] and ws[2][4].value == "2026-11-20 23:59"


def test_run_for_store_writes_a_table_only_when_something_is_due(tmp_path, monkeypatch):
    monkeypatch.setattr(pd, "china_now", lambda: NOW)
    monkeypatch.setattr(pd, "read_store_promos", lambda platform, store_id: {"promos": [pd.normalize("coupon", COUPON)], "errors": []})
    out = pd.run_for_store("s1", "douyin", str(tmp_path))
    assert out["due"] == 1 and out["live"] == 1 and "结果" in out["path"]
    out = pd.run_for_store("s1", "douyin", str(tmp_path), days=1)
    assert out["due"] == 0 and out["path"] == ""


def test_taobao_activities_read_with_their_own_kinds():
    # the list columns of the 千牛 营销工具 pages (KEN 11-04, every list empty there)
    a = pd.normalize("tb_shop", {"activityId": 77, "name": "满2件9折", "startTime": "2026-11-18 00:00:00",
                                 "endTime": "2026-11-20 23:59:59", "status": 1})
    assert (a["kind"], a["name"], a["id"], a["end"]) == ("多件优惠", "满2件9折", "77", dt.datetime(2026, 11, 20, 23, 59, 59))
    c = pd.normalize("tb_coupon", {"name": "店铺券", "endTime": 1795190399000, "amount": 5, "startFee": 99})
    assert c["kind"] == "优惠券" and "detail" not in c        # Taobao money units unconfirmed: not guessed
