"""ws126 (2): scrape_latest_customer_bubble must NOT run the doomed sidebar-click
eval for an unresolvable synthetic ``card:<talk_id>`` identity — that row never
exists by name, so the eval is guaranteed to miss (ws124 logged it x24) and only
wastes a main-tab CDP eval + disturbs focus (the card-identity self-block).

The unresolvable path short-circuits BEFORE the scrape imports/tab-reachable/eval,
so it is cleanly testable with a dummy session.
"""
import asyncio

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    dom_assets,
    ws_session,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_unresolvable_card_identity_short_circuits(monkeypatch):
    # talk->name map has nothing for this talk_id -> unresolvable.
    monkeypatch.setattr(ws_session, "name_for_talk", lambda _t: "")
    monkeypatch.delenv("ECAN_FEIGE_SCRAPE_CARD_SHORT_CIRCUIT", raising=False)

    res = _run(
        dom_assets.scrape_latest_customer_bubble(object(), "card:7656793265634575626")
    )

    assert res["scrape_ok"] is False
    assert res["skip_reason"] == "unresolvable_card_identity"


def test_card_that_resolves_is_not_short_circuited(monkeypatch):
    # A resolvable card identity must NOT take the immediate short-circuit return —
    # it should fall through to the normal scrape path (which, with a dummy session,
    # returns empty WITHOUT the "unresolvable_card_identity" skip_reason).
    monkeypatch.setattr(ws_session, "name_for_talk", lambda _t: "陆地飞鱼")
    monkeypatch.delenv("ECAN_FEIGE_SCRAPE_CARD_SHORT_CIRCUIT", raising=False)

    res = _run(
        dom_assets.scrape_latest_customer_bubble(object(), "card:7656793265634575626")
    )

    assert res["scrape_ok"] is False
    assert res.get("skip_reason") != "unresolvable_card_identity"
