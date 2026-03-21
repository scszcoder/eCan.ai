"""
Test browser-use's in-browser event capture capability within eCan.ai.

Spins up a local HTTP server with pages that fire various browser events
(JS dialogs, navigation, tab creation, DOM changes, form interactions)
and verifies that browser-use's event bus captures them correctly.

This test does NOT require the full eCan.ai application to be running.
It directly uses browser_use's BrowserSession and event system.

Usage:
    # From eCan.ai project root:
    python -m pytest tests/test_browser_event_capture.py -v -s --timeout=120

    # Run a single test class:
    python -m pytest tests/test_browser_event_capture.py::TestDialogEventCapture -v -s

    # Run a single test:
    python -m pytest tests/test_browser_event_capture.py::TestNavigationEventCapture::test_navigate_emits_events -v -s
"""

import asyncio
import os
import socketserver
import sys
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from typing import Dict, List

import pytest
from bubus import BaseEvent

from browser_use import BrowserSession
from browser_use.browser.events import (
    BrowserStateRequestEvent,
    DialogOpenedEvent,
    NavigateToUrlEvent,
    NavigationCompleteEvent,
    NavigationStartedEvent,
    TabCreatedEvent,
)
from browser_use.browser.profile import BrowserProfile

# Skip LLM API key verification -- we don't need an LLM for event tests
os.environ["SKIP_LLM_API_KEY_VERIFICATION"] = "true"



# -- Local HTTP Server -------------------------------------------------


# HTML pages served by the local test server
TEST_PAGES: Dict[str, str] = {
    "/dialogs": """
<!DOCTYPE html>
<html>
<head><title>Dialog Test Page</title></head>
<body>
    <h1>Dialog Event Test</h1>
    <button id="btn-alert" onclick="alert('Hello from alert!')">Trigger Alert</button>
    <button id="btn-confirm" onclick="confirmResult = confirm('Do you confirm?');
        document.getElementById('result').textContent = 'confirm: ' + confirmResult">
        Trigger Confirm
    </button>
    <button id="btn-prompt" onclick="promptResult = prompt('Enter value:', 'default');
        document.getElementById('result').textContent = 'prompt: ' + promptResult">
        Trigger Prompt
    </button>
    <div id="result">No dialog triggered yet</div>
</body>
</html>
""",
    "/timed-events": """
<!DOCTYPE html>
<html>
<head><title>Timed Events Page</title></head>
<body>
    <h1>Timed Event Test</h1>
    <div id="status">waiting</div>
    <div id="counter">0</div>
    <script>
        let count = 0;
        const interval = setInterval(() => {
            count++;
            document.getElementById('counter').textContent = count;
            if (count >= 3) {
                clearInterval(interval);
                document.getElementById('status').textContent = 'done';
            }
        }, 500);
    </script>
</body>
</html>
""",
    "/form-events": """
<!DOCTYPE html>
<html>
<head><title>Form Events Page</title></head>
<body>
    <h1>Form Event Test</h1>
    <form id="test-form" onsubmit="event.preventDefault();
        document.getElementById('result').textContent =
        'submitted: ' + document.getElementById('name-input').value">
        <label for="name-input">Name:</label>
        <input type="text" id="name-input" name="name" placeholder="Enter your name">
        <button type="submit" id="submit-btn">Submit</button>
    </form>
    <div id="result">No submission yet</div>
</body>
</html>
""",
    "/new-tab-link": """
<!DOCTYPE html>
<html>
<head><title>New Tab Test</title></head>
<body>
    <h1>New Tab Event Test</h1>
    <a id="open-tab" href="/target-page" target="_blank">Open in new tab</a>
</body>
</html>
""",
    "/target-page": """
<!DOCTYPE html>
<html>
<head><title>Target Page</title></head>
<body><h1>Target Page Loaded</h1></body>
</html>
""",
    "/simple": """
<!DOCTYPE html>
<html>
<head><title>Simple Page</title></head>
<body><h1>Simple Page</h1><p>This is a simple test page.</p></body>
</html>
""",
    "/customer-chat": """
<!DOCTYPE html>
<html>
<head><title>Customer Chat Simulator</title></head>
<body>
    <h1>Customer Support Chat</h1>
    <div id="chat-box" style="border:1px solid #ccc; padding:10px; min-height:200px;">
        <div class="msg customer">Hi, I have a question about my order</div>
    </div>
    <input type="text" id="chat-input" placeholder="Type a message...">
    <button id="send-btn" onclick="sendMessage()">Send</button>
    <div id="notification" style="display:none;">New message received!</div>
    <script>
        function sendMessage() {
            const input = document.getElementById('chat-input');
            const chatBox = document.getElementById('chat-box');
            if (input.value.trim()) {
                const msg = document.createElement('div');
                msg.className = 'msg agent';
                msg.textContent = input.value;
                chatBox.appendChild(msg);
                input.value = '';
                // Simulate customer reply after 1 second
                setTimeout(() => {
                    const reply = document.createElement('div');
                    reply.className = 'msg customer';
                    reply.textContent = 'Thanks for your response!';
                    chatBox.appendChild(reply);
                    document.getElementById('notification').style.display = 'block';
                    document.getElementById('notification').textContent = 'New message received!';
                }, 1000);
            }
        }
    </script>
</body>
</html>
""",
}


class _TestHTTPRequestHandler(SimpleHTTPRequestHandler):
    """Serves HTML pages from the TEST_PAGES dict."""

    def do_GET(self):
        path = self.path.split("?")[0]  # strip query params
        if path in TEST_PAGES:
            content = TEST_PAGES[path].encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_error(404, f"Test page not found: {path}")

    def log_message(self, format, *args):
        pass  # suppress request logging noise


class _ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


# -- Fixtures ----------------------------------------------------------


@pytest.fixture(scope="session")
def http_server():
    """Start a local HTTP server on a random port serving test HTML pages."""
    server = _ThreadedHTTPServer(("127.0.0.1", 0), _TestHTTPRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()


@pytest.fixture(scope="session")
def base_url(http_server):
    host, port = http_server.server_address
    return f"http://{host}:{port}"


@pytest.fixture(scope="function")
async def browser_session():
    """Real headless browser session for event capture tests."""
    session = BrowserSession(
        browser_profile=BrowserProfile(
            headless=True,
            user_data_dir=None,
            keep_alive=False,
        )
    )
    await session.start()
    yield session
    await session.kill()


class EventCollector:
    """Collects events from the event bus for assertions."""

    def __init__(self):
        self.events: List[BaseEvent] = []

    async def handler(self, event: BaseEvent):
        self.events.append(event)
        return "collected"

    def get_by_type(self, event_type_name: str) -> List[BaseEvent]:
        return [e for e in self.events if e.event_type == event_type_name]

    def has_event(self, event_type_name: str) -> bool:
        return len(self.get_by_type(event_type_name)) > 0

    def clear(self):
        self.events.clear()

    def _remove_from_bus(self, bus, *event_classes):
        """Remove this collector's handler from the event bus (bubus has no off())."""
        for event_cls in event_classes:
            handlers = bus.handlers.get(event_cls.__name__, [])
            bus.handlers[event_cls.__name__] = [
                h for h in handlers if h is not self.handler
            ]


# -- Test Classes ------------------------------------------------------


class TestNavigationEventCapture:
    """Verify that navigation actions emit the expected events on the bus."""

    async def test_navigate_emits_events(self, browser_session: BrowserSession, base_url):
        """Navigating to a URL should produce NavigationStarted and NavigationComplete events."""
        collector = EventCollector()
        bus = browser_session.event_bus

        bus.on(NavigationStartedEvent, collector.handler)
        bus.on(NavigationCompleteEvent, collector.handler)

        try:
            nav = bus.dispatch(NavigateToUrlEvent(url=f"{base_url}/simple"))
            await nav
            await asyncio.sleep(1)

            nav_started = collector.get_by_type("NavigationStartedEvent")
            nav_complete = collector.get_by_type("NavigationCompleteEvent")

            print(f"\n[EVT] Captured {len(nav_started)} NavigationStartedEvent(s)")
            print(f"[EVT] Captured {len(nav_complete)} NavigationCompleteEvent(s)")
            for evt in nav_complete:
                print(f"   -> NavigationComplete: url={getattr(evt, 'url', '?')}")

            assert len(nav_complete) > 0, "Expected at least one NavigationCompleteEvent"

        finally:
            collector._remove_from_bus(bus, NavigationStartedEvent, NavigationCompleteEvent)

    async def test_navigate_to_multiple_pages(self, browser_session: BrowserSession, base_url):
        """Navigation to different pages should each produce events."""
        collector = EventCollector()
        bus = browser_session.event_bus
        bus.on(NavigationCompleteEvent, collector.handler)

        try:
            for page in ["/simple", "/form-events", "/dialogs"]:
                nav = bus.dispatch(NavigateToUrlEvent(url=f"{base_url}{page}"))
                await nav
                await asyncio.sleep(0.5)

            events = collector.get_by_type("NavigationCompleteEvent")
            print(f"\n[EVT] Captured {len(events)} NavigationCompleteEvent(s) across 3 navigations")
            assert len(events) >= 3, f"Expected >=3 NavigationCompleteEvents, got {len(events)}"

        finally:
            collector._remove_from_bus(bus, NavigationCompleteEvent)


class TestDialogEventCapture:
    """Verify that JS dialogs are captured and auto-handled by PopupsWatchdog."""

    async def test_alert_dialog_captured(self, browser_session: BrowserSession, base_url):
        """Triggering alert() should be captured in _closed_popup_messages."""
        nav = browser_session.event_bus.dispatch(
            NavigateToUrlEvent(url=f"{base_url}/dialogs")
        )
        await nav
        await asyncio.sleep(0.5)

        # Clear previous popup messages
        browser_session._closed_popup_messages.clear()

        # Trigger alert via JS evaluation through CDP
        cdp_session = await browser_session.get_or_create_cdp_session(focus=True)
        await cdp_session.cdp_client.send.Runtime.evaluate(
            params={"expression": "document.getElementById('btn-alert').click()"},
            session_id=cdp_session.session_id,
        )

        # Wait for PopupsWatchdog to catch and dismiss the dialog
        await asyncio.sleep(1.5)

        print(f"\n[EVT] Popup messages captured: {browser_session._closed_popup_messages}")

        assert len(browser_session._closed_popup_messages) > 0, (
            "PopupsWatchdog should have captured the alert dialog"
        )
        assert any("Hello from alert" in msg for msg in browser_session._closed_popup_messages), (
            'Expected alert message to contain "Hello from alert"'
        )

    async def test_confirm_dialog_captured(self, browser_session: BrowserSession, base_url):
        """Triggering confirm() should also be captured."""
        nav = browser_session.event_bus.dispatch(
            NavigateToUrlEvent(url=f"{base_url}/dialogs")
        )
        await nav
        await asyncio.sleep(0.5)

        browser_session._closed_popup_messages.clear()

        cdp_session = await browser_session.get_or_create_cdp_session(focus=True)
        await cdp_session.cdp_client.send.Runtime.evaluate(
            params={"expression": "document.getElementById('btn-confirm').click()"},
            session_id=cdp_session.session_id,
        )

        await asyncio.sleep(1.5)

        print(f"\n[EVT] Confirm popup messages: {browser_session._closed_popup_messages}")

        assert len(browser_session._closed_popup_messages) > 0, (
            "PopupsWatchdog should have captured the confirm dialog"
        )
        assert any("Do you confirm" in msg for msg in browser_session._closed_popup_messages), (
            'Expected confirm message to contain "Do you confirm"'
        )


class TestTabEventCapture:
    """Verify that opening new tabs emits TabCreatedEvent."""

    async def test_new_tab_emits_tab_created(self, browser_session: BrowserSession, base_url):
        """Opening a new tab via NavigateToUrlEvent(new_tab=True) should emit TabCreatedEvent."""
        collector = EventCollector()
        bus = browser_session.event_bus
        bus.on(TabCreatedEvent, collector.handler)

        try:
            # Navigate to a page first
            nav = bus.dispatch(NavigateToUrlEvent(url=f"{base_url}/new-tab-link"))
            await nav
            await asyncio.sleep(0.5)

            collector.clear()

            # Open a new tab programmatically
            nav2 = bus.dispatch(
                NavigateToUrlEvent(url=f"{base_url}/target-page", new_tab=True)
            )
            await nav2
            await asyncio.sleep(1)

            tab_events = collector.get_by_type("TabCreatedEvent")
            print(f"\n[EVT] Captured {len(tab_events)} TabCreatedEvent(s)")
            for evt in tab_events:
                print(
                    f"   -> TabCreated: target_id={getattr(evt, 'target_id', '?')}, "
                    f"url={getattr(evt, 'url', '?')}"
                )

            assert len(tab_events) > 0, "Expected at least one TabCreatedEvent"

        finally:
            collector._remove_from_bus(bus, TabCreatedEvent)


class TestBrowserStateCapture:
    """Verify that browser state requests return complete DOM and page info."""

    async def test_browser_state_request(self, browser_session: BrowserSession, base_url):
        """BrowserStateRequestEvent should return a full state summary with DOM."""
        nav = browser_session.event_bus.dispatch(
            NavigateToUrlEvent(url=f"{base_url}/form-events")
        )
        await nav
        await asyncio.sleep(0.5)

        state_event = browser_session.event_bus.dispatch(
            BrowserStateRequestEvent(include_dom=True, include_screenshot=True)
        )
        await state_event
        result = await state_event.event_result(raise_if_any=True)

        print(f"\n[EVT] BrowserStateSummary:")
        print(f"   -> URL: {getattr(result, 'url', 'N/A')}")
        print(f"   -> Title: {getattr(result, 'title', 'N/A')}")
        print(f"   -> Tabs: {len(result.tabs) if hasattr(result, 'tabs') else 'N/A'}")
        print(f"   -> Has screenshot: {result.screenshot is not None}")
        print(
            f"   -> DOM elements in selector_map: "
            f"{len(result.dom_state.selector_map) if result.dom_state else 0}"
        )

        assert hasattr(result, 'url'), "BrowserStateSummary should have a url attribute"
        assert result.dom_state is not None, "Expected DOM state to be present"
        assert len(result.dom_state.selector_map) > 0, "Expected at least one element in selector map"

    async def test_state_captures_dom_elements(self, browser_session: BrowserSession, base_url):
        """The DOM state should contain interactive elements like inputs and buttons."""
        nav = browser_session.event_bus.dispatch(
            NavigateToUrlEvent(url=f"{base_url}/form-events")
        )
        await nav
        await asyncio.sleep(0.5)

        state_event = browser_session.event_bus.dispatch(
            BrowserStateRequestEvent(include_dom=True, include_screenshot=False)
        )
        await state_event
        result = await state_event.event_result(raise_if_any=True)

        # Use llm_representation() to get DOM tree text
        dom_text = result.dom_state.llm_representation() if result.dom_state else ""
        print(f"\n[EVT] DOM text preview (first 500 chars):\n{dom_text[:500]}")

        assert "name" in dom_text.lower() or "input" in dom_text.lower(), (
            "Expected DOM to contain form input elements"
        )


class TestDOMChangeCapture:
    """Verify that browser-use can observe DOM changes via periodic state requests."""

    async def test_timed_dom_changes_captured(self, browser_session: BrowserSession, base_url):
        """Navigate to page with timed DOM updates and observe changes via state + JS eval."""
        nav = browser_session.event_bus.dispatch(
            NavigateToUrlEvent(url=f"{base_url}/timed-events")
        )
        await nav
        await asyncio.sleep(0.3)

        # Read early state via JS
        cdp_session = await browser_session.get_or_create_cdp_session(focus=True)
        early_counter = await cdp_session.cdp_client.send.Runtime.evaluate(
            params={"expression": 'document.getElementById("counter").textContent'},
            session_id=cdp_session.session_id,
        )
        early_val = early_counter.get("result", {}).get("value", "")
        print(f"\n[EVT] Early counter value: {early_val}")

        # Wait for timed JS events to fire (3 x 500ms = 1.5s, plus buffer)
        await asyncio.sleep(2.5)

        # Read final state
        late_counter = await cdp_session.cdp_client.send.Runtime.evaluate(
            params={"expression": 'document.getElementById("counter").textContent'},
            session_id=cdp_session.session_id,
        )
        late_status = await cdp_session.cdp_client.send.Runtime.evaluate(
            params={"expression": 'document.getElementById("status").textContent'},
            session_id=cdp_session.session_id,
        )

        counter_val = late_counter.get("result", {}).get("value", "")
        status_val = late_status.get("result", {}).get("value", "")

        print(f"[EVT] Final counter value: {counter_val}")
        print(f"[EVT] Final status value: {status_val}")

        assert status_val == "done", f'Expected status "done", got "{status_val}"'
        assert counter_val == "3", f'Expected counter "3", got "{counter_val}"'


class TestCustomerChatSimulation:
    """
    Simulate a customer support scenario:
    Navigate to a chat page, send a message, observe DOM mutation (new reply),
    and read updated state -- this mirrors the real-time customer support use case.
    """

    async def test_chat_send_and_reply_detection(self, browser_session: BrowserSession, base_url):
        """Send a message in the chat, wait for simulated customer reply, verify DOM update."""
        nav = browser_session.event_bus.dispatch(
            NavigateToUrlEvent(url=f"{base_url}/customer-chat")
        )
        await nav
        await asyncio.sleep(0.5)

        cdp_session = await browser_session.get_or_create_cdp_session(focus=True)

        # Count initial messages
        initial_count = await cdp_session.cdp_client.send.Runtime.evaluate(
            params={"expression": 'document.querySelectorAll("#chat-box .msg").length'},
            session_id=cdp_session.session_id,
        )
        initial_msg_count = initial_count.get("result", {}).get("value", 0)
        print(f"\n[EVT] Initial message count: {initial_msg_count}")

        # Type a message and click send
        await cdp_session.cdp_client.send.Runtime.evaluate(
            params={
                "expression": (
                    'document.getElementById("chat-input").value = "What is my order status?"; '
                    'document.getElementById("send-btn").click();'
                )
            },
            session_id=cdp_session.session_id,
        )

        # Wait for the agent's message to appear + simulated customer reply (1s delay)
        await asyncio.sleep(2.0)

        # Count messages after interaction
        final_count = await cdp_session.cdp_client.send.Runtime.evaluate(
            params={"expression": 'document.querySelectorAll("#chat-box .msg").length'},
            session_id=cdp_session.session_id,
        )
        final_msg_count = final_count.get("result", {}).get("value", 0)

        # Check notification appeared
        notification = await cdp_session.cdp_client.send.Runtime.evaluate(
            params={"expression": 'document.getElementById("notification").textContent'},
            session_id=cdp_session.session_id,
        )
        notification_text = notification.get("result", {}).get("value", "")

        # Read the last message
        last_msg = await cdp_session.cdp_client.send.Runtime.evaluate(
            params={
                "expression": (
                    'document.querySelector("#chat-box .msg:last-child").textContent'
                )
            },
            session_id=cdp_session.session_id,
        )
        last_msg_text = last_msg.get("result", {}).get("value", "")

        print(f"[EVT] Final message count: {final_msg_count}")
        print(f"[EVT] Notification text: {notification_text}")
        print(f"[EVT] Last message: {last_msg_text}")

        assert final_msg_count > initial_msg_count, (
            f"Expected more messages after sending, got {final_msg_count} (was {initial_msg_count})"
        )
        assert "Thanks" in last_msg_text, (
            f'Expected simulated customer reply containing "Thanks", got "{last_msg_text}"'
        )
        assert "New message received" in notification_text, (
            "Expected notification to appear after customer reply"
        )


class TestEventBusHistory:
    """Verify that the event bus maintains an event history."""

    async def test_event_history_recorded(self, browser_session: BrowserSession, base_url):
        """Events dispatched through the bus should appear in event_history."""
        nav = browser_session.event_bus.dispatch(
            NavigateToUrlEvent(url=f"{base_url}/simple")
        )
        await nav
        await asyncio.sleep(0.5)

        history = browser_session.event_bus.event_history
        event_types = [evt.event_type for evt in history.values()]

        print(f"\n[EVT] Event bus history ({len(history)} events):")
        sorted_events = sorted(
            history.values(), key=lambda e: e.event_created_at.timestamp(), reverse=True
        )
        for evt in sorted_events[:15]:
            url_str = f" url={evt.url}" if hasattr(evt, "url") else ""
            print(f"   -> {evt.event_type}{url_str}")

        assert "NavigateToUrlEvent" in event_types, "NavigateToUrlEvent should be in history"
        assert len(history) > 0, "Event history should not be empty"
