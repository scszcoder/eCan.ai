"""
Poll-Based Chat Message Capture -- Test Rig
============================================

Tests CDP Network interception for detecting incoming chat messages in
HTTP-polling-based chat applications (no WebSocket).

Many enterprise CRM / merchant-side platforms use HTTP long-polling or
short-polling instead of WebSockets.  This test rig validates the
PollingCapture utility class that intercepts those polling responses via
Chrome DevTools Protocol (CDP) Network domain events.

Architecture
------------

    Browser (chat page)
        |
        |  POST /batch_get_params  (every 2s)
        v
    Local HTTP Server (simulated chat backend)
        |
        |  response JSON: { messages: [...], has_new: true }
        v
    CDP Network handlers (registered by PollingCapture)
        |
        |  Network.requestWillBeSent  --> track matching URLs
        |  Network.responseReceived   --> record status
        |  Network.loadingFinished    --> fetch body, run content filters
        v
    Callbacks: on_response(url, method, status, body)
               on_message(url, method, status, body, rule)

How to Structure Your eCan.ai Skill for Poll-Based Chat
--------------------------------------------------------

Option A: browser_event subscription (recommended)
    Use the existing subscribe_browser_event MCP tool:

    Skill diagram:
        [start] --> [browser_automation: navigate to CRM chat page]
                --> [browser_automation: call subscribe_browser_event
                     domain=Network, event_method=Network.responseReceived,
                     label="chat_poll",
                     filter_expr="url contains 'batch_get_params'"]
                --> [pend_event: eventType=browser_event,
                     browserEventLabel="chat_poll"]
                --> [browser_automation: read the new messages from
                     state.attributes.browser_event.params,
                     compose reply, inject via DOM]
                --> loop back to pend_event

    The pend_event node will fire every time a polling response matches.
    The CDP params (including response URL) land in
    state.attributes.browser_event.params via the mapping DSL.

    To also get the response BODY (not just headers), you need a two-step
    approach: subscribe to Network.loadingFinished, then in the browser_automation
    node that runs after pend_event fires, call Network.getResponseBody via
    a run_code action.  Or use Option B.

Option B: PollingCapture in a code node (direct CDP, more control)
    Use a code node to instantiate PollingCapture directly:

    Skill diagram:
        [start] --> [browser_automation: navigate to CRM chat page]
                --> [code: set up PollingCapture with asyncio.Queue]
                --> [pend_event: eventType=timer, timerName="poll_check"]
                --> [code: drain the queue, process new messages]
                --> [browser_automation: inject reply into chat DOM]
                --> loop back to pend_event

    The PollingCapture pushes matched messages into an asyncio.Queue.
    A timer fires periodically; the code node drains the queue and
    processes any new messages.

Option C: Pure DOM observation (simplest, app-agnostic)
    Skip network interception entirely.  Use a timer + DOM extraction:

    Skill diagram:
        [start] --> [browser_automation: navigate to CRM chat page]
                --> [pend_event: eventType=timer, timerName="dom_check",
                     interval=3s]
                --> [browser_automation: extract_dom or evaluate JS to
                     read #chat-box children, diff against last known count]
                --> [browser_automation: if new messages, compose + inject reply]
                --> loop back to pend_event

    Pros: No CDP setup, works on any chat app.
    Cons: Higher latency (timer interval), more DOM parsing.

Usage:
    python -m pytest tests/test_polling_capture.py -v -s
    python -m pytest tests/test_polling_capture.py::TestPollingCapture -v -s
    python -m pytest tests/test_polling_capture.py::TestMultiTabPolling -v -s
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import socketserver
import sys
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

import pytest

if TYPE_CHECKING:
    from browser_use import BrowserSession
    from browser_use.browser.events import NavigateToUrlEvent
    from browser_use.browser.profile import BrowserProfile


# =====================================================================
# PollingCapture -- pure user-land CDP network interception
# =====================================================================
#
# Production classes live in:
#   agent/ec_skills/browser_use_extension/polling_capture.py
# Imported here for test usage.
# =====================================================================

_BROWSER_SESSION_CLS: Any = None
_BROWSER_PROFILE_CLS: Any = None
NavigateToUrlEvent: Any = None
PollingCapture: Any = None
PollingCaptureConfig: Any = None


def _ensure_browser_use_available() -> tuple[Any, Any, Any]:
    """Import browser_use lazily to avoid collection-time hard aborts."""
    global _BROWSER_SESSION_CLS, _BROWSER_PROFILE_CLS, NavigateToUrlEvent

    if _BROWSER_SESSION_CLS and _BROWSER_PROFILE_CLS and NavigateToUrlEvent:
        return _BROWSER_SESSION_CLS, _BROWSER_PROFILE_CLS, NavigateToUrlEvent

    # browser_use may hard-abort the Python process in non-GUI runtimes on macOS.
    # Require explicit opt-in so default test runs remain stable.
    if os.environ.get("ECAN_ENABLE_BROWSER_USE_TESTS") != "1":
        pytest.skip(
            "Skipping browser_use integration tests by default. "
            "Set ECAN_ENABLE_BROWSER_USE_TESTS=1 to enable.",
            allow_module_level=True,
        )

    try:
        from browser_use import BrowserSession as _BrowserSession
        from browser_use.browser.events import NavigateToUrlEvent as _NavigateToUrlEvent
        from browser_use.browser.profile import BrowserProfile as _BrowserProfile
    except BaseException as exc:
        pytest.skip(
            f"browser_use unavailable in current runtime (skipping integration tests): {exc}",
            allow_module_level=True,
        )

    _BROWSER_SESSION_CLS = _BrowserSession
    _BROWSER_PROFILE_CLS = _BrowserProfile
    NavigateToUrlEvent = _NavigateToUrlEvent
    return _BROWSER_SESSION_CLS, _BROWSER_PROFILE_CLS, NavigateToUrlEvent


def _ensure_polling_capture_available() -> tuple[Any, Any]:
    """Import PollingCapture lazily (it transitively imports browser_use)."""
    global PollingCapture, PollingCaptureConfig
    if PollingCapture and PollingCaptureConfig:
        return PollingCapture, PollingCaptureConfig
    try:
        from agent.ec_skills.browser_use_extension.polling_capture import (
            PollingCapture as _PollingCapture,
            PollingCaptureConfig as _PollingCaptureConfig,
        )
    except BaseException as exc:
        pytest.skip(
            f"polling_capture runtime unavailable (skipping integration tests): {exc}",
            allow_module_level=True,
        )
    PollingCapture = _PollingCapture
    PollingCaptureConfig = _PollingCaptureConfig
    return PollingCapture, PollingCaptureConfig


# =====================================================================
# Simulated Chat Backend (HTTP polling, no WebSocket)
# =====================================================================


# Per-session message stores (keyed by session_id)
_CHAT_STORES: Dict[str, List[dict]] = {}
_POLL_COUNTS: Dict[str, int] = {}


def _get_store(session_id: str) -> List[dict]:
    if session_id not in _CHAT_STORES:
        _CHAT_STORES[session_id] = []
    return _CHAT_STORES[session_id]


def _add_message(session_id: str, msg: dict):
    store = _get_store(session_id)
    store.append(msg)


def _reset_stores():
    _CHAT_STORES.clear()
    _POLL_COUNTS.clear()


class _PollingChatHandler(BaseHTTPRequestHandler):
    """Simulates a chat backend with batch_get_params polling endpoint."""

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length).decode("utf-8") if content_length else ""
        try:
            body_json = json.loads(raw_body) if raw_body else {}
        except json.JSONDecodeError:
            body_json = {}

        session_id = body_json.get("session_id", "default")

        if "/batch_get_params" in path:
            if session_id not in _POLL_COUNTS:
                _POLL_COUNTS[session_id] = 0
            _POLL_COUNTS[session_id] += 1

            messages = _get_store(session_id)
            response = json.dumps({
                "status": "ok",
                "poll_seq": _POLL_COUNTS[session_id],
                "messages": messages,
                "has_new": len(messages) > 0,
                "session_id": session_id,
            })
            self._json_response(200, response)

        elif "/send_msg" in path:
            # Agent sending a reply
            text = body_json.get("text", "")
            msg = {
                "msg_id": body_json.get("msg_id", str(int(time.time() * 1000))),
                "from": "agent",
                "text": text,
                "timestamp": int(time.time() * 1000),
            }
            _add_message(session_id, msg)
            self._json_response(200, json.dumps({"status": "sent", "msg_id": msg["msg_id"]}))

        elif "/report_frontend" in path:
            # Telemetry endpoint -- just acknowledge
            self._json_response(200, json.dumps({"status": "ok"}))

        else:
            self.send_error(404, "Not found")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/" or path == "/chat":
            session_id = params.get("session", ["default"])[0]
            html = CHAT_POLLING_HTML.replace("{{SESSION_ID}}", session_id)
            self._html_response(200, html)
        else:
            self.send_error(404, "Not found")

    def _json_response(self, code: int, body: str):
        content = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _html_response(self, code: int, body: str):
        content = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, fmt, *args):
        pass  # suppress noise


CHAT_POLLING_HTML = """
<!DOCTYPE html>
<html>
<head><title>Simulated Chat (HTTP Polling)</title></head>
<body style="font-family: sans-serif; max-width: 600px; margin: 40px auto;">
    <h2 id="title">Simulated Chat (HTTP Polling)</h2>
    <div id="session-id" style="color: #999; font-size: 12px;">Session: {{SESSION_ID}}</div>
    <div id="chat-box"
         style="border: 1px solid #ccc; padding: 16px; min-height: 200px;
                margin: 16px 0; border-radius: 8px; background: #f9f9f9;">
    </div>
    <div style="display: flex; gap: 8px;">
        <input id="msg-input" type="text" placeholder="Type a message..."
               style="flex: 1; padding: 8px; border: 1px solid #ccc; border-radius: 4px;" />
        <button onclick="sendMessage()"
                style="padding: 8px 16px; background: #007bff; color: white;
                       border: none; border-radius: 4px; cursor: pointer;">Send</button>
    </div>
    <div id="poll-count" style="color: #999; font-size: 12px; margin-top: 8px;">Polls: 0</div>
    <div id="msg-count" style="color: #999; font-size: 12px;">Messages: 0</div>
    <script>
        const SESSION_ID = '{{SESSION_ID}}';
        let lastMsgCount = 0;
        let pollCount = 0;

        async function pollMessages() {
            try {
                const resp = await fetch('/batch_get_params?ts=' + Date.now(), {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({session_id: SESSION_ID})
                });
                const data = await resp.json();
                pollCount++;
                document.getElementById('poll-count').textContent = 'Polls: ' + pollCount;

                if (data.messages && data.messages.length > lastMsgCount) {
                    const chatBox = document.getElementById('chat-box');
                    for (let i = lastMsgCount; i < data.messages.length; i++) {
                        const msg = data.messages[i];
                        const div = document.createElement('div');
                        div.className = 'msg ' + msg.from;
                        div.setAttribute('data-msg-id', msg.msg_id);
                        div.style.cssText =
                            'padding: 8px 12px; margin: 4px 0; border-radius: 12px; max-width: 80%;';
                        if (msg.from === 'customer') {
                            div.style.cssText +=
                                'background: #e3f2fd; margin-right: auto;';
                        } else {
                            div.style.cssText +=
                                'background: #c8e6c9; margin-left: auto; text-align: right;';
                        }
                        div.textContent = msg.text;
                        chatBox.appendChild(div);
                    }
                    lastMsgCount = data.messages.length;
                    document.getElementById('msg-count').textContent =
                        'Messages: ' + lastMsgCount;
                    chatBox.scrollTop = chatBox.scrollHeight;
                }
            } catch (e) {
                console.error('Poll error:', e);
            }
        }

        async function sendMessage() {
            const input = document.getElementById('msg-input');
            const text = input.value.trim();
            if (!text) return;
            input.value = '';
            await fetch('/send_msg', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    text: text,
                    from: 'agent',
                    msg_id: '' + Date.now(),
                    session_id: SESSION_ID
                })
            });
        }

        setInterval(pollMessages, 2000);
        pollMessages();
    </script>
</body>
</html>
"""


class _ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


# =====================================================================
# Fixtures
# =====================================================================


@pytest.fixture(scope="session")
def polling_server():
    """Start a threaded HTTP server simulating a polling chat backend."""
    _reset_stores()
    server = _ThreadedHTTPServer(("127.0.0.1", 0), _PollingChatHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()


@pytest.fixture(scope="session")
def poll_base_url(polling_server):
    host, port = polling_server.server_address
    return f"http://{host}:{port}"


@pytest.fixture(scope="function")
async def browser_session():
    BrowserSession, BrowserProfile, _ = _ensure_browser_use_available()
    _ensure_polling_capture_available()
    session = BrowserSession(
        browser_profile=BrowserProfile(
            headless=True,
            user_data_dir=None,
            keep_alive=False,
        )
    )
    await session.start()
    # Let CDP WebSocket reconnection settle (happens once after startup)
    await asyncio.sleep(3)
    yield session
    await session.kill()


# =====================================================================
# Tests
# =====================================================================


class TestPollingCapture:
    """Core tests for the PollingCapture utility."""

    async def test_captures_polling_responses(
        self, browser_session: BrowserSession, poll_base_url: str
    ):
        """PollingCapture should intercept matching HTTP polling responses."""
        _reset_stores()
        session_id = "capture_test_001"

        config = PollingCaptureConfig(
            url_patterns=[r"/batch_get_params"],
            methods=["POST"],
            min_body_length=10,
        )

        # Navigate first, then start capture (navigation resets page CDP session)
        bus = browser_session.event_bus
        await bus.dispatch(
            NavigateToUrlEvent(
                url=f"{poll_base_url}/chat?session={session_id}",
                wait_until="commit",
            )
        )
        await asyncio.sleep(1)

        capture = PollingCapture(session=browser_session, config=config)
        await capture.start()

        # Wait for a few poll cycles
        await asyncio.sleep(7)

        print(f"\n[TEST] Captured {capture.captured_count} polling responses")
        assert capture.captured_count >= 2, (
            f"Expected at least 2 captured responses, got {capture.captured_count}"
        )

        # Verify captured response structure
        for resp in capture.captured_responses[:3]:
            assert "/batch_get_params" in resp["url"]
            assert resp["method"] == "POST"
            assert resp["status"] == 200
            assert len(resp["body"]) > 0
            data = json.loads(resp["body"])
            assert data["status"] == "ok"
            assert "poll_seq" in data

        print(f"[TEST] First response body preview: {capture.captured_responses[0]['body'][:120]}")

    async def test_content_filter_matches_new_messages(
        self, browser_session: BrowserSession, poll_base_url: str
    ):
        """Content filters should detect when polling responses contain new messages."""
        _reset_stores()
        session_id = "filter_test_001"

        matched_queue: asyncio.Queue = asyncio.Queue()

        def on_message(url, method, status, body, rule):
            matched_queue.put_nowait({
                "url": url, "body": body, "rule": rule
            })

        config = PollingCaptureConfig(
            url_patterns=[r"/batch_get_params"],
            methods=["POST"],
            content_filters=[
                lambda body: (
                    "new_message"
                    if '"has_new": true' in body and '"msg_id"' in body
                    else None
                ),
            ],
            min_body_length=10,
        )

        # Navigate first, then start capture
        bus = browser_session.event_bus
        await bus.dispatch(
            NavigateToUrlEvent(
                url=f"{poll_base_url}/chat?session={session_id}",
                wait_until="commit",
            )
        )
        await asyncio.sleep(1)

        capture = PollingCapture(
            session=browser_session,
            config=config,
            on_message=on_message,
        )
        await capture.start()

        # Wait for initial empty polls
        await asyncio.sleep(4)
        assert matched_queue.empty(), "Should have no matches before any messages exist"

        # Simulate incoming customer message
        _add_message(session_id, {
            "msg_id": "msg_2001",
            "from": "customer",
            "text": "Hi, I need help with order #54321",
            "timestamp": int(time.time() * 1000),
        })
        print("\n[SIM] Customer sent: 'Hi, I need help with order #54321'")

        # Wait for next poll cycle to pick it up
        await asyncio.sleep(4)

        assert not matched_queue.empty(), "Content filter should have matched the new message"
        match = matched_queue.get_nowait()
        assert match["rule"] == "new_message"
        body_data = json.loads(match["body"])
        assert any(m["msg_id"] == "msg_2001" for m in body_data["messages"])

        print(f"[TEST] Message detected via content filter: rule={match['rule']}")
        print(f"[TEST] Total captured: {capture.captured_count}, matched: {capture.matched_count}")

    async def test_multiple_messages_detected_sequentially(
        self, browser_session: BrowserSession, poll_base_url: str
    ):
        """Multiple incoming messages should each trigger content filter matches."""
        _reset_stores()
        session_id = "multi_msg_001"

        config = PollingCaptureConfig(
            url_patterns=[r"/batch_get_params"],
            methods=["POST"],
            content_filters=[
                lambda body: (
                    "new_message"
                    if '"has_new": true' in body and '"msg_id"' in body
                    else None
                ),
            ],
            min_body_length=10,
        )

        bus = browser_session.event_bus

        # Navigate first, then start capture (navigation can reset CDP session)
        await bus.dispatch(
            NavigateToUrlEvent(
                url=f"{poll_base_url}/chat?session={session_id}",
                wait_until="commit",
            )
        )
        await asyncio.sleep(1)

        capture = PollingCapture(session=browser_session, config=config)
        await capture.start()

        # Wait for initial polls to confirm capture is working
        await asyncio.sleep(5)
        print(f"\n[TEST] Pre-message captured: {capture.captured_count}")

        # Send 3 messages at intervals
        messages = [
            ("msg_3001", "What's the status of my return?"),
            ("msg_3002", "Can I get a refund instead?"),
            ("msg_3003", "Thanks for checking!"),
        ]

        for msg_id, text in messages:
            await asyncio.sleep(3)  # wait for at least one poll cycle between messages
            _add_message(session_id, {
                "msg_id": msg_id,
                "from": "customer",
                "text": text,
                "timestamp": int(time.time() * 1000),
            })
            print(f"  [SIM] Customer sent: '{text}'")

        # Wait for final poll to pick up last message
        await asyncio.sleep(5)

        print(f"\n[TEST] Total captured: {capture.captured_count}")
        print(f"[TEST] Total matched: {capture.matched_count}")
        # After first message, every subsequent poll with messages should match
        assert capture.matched_count >= 3, (
            f"Expected at least 3 content filter matches, got {capture.matched_count}"
        )

    async def test_url_pattern_filtering(
        self, browser_session: BrowserSession, poll_base_url: str
    ):
        """Only URLs matching the configured patterns should be captured."""
        _reset_stores()
        session_id = "url_filter_001"

        config = PollingCaptureConfig(
            # Only capture send_msg, NOT batch_get_params
            url_patterns=[r"/send_msg"],
            methods=["POST"],
            min_body_length=5,
        )

        # Navigate first, then start capture
        bus = browser_session.event_bus
        await bus.dispatch(
            NavigateToUrlEvent(
                url=f"{poll_base_url}/chat?session={session_id}",
                wait_until="commit",
            )
        )
        await asyncio.sleep(1)

        capture = PollingCapture(session=browser_session, config=config)
        await capture.start()

        # Let several batch_get_params polls fire (should NOT be captured)
        await asyncio.sleep(5)

        # The polling requests to /batch_get_params should be ignored
        poll_captures = [
            r for r in capture.captured_responses if "/batch_get_params" in r["url"]
        ]
        assert len(poll_captures) == 0, (
            f"batch_get_params should NOT be captured, but got {len(poll_captures)}"
        )

        print(f"\n[TEST] Correctly filtered: {capture.captured_count} captures "
              f"(all /send_msg only)")

    async def test_send_msg_capture(
        self, browser_session: BrowserSession, poll_base_url: str
    ):
        """Outbound agent messages via /send_msg should be capturable."""
        _reset_stores()
        session_id = "send_test_001"

        config = PollingCaptureConfig(
            url_patterns=[r"/send_msg"],
            methods=["POST"],
            min_body_length=5,
        )

        # Navigate first, then start capture
        bus = browser_session.event_bus
        await bus.dispatch(
            NavigateToUrlEvent(
                url=f"{poll_base_url}/chat?session={session_id}",
                wait_until="commit",
            )
        )
        await asyncio.sleep(1)

        capture = PollingCapture(session=browser_session, config=config)
        await capture.start()
        await asyncio.sleep(1)

        # Trigger a send_msg by injecting JS into the page
        cdp_session = await browser_session.get_or_create_cdp_session()
        js = """
            fetch('/send_msg', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    text: 'Test reply from agent',
                    from: 'agent',
                    msg_id: 'agent_reply_001',
                    session_id: '%s'
                })
            });
        """ % session_id
        await cdp_session.cdp_client.send.Runtime.evaluate(
            params={"expression": js},
            session_id=cdp_session.session_id,
        )

        await asyncio.sleep(2)

        send_captures = [
            r for r in capture.captured_responses if "/send_msg" in r["url"]
        ]
        assert len(send_captures) >= 1, "Should capture the /send_msg request"

        body_data = json.loads(send_captures[0]["body"])
        assert body_data["status"] == "sent"
        print(f"\n[TEST] Captured outbound send_msg: {body_data}")


class TestMultiTabPolling:
    """Test polling capture across multiple browser tabs (multi-customer)."""

    async def test_polling_across_tabs(
        self, browser_session: BrowserSession, poll_base_url: str
    ):
        """PollingCapture should detect messages from the active tab's polling.

        NOTE: Chrome throttles setInterval in background tabs, so only the
        active (last-opened) tab actually polls.  We verify that capture
        works across tab creation and that the active tab's polls are
        intercepted correctly.
        """
        _reset_stores()

        config = PollingCaptureConfig(
            url_patterns=[r"/batch_get_params"],
            methods=["POST"],
            content_filters=[
                lambda body: (
                    "new_message"
                    if '"has_new": true' in body and '"msg_id"' in body
                    else None
                ),
            ],
            min_body_length=10,
        )

        bus = browser_session.event_bus

        # Open 3 chat tabs with different sessions
        # The last tab (cust_C) will be the active one
        sessions = ["cust_A", "cust_B", "cust_C"]
        for sid in sessions:
            await bus.dispatch(
                NavigateToUrlEvent(
                    url=f"{poll_base_url}/chat?session={sid}",
                    new_tab=True,
                    wait_until="commit",
                )
            )
            await asyncio.sleep(1)

        # Start capture AFTER all tabs are open (navigation resets CDP sessions)
        capture = PollingCapture(session=browser_session, config=config)
        await capture.start()

        # Wait for initial polls (only active tab cust_C polls reliably)
        await asyncio.sleep(5)
        initial_captured = capture.captured_count
        print(f"\n[TEST] Initial captures from active tab: {initial_captured}")
        assert initial_captured >= 1, "Should capture polling from the active tab"

        # Send message to the active tab's session (cust_C)
        _add_message("cust_C", {
            "msg_id": "tabC_001",
            "from": "customer",
            "text": "Question from customer C",
            "timestamp": int(time.time() * 1000),
        })

        await asyncio.sleep(5)

        # Should have captured more responses and at least one match
        assert capture.captured_count > initial_captured
        assert capture.matched_count >= 1, (
            f"Expected at least 1 match for customer C's message, got {capture.matched_count}"
        )

        # Verify the matched message contains customer C's data
        c_matches = [
            m for m in capture.matched_messages
            if "tabC_001" in m["body"]
        ]
        assert len(c_matches) >= 1, "Match should contain customer C's msg_id"

        print(f"[TEST] Captured: {capture.captured_count}, Matched: {capture.matched_count}")
        print(f"[TEST] Customer C matches: {len(c_matches)}")


class TestPollingCaptureIntegration:
    """Integration tests demonstrating eCan.ai skill patterns."""

    async def test_detect_and_respond_workflow(
        self, browser_session: BrowserSession, poll_base_url: str
    ):
        """
        Simulates the full detect-and-respond workflow:
        1. Navigate to chat page
        2. Start polling capture
        3. Customer sends a message (simulated server-side)
        4. Capture detects the message
        5. Agent composes a reply
        6. Reply is injected via /send_msg
        7. Verify reply appears in chat store

        This mirrors the eCan.ai skill workflow described in the module docstring.
        """
        _reset_stores()
        session_id = "workflow_001"

        # Step 1: Set up capture with message queue
        reply_trigger: asyncio.Event = asyncio.Event()
        detected_messages: List[dict] = []

        def on_message(url, method, status, body, rule):
            try:
                data = json.loads(body)
                for msg in data.get("messages", []):
                    if msg["from"] == "customer" and msg["msg_id"] not in [
                        d.get("msg_id") for d in detected_messages
                    ]:
                        detected_messages.append(msg)
                        reply_trigger.set()
            except Exception:
                pass

        config = PollingCaptureConfig(
            url_patterns=[r"/batch_get_params"],
            methods=["POST"],
            content_filters=[
                lambda body: (
                    "new_message"
                    if '"has_new": true' in body and '"from": "customer"' in body
                    else None
                ),
            ],
            min_body_length=10,
        )

        # Step 2: Navigate to chat page first (navigation resets CDP session)
        bus = browser_session.event_bus
        await bus.dispatch(
            NavigateToUrlEvent(
                url=f"{poll_base_url}/chat?session={session_id}",
                wait_until="commit",
            )
        )
        await asyncio.sleep(1)

        capture = PollingCapture(
            session=browser_session,
            config=config,
            on_message=on_message,
        )
        await capture.start()
        await asyncio.sleep(3)

        # Step 3: Simulate customer message
        _add_message(session_id, {
            "msg_id": "wf_001",
            "from": "customer",
            "text": "Do you have this shoe in size 9?",
            "timestamp": int(time.time() * 1000),
        })
        print("\n[WF] Customer: 'Do you have this shoe in size 9?'")

        # Step 4: Wait for detection
        try:
            await asyncio.wait_for(reply_trigger.wait(), timeout=8.0)
        except asyncio.TimeoutError:
            pytest.fail("Timed out waiting for customer message detection")

        assert len(detected_messages) >= 1
        customer_msg = detected_messages[0]
        assert customer_msg["text"] == "Do you have this shoe in size 9?"
        print(f"[WF] Detected: '{customer_msg['text']}'")

        # Step 5: Compose reply (in a real skill, the LLM does this)
        reply_text = f"Let me check on size 9 for you, {session_id}!"

        # Step 6: Send reply via /send_msg (JS injection)
        cdp_session = await browser_session.get_or_create_cdp_session()
        js = """
            fetch('/send_msg', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    text: '%s',
                    from: 'agent',
                    msg_id: 'reply_wf_001',
                    session_id: '%s'
                })
            });
        """ % (reply_text.replace("'", "\\'"), session_id)
        await cdp_session.cdp_client.send.Runtime.evaluate(
            params={"expression": js},
            session_id=cdp_session.session_id,
        )
        await asyncio.sleep(1)

        # Step 7: Verify reply in chat store
        store = _get_store(session_id)
        agent_replies = [m for m in store if m["from"] == "agent"]
        assert len(agent_replies) >= 1, "Agent reply should be in the chat store"
        assert reply_text in agent_replies[0]["text"]

        print(f"[WF] Agent replied: '{agent_replies[0]['text']}'")
        print(f"[WF] Workflow complete: {len(store)} messages in session")

    async def test_browser_event_subscription_pattern(
        self, browser_session: BrowserSession, poll_base_url: str
    ):
        """
        Demonstrates the pattern for using PollingCapture results with
        eCan.ai's browser_event subscription system.

        In a real skill, you would use subscribe_browser_event MCP tool
        with domain=Network, event_method=Network.responseReceived.
        This test validates the CDP event registration pattern directly.
        """
        _reset_stores()
        session_id = "event_sub_001"

        # Navigate first (navigation resets CDP session)
        bus = browser_session.event_bus
        await bus.dispatch(
            NavigateToUrlEvent(
                url=f"{poll_base_url}/chat?session={session_id}",
                wait_until="commit",
            )
        )
        await asyncio.sleep(1)

        # Simulate what BrowserEventService does: register CDP Network handlers
        cdp_session = await browser_session.get_or_create_cdp_session()
        await cdp_session.cdp_client.send.Network.enable(
            session_id=cdp_session.session_id
        )

        # Track Network.responseReceived events (like browser_event_service does)
        received_events: List[dict] = []

        def on_response_received(params, sid):
            try:
                response = (
                    params.get("response", {})
                    if isinstance(params, dict)
                    else getattr(params, "response", {})
                )
                url = (
                    response.get("url")
                    if isinstance(response, dict)
                    else getattr(response, "url", "")
                )
                if url and "/batch_get_params" in url:
                    received_events.append({
                        "url": url,
                        "status": (
                            response.get("status")
                            if isinstance(response, dict)
                            else getattr(response, "status", 0)
                        ),
                    })
            except Exception:
                pass

        browser_session.cdp_client.register.Network.responseReceived(
            on_response_received
        )

        await asyncio.sleep(7)

        assert len(received_events) >= 2, (
            f"Expected at least 2 Network.responseReceived events for polling, "
            f"got {len(received_events)}"
        )

        for evt in received_events[:3]:
            assert "/batch_get_params" in evt["url"]
            assert evt["status"] == 200

        print(f"\n[TEST] CDP Network.responseReceived events captured: {len(received_events)}")
        print("[TEST] This validates the pattern used by subscribe_browser_event MCP tool")
