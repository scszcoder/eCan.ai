"""mt059 Phase 1: tests for the env-gated Feige WS-frame capture diagnostic.

The capture must:
  * be a no-op unless ECAN_FEIGE_WS_CAPTURE=1,
  * attach to the given target, enable Network, and register the three
    websocket event handlers on its OWN dedicated CDP client,
  * log received/sent frames with a text-vs-binary preview, skipping
    control frames (ping/pong/close).
"""
import base64
import logging
import os

import pytest

from agent.ec_skills.browser_use_extension import event_monitor as em


class _FakeRegistry:
    def __init__(self):
        self.handlers = {}

    def register(self, method, cb):
        self.handlers[method] = cb


class _FakeClient:
    def __init__(self, url):
        self.url = url
        self.started = False
        self.stopped = False
        self.calls = []
        self._event_registry = _FakeRegistry()

    async def start(self):
        self.started = True

    async def send_raw(self, method, params, session_id=None):
        self.calls.append((method, params, session_id))
        if method == "Target.attachToTarget":
            return {"sessionId": "sess-1"}
        return {}

    async def stop(self):
        self.stopped = True


class _FakeSession:
    cdp_url = "ws://127.0.0.1:9222/devtools/browser/abc"


@pytest.fixture
def fake_cdp(monkeypatch):
    created = {}

    def _factory(url):
        c = _FakeClient(url)
        created["client"] = c
        return c

    import cdp_use

    monkeypatch.setattr(cdp_use, "CDPClient", _factory)
    return created


async def test_capture_is_noop_when_env_unset(monkeypatch):
    monkeypatch.delenv("ECAN_FEIGE_WS_CAPTURE", raising=False)
    client = await em._start_feige_ws_frame_capture(_FakeSession(), "tid", "新消息")
    assert client is None


async def test_capture_registers_handlers_and_enables_network(monkeypatch, fake_cdp):
    monkeypatch.setenv("ECAN_FEIGE_WS_CAPTURE", "1")
    client = await em._start_feige_ws_frame_capture(_FakeSession(), "tid-123456", "新消息")
    assert client is fake_cdp["client"]
    # Network enabled on the attached session.
    assert ("Network.enable", {}, "sess-1") in client.calls
    # All three websocket handlers registered.
    h = client._event_registry.handlers
    assert "Network.webSocketCreated" in h
    assert "Network.webSocketFrameReceived" in h
    assert "Network.webSocketFrameSent" in h


async def test_capture_logs_text_and_binary_skips_control(monkeypatch, fake_cdp):
    monkeypatch.setenv("ECAN_FEIGE_WS_CAPTURE", "1")
    await em._start_feige_ws_frame_capture(_FakeSession(), "tid", "新消息")
    h = fake_cdp["client"]._event_registry.handlers
    h["Network.webSocketCreated"]({"requestId": "r1", "url": "wss://feige/ws"}, "sess-1")

    # The eCan logger sets propagate=False, so attach a collector directly.
    captured = []

    class _Collector(logging.Handler):
        def emit(self, record):
            captured.append(record.getMessage())

    eclogger = logging.getLogger("eCan")
    handler = _Collector(level=logging.INFO)
    eclogger.addHandler(handler)
    prev_level = eclogger.level
    eclogger.setLevel(logging.INFO)
    try:
        # text frame (opcode 1)
        h["Network.webSocketFrameReceived"](
            {"requestId": "r1", "response": {"opcode": 1, "payloadData": "hello-json"}}, "sess-1"
        )
        # binary frame (opcode 2) — base64 payload
        b64 = base64.b64encode(b"\x08\x96\x01protobuf").decode()
        h["Network.webSocketFrameReceived"](
            {"requestId": "r1", "response": {"opcode": 2, "payloadData": b64}}, "sess-1"
        )
        # ping (opcode 9) — must be skipped
        h["Network.webSocketFrameReceived"](
            {"requestId": "r1", "response": {"opcode": 9, "payloadData": ""}}, "sess-1"
        )
    finally:
        eclogger.removeHandler(handler)
        eclogger.setLevel(prev_level)

    msgs = [m for m in captured if "FEIGE-WS-CAPTURE" in m]
    text_logs = [m for m in msgs if "opcode=1" in m]
    bin_logs = [m for m in msgs if "opcode=2" in m]
    ping_logs = [m for m in msgs if "opcode=9" in m]
    assert text_logs and "text[" in text_logs[0] and "hello-json" in text_logs[0]
    assert bin_logs and "binary[" in bin_logs[0] and "head_hex=" in bin_logs[0]
    assert not ping_logs  # control frames skipped
