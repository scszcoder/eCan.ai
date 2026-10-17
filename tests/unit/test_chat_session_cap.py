"""Chat-scoped browser sessions are capped (2026-10-13: the chip-docs crawler got a new
chat id per batch; 150 cached sessions and their worker threads crashed the app at 7.5 GB)."""
from types import SimpleNamespace

from agent.ec_skills.browser_node import build_helpers as bh


def test_oldest_chat_sessions_beyond_the_cap_are_released(monkeypatch):
    released = []

    def invalidate(session, *, reason, stop_worker=True):
        released.append(session.id)
        for k, v in list(bh.cached_browser_sessions.items()):
            if v is session:
                bh.cached_browser_sessions.pop(k)
        return True

    monkeypatch.setattr(bh, "invalidate_browser_session_for_recovery", invalidate)
    monkeypatch.setattr(bh, "MAX_CHAT_BROWSER_SESSIONS", 3)
    monkeypatch.setattr(bh, "cached_browser_sessions", {})
    bh.cached_browser_sessions["node:x"] = SimpleNamespace(id="node")
    for i in range(5):
        bh.cached_browser_sessions[f"chat:c{i}:crawler"] = SimpleNamespace(id=f"c{i}")
    assert bh.evict_excess_chat_sessions("chat:c4:crawler") == 2
    assert released == ["c0", "c1"]
    assert list(bh.cached_browser_sessions) == ["node:x", "chat:c2:crawler", "chat:c3:crawler", "chat:c4:crawler"]


def test_under_the_cap_nothing_is_released(monkeypatch):
    monkeypatch.setattr(bh, "invalidate_browser_session_for_recovery",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("released")))
    monkeypatch.setattr(bh, "cached_browser_sessions", {f"chat:c{i}": object() for i in range(3)})
    assert bh.evict_excess_chat_sessions("chat:c2") == 0
