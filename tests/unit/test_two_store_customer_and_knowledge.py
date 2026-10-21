"""Two 抖店 stores, one buyer (customer run 2026-10-19 13:34, yat).

The tester chatted with both stores as the same buyer 'sc'. The front desk's
per-customer records were keyed by name only, so store 二号's 牙膏 question went
to the Q&A with store 三号's replies in its history; and with no catalog for
store 二号 the knowledge lookup fell through to the account-wide LightRAG base,
which held store 三号's 童装 material -> "这边主营童装"."""
import importlib
from types import SimpleNamespace

import pytest

FC = "agent.ec_skills.browser_use_extension.hooks.external.feige_chat."


@pytest.fixture
def shops(monkeypatch):
    ws = importlib.import_module(FC + "ws_session")
    sc = importlib.import_module(FC + "shop_context")
    fd = importlib.import_module(FC + "front_desk")
    monkeypatch.setattr(ws, "_first_shop", [""])
    monkeypatch.setattr(ws, "_shops", {})
    monkeypatch.setattr(fd, "_FEIGE_FD_DISPATCH_REG", {})
    monkeypatch.setattr(fd, "_FEIGE_FD_DISPATCH_REG_BY_SHOP", {})
    a = ws.register_shop("profile:fp-douyin-6a4b2c53-login")   # 二号, first shop
    b = ws.register_shop("profile:fp-douyin-167bb80f-login")   # 三号
    return ws, sc, fd, a, b


def test_same_buyer_in_two_stores_keeps_two_histories(shops):
    _, sc, _, a, b = shops
    d = sc.ShopScopedDict()
    tok = sc.set_current_shop(a)
    d.setdefault("sc", []).append("有牙膏卖吗？")
    sc.reset_current_shop(tok)
    tok = sc.set_current_shop(b)
    d.setdefault("sc", []).append("有质保吗？")
    assert d["sc"] == ["有质保吗？"]
    sc.reset_current_shop(tok)
    tok = sc.set_current_shop(a)
    assert d["sc"] == ["有牙膏卖吗？"] and "sc" in d
    sc.reset_current_shop(tok)
    # single store / no shop known: plain keys, as before
    assert d.get("sc") == ["有牙膏卖吗？"]
    d.clear()
    assert len(d) == 0


def test_real_records_are_per_shop(shops):
    _, sc, _, a, b = shops
    ds = importlib.import_module(FC + "dispatch_state")
    ai = importlib.import_module(FC + "actionable_items")
    for m in (ds.last_agent_reply_by_customer, ds.recent_agent_replies_by_customer,
              ds.last_dispatched_msg_id_by_customer, ds.last_recipient_by_customer,
              ai._customer_recent_messages):
        assert isinstance(m, sc.ShopScopedDict)
    tok = sc.set_current_shop(b)
    ds.last_agent_reply_by_customer["sc"] = "这边主营童装哦"
    sc.reset_current_shop(tok)
    tok = sc.set_current_shop(a)
    try:
        assert "sc" not in ds.last_agent_reply_by_customer
    finally:
        sc.reset_current_shop(tok)
        ds.last_agent_reply_by_customer.clear()


def test_direct_delivery_enters_the_front_desk_s_shop(shops):
    _, sc, fd, a, b = shops
    fd._set_fd_slot(a, ("cfg", SimpleNamespace(calling_agent_id="agent_FD2"), None))
    fd._set_fd_slot(b, ("cfg", SimpleNamespace(calling_agent_id="agent_FD3"), None))
    tok = fd.enter_agent_shop("agent_FD3")
    assert sc.current_shop() == b
    sc.reset_current_shop(tok)
    tok = fd.enter_agent_shop("agent_FD2")
    assert sc.scoped_key("sc") == "sc"            # first shop: plain key
    sc.reset_current_shop(tok)
    assert fd.enter_agent_shop("agent_unknown") is None


def _ks(monkeypatch, stores, has_products):
    ab = importlib.import_module("knowledge.ks.agent_bridge")
    monkeypatch.setattr(ab, "enabled", lambda: True)
    monkeypatch.setattr(ab, "_has_product_knowledge", lambda svc: has_products)
    svc = importlib.import_module("knowledge.ks.service")
    monkeypatch.setattr(svc, "get_service", lambda mw: SimpleNamespace())
    monkeypatch.setattr(svc, "get_router", lambda mw: SimpleNamespace(all_connections=lambda: []))
    mw = SimpleNamespace(ec_db_mgr=SimpleNamespace(store_service=SimpleNamespace(
        list_stores=lambda: [{"id": s} for s in stores])))
    return ab, mw


def test_store_without_catalog_does_not_borrow_another_store_s_material(monkeypatch):
    ab, mw = _ks(monkeypatch, ["douyin-抖音二号", "douyin-抖音三号"], has_products=False)
    out = ab.try_product_answer(mw, {"query": "有牙膏卖吗？", "workspace": "",
                                     "_ks_scope": {"store_id": "douyin-抖音二号"}})
    assert out is not None and out["data"]["confidence"]["decision"]["should_answer"] is False
    assert "douyin-抖音二号" in out["data"]["response"] and "其他店铺" in out["data"]["response"]


def test_single_store_still_falls_back_to_the_knowledge_base(monkeypatch):
    ab, mw = _ks(monkeypatch, ["douyin-抖音二号"], has_products=False)
    assert ab.try_product_answer(mw, {"query": "有牙膏卖吗？", "workspace": "",
                                      "_ks_scope": {"store_id": "douyin-抖音二号"}}) is None
    # unscoped turn: unchanged too
    ab, mw = _ks(monkeypatch, ["a", "b"], has_products=False)
    assert ab.try_product_answer(mw, {"query": "x", "workspace": "", "_ks_scope": {}}) is None
