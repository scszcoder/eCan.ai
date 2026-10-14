"""Agent bridge: rag_query answers from product knowledge, scoped by state."""
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


async def test_rag_query_tool_uses_product_knowledge_before_lightrag(wired, monkeypatch):
    from agent.ec_skills.rag import local_rag_mcp

    def no_lightrag():
        raise AssertionError("LightRAG must not be called when product knowledge answers")

    monkeypatch.setattr(local_rag_mcp, "get_client", no_lightrag)
    # Awaited inside pytest-asyncio's loop: asyncio.run() would leave no current
    # loop behind and break later tests that call get_event_loop().
    out = await local_rag_mcp.rag_query(None, {"input": {
        "query": "身高170穿什么码", "_ks_scope": {"platform_item_id": "6600001"}}})
    assert out[0].meta["data"]["source"] == "product_knowledge"
    assert "尺码表" in out[0].text


def test_workspace_pinned_query_skips_product_knowledge(wired):
    """A rag_query pinned to a LightRAG workspace keeps its tenant isolation."""
    assert ab.try_product_answer(None, {"query": "这件是什么材质", "workspace": "storeB",
                                        "_ks_scope": {"platform_item_id": "3500009"}}) is None


def test_run_scope_wins_over_llm_supplied_ids(wired):
    """The LLM's tool args can't override the run's own product scope."""
    meta = ab.try_product_answer(None, {"query": "这件是什么材质", "platform_item_id": "999999999",
                                        "_ks_scope": {"platform_item_id": "3500009"}})
    assert meta["data"]["product_knowledge"]["product"]["code"] == "TS-001"


def test_a_shared_qa_turn_is_scoped_to_the_store_that_dispatched_it():
    """A Q&A agent shared by several stores' front desks has no store of its own:
    the store comes from the front desk's dispatch JSON for that turn."""
    import json
    turn = {"input": json.dumps({"customer_id": "c1", "session_id": "s1", "store_id": "优衣小铺天猫店",
                                 "latest_message": "store_id: 别的店"}, ensure_ascii=False),
            "prompt_refs": {"front_desk_agent_id": "fdA,fdB"}}
    assert ab.scope_from_state(turn)["store_id"] == "优衣小铺天猫店"
    own = dict(turn, prompt_refs={"store_id": "自己的店"})     # a task's own store wins
    assert ab.scope_from_state(own)["store_id"] == "自己的店"
    chat = {"input": json.dumps({"text": "hi", "store_id": "x"})}   # not a dispatch payload
    assert ab.scope_from_state(chat)["store_id"] == ""


def test_inside_a_run_the_llm_cannot_name_the_store(wired, monkeypatch):
    seen = {}
    import knowledge.ks.service as service_mod
    real = service_mod.get_service

    def spy():
        svc = real()
        orig = svc.search
        svc.search = lambda *a, **k: seen.update(k) or orig(*a, **k)
        return svc
    monkeypatch.setattr(service_mod, "get_service", spy)
    ab.try_product_answer(None, {"query": "这件是什么材质", "store_id": "别人的店",
                                 "_ks_scope": {"store_id": "", "platform_item_id": "3500009"}})
    assert not seen.get("store_ref")


def test_a_shared_turn_puts_its_store_on_the_run_scope():
    """Usage / metering of a shared Q&A turn is attributed to the asking store."""
    import contextvars
    import json
    from types import SimpleNamespace
    from agent.ec_tasks.runner import TaskRunner
    from utils.log_scope import get_scope, set_scope
    r = TaskRunner.__new__(TaskRunner)
    text = json.dumps({"customer_id": "c1", "session_id": "s1", "store_id": "店B"}, ensure_ascii=False)
    msg = SimpleNamespace(message=SimpleNamespace(parts=[{"type": "text", "text": text}]))

    def turn(scope_fields):
        set_scope(**scope_fields)
        r._scope_turn_store(msg)
        return get_scope().get("store_id")
    assert contextvars.copy_context().run(turn, {"agent_id": "qa1"}) == "店B"
    assert contextvars.copy_context().run(turn, {"store_id": "自己的店"}) == "自己的店"   # the task's own wins
