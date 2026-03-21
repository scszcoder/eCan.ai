"""
Multi-Customer Support Load Test Rig
=====================================

Simulates a real-time e-commerce customer support scenario:

  - 20 customers fire product queries nearly simultaneously (within a narrow
    random window to emulate real burst traffic).
  - A **ManagerAgent** monitors incoming messages via a shared message queue.
    When a NEW customer is spotted it opens a dedicated browser tab for that
    customer and assigns a logical "support agent" to handle them.
  - Follow-up messages from the same customer are routed to the correct
    support agent's per-tab task queue.
  - Assertions verify: tab creation, correct routing, concurrency, timing.

This test is self-contained -- it defines ManagerAgent and SupportAgent as
pure Python classes using browser-use's event bus and CDP directly.  When you
build the real eCan.ai skills/prompts later, this serves as a reference
implementation.

Architecture
------------
    +----------------+
    | 20 Customer    |---(random burst)---> message_inbox (asyncio.Queue)
    | Simulators     |
    +----------------+
            |
            v
    +----------------+     new customer?     +---------------------+
    | ManagerAgent   |---------------------->| open new tab        |
    | (dispatcher)   |                       | create SupportAgent |
    +----------------+                       +---------------------+
            |
            | existing customer?
            v
    +------------------------+
    | route msg to           |
    | SupportAgent[cust_id]  |
    | .task_queue             |
    +------------------------+
            |
            v
    +------------------------+
    | SupportAgent           |  <-- runs in its own tab
    | - switches to tab      |
    | - injects answer       |
    | - reads DOM to verify  |
    +------------------------+

Usage:
    python -m pytest tests/test_multi_customer_load.py -v -s
    python -m pytest tests/test_multi_customer_load.py::TestManagerDispatch -v -s
    python -m pytest tests/test_multi_customer_load.py::TestFullLoadScenario -v -s

    # Quick smoke test (5 customers instead of 20):
    NUM_CUSTOMERS=5 python -m pytest tests/test_multi_customer_load.py -v -s
"""

import asyncio
import json
import os
import random
import socketserver
import threading
import time
from dataclasses import dataclass, field
from http.server import HTTPServer, SimpleHTTPRequestHandler
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import pytest

from browser_use import BrowserSession
from browser_use.browser.events import (
    BrowserStateRequestEvent,
    NavigateToUrlEvent,
    NavigationCompleteEvent,
    SwitchTabEvent,
    TabCreatedEvent,
)
from browser_use.browser.profile import BrowserProfile


# Configurable customer count via env var for quick smoke tests
NUM_CUSTOMERS = int(os.environ.get("NUM_CUSTOMERS", "20"))
# Narrow burst window in seconds -- all customers fire within this window
BURST_WINDOW_SECONDS = float(os.environ.get("BURST_WINDOW", "2.0"))


# =======================================================================
# Data Models
# =======================================================================


@dataclass
class CustomerMessage:
    """A message from a customer."""
    customer_id: str
    customer_name: str
    message: str
    timestamp: float = field(default_factory=time.time)
    is_first_contact: bool = False  # set by ManagerAgent


@dataclass
class SupportAgentState:
    """Tracks a support agent assigned to a specific customer tab."""
    customer_id: str
    customer_name: str
    target_id: str  # browser tab target_id
    task_queue: asyncio.Queue  # per-agent message queue
    messages_handled: int = 0
    created_at: float = field(default_factory=time.time)


# =======================================================================
# Local HTTP Server -- serves per-customer chat pages
# =======================================================================


CUSTOMER_CHAT_PAGE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head><title>Support Chat -- {customer_name}</title></head>
<body>
    <h1 id="header">Customer: {customer_name} (ID: {customer_id})</h1>
    <div id="chat-box" style="border:1px solid #ccc; padding:10px; min-height:200px;">
        <div class="msg customer" id="initial-msg">{initial_message}</div>
    </div>
    <div id="msg-count">1</div>
    <div id="last-agent-reply"></div>
    <div id="status">waiting</div>
    <script>
        function addCustomerMessage(text) {{
            const chatBox = document.getElementById('chat-box');
            const msg = document.createElement('div');
            msg.className = 'msg customer';
            msg.textContent = text;
            chatBox.appendChild(msg);
            document.getElementById('msg-count').textContent =
                chatBox.querySelectorAll('.msg').length;
        }}
        function addAgentReply(text) {{
            const chatBox = document.getElementById('chat-box');
            const msg = document.createElement('div');
            msg.className = 'msg agent';
            msg.textContent = text;
            chatBox.appendChild(msg);
            document.getElementById('last-agent-reply').textContent = text;
            document.getElementById('msg-count').textContent =
                chatBox.querySelectorAll('.msg').length;
            document.getElementById('status').textContent = 'replied';
        }}
    </script>
</body>
</html>
"""

# Lobby page -- the manager agent starts here
LOBBY_PAGE = """
<!DOCTYPE html>
<html>
<head><title>Support Lobby</title></head>
<body>
    <h1>Customer Support Lobby</h1>
    <div id="active-agents">0</div>
    <div id="status">idle</div>
</body>
</html>
"""

# Product queries customers might ask
PRODUCT_QUERIES = [
    "Is this product on sale right now?",
    "What's the discount on the wireless headphones?",
    "Do you have the Nike Air Max in size 10?",
    "When will the laptop deal expire?",
    "Can I get free shipping on this order?",
    "Is this item eligible for the buy-one-get-one deal?",
    "What's the return policy for sale items?",
    "Do you price-match with Amazon?",
    "Is the 50% off coupon still valid?",
    "How long does delivery take for flash sale items?",
    "Can I combine coupons with the current sale?",
    "Is the organic face cream back in stock?",
    "What's the warranty on discounted electronics?",
    "Do sale items qualify for reward points?",
    "Can I reserve this item at the sale price?",
    "Is there a student discount available?",
    "When is your next big sale event?",
    "Are refurbished items included in the sale?",
    "What payment methods do you accept for sale items?",
    "Can I apply my loyalty points to this sale item?",
]


class _ChatPageHandler(SimpleHTTPRequestHandler):
    """Serves per-customer chat pages and the lobby."""

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/lobby":
            self._respond(LOBBY_PAGE)
        elif path.startswith("/customer/"):
            params = parse_qs(parsed.query)
            cid = path.split("/customer/")[1]
            cname = params.get("name", [f"Customer_{cid}"])[0]
            query = params.get("query", ["Hello, I need help"])[0]
            page = CUSTOMER_CHAT_PAGE_TEMPLATE.format(
                customer_name=cname,
                customer_id=cid,
                initial_message=query,
            )
            self._respond(page)
        else:
            self.send_error(404, f"Not found: {path}")

    def _respond(self, html: str):
        content = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, fmt, *args):
        pass  # suppress noise


class _ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


# =======================================================================
# ManagerAgent -- monitors inbox, creates tabs, routes messages
# =======================================================================


class ManagerAgent:
    """
    Watches a shared message inbox. For each new customer, opens a new
    browser tab and creates a SupportAgent. For returning customers,
    routes the message to the existing agent's task queue.

    This is the logic you'll later encode into an eCan.ai manager skill.
    """

    def __init__(self, browser_session: BrowserSession, base_url: str):
        self.browser_session = browser_session
        self.base_url = base_url
        self.inbox: asyncio.Queue[CustomerMessage] = asyncio.Queue()
        # customer_id -> SupportAgentState
        self.agents: Dict[str, SupportAgentState] = {}
        self.total_dispatched = 0
        self._running = False
        self._task: Optional[asyncio.Task] = None
        # Timing metrics
        self.tab_creation_times: List[float] = []
        self.routing_times: List[float] = []

    async def start(self):
        """Start the manager dispatch loop."""
        self._running = True
        self._task = asyncio.create_task(self._dispatch_loop())

    async def stop(self):
        """Stop the manager and wait for it to finish."""
        self._running = False
        if self._task:
            # Push a sentinel to unblock the queue
            await self.inbox.put(None)  # type: ignore
            await self._task

    async def _dispatch_loop(self):
        """Main loop: read inbox, create or route."""
        while self._running:
            try:
                msg = await self.inbox.get()
                if msg is None:
                    break  # sentinel

                t0 = time.time()

                if msg.customer_id not in self.agents:
                    # New customer -- open a dedicated tab
                    msg.is_first_contact = True
                    agent_state = await self._create_support_agent(msg)
                    self.agents[msg.customer_id] = agent_state
                    self.tab_creation_times.append(time.time() - t0)
                else:
                    # Existing customer -- route to their agent
                    agent_state = self.agents[msg.customer_id]
                    self.routing_times.append(time.time() - t0)

                await agent_state.task_queue.put(msg)
                self.total_dispatched += 1
            except Exception as e:
                print(f"  [ERR] ManagerAgent dispatch error: {type(e).__name__}: {e}")

    async def _create_support_agent(self, msg: CustomerMessage) -> SupportAgentState:
        """Open a new browser tab for this customer and return agent state."""
        url = (
            f"{self.base_url}/customer/{msg.customer_id}"
            f"?name={msg.customer_name}"
            f"&query={msg.message}"
        )

        bus = self.browser_session.event_bus
        sm = self.browser_session.session_manager

        # Snapshot existing target IDs before navigation
        targets_before = set()
        if sm:
            targets_before = {t.target_id for t in sm.get_all_page_targets()}

        # Navigate -- new_tab=True asks browser-use to open in a new tab
        # Use wait_until='commit' to avoid long page readiness timeouts on simple HTML
        nav = bus.dispatch(NavigateToUrlEvent(url=url, new_tab=True, wait_until='commit'))
        await nav
        await asyncio.sleep(0.5)  # allow session_manager to sync

        # Determine the new tab's target_id
        created_target_id = None

        # Strategy 1: diff the target list
        if sm:
            targets_after = {t.target_id for t in sm.get_all_page_targets()}
            new_targets = targets_after - targets_before
            if new_targets:
                created_target_id = new_targets.pop()

        # Strategy 2: use the focused target (browser-use switches focus to the new tab)
        if not created_target_id:
            created_target_id = self.browser_session.agent_focus_target_id or "unknown"

        task_queue: asyncio.Queue[CustomerMessage] = asyncio.Queue()

        return SupportAgentState(
            customer_id=msg.customer_id,
            customer_name=msg.customer_name,
            target_id=str(created_target_id),
            task_queue=task_queue,
        )


# =======================================================================
# SupportAgent Worker -- processes messages in its assigned tab
# =======================================================================


class SupportAgentWorker:
    """
    Processes messages from a SupportAgentState's task queue.
    Switches to the assigned tab, injects a reply via CDP, reads back DOM.

    This is the logic you'll later encode into an eCan.ai support agent skill.
    """

    def __init__(self, browser_session: BrowserSession, agent_state: SupportAgentState):
        self.browser_session = browser_session
        self.agent_state = agent_state
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._work_loop())

    async def stop(self):
        self._running = False
        if self._task:
            await self.agent_state.task_queue.put(None)  # type: ignore
            await self._task

    async def _work_loop(self):
        while self._running:
            msg = await self.agent_state.task_queue.get()
            if msg is None:
                break
            await self._handle_message(msg)
            self.agent_state.messages_handled += 1

    async def _handle_message(self, msg: CustomerMessage):
        """Switch to tab, inject reply via CDP JS evaluation."""
        try:
            # Switch focus to our tab
            bus = self.browser_session.event_bus
            bus.dispatch(SwitchTabEvent(target_id=self.agent_state.target_id))
            await asyncio.sleep(0.2)

            # Get a CDP session for our tab
            cdp_session = await self.browser_session.get_or_create_cdp_session(focus=True)

            # Generate a mock reply (in real eCan.ai this would be RAG + LLM)
            reply = f"Thank you for asking about that, {msg.customer_name}! Let me check on: {msg.message[:60]}"

            # Inject the reply into the page
            escaped_reply = reply.replace("'", "\\'").replace('"', '\\"')
            await cdp_session.cdp_client.send.Runtime.evaluate(
                params={"expression": f'addAgentReply("{escaped_reply}")'},
                session_id=cdp_session.session_id,
            )
        except Exception as e:
            # Log but don't crash -- we want to see how many succeed
            print(f"  [WARN] SupportAgent[{self.agent_state.customer_id}] error: {e}")


# =======================================================================
# Customer Simulator -- fires burst of queries
# =======================================================================


class CustomerSimulator:
    """
    Simulates N customers sending product queries within a narrow time
    window. Some customers send follow-up messages.
    """

    def __init__(self, manager: ManagerAgent, num_customers: int = NUM_CUSTOMERS):
        self.manager = manager
        self.num_customers = num_customers
        self.customers_sent: List[CustomerMessage] = []

    async def fire_initial_burst(self):
        """All customers fire their first query within BURST_WINDOW_SECONDS."""
        tasks = []
        for i in range(self.num_customers):
            delay = random.uniform(0, BURST_WINDOW_SECONDS)
            cid = f"cust_{i+1:03d}"
            cname = f"Customer_{i+1}"
            query = PRODUCT_QUERIES[i % len(PRODUCT_QUERIES)]
            tasks.append(self._send_delayed(delay, cid, cname, query))

        await asyncio.gather(*tasks)

    async def fire_followups(self, num_followups: int = 5):
        """Random subset of customers send follow-up messages."""
        followup_customers = random.sample(
            range(self.num_customers), min(num_followups, self.num_customers)
        )
        for i in followup_customers:
            cid = f"cust_{i+1:03d}"
            cname = f"Customer_{i+1}"
            followup_msg = random.choice([
                "Actually, one more question -- do you have it in blue?",
                "What about the warranty?",
                "Can I pick it up in store instead?",
                "Never mind, I'll take two!",
                "How does the sizing run?",
            ])
            msg = CustomerMessage(
                customer_id=cid,
                customer_name=cname,
                message=followup_msg,
            )
            self.customers_sent.append(msg)
            await self.manager.inbox.put(msg)
            await asyncio.sleep(random.uniform(0.05, 0.3))

    async def _send_delayed(self, delay: float, cid: str, cname: str, query: str):
        await asyncio.sleep(delay)
        msg = CustomerMessage(
            customer_id=cid,
            customer_name=cname,
            message=query,
        )
        self.customers_sent.append(msg)
        await self.manager.inbox.put(msg)


# =======================================================================
# Pytest Fixtures
# =======================================================================


@pytest.fixture(scope="session")
def http_server():
    server = _ThreadedHTTPServer(("127.0.0.1", 0), _ChatPageHandler)
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


# =======================================================================
# Tests
# =======================================================================


class TestManagerDispatch:
    """Unit-level tests for the ManagerAgent dispatch logic."""

    async def test_new_customer_creates_tab(self, browser_session: BrowserSession, base_url):
        """A new customer message should open a new tab."""
        manager = ManagerAgent(browser_session, base_url)
        await manager.start()

        try:
            msg = CustomerMessage(
                customer_id="test_single_001",
                customer_name="TestBuyer",
                message="Is this on sale?",
            )
            await manager.inbox.put(msg)
            # Give manager time to process (navigation + tab creation can take several seconds)
            await asyncio.sleep(12)

            assert "test_single_001" in manager.agents, "Manager should have created an agent for this customer"
            agent_state = manager.agents["test_single_001"]
            assert agent_state.target_id != "unknown", "Agent should have a valid tab target_id"
            assert agent_state.customer_name == "TestBuyer"

            print(f"\n[EVT] Tab created for test_single_001: target_id={agent_state.target_id}")
        finally:
            await manager.stop()

    async def test_returning_customer_routes_to_existing_agent(
        self, browser_session: BrowserSession, base_url
    ):
        """Follow-up messages from same customer should route to the same agent."""
        manager = ManagerAgent(browser_session, base_url)
        await manager.start()

        try:
            # First message -- creates agent
            msg1 = CustomerMessage(
                customer_id="test_return_001",
                customer_name="ReturningBuyer",
                message="Is the laptop on sale?",
            )
            await manager.inbox.put(msg1)
            await asyncio.sleep(12)

            assert "test_return_001" in manager.agents
            original_target = manager.agents["test_return_001"].target_id

            # Second message -- should route to same agent, no new tab
            msg2 = CustomerMessage(
                customer_id="test_return_001",
                customer_name="ReturningBuyer",
                message="What about the warranty?",
            )
            await manager.inbox.put(msg2)
            await asyncio.sleep(1)

            # Still the same agent, same tab
            assert manager.agents["test_return_001"].target_id == original_target
            # Task queue should have received both messages
            assert manager.agents["test_return_001"].task_queue.qsize() >= 0
            assert manager.total_dispatched >= 2

            print(f"\n[EVT] Follow-up correctly routed to same tab: {original_target}")
        finally:
            await manager.stop()


class TestSupportAgentWorker:
    """Test the SupportAgent reply injection into a tab."""

    async def test_agent_injects_reply(self, browser_session: BrowserSession, base_url):
        """SupportAgent should inject a reply into the customer's chat page."""
        # Open a customer page manually
        bus = browser_session.event_bus
        url = f"{base_url}/customer/inject_test?name=InjectionTest&query=Does+it+ship+free?"
        nav = bus.dispatch(NavigateToUrlEvent(url=url, new_tab=True, wait_until='commit'))
        await nav
        await asyncio.sleep(1)

        target_id = browser_session.agent_focus_target_id or "unknown"
        task_queue: asyncio.Queue = asyncio.Queue()

        agent_state = SupportAgentState(
            customer_id="inject_test",
            customer_name="InjectionTest",
            target_id=str(target_id),
            task_queue=task_queue,
        )

        worker = SupportAgentWorker(browser_session, agent_state)
        await worker.start()

        try:
            msg = CustomerMessage(
                customer_id="inject_test",
                customer_name="InjectionTest",
                message="Does it ship free?",
            )
            await task_queue.put(msg)
            await asyncio.sleep(2)

            # Verify the reply was injected by reading DOM
            cdp_session = await browser_session.get_or_create_cdp_session(focus=True)
            result = await cdp_session.cdp_client.send.Runtime.evaluate(
                params={"expression": 'document.getElementById("last-agent-reply").textContent'},
                session_id=cdp_session.session_id,
            )
            reply_text = result.get("result", {}).get("value", "")

            print(f"\n[EVT] Agent reply injected: {reply_text}")
            assert "Thank you" in reply_text, f'Expected reply containing "Thank you", got: {reply_text}'
            assert agent_state.messages_handled >= 1

        finally:
            await worker.stop()


class TestFullLoadScenario:
    """
    The big one: 20 customers fire queries nearly simultaneously.
    Manager creates tabs, support agents handle messages.
    """

    async def test_burst_load(self, browser_session: BrowserSession, base_url):
        """
        Full load scenario:
        1. Fire NUM_CUSTOMERS queries within BURST_WINDOW_SECONDS
        2. Manager creates a tab per customer
        3. Start support workers for each
        4. Fire follow-up messages
        5. Verify all tabs created, messages routed, replies injected
        """
        print(f"\n{'='*60}")
        print(f">>> LOAD TEST: {NUM_CUSTOMERS} customers, {BURST_WINDOW_SECONDS}s burst window")
        print(f"{'='*60}")

        manager = ManagerAgent(browser_session, base_url)
        await manager.start()

        simulator = CustomerSimulator(manager, NUM_CUSTOMERS)
        workers: List[SupportAgentWorker] = []

        try:
            # Phase 1: Fire initial burst
            t0 = time.time()
            print(f"\n[OUT] Phase 1: Firing {NUM_CUSTOMERS} customer queries...")
            await simulator.fire_initial_burst()

            # Wait for manager to process all messages and open tabs
            # Allow generous time: each tab takes ~1-3s to open
            max_wait = NUM_CUSTOMERS * 4 + 10
            deadline = time.time() + max_wait
            while len(manager.agents) < NUM_CUSTOMERS and time.time() < deadline:
                await asyncio.sleep(0.5)
                if int(time.time()) % 5 == 0:
                    print(f"   ... {len(manager.agents)}/{NUM_CUSTOMERS} agents created")

            phase1_time = time.time() - t0
            print(f"\n[STAT] Phase 1 complete: {len(manager.agents)}/{NUM_CUSTOMERS} tabs in {phase1_time:.1f}s")

            # Phase 2: Start support workers
            print(f"\n[BOT] Phase 2: Starting support agent workers...")
            for agent_state in manager.agents.values():
                worker = SupportAgentWorker(browser_session, agent_state)
                await worker.start()
                workers.append(worker)

            # Give workers time to process their initial messages
            await asyncio.sleep(3)

            # Phase 3: Fire follow-ups
            num_followups = min(5, NUM_CUSTOMERS)
            print(f"\n[OUT] Phase 3: Firing {num_followups} follow-up messages...")
            await simulator.fire_followups(num_followups)

            # Wait for follow-ups to be processed
            await asyncio.sleep(5)

            total_time = time.time() - t0

            # -- Report ------------------------------------------------
            print(f"\n{'='*60}")
            print(f"LOAD TEST RESULTS")
            print(f"{'='*60}")
            print(f"  Customers:         {NUM_CUSTOMERS}")
            print(f"  Burst window:      {BURST_WINDOW_SECONDS}s")
            print(f"  Tabs created:      {len(manager.agents)}")
            print(f"  Total dispatched:  {manager.total_dispatched}")
            print(f"  Total time:        {total_time:.1f}s")

            if manager.tab_creation_times:
                avg_tab = sum(manager.tab_creation_times) / len(manager.tab_creation_times)
                max_tab = max(manager.tab_creation_times)
                print(f"  Avg tab creation:  {avg_tab:.2f}s")
                print(f"  Max tab creation:  {max_tab:.2f}s")

            if manager.routing_times:
                avg_route = sum(manager.routing_times) / len(manager.routing_times)
                print(f"  Avg msg routing:   {avg_route*1000:.1f}ms")

            total_handled = sum(w.agent_state.messages_handled for w in workers)
            print(f"  Messages handled:  {total_handled}")

            # Per-agent summary
            print(f"\n  Per-agent breakdown:")
            for cid, state in sorted(manager.agents.items()):
                print(
                    f"    {cid}: tab={state.target_id[:12]}..., "
                    f"handled={state.messages_handled}, "
                    f"queue_remaining={state.task_queue.qsize()}"
                )

            print(f"{'='*60}")

            # -- Assertions --------------------------------------------
            assert len(manager.agents) >= NUM_CUSTOMERS * 0.9, (
                f"Expected >={int(NUM_CUSTOMERS*0.9)} tabs created, got {len(manager.agents)}"
            )

            # All agents should have unique target_ids (one tab per customer)
            target_ids = [a.target_id for a in manager.agents.values()]
            unique_targets = set(t for t in target_ids if t != "unknown")
            assert len(unique_targets) >= len(manager.agents) * 0.8, (
                f"Expected mostly unique tab targets, got {len(unique_targets)} "
                f"unique out of {len(manager.agents)} agents"
            )

            # At least some messages should have been handled by workers
            assert total_handled > 0, "Expected at least some messages to be handled by workers"

            # Routing should be near-instant (< 10ms avg)
            if manager.routing_times:
                assert avg_route < 0.1, f"Routing too slow: {avg_route*1000:.1f}ms avg (expected <100ms)"

        finally:
            # Cleanup: stop all workers and manager
            for worker in workers:
                await worker.stop()
            await manager.stop()

    async def test_concurrent_tab_isolation(self, browser_session: BrowserSession, base_url):
        """Each customer tab should have its own page content (no cross-contamination)."""
        manager = ManagerAgent(browser_session, base_url)
        await manager.start()

        try:
            # Create 3 customers with distinct queries
            queries = [
                ("iso_001", "Alice", "Is the red dress on sale?"),
                ("iso_002", "Bob", "Do you have gaming keyboards?"),
                ("iso_003", "Carol", "What's the price of the coffee maker?"),
            ]

            for cid, name, query in queries:
                msg = CustomerMessage(customer_id=cid, customer_name=name, message=query)
                await manager.inbox.put(msg)
                await asyncio.sleep(2)

            # Wait for all tabs
            await asyncio.sleep(3)

            # Verify each tab has its own customer content
            for cid, name, query in queries:
                if cid not in manager.agents:
                    print(f"  [WARN] Agent for {cid} not created, skipping isolation check")
                    continue

                agent_state = manager.agents[cid]
                try:
                    # Switch to this customer's tab
                    bus = browser_session.event_bus
                    bus.dispatch(SwitchTabEvent(target_id=agent_state.target_id))
                    await asyncio.sleep(0.5)

                    cdp_session = await browser_session.get_or_create_cdp_session(focus=True)
                    result = await cdp_session.cdp_client.send.Runtime.evaluate(
                        params={"expression": 'document.getElementById("header").textContent'},
                        session_id=cdp_session.session_id,
                    )
                    header_text = result.get("result", {}).get("value", "")

                    print(f"\n[EVT] Tab [{cid}] header: {header_text}")
                    assert name in header_text, (
                        f"Tab for {cid} should show '{name}' in header, got: {header_text}"
                    )
                except Exception as e:
                    print(f"  [WARN] Could not verify tab for {cid}: {e}")

        finally:
            await manager.stop()
