"""A store chore (not a live-chat run) never works in the store's chat tab
(2026-10-23 KEN: 抖店商品导出 browsed the 飞鸽 workspace tab to 商品管理)."""
import asyncio
import types

import pytest

from agent.ec_skills import live_chat_dispatch
from agent.ec_skills.browser_node import runner

CHAT = "https://im.jinritemai.com/pc_seller_v2/main/workspace"


class Session:
    def __init__(self, tabs, focus):
        self.tabs = {tid: types.SimpleNamespace(url=u, target_type="page") for tid, u in tabs.items()}
        self.agent_focus_target_id = focus
        self.events = []
        sess = self
        self.session_manager = types.SimpleNamespace(get_target=lambda t: sess.tabs.get(t),
                                                     get_all_targets=lambda: sess.tabs)

        async def dispatch(ev):
            sess.events.append(ev)
            if type(ev).__name__ == "SwitchTabEvent":
                sess.agent_focus_target_id = ev.target_id
            elif getattr(ev, "new_tab", False):
                sess.tabs["NEW"] = types.SimpleNamespace(url=ev.url, target_type="page")
                sess.agent_focus_target_id = "NEW"
        self.event_bus = types.SimpleNamespace(dispatch=dispatch)


def run(coro):
    return asyncio.run(coro)


def test_a_chore_moves_to_an_existing_non_chat_tab(monkeypatch):
    monkeypatch.setattr(live_chat_dispatch, "active_site", lambda: None)
    s = Session({"A": CHAT, "B": CHAT + "#ecan_det", "C": "https://fxg.jinritemai.com/ffa/g/list"}, "A")
    assert run(runner.step_off_live_chat_tab(s)) == "C" and s.agent_focus_target_id == "C"


def test_a_chore_opens_a_blank_tab_and_never_a_second_chat_page(monkeypatch):
    monkeypatch.setattr(live_chat_dispatch, "active_site", lambda: None)
    s = Session({"A": CHAT, "B": CHAT + "#ecan_det"}, "A")
    run(runner.step_off_live_chat_tab(s))
    assert s.agent_focus_target_id == "NEW" and s.tabs["NEW"].url == "about:blank"
    n = len(s.events)
    assert run(runner.navigate_blank_tab_to_store_url(s, {"prompt_refs": {"store_url": CHAT}})) is None
    assert len(s.events) == n and s.agent_focus_target_id == "NEW"   # no switch back, no chat page opened


def test_the_live_chat_run_itself_stays_put(monkeypatch):
    monkeypatch.setattr(live_chat_dispatch, "active_site", lambda: "feige_chat")
    s = Session({"A": CHAT, "C": "https://fxg.jinritemai.com/x"}, "A")
    assert run(runner.step_off_live_chat_tab(s)) is None and s.agent_focus_target_id == "A"
