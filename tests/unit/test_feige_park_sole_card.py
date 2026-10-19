"""A parked card-only reply goes out once it is the only nameless card
conversation in its store (2026-10-19, store 三号: two card-only customers at
once -> ws173 rightly refused both, and both replies stayed parked until they
expired because neither conversation ever gained a name). Another store's
nameless card customer does not count -- its rows are in a different sidebar."""
import asyncio
import importlib
from types import SimpleNamespace
from unittest.mock import patch

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    dispatch_state, undeliverable,
)

from tests.unit.test_feige_park_flush_once import _Action

TALK, OTHER = "7698239095159489820", "7698238894856258845"


def _flush(population):
    opened, sent = [], []
    acts = {"feige_open_session": _Action(opened), "feige_send_message": _Action(sent)}
    acts["feige_open_session"].param_model = lambda **kw: SimpleNamespace(text=kw.get("customer_name"), **kw)
    ctrl = SimpleNamespace(registry=SimpleNamespace(registry=SimpleNamespace(actions=acts)))
    wss = SimpleNamespace(_k=lambda s: "shop", _talk_in_shop=lambda t, s: True,
                          name_for_talk=lambda t: "", ws_thread_snapshot=lambda *a, **k: {},
                          unnamed_card_talks=lambda shop=None, **k: list(population))
    with patch.dict("sys.modules", {
            "agent.ec_skills.browser_use_extension.extension_tools_service": SimpleNamespace(custom_controller=ctrl)}), \
            patch("agent.ec_skills.browser_use_extension.hooks.external.feige_chat.ws_session", wss, create=True):
        delivered = asyncio.run(undeliverable.resolve_and_flush(object()))
    return delivered, opened, sent


def _park():
    undeliverable._PARKED.clear()
    dispatch_state.recent_agent_replies_by_customer.clear()
    undeliverable.park(f"card:{TALK}", "您好，这款男童篮球服券后55.9元，明天发货。")


def test_two_nameless_cards_stay_parked():
    _park()
    delivered, opened, sent = _flush([TALK, OTHER])
    assert (delivered, sent) == (0, []) and TALK in undeliverable._PARKED


def test_sole_nameless_card_is_delivered_by_its_card_row():
    _park()
    delivered, opened, sent = _flush([TALK])          # the other one got a name / left
    assert delivered == 1 and sent == ["您好，这款男童篮球服券后55.9元，明天发货。"]
    assert opened == []                                # no open-by-name: there is no name
    assert TALK not in undeliverable._PARKED


def test_aged_out_self_with_no_other_card_is_delivered():
    _park()
    delivered, _, sent = _flush([])                    # its own card left the 120 s window
    assert delivered == 1 and sent


def test_population_is_per_store(monkeypatch):
    ws = importlib.import_module("agent.ec_skills.browser_use_extension.hooks.external.feige_chat.ws_session")
    import time
    now = time.time() * 1000
    monkeypatch.setattr(ws, "_first_shop", [""])
    monkeypatch.setattr(ws, "_shops", {})
    a = ws.register_shop("profile:fp-store2")
    b = ws.register_shop("profile:fp-store3")
    card = lambda: {"cust": {"text": "[商品卡片] x", "type": "template_card", "ts": now}}
    monkeypatch.setattr(ws, "_thread", {"t2": card(), "t3": card()})
    monkeypatch.setattr(ws, "_talk_to_name", {})
    monkeypatch.setattr(ws, "_shop_by_talk", {"t2": a, "t3": b})
    assert sorted(ws.unnamed_card_talks()) == ["t2", "t3"]          # process-wide, as before
    assert ws.unnamed_card_talks(shop=a) == ["t2"]
    assert ws.unnamed_card_talks(shop=b) == ["t3"]
