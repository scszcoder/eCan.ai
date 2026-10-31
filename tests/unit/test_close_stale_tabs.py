"""Tabs an earlier run left on the run's own pages are closed (拼多多 run 62)."""

import asyncio
from types import SimpleNamespace

from agent.ec_skills.browser_node import runner


def _session(urls, focus):
    sent = []
    targets = {tid: SimpleNamespace(target_type="page", url=u) for tid, u in urls.items()}

    async def dispatch(ev):
        sent.append(ev.target_id)
    return SimpleNamespace(session_manager=SimpleNamespace(get_all_targets=lambda: targets),
                           agent_focus_target_id=focus, event_bus=SimpleNamespace(dispatch=dispatch)), sent


def test_only_other_tabs_on_the_runs_pages_are_closed():
    s, sent = _session({"A": "https://mms.pinduoduo.com/goods/goods_add/index?id=1",     # focused: kept
                        "B": "https://mms.pinduoduo.com/goods/goods_add/index?id=2",     # stale: closed
                        "C": "https://mms.pinduoduo.com/chat-merchant/index.html",       # live chat: kept
                        "D": "https://mms.pinduoduo.com/goods/goods_list"}, focus="A")   # not matching: kept
    state = {"prompt_refs": {"close_tabs_matching": r"mms\.pinduoduo\.com/goods/(goods_add|category)"}}
    assert asyncio.run(runner.close_stale_tabs(s, state)) == 1 and sent == ["B"]


def test_nothing_is_closed_without_a_pattern():
    s, sent = _session({"B": "https://mms.pinduoduo.com/goods/goods_add"}, focus="A")
    assert asyncio.run(runner.close_stale_tabs(s, {"prompt_refs": {}})) == 0 and sent == []
