"""query_inventories / query_price default to the store's own back office
(2026-10-24 KEN: the default "mock" vendor told buyers "暂无库存记录" for a
product the store had 600 of)."""
import asyncio
import json
import types

import pytest

from agent.mcp.server.integrations import customer_data_tools as cdt
from agent.mcp.server.integrations import store_page_vendor as spv

LIVE = [{"id": "3826533688146002286", "title": "女童夏季薄款牛仔短裤2026新款", "stock": 600, "price_fen": 4800},
        {"id": "3806636940602769454", "title": "NASA2025秋季中大童儿童装T恤", "stock": 0, "price_fen": 0}]


@pytest.fixture(autouse=True)
def live(monkeypatch):
    monkeypatch.delenv("ECAN_CUSTOMER_DATA_VENDOR", raising=False)
    monkeypatch.setattr(spv, "_live_products", lambda: LIVE)
    product = {"title": "女童夏季薄款牛仔短裤2026新款", "listings": [{"platform_item_id": "3826533688146002286"}]}
    store = types.SimpleNamespace(find_product_by_code=lambda tid, code: product if code == "01448143f0b0" else None)
    svc = types.SimpleNamespace(store=store, tenant_id=lambda t: "tn")
    import knowledge.ks.service as ks_service
    monkeypatch.setattr(ks_service, "get_service", lambda mw=None: svc)


def _call(fn, **inp):
    out = asyncio.run(fn(None, {"input": inp}))
    return out[0].meta, json.loads(out[0].text) if out[0].text.startswith("{") else out[0].text


def test_stock_comes_from_the_store_by_the_knowledge_base_code():
    meta, body = _call(cdt.query_inventories, sku="01448143f0b0")
    assert meta["vendor_id"] == "store" and body["found"] and body["in_stock"] and body["stock_total"] == 600


def test_price_and_a_product_id_and_an_empty_stock():
    _, body = _call(cdt.query_price, sku="3826533688146002286")
    assert body["price_yuan_from"] == 48.0
    _, body = _call(cdt.query_inventories, sku="3806636940602769454")
    assert body["found"] and body["in_stock"] is False


def test_an_unknown_product_never_reads_as_out_of_stock():
    _, body = _call(cdt.query_inventories, sku="ZZZ-404")
    assert body["found"] is False and "不代表没货" in body["note"]


def test_orders_point_to_the_verified_lookup():
    _, body = _call(cdt.query_order, order_id="6930000000001")
    assert "lookup_order" in body["note"]


def test_mock_only_when_asked_for(monkeypatch):
    monkeypatch.setenv("ECAN_CUSTOMER_DATA_VENDOR", "mock")
    meta, _ = _call(cdt.query_inventories, sku="01448143f0b0")
    assert meta["vendor_id"] == "mock"
