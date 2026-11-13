"""A "session:*" tap (the CLI's chat stream) copies every session push without changing who
else gets it: the GUI keeps the send-to-all fallback for sessions it has not subscribed to."""
import asyncio
import json

from gui.LocalServer import AppWebSocketManager


class _WS:
    def __init__(self):
        self.sent = []

    async def send_text(self, text):
        self.sent.append(json.loads(text))


def _mgr():
    m = object.__new__(AppWebSocketManager)      # a fresh one, not the app's singleton
    m._connections, m._all_connections, m._connection_timestamps = {}, set(), {}
    return m


def _join(m, ws, *channels):
    m._all_connections.add(ws)
    for ch in channels:
        m._connections.setdefault(ch, set()).add(ws)


def _send(m, channel):
    asyncio.run(m.broadcast({"type": "skill_editor.chat.stream_end", "payload": {"c": channel}}, channel))


def test_tap_does_not_take_the_fallback_from_the_gui():
    m, gui, cli = _mgr(), _WS(), _WS()
    _join(m, gui)
    _join(m, cli, "session:*")
    _send(m, "session:bg")                       # a background session nobody subscribed to
    assert [e["payload"]["c"] for e in gui.sent] == ["session:bg"]
    assert [e["payload"]["c"] for e in cli.sent] == ["session:bg"]   # once, not twice


def test_tap_gets_subscribed_sessions_too_and_others_do_not():
    m, gui, other, cli = _mgr(), _WS(), _WS(), _WS()
    _join(m, gui, "session:open")
    _join(m, other)
    _join(m, cli, "session:*")
    _send(m, "session:open")
    assert len(gui.sent) == 1 and len(cli.sent) == 1 and other.sent == []


def test_tap_ignores_other_prefixes_and_unchanneled_rules():
    m, gui, cli = _mgr(), _WS(), _WS()
    _join(m, gui, "lightrag:q1")
    _join(m, cli, "session:*")
    _send(m, "lightrag:q1")
    assert len(gui.sent) == 1 and cli.sent == []
