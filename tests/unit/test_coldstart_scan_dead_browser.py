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
