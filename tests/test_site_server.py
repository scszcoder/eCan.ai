"""
Multi-Customer Chat Test Rig Server
====================================

A self-contained HTTP server that simulates a multi-customer e-commerce
chat platform using HTTP polling (no WebSocket).  Designed for end-to-end
testing of eCan.ai multi-agent customer support workflows.

Serves three things:
  1. /control  — Control panel with 3 buttons:
       • Start / Restart Server  (tears down & restarts fresh)
       • Simulate 3 New Customers (3 new chats within ~1s)
       • Simulate 3 Follow-up Messages (random msgs from existing customers)
  2. /chat?session=<id>  — Per-customer chat page (HTTP-polling)
  3. REST API endpoints:
       POST /api/sim/new_customers    — inject N new customer conversations
       POST /api/sim/followup         — inject N follow-up messages
       POST /batch_get_params         — polling endpoint (returns messages)
       POST /send_msg                 — agent reply endpoint
       POST /api/reset                — clear all state
       GET  /api/state                — dump current server state as JSON

Architecture
------------
    Browser (chat page per customer)
        |
        |  POST /batch_get_params  (every 2s, per session)
        v
    This Server (in-memory message store, keyed by session_id)
        |
        v
    CDP Network interception (PollingCapture / Event Monitors)
        |
        v
    eCan.ai agent tasks react to new messages

Usage:
    python tests/test_site_server.py                     # default port 9877
    python tests/test_site_server.py --port 9877
    python tests/test_site_server.py --host 0.0.0.0      # expose to LAN
"""

import argparse
import json
import os
import random
import socketserver
import string
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# =====================================================================
# In-memory state
# =====================================================================

# session_id -> list of message dicts
_CHAT_STORES: Dict[str, List[dict]] = {}
# session_id -> poll count
_POLL_COUNTS: Dict[str, int] = {}
# session_id -> customer metadata
_CUSTOMERS: Dict[str, dict] = {}
# global event log (most recent 200 entries)
_EVENT_LOG: List[dict] = []

_MAX_EVENT_LOG = 200
DEFAULT_FRONT_DESK_AGENT_ID = "agent_48bdd65f982a4cdb"
DEFAULT_SERVICE_AGENT_ID = "agent_b31f281332104b93"

# Sample product queries for simulation
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
]

FOLLOWUP_MESSAGES = [
    "Actually, one more question -- do you have it in blue?",
    "What about the warranty on this?",
    "Can I pick it up in store instead?",
    "Never mind, I'll take two!",
    "How does the sizing run for this?",
    "Is there a student discount available?",
    "Can I combine coupons with the current sale?",
    "When is your next big sale event?",
    "Do sale items qualify for reward points?",
    "What payment methods do you accept?",
]

CUSTOMER_NAMES = [
    "Alice", "Bob", "Carol", "David", "Eve", "Frank", "Grace",
    "Hank", "Ivy", "Jack", "Karen", "Leo", "Mia", "Nick", "Olivia",
]


def _get_store(session_id: str) -> List[dict]:
    if session_id not in _CHAT_STORES:
        _CHAT_STORES[session_id] = []
    return _CHAT_STORES[session_id]


def _add_message(session_id: str, msg: dict):
    store = _get_store(session_id)
    store.append(msg)
    _log_event("message", {
        "session_id": session_id,
        "msg_id": msg.get("msg_id"),
        "from": msg.get("from"),
        "text": msg.get("text", "")[:80],
    })


def _log_event(event_type: str, data: dict):
    entry = {"type": event_type, "timestamp": int(time.time() * 1000), **data}
    _EVENT_LOG.append(entry)
    if len(_EVENT_LOG) > _MAX_EVENT_LOG:
        _EVENT_LOG.pop(0)


def _reset_all():
    _CHAT_STORES.clear()
    _POLL_COUNTS.clear()
    _CUSTOMERS.clear()
    _EVENT_LOG.clear()
    _log_event("reset", {"message": "All state cleared"})


def _generate_session_id() -> str:
    return "cust_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=6))


def _create_new_customer() -> dict:
    """Create a new customer with a unique session and an initial message."""
    session_id = _generate_session_id()
    name = random.choice(CUSTOMER_NAMES) + "_" + session_id[-4:]
    query = random.choice(PRODUCT_QUERIES)
    msg_id = f"msg_{int(time.time()*1000)}_{random.randint(100,999)}"

    _CUSTOMERS[session_id] = {
        "session_id": session_id,
        "name": name,
        "created_at": int(time.time() * 1000),
    }

    _add_message(session_id, {
        "msg_id": msg_id,
        "from": "customer",
        "text": query,
        "customer_name": name,
        "customer_name": name,
        "timestamp": int(time.time() * 1000),
    })

    return {"session_id": session_id, "name": name, "query": query, "msg_id": msg_id}


def _discover_open_chat_tabs_from_cdp(cdp_port: int = 9228, limit: int = 3) -> List[dict]:
    base_url = f"http://127.0.0.1:{int(cdp_port)}/json/list"
    sys.stderr.write(f"[test_rig] discover_open_chat_tabs_from_cdp port={cdp_port} limit={limit}\n")
    req = Request(base_url, headers={"User-Agent": "eCan-test-rig"})
    with urlopen(req, timeout=3) as resp:
        payload = json.loads(resp.read().decode("utf-8", errors="replace"))

    tabs: List[dict] = []
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "")
        url = str(item.get("url") or "")
        if item_type not in ("page", "tab"):
            continue
        if "127.0.0.1:9877/chat?session=" not in url and "localhost:9877/chat?session=" not in url:
            continue
        parsed = urlparse(url)
        session_id = (parse_qs(parsed.query).get("session") or [""])[0].strip()
        if not session_id:
            continue
        customer = _CUSTOMERS.get(session_id, {})
        tabs.append({
            "session_id": session_id,
            "tab_id": str(item.get("id") or "").strip(),
            "chat_url": url,
            "customer_name": customer.get("name") or session_id,
            "title": str(item.get("title") or "").strip(),
        })

    deduped: List[dict] = []
    seen_sessions = set()
    for item in tabs:
        sid = item["session_id"]
        if sid in seen_sessions:
            continue
        seen_sessions.add(sid)
        deduped.append(item)
    sys.stderr.write(
        "[test_rig] discovered_chat_tabs="
        + json.dumps(deduped[: max(1, int(limit))], ensure_ascii=False)
        + "\n"
    )
    return deduped[: max(1, int(limit))]


def _send_direct_service_assignments(
    assignments: List[dict],
    sender_agent_id: str = DEFAULT_FRONT_DESK_AGENT_ID,
    recipient_agent_id: str = DEFAULT_SERVICE_AGENT_ID,
    local_server_port: int = 4668,
) -> List[dict]:
    endpoint = f"http://127.0.0.1:{int(local_server_port)}/api/test-direct-service-assign"
    body = {
        "sender_agent_id": sender_agent_id,
        "recipient_agent_id": recipient_agent_id,
        "assignments": assignments,
    }
    sys.stderr.write(
        "[test_rig] forwarding_direct_assignments_to_app="
        + json.dumps({"endpoint": endpoint, **body}, ensure_ascii=False)
        + "\n"
    )
    req = Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "eCan-test-rig"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=20) as resp:
            response_payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except HTTPError as e:
        error_body = ""
        try:
            error_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        sys.stderr.write(
            "[test_rig] app_direct_assignment_http_error="
            + json.dumps({
                "status": getattr(e, "code", None),
                "reason": str(e),
                "body": error_body[:4000],
            }, ensure_ascii=False)
            + "\n"
        )
        raise
    results = response_payload.get("results") or []
    sys.stderr.write(
        "[test_rig] app_direct_assignment_response="
        + json.dumps(response_payload, ensure_ascii=False, default=str)
        + "\n"
    )
    return results


def _send_followup(session_id: str) -> Optional[dict]:
    """Send a follow-up message from an existing customer."""
    if session_id not in _CUSTOMERS:
        return None
    customer = _CUSTOMERS[session_id]
    text = random.choice(FOLLOWUP_MESSAGES)
    injected_at_ms = int(time.time() * 1000)
    msg_id = f"msg_{injected_at_ms}_{random.randint(100,999)}"
    _add_message(session_id, {
        "msg_id": msg_id,
        "from": "customer",
        "text": text,
        "customer_name": customer["name"],
        "timestamp": injected_at_ms,
    })
    sys.stderr.write(
        "[test_rig] followup_injected="
        + json.dumps({
            "session_id": session_id,
            "customer_name": customer["name"],
            "msg_id": msg_id,
            "injected_at_ms": injected_at_ms,
            "text": text,
        }, ensure_ascii=False)
        + "\n"
    )
    return {
        "session_id": session_id,
        "name": customer["name"],
        "text": text,
        "msg_id": msg_id,
        "injected_at_ms": injected_at_ms,
    }


# =====================================================================
# Chat Page HTML (per-customer, HTTP-polling)
# =====================================================================

CHAT_PAGE_HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>Chat — {{CUSTOMER_NAME}}</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           max-width: 600px; margin: 40px auto; padding: 0 16px; background: #f5f5f5; }
    h2 { margin-bottom: 4px; }
    .meta { color: #999; font-size: 12px; margin-bottom: 12px; }
    #messages { border: 1px solid #ddd; padding: 16px; min-height: 250px;
                border-radius: 12px; background: #fff; overflow-y: auto; max-height: 500px; }
    .msg { padding: 8px 14px; margin: 6px 0; border-radius: 16px; max-width: 80%;
           line-height: 1.4; font-size: 14px; }
    .msg.customer { background: #e3f2fd; margin-right: auto; }
    .msg.agent    { background: #c8e6c9; margin-left: auto; text-align: right; }
    .input-row { display: flex; gap: 8px; margin-top: 12px; }
    .input-row input { flex: 1; padding: 10px 14px; border: 1px solid #ddd;
                       border-radius: 8px; font-size: 14px; }
    .input-row button { padding: 10px 20px; background: #1976d2; color: #fff;
                        border: none; border-radius: 8px; cursor: pointer; font-size: 14px; }
    .input-row button:hover { background: #1565c0; }
    .stats { color: #999; font-size: 12px; margin-top: 8px; display: flex; gap: 16px; }
  </style>
</head>
<body>
  <h2>💬 {{CUSTOMER_NAME}}</h2>
  <div class="meta">Session: {{SESSION_ID}} · Polling every 2s</div>
  <div id="messages">{{INITIAL_MESSAGES_HTML}}</div>
  <div class="input-row">
    <input id="msg-input" type="text" placeholder="Type a message…"
           onkeydown="if(event.key==='Enter')sendMessage()" />
    <button onclick="sendMessage()">Send</button>
  </div>
  <div class="stats">
    <span>Polls: <span id="poll-count">0</span></span>
    <span>Messages: <span id="msg-count">0</span></span>
  </div>
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
        document.getElementById('poll-count').textContent = pollCount;

        const chatBox = document.getElementById('messages');
        const messages = Array.isArray(data.messages) ? data.messages : [];
        chatBox.innerHTML = messages.map(msg => {
          const from = String(msg.from || '');
          const msgId = String(msg.msg_id || '');
          const ts = String(msg.timestamp || '');
          const safeText = String((msg.customer_name && msg.from === 'customer'
            ? msg.customer_name + ': ' : '') + (msg.text || ''))
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
          return `<div class="msg ${from}" data-msg-id="${msgId}" data-from="${from}" data-ts="${ts}">${safeText}</div>`;
        }).join('');
        lastMsgCount = messages.length;
        document.getElementById('msg-count').textContent = lastMsgCount;
        chatBox.scrollTop = chatBox.scrollHeight;
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


# =====================================================================
# Control Panel HTML
# =====================================================================

CONTROL_PANEL_HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>eCan.ai — Multi-Customer Test Rig</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           max-width: 900px; margin: 0 auto; padding: 24px; background: #0d1117; color: #e6edf3; }
    h1 { font-size: 24px; margin-bottom: 4px; }
    .subtitle { color: #8b949e; font-size: 14px; margin-bottom: 24px; }
    .btn-row { display: flex; gap: 12px; margin-bottom: 24px; flex-wrap: wrap; }
    .btn { padding: 12px 24px; border: 1px solid #30363d; border-radius: 8px;
           cursor: pointer; font-size: 14px; font-weight: 600;
           transition: all 0.15s; display: flex; align-items: center; gap: 8px; }
    .btn:hover { transform: translateY(-1px); }
    .btn:active { transform: translateY(0); }
    .btn-green  { background: #238636; color: #fff; border-color: #238636; }
    .btn-green:hover { background: #2ea043; }
    .btn-blue   { background: #1f6feb; color: #fff; border-color: #1f6feb; }
    .btn-blue:hover { background: #388bfd; }
    .btn-orange { background: #bd5800; color: #fff; border-color: #bd5800; }
    .btn-orange:hover { background: #d47616; }
    .btn-red    { background: #da3633; color: #fff; border-color: #da3633; }
    .btn-red:hover { background: #f85149; }
    .btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

    .section { background: #161b22; border: 1px solid #30363d; border-radius: 12px;
               padding: 16px; margin-bottom: 16px; }
    .section h3 { font-size: 14px; color: #8b949e; text-transform: uppercase;
                  letter-spacing: 0.5px; margin-bottom: 12px; }

    #log { font-family: 'Cascadia Code', 'Fira Code', monospace; font-size: 12px;
           max-height: 300px; overflow-y: auto; background: #0d1117;
           border: 1px solid #21262d; border-radius: 8px; padding: 12px;
           line-height: 1.6; }
    .log-entry { border-bottom: 1px solid #21262d; padding: 2px 0; }
    .log-ts { color: #484f58; }
    .log-type { font-weight: 600; }
    .log-type.message { color: #58a6ff; }
    .log-type.sim { color: #f0883e; }
    .log-type.reset { color: #da3633; }

    .customer-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
                     gap: 8px; }
    .customer-card { background: #0d1117; border: 1px solid #21262d; border-radius: 8px;
                     padding: 10px 12px; font-size: 13px; }
    .customer-card .name { font-weight: 600; color: #58a6ff; }
    .customer-card .session { color: #484f58; font-size: 11px; }
    .customer-card .msg-count { color: #8b949e; }
    .customer-card a { color: #58a6ff; text-decoration: none; font-size: 12px; }
    .customer-card a:hover { text-decoration: underline; }

    .stat-row { display: flex; gap: 24px; margin-bottom: 16px; }
    .stat { text-align: center; }
    .stat .val { font-size: 28px; font-weight: 700; color: #58a6ff; }
    .stat .lbl { font-size: 12px; color: #8b949e; }
  </style>
</head>
<body>
  <h1>🧪 Multi-Customer Chat Test Rig</h1>
  <div class="subtitle">Simulated e-commerce chat platform for eCan.ai multi-agent testing</div>

  <!-- Buttons -->
  <div class="btn-row">
    <button class="btn btn-red" onclick="resetServer()" id="btn-reset">
      🔄 Reset Server
    </button>
    <button class="btn btn-blue" onclick="simNewCustomers()" id="btn-new">
      👤 3 New Customers
    </button>
    <button class="btn btn-orange" onclick="simFollowups()" id="btn-followup">
      💬 3 Follow-up Messages
    </button>
    <button class="btn btn-green" onclick="assignOpenTabs()" id="btn-assign-tabs">
      🧪 Assign 3 Open Chat Tabs
    </button>
  </div>

  <!-- Stats -->
  <div class="section">
    <h3>Dashboard</h3>
    <div class="stat-row">
      <div class="stat"><div class="val" id="stat-customers">0</div><div class="lbl">Customers</div></div>
      <div class="stat"><div class="val" id="stat-messages">0</div><div class="lbl">Messages</div></div>
      <div class="stat"><div class="val" id="stat-sessions">0</div><div class="lbl">Sessions</div></div>
    </div>
  </div>

  <!-- Active Customers -->
  <div class="section">
    <h3>Active Customers</h3>
    <div id="customers" class="customer-grid">
      <div style="color: #484f58;">No customers yet. Click "3 New Customers" to start.</div>
    </div>
  </div>

  <!-- Event Log -->
  <div class="section">
    <h3>Event Log</h3>
    <div id="log"></div>
  </div>

  <script>
    const BASE = '';

    async function resetServer() {
      btn('btn-reset', true);
      try {
        const resp = await fetch(BASE + '/api/reset', {method: 'POST'});
        const data = await resp.json();
        addLog('reset', 'Server state cleared');
        refreshState();
      } catch(e) { addLog('error', 'Reset failed: ' + e); }
      btn('btn-reset', false);
    }

    async function simNewCustomers() {
      btn('btn-new', true);
      try {
        const resp = await fetch(BASE + '/api/sim/new_customers', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({count: 3})
        });
        const data = await resp.json();
        if (data.customers) {
          data.customers.forEach(c => {
            addLog('sim', `New customer: ${c.name} (${c.session_id}) — "${c.query}"`);
          });
        }
        refreshState();
      } catch(e) { addLog('error', 'Sim failed: ' + e); }
      btn('btn-new', false);
    }

    async function simFollowups() {
      btn('btn-followup', true);
      try {
        const resp = await fetch(BASE + '/api/sim/followup', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            count: 3,
            use_open_chat_tabs: true,
            cdp_port: 9228
          })
        });
        const data = await resp.json();
        if (data.messages) {
          data.messages.forEach(m => {
            addLog('sim', `Follow-up from ${m.name} (${m.session_id}): "${m.text}"`);
          });
        }
        if (data.error) addLog('error', data.error);
        refreshState();
      } catch(e) { addLog('error', 'Followup failed: ' + e); }
      btn('btn-followup', false);
    }

    async function assignOpenTabs() {
      btn('btn-assign-tabs', true);
      try {
        const resp = await fetch(BASE + '/api/test/assign_open_tabs', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            count: 3,
            cdp_port: 9228,
            local_server_port: 4668,
            sender_agent_id: 'agent_48bdd65f982a4cdb',
            recipient_agent_id: 'agent_b31f281332104b93'
          })
        });
        const data = await resp.json();
        if (data.assignments) {
          data.assignments.forEach(a => {
            addLog(
              data.success ? 'sim' : 'error',
              `Direct assign ${a.session_id} -> ${a.recipient_agent_id} tab ${a.tab_id} msg ${a.message_id || 'n/a'}`
            );
          });
        }
        if (data.error) addLog('error', data.error);
      } catch(e) { addLog('error', 'Direct assign failed: ' + e); }
      btn('btn-assign-tabs', false);
    }

    async function refreshState() {
      try {
        const resp = await fetch(BASE + '/api/state');
        const data = await resp.json();

        // Stats
        document.getElementById('stat-customers').textContent = Object.keys(data.customers || {}).length;
        document.getElementById('stat-sessions').textContent = Object.keys(data.sessions || {}).length;
        let totalMsgs = 0;
        Object.values(data.sessions || {}).forEach(msgs => totalMsgs += msgs.length);
        document.getElementById('stat-messages').textContent = totalMsgs;

        // Customer grid
        const grid = document.getElementById('customers');
        const customers = Object.values(data.customers || {});
        if (customers.length === 0) {
          grid.innerHTML = '<div style="color:#484f58;">No customers yet. Click "3 New Customers" to start.</div>';
        } else {
          grid.innerHTML = customers.map(c => {
            const msgs = (data.sessions[c.session_id] || []);
            const lastMsg = msgs.length > 0 ? msgs[msgs.length - 1].text : '';
            return `<div class="customer-card">
              <div class="name">${c.name}</div>
              <div class="session">${c.session_id}</div>
              <div class="msg-count">${msgs.length} message(s)</div>
              <div style="color:#8b949e;font-size:12px;margin-top:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
                   title="${lastMsg.replace(/"/g, '&quot;')}">Last: ${lastMsg}</div>
              <a href="/chat?session=${c.session_id}" target="_blank">Open Chat ↗</a>
            </div>`;
          }).join('');
        }

        // Event log
        if (data.event_log && data.event_log.length > 0) {
          const logDiv = document.getElementById('log');
          logDiv.innerHTML = data.event_log.slice(-50).reverse().map(e => {
            const ts = new Date(e.timestamp).toLocaleTimeString();
            return `<div class="log-entry"><span class="log-ts">${ts}</span> <span class="log-type ${e.type}">[${e.type}]</span> ${e.text || e.message || JSON.stringify(e)}</div>`;
          }).join('');
        }
      } catch(e) {
        console.error('State refresh error:', e);
      }
    }

    function addLog(type, text) {
      const logDiv = document.getElementById('log');
      const ts = new Date().toLocaleTimeString();
      const entry = document.createElement('div');
      entry.className = 'log-entry';
      entry.innerHTML = `<span class="log-ts">${ts}</span> <span class="log-type ${type}">[${type}]</span> ${text}`;
      logDiv.prepend(entry);
      // Trim old entries
      while (logDiv.children.length > 100) logDiv.removeChild(logDiv.lastChild);
    }

    function btn(id, disabled) {
      document.getElementById(id).disabled = disabled;
    }

    // Auto-refresh every 3s
    setInterval(refreshState, 3000);
    refreshState();
  </script>
</body>
</html>
"""


# =====================================================================
# HTTP Request Handler
# =====================================================================


class TestSiteHandler(BaseHTTPRequestHandler):
    """Handles all routes for the test rig."""

    @staticmethod
    def _render_initial_messages_html(session_id: str) -> str:
        messages = _get_store(session_id)
        html_parts = []
        for msg in messages:
            from_value = str(msg.get("from") or "")
            msg_id = str(msg.get("msg_id") or "")
            ts = str(msg.get("timestamp") or "")
            text_prefix = ""
            if from_value == "customer" and msg.get("customer_name"):
                text_prefix = f"{msg.get('customer_name')}: "
            text = f"{text_prefix}{str(msg.get('text') or '')}"
            safe_text = (
                text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
            )
            html_parts.append(
                f'<div class="msg {from_value}" '
                f'data-msg-id="{msg_id}" data-from="{from_value}" data-ts="{ts}">'
                f"{safe_text}</div>"
            )
        return "".join(html_parts)

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            params = parse_qs(parsed.query)

            if path == "/" or path == "/control":
                self._html_response(200, CONTROL_PANEL_HTML)

            elif path == "/chat":
                session_id = params.get("session", ["default"])[0]
                customer = _CUSTOMERS.get(session_id, {})
                name = customer.get("name", session_id)
                html = CHAT_PAGE_HTML
                html = html.replace("{{SESSION_ID}}", session_id)
                html = html.replace("{{CUSTOMER_NAME}}", name)
                html = html.replace("{{INITIAL_MESSAGES_HTML}}", self._render_initial_messages_html(session_id))
                self._html_response(200, html)

            elif path == "/api/state":
                state = {
                    "customers": _CUSTOMERS,
                    "sessions": {sid: msgs for sid, msgs in _CHAT_STORES.items()},
                    "poll_counts": _POLL_COUNTS,
                    "event_log": _EVENT_LOG[-50:],
                }
                self._json_response(200, json.dumps(state, default=str))

            else:
                self.send_error(404, "Not found")
        except Exception as exc:
            sys.stderr.write(f"[test_rig] GET {self.path} failed: {exc}\n")
            sys.stderr.write(traceback.format_exc())
            try:
                self._html_response(500, "<html><body><h1>500 Internal Server Error</h1></body></html>")
            except Exception:
                pass

    def do_POST(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path

            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length).decode("utf-8") if content_length else ""
            try:
                body_json = json.loads(raw_body) if raw_body else {}
            except json.JSONDecodeError:
                body_json = {}

            # --- Polling endpoint (used by chat pages) ---
            if "/batch_get_params" in path:
                session_id = body_json.get("session_id", "default")
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

            # --- Agent reply endpoint ---
            elif "/send_msg" in path:
                session_id = body_json.get("session_id", "default")
                text = body_json.get("text", "")
                msg = {
                    "msg_id": body_json.get("msg_id", str(int(time.time() * 1000))),
                    "from": "agent",
                    "text": text,
                    "timestamp": int(time.time() * 1000),
                }
                _add_message(session_id, msg)
                self._json_response(200, json.dumps({"status": "sent", "msg_id": msg["msg_id"]}))

            # --- Simulation: new customers ---
            elif path == "/api/sim/new_customers":
                count = body_json.get("count", 3)
                count = max(1, min(count, 20))  # clamp 1-20
                customers = []
                for i in range(count):
                    # Stagger slightly within ~1 second
                    if i > 0:
                        time.sleep(random.uniform(0.1, 0.3))
                    c = _create_new_customer()
                    customers.append(c)
                _log_event("sim", {"message": f"Created {count} new customers"})
                self._json_response(200, json.dumps({"success": True, "customers": customers}))

            # --- Simulation: follow-up messages ---
            elif path == "/api/sim/followup":
                count = body_json.get("count", 3)
                count = max(1, min(count, 20))
                existing = list(_CUSTOMERS.keys())
                use_open_chat_tabs = bool(body_json.get("use_open_chat_tabs", False))
                if use_open_chat_tabs:
                    cdp_port = int(body_json.get("cdp_port", 9228) or 9228)
                    open_tabs = _discover_open_chat_tabs_from_cdp(cdp_port=cdp_port, limit=count)
                    targeted_sessions = [str(t.get("session_id") or "").strip() for t in open_tabs if str(t.get("session_id") or "").strip()]
                    if targeted_sessions:
                        existing = targeted_sessions
                        sys.stderr.write(
                            "[test_rig] followup_target_sessions="
                            + json.dumps(targeted_sessions, ensure_ascii=False)
                            + "\n"
                        )
                if not existing:
                    self._json_response(200, json.dumps({
                        "success": False,
                        "error": "No existing customers. Create some first.",
                        "messages": [],
                    }))
                    return
                messages = []
                selected = random.sample(existing, min(count, len(existing)))
                for sid in selected:
                    if len(messages) > 0:
                        time.sleep(random.uniform(0.1, 0.3))
                    result = _send_followup(sid)
                    if result:
                        messages.append(result)
                _log_event("sim", {"message": f"Sent {len(messages)} follow-up messages"})
                self._json_response(200, json.dumps({"success": True, "messages": messages}))

            # --- Direct service assignment harness ---
            elif path == "/api/test/assign_open_tabs":
                count = max(1, min(int(body_json.get("count", 3) or 3), 10))
                cdp_port = int(body_json.get("cdp_port", 9228) or 9228)
                local_server_port = int(body_json.get("local_server_port", 4668) or 4668)
                sender_agent_id = str(body_json.get("sender_agent_id") or DEFAULT_FRONT_DESK_AGENT_ID).strip()
                recipient_agent_id = str(body_json.get("recipient_agent_id") or DEFAULT_SERVICE_AGENT_ID).strip()

                tabs = _discover_open_chat_tabs_from_cdp(cdp_port=cdp_port, limit=count)
                if not tabs:
                    self._json_response(200, json.dumps({
                        "success": False,
                        "error": f"No open chat tabs found from CDP on port {cdp_port}.",
                        "assignments": [],
                    }))
                    return

                assignments = _send_direct_service_assignments(
                    tabs,
                    sender_agent_id=sender_agent_id,
                    recipient_agent_id=recipient_agent_id,
                    local_server_port=local_server_port,
                )
                ok = [a for a in assignments if a.get("success")]
                _log_event("sim", {
                    "message": (
                        f"Direct service assignment harness sent {len(ok)}/{len(assignments)} "
                        f"assignment(s) to {recipient_agent_id}"
                    )
                })
                self._json_response(200, json.dumps({
                    "success": len(ok) == len(assignments),
                    "count": len(assignments),
                    "assignments": assignments,
                }, default=str))

            # --- Reset ---
            elif path == "/api/reset":
                _reset_all()
                self._json_response(200, json.dumps({"success": True, "message": "State cleared"}))

            # --- Telemetry (no-op) ---
            elif "/report_frontend" in path:
                self._json_response(200, json.dumps({"status": "ok"}))

            else:
                self.send_error(404, "Not found")
        except Exception as exc:
            sys.stderr.write(f"[test_rig] POST {self.path} failed: {exc}\n")
            sys.stderr.write(traceback.format_exc())
            try:
                self._json_response(500, json.dumps({"success": False, "error": str(exc)}))
            except Exception:
                pass

    # --- Response helpers ---

    def _json_response(self, code: int, body: str):
        content = body.encode("utf-8", errors="replace")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content)

    def _html_response(self, code: int, body: str):
        content = body.encode("utf-8", errors="replace")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, fmt, *args):
        # Compact logging: only show non-polling requests
        msg = fmt % args
        if "/batch_get_params" not in msg and "/api/state" not in msg:
            sys.stderr.write(f"  [{time.strftime('%H:%M:%S')}] {msg}\n")


class ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


# =====================================================================
# Main entry point
# =====================================================================

def start_server(host: str = "127.0.0.1", port: int = 9877) -> ThreadedHTTPServer:
    """Start the test rig server and return the server instance."""
    server = ThreadedHTTPServer((host, port), TestSiteHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"  [OK] Test site server running at http://{host}:{port}")
    print(f"     Control panel: http://{host}:{port}/control")
    return server


def main():
    parser = argparse.ArgumentParser(description="Multi-Customer Chat Test Rig Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=9877, help="Port to bind to (default: 9877)")
    args = parser.parse_args()

    print("=" * 60)
    print("  eCan.ai Multi-Customer Chat Test Rig")
    print("=" * 60)

    server = start_server(args.host, args.port)

    print(f"\n  Endpoints:")
    print(f"    GET  /control                — Control panel (3 buttons)")
    print(f"    GET  /chat?session=<id>      — Per-customer chat page")
    print(f"    POST /batch_get_params       — Polling endpoint")
    print(f"    POST /send_msg               — Agent reply endpoint")
    print(f"    POST /api/sim/new_customers  — Simulate new customers")
    print(f"    POST /api/sim/followup       — Simulate follow-up messages")
    print(f"    POST /api/reset              — Clear all state")
    print(f"    GET  /api/state              — Dump current state")
    print(f"\n  Press Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n  Shutting down...")
        server.shutdown()
        print("  Done.")


if __name__ == "__main__":
    main()
