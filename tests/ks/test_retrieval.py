"""Path A retrieval: tiers, scoping, policy inheritance and tenant isolation."""


def test_product_card_answers_material_from_the_record(svc, shop):
    r = svc.search("这件是什么材质的", store_ref=shop["tmall"]["id"], platform_item_id="6600001")
    assert r["tier"] == 0
    assert r["product"]["code"] == "TS-001"
    assert {"key": "材质", "value": "100%棉", "source": "attribute"} in r["facts"]
    assert r["should_answer"]
    assert "100%棉" in r["context"]


def test_same_product_resolves_from_either_store(svc, shop):
    a = svc.search("面料是什么", store_ref=shop["tmall"]["id"], platform_item_id="6600001")
    b = svc.search("面料是什么", store_ref=shop["douyin"]["id"], platform_item_id="3500009")
    assert a["product"]["id"] == b["product"]["id"] == shop["cotton"]["id"]


def test_size_question_returns_size_chart(svc, shop):
    r = svc.search("身高170穿什么尺码", store_ref=shop["tmall"]["id"], platform_item_id="6600001")
    keys = [f["key"] for f in r["facts"]]
    assert "尺码表" in keys and r["tier"] == 0


def test_store_policy_override_wins(svc, shop):
    r = svc.search("可以七天无理由退货吗", store_ref=shop["douyin"]["id"], platform_item_id="3500009")
    assert len(r["policies"]) == 1
    assert "运费险" in r["policies"][0]["text"] and r["policies"][0]["inherited"] is False


def test_store_without_override_inherits_merchant_default(svc, shop):
    r = svc.search("可以退货吗", store_ref=shop["tmall"]["id"], platform_item_id="6600001")
    assert "吊牌完好" in r["policies"][0]["text"] and r["policies"][0]["inherited"] is True


def test_similar_product_trap_faq_is_scoped_to_the_card(svc, shop):
    # Both shirts have the same FAQ question with different answers.
    cotton = svc.search("会缩水吗", store_ref=shop["tmall"]["id"], platform_item_id="6600001")
    linen = svc.search("会缩水吗", store_ref=shop["tmall"]["id"], platform_item_id="6600002")
    assert cotton["faq"] and "1-2%" in cotton["faq"][0]["answer"]
    assert linen["faq"] and "3-5%" in linen["faq"][0]["answer"]
    assert all(f["product_id"] == shop["cotton"]["id"] for f in cotton["faq"])


def test_other_merchant_never_leaks(svc, shop):
    # Same platform item id exists in the other tenant; questions about it
    # from merchant A must only see merchant A's data.
    r = svc.search("会缩水吗 可以退货吗", store_ref=shop["tmall"]["id"], platform_item_id="6600001")
    blob = r["context"] + str(r["faq"]) + str(r["chunks"]) + str(r["policies"])
    assert "别家" not in blob
    # And the other tenant can't reach A's product by id.
    r2 = svc.search("材质", product_id=shop["cotton"]["id"], tenant_id=shop["other_tid"])
    assert r2["product"] is None


def test_no_card_finds_candidate_products_in_the_store(svc, shop):
    r = svc.search("有没有亚麻的短袖", store_ref=shop["tmall"]["id"])
    assert r["tier"] == 3
    assert r["candidates"] and r["candidates"][0]["code"] == "TS-002"


def test_unknown_question_does_not_claim_confidence(svc, shop):
    r = svc.search("你们老板贵姓", store_ref=shop["tmall"]["id"], platform_item_id="6600001")
    assert not r["should_answer"]
    assert r["reason"] == "no_relevant_knowledge"


def test_timings_are_reported(svc, shop):
    r = svc.search("材质", store_ref=shop["tmall"]["id"], platform_item_id="6600001")
    assert {"scope", "tier0_facts", "embed_query", "search", "total"} <= set(r["timings_ms"])
    assert r["timings_ms"]["total"] < 2000


def test_store_ref_accepts_name(svc, shop):
    r = svc.search("发货用什么快递", store_ref="优衣小铺天猫店")
    assert r["store"]["id"] == shop["tmall"]["id"]
    assert r["policies"] and "中通" in r["policies"][0]["text"]


def test_recommendation_request_gets_the_stores_products(svc, shop):
    # "推荐一下" names no product: the answer offers the store's own products.
    r = svc.search("东西太多了，推荐一下吧", store_ref=shop["tmall"]["id"])
    assert r["should_answer"]
    assert {p["code"] for p in r["shortlist"]} == {"TS-001", "TS-002"}
    assert "[可推荐商品]" in r["context"] and "男士亚麻圆领短袖T恤" in r["context"]


def test_recommendation_puts_what_the_buyer_asked_for_first(svc, shop):
    svc.save_product({"code": "TS-001", "title": "男士纯棉圆领短袖T恤", "category": "男装/T恤",
                      "attributes": {"材质": "100%棉"}})                # saved last: not first by recency
    r = svc.search("想要亚麻的，推荐哪款好", store_ref=shop["tmall"]["id"])
    assert r["shortlist"][0]["code"] == "TS-002"


def test_recommendation_only_offers_this_stores_products(svc, shop):
    r = svc.search("推荐一款", store_ref=shop["douyin"]["id"])
    assert [p["code"] for p in r["shortlist"]] == ["TS-001"]       # linen is only listed in the tmall store
    assert "竞品" not in r["context"]


def test_store_recommendation_rule_reaches_the_answer(svc, shop):
    svc.save_policy("recommendation", "顾客让推荐时优先推荐纯棉款。")
    r = svc.search("帮我选一件", store_ref=shop["tmall"]["id"])
    assert "[店铺规则·推荐规则]" not in r["context"]               # no recommendation word in this question
    r = svc.search("推荐哪个好", store_ref=shop["tmall"]["id"])
    assert "顾客让推荐时优先推荐纯棉款" in r["context"] and r["shortlist"]


def test_ordinary_question_has_no_shortlist(svc, shop):
    r = svc.search("有没有亚麻的短袖", store_ref=shop["tmall"]["id"])
    assert r["shortlist"] == [] and "[可推荐商品]" not in r["context"]
