"""Card-only customers get their name from their thread (2026-10-19, store 三号).

Two buyers each sent only a product card: their frames carry no name and their
sidebar previews are both "[商品]", so both replies stayed parked. Opening each
"[商品]" row and matching the card in its thread to the conversation's WS card
names them; the parked replies then go out under the real names."""
import asyncio
import importlib
import time

import pytest

FC = "agent.ec_skills.browser_use_extension.hooks.external.feige_chat."
T1, T2 = "7698239095159489820", "7698238894856258845"
CARD1 = "[商品卡片] 男童篮球服套装夏季新款中大童儿童速干运动服宽松青少年训练服薄 商品ID:3806636856926404910"
CARD2 = "[商品卡片] 男童短袖球服套装运动服女童青少年速干衣透气短裤中大童 商品ID:3812345678901234567"


@pytest.fixture
def store(monkeypatch):
    ws = importlib.import_module(FC + "ws_session")
    fd = importlib.import_module(FC + "front_desk")
    und = importlib.import_module(FC + "undeliverable")
    da = importlib.import_module(FC + "dom_assets")
    tl = importlib.import_module(FC + "typing_lock")
    now = time.time() * 1000
    monkeypatch.setattr(ws, "_first_shop", [""])
    monkeypatch.setattr(ws, "_shops", {})
    monkeypatch.setattr(ws, "_thread", {
        T1: {"cust": {"text": CARD1, "type": "template_card", "ts": now}},
        T2: {"cust": {"text": CARD2, "type": "template_card", "ts": now}}})
    monkeypatch.setattr(ws, "_talk_to_name", {})
    monkeypatch.setattr(ws, "_shop_by_talk", {})
    monkeypatch.setattr(ws, "_routing", {})
    monkeypatch.setattr(fd, "_CARD_BRIDGE_TRIED", {})
    monkeypatch.setattr(und, "_PARKED", {T1: {"talk": T1, "parked_at": time.time()},
                                         T2: {"talk": T2, "parked_at": time.time()}})
    monkeypatch.setattr(und, "_prune_locked", lambda now: None)
    monkeypatch.setattr(tl, "holder", lambda *a, **k: "")
    threads = {"小明": "男童篮球服套装夏季新款中大童儿童速干运动服宽松青少年训练服薄",
               "小红": "男童短袖球服套装运动服女童青少年速干衣透气短裤中大童"}
    scraped = []

    async def fake_scrape(session, name, **kw):
        scraped.append(name)
        return {"scrape_ok": True, "product_cards": [{"title": threads[name]}]}
    monkeypatch.setattr(da, "scrape_latest_customer_bubble", fake_scrape)
    rows = [{"name": "小明", "preview": "[商品]"}, {"name": "小红", "preview": "[商品]"},
            {"name": "老顾客", "preview": "好的谢谢"}]
    return ws, fd, threads, scraped, rows


def _run(fd, rows):
    return asyncio.run(fd._bind_card_convs_by_thread(object(), rows, ""))


def test_two_card_only_customers_are_named_from_their_threads(store):
    ws, fd, _, scraped, rows = store
    assert _run(fd, rows) == 2
    assert ws.name_for_talk(T1) == "小明" and ws.name_for_talk(T2) == "小红"
    assert sorted(scraped) == ["小明", "小红"]            # never the text row


def test_same_product_from_two_buyers_stays_parked(store):
    ws, fd, threads, _, rows = store
    threads["小红"] = threads["小明"]
    ws._thread[T2]["cust"]["text"] = CARD1
    assert _run(fd, rows) == 0 and not ws._talk_to_name


def test_nothing_parked_means_no_clicking(store, monkeypatch):
    ws, fd, _, scraped, rows = store
    und = importlib.import_module(FC + "undeliverable")
    monkeypatch.setattr(und, "_PARKED", {})
    assert _run(fd, rows) == 0 and scraped == []


def test_no_click_while_a_reply_is_being_typed(store, monkeypatch):
    ws, fd, _, scraped, rows = store
    tl = importlib.import_module(FC + "typing_lock")
    monkeypatch.setattr(tl, "holder", lambda *a, **k: "someone")
    assert _run(fd, rows) == 0 and scraped == []


def test_each_row_is_tried_at_most_once_a_minute(store):
    ws, fd, threads, scraped, rows = store
    threads["小明"] = threads["小红"] = "完全不同的商品标题啊啊啊"
    _run(fd, rows)
    _run(fd, rows)
    assert sorted(scraped) == ["小明", "小红"]
