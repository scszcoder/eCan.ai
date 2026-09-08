"""ws196: a come-back-after-a-long-gap follow-up still carries the product.

2026-09-08: a customer left a chat and returned 99 min later; to us that's a
cold start, to them it's a natural follow-up ("会不会过敏") about the same item.
The 30-min pinned card had expired, so the LLM got no product and guessed
(answered price for an allergy question). The long-TTL conversation anchor keeps
the product available as a fallback well past the 30-min pin."""

import time

import agent.ec_skills.browser_use_extension.hooks.external.feige_chat.actionable_items as ai


def _reset():
    ai._pinned_card.clear()
    ai._conv_card.clear()
    ai._customer_recent_messages.clear()


CARD = "[商品卡片] 男童夏装T恤 商品ID:PID1 | 价格:￥38.00(券后价) 属性:面料材质=聚酯纤维100% 适用季节=夏季"


def test_comeback_after_30min_still_has_product(monkeypatch):
    monkeypatch.setenv("ECAN_FEIGE_CONV_CARD", "1")
    monkeypatch.setenv("ECAN_FEIGE_CARD_RESHARE", "1")
    _reset()
    ai.pin_card_detail(["陆地飞鱼"], CARD)
    # Age the 30-min pin past its TTL, keep the 6h conv anchor fresh (the 99-min gap).
    old = time.time() - (ai._PINNED_CARD_TTL_S + 600)
    ai._pinned_card["陆地飞鱼"] = (old, CARD)
    msgs = ai._get_recent_messages("陆地飞鱼")
    assert any("面料材质=聚酯纤维100%" in m for m in msgs), msgs


def test_conv_anchor_expires_after_its_own_ttl(monkeypatch):
    monkeypatch.setenv("ECAN_FEIGE_CONV_CARD", "1")
    monkeypatch.setenv("ECAN_FEIGE_CARD_RESHARE", "1")
    _reset()
    ai.pin_card_detail(["陆地飞鱼"], CARD)
    stale = time.time() - (ai._CONV_CARD_TTL_S + 600)
    ai._pinned_card["陆地飞鱼"] = (stale, CARD)
    ai._conv_card["陆地飞鱼"] = (stale, CARD)
    msgs = ai._get_recent_messages("陆地飞鱼")
    assert not any("面料材质" in m for m in msgs), msgs


def test_kill_switch_disables_anchor(monkeypatch):
    monkeypatch.setenv("ECAN_FEIGE_CONV_CARD", "0")
    monkeypatch.setenv("ECAN_FEIGE_CARD_RESHARE", "1")
    _reset()
    # With the anchor disabled, pin_card_detail must not populate _conv_card.
    ai.pin_card_detail(["陆地飞鱼"], CARD)
    old = time.time() - (ai._PINNED_CARD_TTL_S + 600)
    ai._pinned_card["陆地飞鱼"] = (old, CARD)
    msgs = ai._get_recent_messages("陆地飞鱼")
    assert not any("面料材质" in m for m in msgs), msgs


def test_fresh_pin_still_primary(monkeypatch):
    monkeypatch.setenv("ECAN_FEIGE_CONV_CARD", "1")
    monkeypatch.setenv("ECAN_FEIGE_CARD_RESHARE", "1")
    _reset()
    ai.pin_card_detail(["陆地飞鱼"], CARD)   # fresh — within 30 min
    msgs = ai._get_recent_messages("陆地飞鱼")
    # card present exactly once (no duplicate from pin + anchor)
    assert sum(1 for m in msgs if "面料材质=聚酯纤维100%" in m) == 1, msgs
