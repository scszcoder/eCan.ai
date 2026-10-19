"""The Feige cold-start recovery scan runs every ~5 s per store. With the store's
browser dead (no SessionManager / root CDP client) every probe failed -- ~24k
failed evals in 16 h (customer 2026-10-18). It must skip without probing and
say so once, and resume once the browser is back."""
import asyncio
from types import SimpleNamespace

import importlib

import pytest

_PKG = "agent.ec_skills.browser_use_extension.hooks.external.feige_chat"
fd = None


@pytest.fixture
def probes(monkeypatch):
    calls = []

    async def fake_reachable(sess):
        calls.append(sess)
        return False

    global fd
    # Look the modules up now: other test files may have replaced them in sys.modules.
    fd = importlib.import_module(_PKG + ".front_desk")
    monkeypatch.setenv("ECAN_FEIGE_COLDSTART_RECOVERY_SCRAPE", "1")
    monkeypatch.setattr(importlib.import_module(_PKG + ".dom_assets"), "ensure_feige_tab_reachable", fake_reachable)
    fd._COLDSTART_DEAD_SESSIONS.clear()
    return calls


def _scan(sess):
    return asyncio.run(fd.coldstart_overdue_recovery_scan(legacy_dispatcher=lambda item: None,
                                                          browser_session=sess))


def test_dead_browser_is_not_probed_and_is_reported_once(probes, monkeypatch):
    warned = []
    monkeypatch.setattr(fd.logger, "warning", lambda msg, *a, **k: warned.append(msg))
    dead = SimpleNamespace(session_manager=None, _cdp_client_root=None)
    assert _scan(dead) == 0 and _scan(dead) == 0 and _scan(dead) == 0
    assert probes == []                                   # no probe against a dead browser
    assert sum("scan paused" in m for m in warned) == 1   # said once, not every tick


def test_live_browser_is_probed_again(probes):
    sess = SimpleNamespace(session_manager=None, _cdp_client_root=None)
    _scan(sess)
    sess.session_manager, sess._cdp_client_root = object(), object()   # browser came back
    _scan(sess)
    assert probes == [sess]
    assert id(sess) not in fd._COLDSTART_DEAD_SESSIONS


def test_two_front_desks_on_one_store_are_reported_once(probes, monkeypatch):
    warned = []
    monkeypatch.setattr(fd.logger, "warning", lambda msg, *a, **k: warned.append(msg))
    monkeypatch.setattr(fd, "_FEIGE_FD_DISPATCH_REG_BY_SHOP", {})
    monkeypatch.setattr(fd, "_SHARED_STORE_WARNED", set())
    zhang = SimpleNamespace(card=SimpleNamespace(name="前台小张", id="a1"))
    san = SimpleNamespace(card=SimpleNamespace(name="前台-抖音三号", id="a2"))
    fd._set_fd_slot("douyin-167bb80f-login", (None, None, zhang))
    fd._set_fd_slot("douyin-167bb80f-login", (None, None, zhang))   # same agent again: fine
    assert warned == []
    fd._set_fd_slot("douyin-167bb80f-login", (None, None, san))
    fd._set_fd_slot("douyin-167bb80f-login", (None, None, san))
    assert len(warned) == 1 and "前台小张" in warned[0] and "前台-抖音三号" in warned[0]


def test_two_stores_do_not_reset_each_other_s_row_ages(monkeypatch):
    """2026-10-19: each store's scan GC dropped the other store's keys, so no row
    ever aged past the stale gate and the safety net routed nothing in either
    store for minutes (store 三号: not_stale_yet x3 from 12:59 to the end)."""
    fd_ = importlib.import_module(_PKG + ".front_desk")
    monkeypatch.setattr(fd_, "_BACKSTOP_FIRST_SEEN", {})
    monkeypatch.setattr(fd_, "_BACKSTOP_ROUTED", set())
    k2 = ("profile:store2", "packet", "这款牙线有草莓味的吗？")
    k3 = ("profile:store3", "packet", "[商品]")
    fd_._BACKSTOP_FIRST_SEEN.update({k2: 1.0, k3: 2.0})
    fd_._backstop_gc("profile:store2", {k2})          # store 二号's scan
    fd_._backstop_gc("profile:store3", {k3})          # store 三号's scan
    assert fd_._BACKSTOP_FIRST_SEEN == {k2: 1.0, k3: 2.0}   # first-seen times survive
    fd_._backstop_gc("profile:store2", set())         # the row left store 二号's sidebar
    assert k2 not in fd_._BACKSTOP_FIRST_SEEN and k3 in fd_._BACKSTOP_FIRST_SEEN
