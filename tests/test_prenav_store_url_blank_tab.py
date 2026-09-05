"""Pre-run navigation strategy 3: a BLANK focused tab + a deployed store URL
(prompt_refs.store_url) → open the store URL there / switch to an existing
store tab; a real page stays untouched (customer run 2026-09-04/05:
auto-started Chrome sat on about:blank for hours)."""

import asyncio
from types import SimpleNamespace

import pytest

from agent.ec_skills.browser_node import runner as R

STORE = "https://im.jinritemai.com/pc_seller_v2/main/workspace"


class _Bus:
    def __init__(self):
        self.events = []

    async def dispatch(self, ev):
        self.events.append(ev)


class _SM:
    def __init__(self, targets):
        self._t = targets

    def get_target(self, tid):
        return self._t.get(tid)

    def get_all_targets(self):
        return dict(self._t)


def _session(focus, targets):
    s = SimpleNamespace()
    s.agent_focus_target_id = focus
    s.session_manager = _SM(targets)
    s.event_bus = _Bus()

    async def _summary(include_screenshot=False):
        return {}
    s.get_browser_state_summary = _summary
    return s


def _tgt(url, ttype="page"):
    return SimpleNamespace(url=url, target_type=ttype)


def test_extract_store_url_sources():
    assert R.extract_store_url({"prompt_refs": {"store_url": STORE}}) == STORE
    assert R.extract_store_url({"prompt_refs": {"store_urls": [STORE, "x"]}}) == STORE
    assert R.extract_store_url({"prompt_refs": {"store_url": "not a url"}}) is None
    assert R.extract_store_url({"prompt_refs": {}}) is None
    assert R.extract_store_url(None) is None


def test_blank_tab_navigates_to_store_url(monkeypatch):
    monkeypatch.setattr(R.asyncio, "sleep", _fast_sleep)
    s = _session("T1", {"T1": _tgt("about:blank")})
    out = asyncio.run(R.navigate_blank_tab_to_store_url(s, {"prompt_refs": {"store_url": STORE}}))
    assert out == STORE
    assert len(s.event_bus.events) == 1
    ev = s.event_bus.events[0]
    assert type(ev).__name__ == "NavigateToUrlEvent" and ev.url == STORE and ev.new_tab is False


def test_blank_tab_switches_to_existing_store_tab(monkeypatch):
    monkeypatch.setattr(R.asyncio, "sleep", _fast_sleep)
    s = _session("T1", {"T1": _tgt("about:blank"), "T2": _tgt(STORE + "#x")})
    out = asyncio.run(R.navigate_blank_tab_to_store_url(s, {"prompt_refs": {"store_url": STORE}}))
    assert out == STORE
    ev = s.event_bus.events[0]
    assert type(ev).__name__ == "SwitchTabEvent" and ev.target_id == "T2"


def test_real_page_is_left_alone(monkeypatch):
    monkeypatch.setattr(R.asyncio, "sleep", _fast_sleep)
    s = _session("T1", {"T1": _tgt("https://fxg.jinritemai.com/ffa/mshop/homepage/index")})
    out = asyncio.run(R.navigate_blank_tab_to_store_url(s, {"prompt_refs": {"store_url": STORE}}))
    assert out is None and s.event_bus.events == []


def test_no_store_url_or_no_session_manager_is_noop():
    s = _session("T1", {"T1": _tgt("about:blank")})
    assert asyncio.run(R.navigate_blank_tab_to_store_url(s, {"prompt_refs": {}})) is None
    s.session_manager = None
    assert asyncio.run(R.navigate_blank_tab_to_store_url(s, {"prompt_refs": {"store_url": STORE}})) is None
    assert s.event_bus.events == []


async def _fast_sleep(_s):
    return None
