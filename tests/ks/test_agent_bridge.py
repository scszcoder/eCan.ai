"""Agent bridge: rag_query answers from product knowledge, scoped by state."""
import asyncio

import pytest

from knowledge.ks import agent_bridge as ab


@pytest.fixture(autouse=True)
def _fresh_cache():
    ab._stats_cache.update({"at": 0.0, "has_data": False, "key": None})


@pytest.fixture
def wired(svc, shop, monkeypatch):
    import knowledge.ks.service as service_mod
    monkeypatch.setattr(service_mod, "get_service", lambda main_window=None: svc)
    return svc


def test_extract_item_id_takes_the_latest_card():
    text = "[商品卡片] 旧款 价格:￥59 商品ID:6600002\n...\n[商品卡片] 男士纯棉T恤 价格:￥69 商品ID:6600001"
    assert ab.extract_item_id(text) == "6600001"
    assert ab.extract_item_id("没有卡片") == ""


def test_scope_from_state_reads_task_store_and_card():
    state = {
        "prompt_refs": {"store_id": "优衣小铺天猫店"},
        "attributes": {"customer_recent_messages": ["[商品卡片] 男士纯棉圆领短袖T恤 价格:￥69 商品ID:6600001", "这件起球吗"]},
    }
    assert ab.scope_from_state(state) == {"store_id": "优衣小铺天猫店", "platform_item_id": "6600001"}


def test_answers_from_product_card_without_store(wired):
    # A shared Q&A agent doesn't know the store; the item id identifies both.
    meta = ab.try_product_answer(None, {"query": "这件是什么材质", "_ks_scope": {"platform_item_id": "3500009"}})
    assert meta["data"]["source"] == "product_knowledge"
    pk = meta["data"]["product_knowledge"]
    assert pk["product"]["code"] == "TS-001" and pk["store"]["name"] == "优衣小铺抖音店"
    assert "100%棉" in meta["data"]["response"]
    assert meta["data"]["confidence"]["decision"]["should_answer"] is True


def test_store_policy_comes_from_the_card_store(wired):
    meta = ab.try_product_answer(None, {"query": "可以退货吗 [商品卡片] 男士纯棉T恤 商品ID:3500009"})
    assert "运费险" in meta["data"]["response"]  # douyin store override, found via the card


def test_unconfident_answers_fall_through(wired):
    assert ab.try_product_answer(None, {"query": "你们老板贵姓"}) is None


def test_disabled_or_empty_catalog_falls_through(svc, monkeypatch):
    import knowledge.ks.service as service_mod
    monkeypatch.setattr(service_mod, "get_service", lambda main_window=None: svc)
    assert ab.try_product_answer(None, {"query": "这件是什么材质"}) is None  # no products yet
    monkeypatch.setenv("ECAN_KS_PRODUCT_QA", "0")
    assert ab.try_product_answer(None, {"query": "这件是什么材质"}) is None


def test_rag_query_tool_uses_product_knowledge_before_lightrag(wired, monkeypatch):
    from agent.ec_skills.rag import local_rag_mcp

    def no_lightrag():
        raise AssertionError("LightRAG must not be called when product knowledge answers")

    monkeypatch.setattr(local_rag_mcp, "get_client", no_lightrag)
    out = asyncio.run(local_rag_mcp.rag_query(None, {"input": {
        "query": "身高170穿什么码", "_ks_scope": {"platform_item_id": "6600001"}}}))
    assert out[0].meta["data"]["source"] == "product_knowledge"
    assert "尺码表" in out[0].text
