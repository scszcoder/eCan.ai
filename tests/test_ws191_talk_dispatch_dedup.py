"""ws191: one answer per conversation across identities, and one canonical card
price. Regression guard for the 2026-09-05 duplicate (talk 7682040317431907610
= 陆地飞鱼 answered 券后28元 AND 券后38元)."""

import importlib

ds = importlib.import_module(
    "agent.ec_skills.browser_use_extension.hooks.external.feige_chat.dispatch_state"
)
pds = importlib.import_module(
    "agent.ec_skills.browser_use_extension.hooks.external.feige_chat.product_detail_store"
)


def _reset():
    with ds._talk_dispatch_lock:
        ds._talk_dispatch_at.clear()


# ── Fix 1: talk-level cross-identity dedup ───────────────────────────────────

def test_second_identity_for_same_talk_is_suppressed():
    _reset()
    talk = "7682040317431907610"
    # Named WS frame dispatches first.
    assert ds.talk_recently_dispatched(talk) is False
    ds.note_talk_dispatched(talk, msg_id="")
    # The parked card:<talk> for the SAME talk arrives later -> duplicate.
    assert ds.talk_recently_dispatched(talk) is True


def test_new_turn_with_different_msg_id_is_allowed():
    _reset()
    talk = "t1"
    ds.note_talk_dispatched(talk, msg_id="m1")
    # A genuinely new customer message (different msg_id) must NOT be suppressed.
    assert ds.talk_recently_dispatched(talk, msg_id="m2") is False


def test_claim_expires_after_ttl():
    _reset()
    talk = "t2"
    ds.note_talk_dispatched(talk)
    assert ds.talk_recently_dispatched(talk, ttl=0.0) is False


def test_pure_card_conversation_first_dispatch_allowed():
    _reset()
    # No prior claim -> a card-only conversation dispatches normally.
    assert ds.talk_recently_dispatched("card-only-talk") is False


def test_empty_talk_never_suppresses():
    _reset()
    assert ds.talk_recently_dispatched("") is False
    ds.note_talk_dispatched("")  # no-op, must not raise


# ── Fix 2: authoritative card price replaces the ambiguous slim price ─────────

def _seed(goods_id, title, detail):
    import time
    with pds._lock:
        if goods_id:
            pds._by_goods[goods_id] = (time.time(), detail)
        if title:
            pds._by_title[title] = (time.time(), detail)


def test_slim_card_price_replaced_by_authoritative_detail(monkeypatch):
    monkeypatch.setenv("ECAN_FEIGE_CARD_JSON", "1")
    with pds._lock:
        pds._by_goods.clear()
        pds._by_title.clear()
    title = "童装男童夏装T恤2026新款中大童夏季男孩休闲上衣帅气儿童短袖潮t"
    auth = "价格:￥38.00(券后价) 原价:￥48.00 优惠:券立减10元 48小时内发货"
    _seed("3826537317292703863", title, auth)
    # Slim DOM card with an AMBIGUOUS price and no 商品ID (the named-lane form).
    slim = f"[商品卡片] {title} ￥38.00 (券:立减10元) 未发货极速退款"
    out = pds.enrich_card_text(slim)
    assert "券后价" in out and "原价:￥48.00" in out
    assert out.startswith("[商品卡片] " + title)


def test_card_without_stored_detail_is_unchanged(monkeypatch):
    monkeypatch.setenv("ECAN_FEIGE_CARD_JSON", "1")
    with pds._lock:
        pds._by_goods.clear()
        pds._by_title.clear()
    slim = "[商品卡片] 某未知商品 ￥9.90 (券:立减1元)"
    assert pds.enrich_card_text(slim) == slim


def test_non_card_text_untouched(monkeypatch):
    monkeypatch.setenv("ECAN_FEIGE_CARD_JSON", "1")
    assert pds.enrich_card_text("你好，在吗") == "你好，在吗"


def test_enrich_is_idempotent(monkeypatch):
    monkeypatch.setenv("ECAN_FEIGE_CARD_JSON", "1")
    with pds._lock:
        pds._by_goods.clear()
        pds._by_title.clear()
    title = "T恤"
    auth = "价格:￥38.00(券后价) 原价:￥48.00 优惠:券立减10元"
    _seed("g1", title, auth)
    once = pds.enrich_card_text(f"[商品卡片] {title} 商品ID:g1 | old")
    twice = pds.enrich_card_text(once)
    assert once == twice
