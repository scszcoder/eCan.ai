"""lookup_order (2026-10-23): after-sales acts only on an order the platform ties
to THIS conversation's buyer; no personal data reaches the model. The store
page is faked -- the request shapes were taken from live 抖店 / 拼多多 pages."""
import asyncio
import json

import pytest

from agent.mcp.server.aftersales import order_lookup as ol

PDD_ORDER = {"orderSn": "231023-123456789012345", "orderStatusStr": "已签收", "goodsName": "珊瑚绒睡衣套装",
             "goodsNumber": 1, "spec": "蓝色 L", "orderAmount": 8900, "confirmTimeStr": "2026-10-20 10:00",
             "receiveName": "张三", "receiveMobile": "13800001111", "address": "上海市某路1号",
             "provinceName": "上海"}


def _run(inp, orders, platform_tabs=1, code=0, success=True):
    calls = []

    async def fake_eval(ws, js):
        calls.append(js)
        if "cmpoent/order/query" in js:
            return {"http": 200, "code": code, "msg": "", "total": len(orders), "orders": orders}
        return {"http": 200, "code": 1000000, "success": success, "total": len(orders), "orders": orders}

    mp = pytest.MonkeyPatch()
    mp.setattr(ol.store_page, "store_tabs", lambda p: [{"profile": f"p{i}", "ws": "ws://x"} for i in range(platform_tabs)])
    mp.setattr(ol.store_page, "evaluate", fake_eval)
    mp.setattr(ol, "_buyer_key", lambda p, c: ("AQ" + "k" * 86) if p == "douyin" and c else c)
    try:
        out = json.loads(asyncio.run(ol.lookup_order(None, {"input": inp}))[0].text)
    finally:
        mp.undo()
    return out, calls


def test_the_buyers_own_order_is_verified_without_personal_data():
    out, calls = _run({"platform": "拼多多", "customer_id": "4486121917", "order_id": "231023-123456789012345"},
                      [PDD_ORDER])
    assert out["verified"] is True
    o = out["order"]
    assert o["orderSn"] == "231023-123456789012345" and o["goodsName"] and o["spec"] == "蓝色 L"
    for pii in ("receiveName", "receiveMobile", "address", "provinceName"):
        assert pii not in o
    assert "张三" not in json.dumps(out, ensure_ascii=False) and "13800001111" not in json.dumps(out)


def test_an_order_number_that_is_not_this_buyers_reveals_nothing():
    out, _ = _run({"platform": "pdd", "customer_id": "4486121917", "order_id": "999999-000000000000001"},
                  [PDD_ORDER])
    assert out["verified"] is False and out["order"] is None
    assert "NOT among this buyer's orders" in out["note"]


def test_without_an_order_number_the_buyers_recent_orders_come_back():
    out, _ = _run({"platform": "douyin", "customer_id": "某买家"},
                  [{"order_id": "6912345678901234567", "order_status_desc": "已发货", "product_name": "T恤",
                    "post_tel": "13800001111", "post_receiver": "李四"}])
    assert out["verified"] is False and out["buyer_order_count"] == 1
    assert out["recent_orders"][0]["order_id"] == "6912345678901234567"
    assert "13800001111" not in json.dumps(out) and "李四" not in json.dumps(out, ensure_ascii=False)


def test_unknown_buyer_or_platform_is_refused_without_a_lookup():
    out, calls = _run({"platform": "douyin", "customer_id": ""}, [PDD_ORDER])
    assert out["ok"] is False and not calls
    out, calls = _run({"platform": "淘宝", "customer_id": "x"}, [PDD_ORDER])
    assert out["ok"] is False and not calls


def test_only_read_endpoints_are_requested():
    _, calls = _run({"platform": "douyin", "customer_id": "c", "order_id": "1"}, [])
    _, calls2 = _run({"platform": "pdd", "customer_id": "1", "order_id": "1"}, [])
    paths = set()
    for js in calls + calls2:
        paths.update(p for p in ("cmpoent/order/query", "userAllOrder") if p in js)
        for forbidden in ("mobile/get", "price/update", "sendUserCashRefund", "remarks/mallConfirm",
                          "orderAddressInfo", "send_message", "Refund"):
            assert forbidden not in js
    assert paths == {"cmpoent/order/query", "userAllOrder"}


def test_douyin_buyer_key_comes_from_the_conversation():
    from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import ws_session as ws
    key = "AQ" + "x" * 86
    mp = pytest.MonkeyPatch()
    mp.setitem(ws._uid_by_talk, "7699304524657247498", key)
    mp.setattr(ws, "talk_for_name", lambda name, shop="": "7699304524657247498" if name == "童趣科普" else "")
    try:
        assert ws.buyer_key_for("童趣科普") == key
        assert ws.buyer_key_for("card:7699304524657247498") == key
        assert ws.buyer_key_for(key) == key
        assert ws.buyer_key_for("没见过的人") == ""
    finally:
        mp.undo()
