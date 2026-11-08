from agent.ec_skills import price_check as pc

SKUS = [
    {"product_id": "101", "code": "A1", "title": "睡衣", "sku_code": "A1-RED-M", "spec": {"颜色": "红色", "尺码": "M"}, "price": 100},
    {"product_id": "101", "code": "A1", "title": "睡衣", "sku_code": "A1-RED-L", "spec": {"颜色": "红色", "尺码": "L"}, "price": 120},
    {"product_id": "202", "code": "B2", "title": "拖鞋", "sku_code": "", "spec": {"颜色": "灰色"}, "price": 30},
]


def _xlsx(tmp_path, rows):
    import openpyxl
    wb = openpyxl.Workbook()
    for r in rows:
        wb.active.append(r)
    p = str(tmp_path / "价格表.xlsx")
    wb.save(p)
    return p


def test_reads_a_merchants_own_headers_below_a_title_row(tmp_path):
    p = _xlsx(tmp_path, [["双11控价表"], ["货号", "商品名称", "规格", "建议零售价", "最低价"],
                         ["A1", "睡衣", "红色/M", "¥100", 80], ["B2", "拖鞋", None, 30, None], [None, None, None, None, None]])
    rows = pc.read_table(p)
    assert rows == [{"code": "A1", "title": "睡衣", "spec": "红色/M", "target": 100.0, "floor": 80.0},
                    {"code": "B2", "title": "拖鞋", "target": 30.0, "floor": None}]


def test_reads_csv_in_gbk(tmp_path):
    p = tmp_path / "t.csv"
    p.write_bytes("商家编码,售价\nA1-RED-L,120\n".encode("gb18030"))
    assert pc.read_table(str(p)) == [{"sku_code": "A1-RED-L", "target": 120.0, "floor": None}]


def test_best_coupon_uses_reachable_store_or_own_product_coupons_only():
    coupons = [{"threshold": 99, "amount": 10}, {"threshold": 200, "amount": 50},
               {"product_id": "101", "threshold": 0, "amount": 15}, {"product_id": "999", "amount": 40}]
    assert pc.best_coupon(100, "101", coupons) == 15
    assert pc.best_coupon(100, "202", coupons) == 10
    assert pc.best_coupon(30, "202", coupons) == 0


def test_sku_row_wins_over_its_products_row_and_flags_gaps():
    table = [{"code": "A1", "target": 100.0, "floor": None},
             {"sku_code": "A1-RED-L", "target": 150.0, "floor": 110.0},
             {"code": "B2", "target": 30.0, "floor": None},
             {"code": "ZZ", "target": 9.0, "floor": None}]
    res = {(r.get("SKU编码") or r["表格编码"]): r for r in pc.check(table, SKUS, [{"threshold": 100, "amount": 10}])}
    assert res["A1-RED-L"]["券后价"] == 110 and res["A1-RED-L"]["结果"] == "偏低"   # 110 vs 150, floor 110 kept
    assert res["A1-RED-M"]["券后价"] == 90 and res["A1-RED-M"]["结果"] == "正常"    # -10.0% is inside the tolerance
    assert res["B2"]["结果"] == "正常"
    assert res["ZZ"]["结果"] == "店铺里没找到"


def test_below_floor_and_spec_rows():
    table = [{"code": "A1", "spec": "红色 M", "target": 100.0, "floor": 95.0}]
    out = pc.check(table, SKUS, [{"product_id": "101", "threshold": 0, "amount": 10}])
    assert len(out) == 1 and out[0]["SKU编码"] == "A1-RED-M" and out[0]["结果"] == "低于底价"
    assert "低于底价" in pc.summary(out, "小店一号")


def test_excel_is_written(tmp_path):
    out = pc.check([{"code": "B2", "target": 20.0, "floor": None}], SKUS, [])
    p = pc.write_xlsx(out, str(tmp_path / "r" / "价格核验.xlsx"))
    import openpyxl
    ws = openpyxl.load_workbook(p).active
    assert [c.value for c in ws[1]][:2] == ["结果", "表格编码"] and ws[2][0].value == "偏高"


def test_pdd_coupons_keep_goods_ids_only_for_goods_coupons():
    from agent.ec_skills.store_prices import pdd_coupons
    out = pdd_coupons({"mallCoupons": [{"discount": 500, "minAmount": 9900, "goodsId": 1}],
                       "goodsCoupons": [{"discount": 300, "goodsId": 42}, {"discount": 0}]})
    assert out == [{"product_id": "", "threshold": 99.0, "amount": 5.0, "name": ""},
                   {"product_id": "42", "threshold": 0, "amount": 3.0, "name": ""}]


def test_run_for_store_uses_the_newest_table_and_this_stores_skus(tmp_path, monkeypatch):
    import os, time
    from agent.ec_skills import store_prices
    old = _xlsx(tmp_path, [["货号", "售价"], ["B2", 999]])
    os.utime(old, (time.time() - 100, time.time() - 100))
    import openpyxl
    wb = openpyxl.Workbook(); wb.active.append(["货号", "售价"]); wb.active.append(["B2", 30])
    wb.save(str(tmp_path / "新价格表.xlsx"))
    other = dict(SKUS[2], store_id="s2", price=1)
    monkeypatch.setattr(store_prices, "read_store_skus",
                        lambda platform, store_id="": ([dict(SKUS[2], store_id="s1"), other], [{"store_id": "s2", "amount": 20}]))
    out = pc.run_for_store("s1", "pdd", str(tmp_path))
    assert out["table"] == "新价格表.xlsx" and out["skus"] == 1 and out["counts"] == {"正常": 1}
    assert os.path.isfile(out["path"]) and "结果" in out["path"]


def test_no_price_table_yet_is_not_a_failure(tmp_path):
    out = pc.run_for_store("s1", "pdd", str(tmp_path))
    assert out["path"] == "" and "还没有价格表" in out["summary"]


def test_a_taobao_sku_matches_by_item_id_and_its_spec_values():
    from agent.ec_skills import price_check, store_prices
    s = store_prices.tmall_sku({"product_id": "700000000001", "title": "睡衣", "sku_id": "600000000001",
                                "prop": "深蓝色/XS", "price": "398.00"}, "tmall-小店三号")
    assert s["spec"] == {"规格1": "深蓝色", "规格2": "XS"} and s["price"] == 398.0 and s["platform"] == "tmall"
    assert price_check.match({"product_id": "700000000001", "spec": "深蓝色 XS"}, [s]) == [s]
    assert price_check.match({"product_id": "700000000001", "spec": "红色/XS"}, [s]) == []
