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


def test_a_stale_or_other_stores_plan_is_not_run(tmp_path, monkeypatch):
    folder = str(tmp_path)
    monkeypatch.setattr(sw, "china_now", lambda: dt.datetime(2026, 11, 4, 10, 0))
    _table(folder, [["ECAN测试券", "立减", None, 5, "2026-11-05", "2026-11-06", None, None]])
    sw.propose("coupon", "douyin", "s1", folder)
    assert sw.load_plan(folder, "coupon", "s2")[0] is None
    monkeypatch.setattr(sw, "china_now", lambda: dt.datetime(2026, 11, 5, 11, 0))
    plan, why = sw.load_plan(folder, "coupon", "s1")
    assert plan is None and "超过" in why
