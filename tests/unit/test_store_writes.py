import datetime as dt
import json
import os

import openpyxl

from agent.ec_skills import store_writes as sw

TODAY = dt.date(2026, 11, 4)


def _table(folder, rows):
    wb = openpyxl.Workbook()
    wb.active.append(["优惠券申请"])
    wb.active.append(["名称", "类型", "门槛", "面额", "开始", "结束", "发放量", "商品ID"])
    for r in rows:
        wb.active.append(r)
    os.makedirs(folder, exist_ok=True)
    p = os.path.join(folder, "申请.xlsx")
    wb.save(p)
    return p


def test_rows_are_checked_before_anything_is_proposed():
    good, bad = sw.check_coupon({"name": "满99减5", "kind": "满减", "threshold": 99, "amount": 5,
                                 "start": "2026-11-05", "end": "2026/11/06", "product_ids": "11, 22"}, TODAY)
    assert not bad and good["scope"] == "商品" and good["product_ids"] == ["11", "22"]
    assert good["start"] == "2026/11/05 00:00:00" and good["end"] == "2026/11/06 23:59:59"
    _, bad = sw.check_coupon({"name": "x", "kind": "满减", "threshold": 5, "amount": 5, "start": "2026-11-01",
                              "end": "2027-12-01"}, TODAY)
    assert "满减的门槛要大于面额" in bad and "开始日期早于今天" in bad
    c, bad = sw.check_coupon({"name": "八折", "discount": "8折", "end": "2026-11-30"}, TODAY)
    assert c["kind"] == "折扣" and c["discount"] == 8 and c["scope"] == "全店" and not bad


def test_propose_writes_a_plan_and_changes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(sw, "china_now", lambda: dt.datetime(2026, 11, 4, 10, 0))
    folder = str(tmp_path)
    _table(folder, [["ECAN测试券", "满减", 99, 5, "2026-11-05", "2026-11-06", 10, "3806636940602769454"],
                    ["坏的", "满减", 5, 9, "2026-11-05", "2026-11-06", None, None]])
    out = sw.propose("coupon", "douyin", "douyin-小店一号", folder)
    assert out["items"] == 1 and "第2行" in out["summary"] and "还没有改店铺" in out["summary"]
    plan = json.load(open(os.path.join(folder, sw.PLAN), encoding="utf-8"))
    assert plan["items"][0]["product_ids"] == ["3806636940602769454"]
    assert sw.propose("coupon", "pdd", "x", folder)["items"] == 0      # no flow for 拼多多 yet


def test_execute_runs_only_a_fresh_plan_once_and_reads_the_store_back(tmp_path, monkeypatch):
    monkeypatch.setattr(sw, "china_now", lambda: dt.datetime(2026, 11, 4, 10, 0))
    folder = str(tmp_path)
    _table(folder, [["ECAN测试券", "满减", 99, 5, "2026-11-05", "2026-11-06", 10, None]])
    sw.propose("coupon", "douyin", "s1", folder)
    from agent.ec_skills.fill import node
    ran = []

    async def fake_run(port, flow, guards, data, roles, paths, mode, cache):
        ran.append((port, mode, data["name"], guards))
        return {"ok": True}
    monkeypatch.setattr(node, "_open_and_run", fake_run)
    monkeypatch.setattr(node, "_port", lambda store_id, seed, profile_id="": 9222)
    monkeypatch.setattr(sw, "verify_coupons", lambda p, s, names: {n: True for n in names})
    flow = {"steps": [], "guards": {"forbid_click": "提交"}}
    out = sw.execute("coupon", "douyin", "s1", folder, flow)
    assert out["done"] == 1 and ran == [(9222, "publish", "ECAN测试券", {"forbid_click": "提交"})]
    assert os.path.isfile(out["path"]) and not os.path.exists(os.path.join(folder, sw.PLAN))
    again = sw.execute("coupon", "douyin", "s1", folder, flow)
    assert again["done"] == 0 and "没有待确认" in again["summary"] and len(ran) == 1


def test_the_read_back_waits_for_the_list_to_catch_up(monkeypatch):
    calls = []
    monkeypatch.setattr(sw.time, "sleep", lambda s: None)
    monkeypatch.setattr(sw, "verify_coupons", lambda p, s, names: (calls.append(1), {n: len(calls) > 1 for n in names})[1])
    assert sw._verify("coupon", "douyin", "s1", [{"name": "A"}]) == {0: "已创建"} and len(calls) == 2


def _sheet(folder, header, rows, name="申请.xlsx"):
    wb = openpyxl.Workbook()
    wb.active.append(header)
    for r in rows:
        wb.active.append(r)
    os.makedirs(folder, exist_ok=True)
    wb.save(os.path.join(folder, name))


def test_price_cut_rows_with_one_name_become_one_activity(tmp_path, monkeypatch):
    monkeypatch.setattr(sw, "china_now", lambda: dt.datetime(2026, 11, 4, 10, 0))
    folder = str(tmp_path)
    _sheet(folder, ["名称", "商品ID", "活动价", "开始", "结束"],
           [["双十一直降", 111, 99, "2026-11-05", "2026-11-12"], ["双十一直降", "222", "¥59.9", "2026-11-05", "2026-11-12"],
            ["双十一直降", 111, 88, "2026-11-05", "2026-11-12"], ["", "abc", 0, "2026-11-01", None]])
    out = sw.propose("price_cut", "douyin", "s1", folder)
    plan = json.load(open(os.path.join(folder, sw.PLAN), encoding="utf-8"))
    assert out["items"] == 1 and plan["items"][0]["items"] == [{"product_id": "111", "price": 99}, {"product_id": "222", "price": 59.9}]
    assert "商品 111 重复" in out["summary"] and "商品ID要是数字" in out["summary"] and "一口价 59.9 元" in out["summary"]


def test_main_pic_needs_the_picture_in_the_folder_and_waits_for_its_time(tmp_path, monkeypatch):
    monkeypatch.setattr(sw, "china_now", lambda: dt.datetime(2026, 11, 4, 10, 0))
    folder = str(tmp_path)
    open(os.path.join(folder, "new.png"), "wb").write(b"x")
    _sheet(folder, ["商品ID", "第几张", "图片", "生效时间"],
           [["3852187119833448857", 1, "new.png", None], ["3852187119833448857", 2, "new.png", "2026/11/06 20:00"],
            ["3852187119833448857", 1, "missing.png", None]])
    out = sw.propose("main_pic", "douyin", "s1", folder)
    assert out["items"] == 2 and "missing.png" in out["summary"] and "2026-11-06 20:00 以后替换" in out["summary"]
    from agent.ec_skills.fill import node
    ran = []

    async def fake_run(port, flow, guards, data, roles, paths, mode, cache):
        ran.append((data["slot"], roles, paths))
        return {"ok": True}
    monkeypatch.setattr(node, "_open_and_run", fake_run)
    monkeypatch.setattr(node, "_port", lambda store_id, seed, profile_id="": 9222)
    first = sw.execute("main_pic", "douyin", "s1", folder, {"steps": []})
    assert [r[0] for r in ran] == [1] and ran[0][1] == {"main_new": ["new.png"]}
    assert ran[0][2]["new.png"] == os.path.join(folder, "new.png") and "还有 1 个没到生效时间" in first["summary"]
    assert "还没到生效时间" in sw.execute("main_pic", "douyin", "s1", folder, {"steps": []})["summary"]
    monkeypatch.setattr(sw, "china_now", lambda: dt.datetime(2026, 11, 6, 20, 5))   # past the 24 h, before its own
    assert sw.execute("main_pic", "douyin", "s1", folder, {"steps": []})["done"] == 1 and [r[0] for r in ran] == [1, 2]


def test_a_stale_or_other_stores_plan_is_not_run(tmp_path, monkeypatch):
    folder = str(tmp_path)
    monkeypatch.setattr(sw, "china_now", lambda: dt.datetime(2026, 11, 4, 10, 0))
    _table(folder, [["ECAN测试券", "立减", None, 5, "2026-11-05", "2026-11-06", None, None]])
    sw.propose("coupon", "douyin", "s1", folder)
    assert sw.load_plan(folder, "coupon", "s2")[0] is None
    monkeypatch.setattr(sw, "china_now", lambda: dt.datetime(2026, 11, 5, 11, 0))
    plan, why = sw.load_plan(folder, "coupon", "s1")
    assert plan is None and "超过" in why


SKUS = [{"product_id": "111", "title": "童装", "sku_id": "1", "spec": {"颜色": "粉", "尺码": "110cm"}, "price": 229.0, "stock": 10},
        {"product_id": "111", "title": "童装", "sku_id": "2", "spec": {"颜色": "蓝", "尺码": "110cm"}, "price": 229.0, "stock": 10}]


def test_goods_edit_resolves_specs_to_skus_and_shows_old_to_new():
    rows = [{"product_id": "111", "sku": "粉/110cm", "price": 199}, {"product_id": "111", "stock": 5},
            {"product_id": "111", "sku": "绿", "price": 1}, {"product_id": "999", "price": 9}, {"product_id": "111"}]
    items, problems = sw._plan_goods_edit(rows, "", TODAY, SKUS)
    assert len(items) == 1 and [(c["sku_id"], c.get("price"), c["stock"]) for c in items[0]["changes"]] == [("1", 199, 5), ("2", None, 5)]
    assert len(problems) == 3 and "没有规格「绿」" in problems[0] and "没有这个商品ID" in problems[1] and "都没填" in problems[2]
    text = sw.describe_goods_edit(items[0])
    assert "粉/110cm 价格 229.0→199，库存 10→5" in text and "蓝/110cm 库存 10→5" in text
    big, _ = sw._plan_goods_edit([{"product_id": "111", "sku": "2", "price": 50}], "", TODAY, SKUS)
    assert "请看清楚" in sw.describe_goods_edit(big[0])


def test_goods_edit_and_shelf_run_through_their_flow_and_read_back(tmp_path, monkeypatch):
    monkeypatch.setattr(sw, "china_now", lambda: dt.datetime(2026, 11, 4, 10, 0))
    from agent.ec_skills import store_prices, store_quality
    from agent.ec_skills.fill import node
    monkeypatch.setattr(store_prices, "read_store_skus", lambda platform, store_id="": (SKUS, []))
    folder = str(tmp_path)
    wb = openpyxl.Workbook()
    wb.active.append(["商品ID", "规格", "价格", "库存"])
    wb.active.append(["111", "", None, 7])
    wb.save(os.path.join(folder, "改库存.xlsx"))
    out = sw.propose("goods_edit", "douyin", "s1", folder)
    assert out["items"] == 1 and "还没有改店铺" in out["summary"]
    sent = []

    async def fake_run(port, flow, guards, data, roles, paths, mode, cache):
        sent.append(data)
        return {"ok": True}
    monkeypatch.setattr(node, "_open_and_run", fake_run)
    monkeypatch.setattr(node, "_port", lambda store_id, seed, profile_id="": 9222)
    after = [dict(s, stock=7) for s in SKUS]
    after[1]["stock"] = 10
    monkeypatch.setattr(store_prices, "read_store_skus", lambda platform, store_id="": (after, []))
    res = sw.execute("goods_edit", "douyin", "s1", folder, {"steps": []})
    assert [c["stock"] for c in sent[0]["changes"]] == [7, 7]
    assert "已保存，蓝/110cm 库存现在是 10" in res["summary"] and os.path.isfile(res["path"])
    shelf = str(tmp_path / "shelf")
    os.makedirs(shelf)
    wb = openpyxl.Workbook()
    wb.active.append(["商品ID", "操作"])
    wb.active.append(["111", "下架"])
    wb.active.append(["222", "删除"])
    wb.save(os.path.join(shelf, "上下架.xlsx"))
    out = sw.propose("shelf", "douyin", "s1", shelf)
    assert out["items"] == 1 and "操作要写 上架 或 下架" in out["summary"] and "重新审核" in out["summary"]
    monkeypatch.setattr(store_quality, "read_status", lambda store_id="": {"111": {"status": "已下架"}})
    res = sw.execute("shelf", "douyin", "s1", shelf, {"steps": []})
    assert "商品 111 下架" in res["summary"] and "：已下架" in res["summary"]
