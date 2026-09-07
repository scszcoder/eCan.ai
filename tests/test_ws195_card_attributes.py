"""ws195: product ATTRIBUTES (面料材质/尺码/功能…) must reach the QA card context.

2026-09-07 customer report: when a customer sends a product card and asks
"会不会掉色", the QA agent fobs off with "这边帮您核实一下…稍后回复您" — because
the card context carried only 价格/券/发货 (ws186), never the material that
answers the question, even though the captured product JSON has it. Two gaps:
  1. get_product_list bodies (data = LIST) — the ones with full
     property_value_pair — were dropped by a dict-only guard.
  2. _detail_from_goods never read property_value_pair.
Fix: parse list bodies, extract a whitelisted 属性 line, merge it into detail_for.
"""

import json

import agent.ec_skills.browser_use_extension.hooks.external.feige_chat.product_detail_store as s


def _reset():
    with s._lock:
        s._by_goods.clear()
        s._by_title.clear()
        s._by_goods_attrs.clear()
        s._by_title_attrs.clear()


_LIST_BODY = json.dumps({
    "code": 0,
    "data": [{
        "product_id": "",   # top-level empty — real id is nested
        "product_item": {"product_base_info": {
            "product_id": "PID1",
            "title": "女童牛仔短裤",
            "property_value_pair": [
                {"Property": {"PropertyName": "面料材质"}, "Values": [{"ValueName": "聚酯纤维100%"}]},
                {"Property": {"PropertyName": "适用年龄"}, "Values": [{"ValueName": "中童"}]},
                {"Property": {"PropertyName": "功能"}, "Values": [{"ValueName": "透气"}, {"ValueName": "耐磨"}]},
                {"Property": {"PropertyName": "风格"}, "Values": [{"ValueName": "复古港风"}]},  # NOT whitelisted
            ],
        }},
    }],
})

_CARD_BODY = json.dumps({
    "code": 0,
    "data": {"b_goods": [{
        "product_id": "PID1", "product_name": "女童牛仔短裤",
        "current_price": {"price": "58.00", "suffix": "券后价"}, "price": "68.00",
    }]},
})


def test_list_body_is_parsed_and_attrs_stored(monkeypatch):
    monkeypatch.setenv("ECAN_FEIGE_CARD_JSON", "1")
    _reset()
    # data=LIST body (get_product_list) used to be dropped — now yields attrs.
    assert s.note_detail_body("https://x/get_product_list", _LIST_BODY) == 1
    detail = s.detail_for("PID1")
    assert "面料材质=聚酯纤维100%" in detail
    assert "适用年龄=中童" in detail
    assert "功能=透气/耐磨" in detail


def test_attr_whitelist_excludes_noise(monkeypatch):
    monkeypatch.setenv("ECAN_FEIGE_CARD_JSON", "1")
    _reset()
    s.note_detail_body("https://x/get_product_list", _LIST_BODY)
    # 风格 is not in the CS whitelist — kept out to protect the token budget.
    assert "风格" not in s.detail_for("PID1")


def test_price_and_attrs_merge(monkeypatch):
    monkeypatch.setenv("ECAN_FEIGE_CARD_JSON", "1")
    _reset()
    s.note_detail_body("https://x/get_product_list", _LIST_BODY)      # attrs
    s.note_detail_body("https://x/getTemplateCardDataV2", _CARD_BODY)  # price
    merged = s.detail_for("PID1")
    assert "价格:￥58.00" in merged        # price half survives
    assert "属性:面料材质=聚酯纤维100%" in merged   # attrs half survives
    # enrich carries both onto the card text the QA agent sees.
    enriched = s.enrich_card_text("[商品卡片] 女童牛仔短裤 商品ID:PID1")
    assert "面料材质=聚酯纤维100%" in enriched and "价格:￥58.00" in enriched


def test_lookup_by_title_fallback(monkeypatch):
    monkeypatch.setenv("ECAN_FEIGE_CARD_JSON", "1")
    _reset()
    s.note_detail_body("https://x/get_product_list", _LIST_BODY)
    assert "面料材质=聚酯纤维100%" in s.detail_for("", "女童牛仔短裤")
