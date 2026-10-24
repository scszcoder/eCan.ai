"""用户画像: what buyers say about the person the item is for, kept per store."""
import json

import pytest

from knowledge.ks import buyer_profiles as bp


@pytest.mark.parametrize("text, who, fields, gift", [
    ("我想给6岁女儿买衣服，身高120，预算100以内", "女儿",
     {"gender": "女", "age": "6岁", "height": "120cm", "budget": "100元以内"}, False),
    ("身高1米2的孩子穿多大", "孩子", {"height": "120cm"}, False),
    ("平时穿XL码，体重140斤", "", {"weight": "140斤", "size": "XL"}, False),
    ("送朋友的生日礼物，喜欢粉色", "朋友", {"occasion": "生日", "prefs": ["粉色"]}, True),
    ("200块左右的有吗", "", {"budget": "200元左右"}, False),
    ("宝宝18个月", "宝宝", {"age": "18个月"}, False),
])
def test_what_a_message_says_about_the_person(text, who, fields, gift):
    assert bp.read_message(text) == (who, fields, gift)


@pytest.mark.parametrize("text", ["这件M码有吗", "裤长90cm吗", "10斤装的吗", "这款多少钱", "1米8的床有吗"])
def test_product_questions_say_nothing_about_the_person(text):
    assert bp.read_message(text) == ("", {}, False)


def test_a_profile_builds_up_over_the_chat(tmp_path):
    p = bp.BuyerProfiles(str(tmp_path))
    p.note("s1", "b1", "给我女儿买的", "小雨妈妈")
    p.note("s1", "b1", "她6岁，身高120")                   # no recipient named: the current one
    prof = p.note("s1", "b1", "推荐一下吧")
    rec = prof["recipients"]["女儿"]["fields"]
    assert rec == {"gender": "女", "age": "6岁", "height": "120cm"} and prof["name"] == "小雨妈妈"
    assert bp.describe(prof).endswith("当前：给女儿买：女，6岁，120cm")


def test_one_buyer_can_shop_for_several_people(tmp_path):
    p = bp.BuyerProfiles(str(tmp_path))
    p.note("s1", "b1", "给女儿买，6岁")
    prof = p.note("s1", "b1", "再给儿子挑一件，他8岁")
    assert prof["current"] == "儿子"
    assert prof["recipients"]["女儿"]["fields"]["age"] == "6岁"
    assert prof["recipients"]["儿子"]["fields"]["age"] == "8岁"
    assert "当前：给儿子买：男，8岁；之前还提到：给女儿买：女，6岁" in bp.describe(prof)


def test_the_owners_correction_is_not_overwritten(tmp_path):
    p = bp.BuyerProfiles(str(tmp_path))
    p.note("s1", "b1", "给女儿买，身高120")
    p.set_fields("s1", "b1", "女儿", {"height": "125cm"})
    prof = p.note("s1", "b1", "身高130")
    assert prof["recipients"]["女儿"]["fields"]["height"] == "125cm"
    p.set_fields("s1", "b1", "女儿", {"height": ""})              # cleared: the chat may fill it again
    assert p.note("s1", "b1", "身高130")["recipients"]["女儿"]["fields"]["height"] == "130cm"


def test_stores_and_buyers_are_kept_apart_and_old_buyers_dropped(tmp_path, monkeypatch):
    p = bp.BuyerProfiles(str(tmp_path))
    p.note("s1", "b1", "给女儿买，6岁")
    p.note("s2", "b1", "给老公买")
    assert p.get("s2", "b1")["current"] == "老公" and p.get("s1", "b1")["current"] == "女儿"
    later = bp.time.time() + (bp.RETAIN_DAYS + 1) * 86400
    monkeypatch.setattr(bp.time, "time", lambda: later)
    assert p.get("s1", "b1") is None and p.list("s1") == []


def test_delete_one_person_or_the_buyer(tmp_path):
    p = bp.BuyerProfiles(str(tmp_path))
    p.note("s1", "b1", "给女儿买")
    p.note("s1", "b1", "给儿子买")
    assert p.delete("s1", "b1", "儿子")
    assert list(p.get("s1", "b1")["recipients"]) == ["女儿"] and p.get("s1", "b1")["current"] == "女儿"
    assert p.delete("s1", "b1") and p.get("s1", "b1") is None


def test_the_hand_off_carries_the_profile_and_eval_buyers_are_not_kept(svc, monkeypatch, tmp_path):
    import knowledge.ks.service as service_mod
    from agent.ec_skills.node_runtime import frontdesk_dispatch as fd
    svc.data_dir = str(tmp_path)
    monkeypatch.setattr(service_mod, "get_service", lambda main_window=None: svc)
    payload = {"store_id": "douyin-1", "customer_id": "buyer-9", "latest_message": "给6岁女儿买，推荐一下",
               "customer_recent_messages": ["[商品卡片] …"]}
    fd.add_profile_line(payload)
    assert payload["customer_recent_messages"][-1].startswith("[顾客画像]")
    assert svc.list_profiles("douyin-1")[0]["customer_id"] == "buyer-9"
    ev = {"store_id": "douyin-1", "customer_id": "eval-ev1", "latest_message": "给儿子买，8岁"}
    fd.add_profile_line(ev)
    assert "给儿子买" in ev["customer_recent_messages"][-1]
    assert [b["customer_id"] for b in svc.list_profiles("douyin-1")] == ["buyer-9"]


def test_a_recommendation_is_searched_with_the_buyers_profile(svc, shop, monkeypatch):
    from knowledge.ks import agent_bridge as ab
    import knowledge.ks.service as service_mod
    monkeypatch.setattr(service_mod, "get_service", lambda main_window=None: svc)
    monkeypatch.setattr(ab, "enabled", lambda: True)
    seen = {}
    real = svc.search
    monkeypatch.setattr(svc, "search", lambda q, **kw: seen.setdefault("q", q) and real(q, **kw))
    turn = {"customer_id": "b1", "latest_message": "推荐一款吧",
            "customer_recent_messages": ["[顾客画像]（…） 当前：给老公买：男，身高175cm，偏好亚麻"]}
    ab.try_product_answer(None, {"query": json.dumps(turn, ensure_ascii=False), "workspace": "",
                                 "_ks_scope": {"store_id": shop["tmall"]["id"]}})
    assert seen["q"].startswith("推荐一款吧（给老公买：男，身高175cm") and "亚麻" in seen["q"]
