"""IPC handler for multi-tab Feige diagnostic experiments.

Used by the "Test Feige Tabs" buttons on the Tests page.  Used during
the 2026-05-20 multi-tab refactor planning to gather concrete data
about how Chrome enumerates and isolates multiple Feige tabs.

Two modes:

* ``inventory`` (default, read-only) — enumerate all open Feige tabs,
  capture per-tab DOM state (sidebar, focused customer, etc.), compute
  cross-tab comparisons.  No side effects.

* ``concurrent_send`` — types a test message into two different Feige
  tabs (each focused on a different customer) simultaneously, measures
  server-side delivery + cross-tab sidebar propagation.  Used to verify
  that Chrome / Feige actually permit parallel typing on multiple tabs.

Both modes connect to Chrome via the CDP debugging port (default 9228)
independently of any existing ``BrowserSession`` — same pattern
``EventMonitor`` uses (``event_monitor.py:66``).
"""

from __future__ import annotations

import asyncio
import json
import time
import traceback
import urllib.request
from typing import Any, Dict, List, Optional

from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import (
    IPCRequest,
    IPCResponse,
    create_error_response,
    create_success_response,
)
from utils.logger_helper import logger_helper as logger


DEFAULT_CDP_PORT = 9228

# Read-only diagnostic snapshot.  Designed to NEVER mutate DOM.
# Returns a JSON string (Runtime.evaluate handles string returns cleanly).
_FEIGE_TAB_SNAPSHOT_JS = r"""
(function() {
  var out = {
    ready_state: document.readyState,
    title: document.title,
    url: location.href,
    eval_started_at_ms: Date.now(),
    sidebar_count: 0,
    focused_customer: null,
    focused_msg_id: null,
    sidebar_sample: [],
    bubble_count: 0,
    body_text_len: (document.body && document.body.innerText || '').length
  };
  try {
    // Sidebar enumeration — try multiple selector patterns observed across
    // Feige UI versions.  Sidebar rows have a customer-name element and a
    // last-message preview.
    var sidebar_rows = document.querySelectorAll(
      '[data-qa-id="qa-conversation-item"], '
      + '[data-qa-id*="conversation-item"], '
      + '.conversation-item, '
      + '[class*="conversation-item"], '
      + '[class*="ConversationItem"]'
    );
    out.sidebar_count = sidebar_rows.length;

    // Sample first 10 sidebar rows
    var sample_limit = Math.min(10, sidebar_rows.length);
    for (var i = 0; i < sample_limit; i++) {
      var row = sidebar_rows[i];
      var row_text = (row.innerText || '').trim();
      // Try to split into name + preview heuristically (first line vs rest)
      var lines = row_text.split('\n').map(function(s){return s.trim();}).filter(function(s){return s.length > 0;});
      var is_active = row.classList.contains('active')
                    || row.classList.contains('selected')
                    || /(?:^|\s)active(?:\s|$)/.test(row.className)
                    || /(?:^|\s)is-active(?:\s|$)/.test(row.className);
      out.sidebar_sample.push({
        idx: i,
        text_preview: row_text.substring(0, 120),
        first_line: lines[0] || '',
        is_active: is_active
      });
    }

    // Focused customer = whichever sidebar row is class-active OR header text
    var active_row = null;
    for (var j = 0; j < sidebar_rows.length; j++) {
      if (sidebar_rows[j].classList.contains('active')
          || sidebar_rows[j].classList.contains('selected')
          || /(?:^|\s)is-active(?:\s|$)/.test(sidebar_rows[j].className)) {
        active_row = sidebar_rows[j];
        break;
      }
    }
    if (active_row) {
      out.focused_customer = (active_row.innerText || '').trim().substring(0, 60);
    }
    // Try chat header text as alternate focused-customer signal
    var headers = document.querySelectorAll(
      '[class*="chat-header"], [class*="ChatHeader"], '
      + '[class*="conversation-header"], [class*="ConversationHeader"]'
    );
    if (headers.length > 0) {
      out.header_text = (headers[0].innerText || '').trim().substring(0, 80);
    }

    // Latest bubble msg_id (read-only)
    var bubbles = document.querySelectorAll('[data-id], [data-message-id], [data-msg-id]');
    out.bubble_count = bubbles.length;
    if (bubbles.length > 0) {
      var last = bubbles[bubbles.length - 1];
      out.focused_msg_id = last.getAttribute('data-id')
                        || last.getAttribute('data-message-id')
                        || last.getAttribute('data-msg-id')
                        || '';
    }
  } catch (e) {
    out.error = String(e);
  }
  out.eval_finished_at_ms = Date.now();
  return JSON.stringify(out);
})();
"""

# Concurrent-send action.  Substitutes __CUSTOMER_NAME__ and __MESSAGE_TEXT__
# placeholders at Python build time.  Returns JSON with step-by-step timing.
_FEIGE_CLICK_SIDEBAR_AND_SEND_JS = r"""
(function() {
  var customer_name = "__CUSTOMER_NAME__";
  var message_text = "__MESSAGE_TEXT__";
  var out = { started_at_ms: Date.now(), steps: [] };
  function step(name, ok, info) {
    out.steps.push({
      t_ms: Date.now() - out.started_at_ms,
      name: name,
      ok: ok,
      info: info == null ? null : String(info).substring(0, 200)
    });
  }
  try {
    var rows = document.querySelectorAll(
      '[data-qa-id="qa-conversation-item"], '
      + '[data-qa-id*="conversation-item"], '
      + '.conversation-item, '
      + '[class*="conversation-item"], '
      + '[class*="ConversationItem"]'
    );
    var target_row = null;
    for (var i = 0; i < rows.length; i++) {
      var t = (rows[i].innerText || '');
      if (t.indexOf(customer_name) >= 0) { target_row = rows[i]; break; }
    }
    if (!target_row) {
      step('find_sidebar_row', false, 'no row matches customer_name=' + customer_name);
      out.error = 'customer_not_found';
      return JSON.stringify(out);
    }
    step('find_sidebar_row', true, 'matched row idx');
    target_row.click();
    step('click_row', true, null);

    // Best-effort sync wait for chat thread to load.  We can't truly sleep
    // in synchronous JS, but Feige's chat thread typically renders within
    // a few ms after the sidebar click for already-loaded threads.
    var input = null;
    var input_search_started = Date.now();
    for (var attempt = 0; attempt < 50; attempt++) {
      input = document.querySelector('[contenteditable="true"]')
            || document.querySelector('textarea[class*="input"]')
            || document.querySelector('textarea[class*="Input"]')
            || document.querySelector('textarea');
      if (input) break;
      // Busy-wait briefly (Feige typically renders within ~30ms)
      var sleep_start = performance.now();
      while (performance.now() - sleep_start < 20) { /* spin */ }
    }
    step('find_input', !!input, input ? input.tagName : 'not_found');
    if (!input) {
      out.error = 'no_input';
      return JSON.stringify(out);
    }

    if (input.tagName === 'TEXTAREA') {
      input.value = message_text;
      input.dispatchEvent(new Event('input', { bubbles: true }));
    } else {
      input.innerText = message_text;
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }
    step('type_text', true, 'len=' + message_text.length);

    var send_btn = document.querySelector(
      '[class*="send-btn"], [class*="send-button"], [class*="SendBtn"], button[class*="send"], [class*="sendButton"]'
    );
    if (!send_btn) {
      step('find_send_btn', false, 'no send button');
      out.error = 'no_send_btn';
      return JSON.stringify(out);
    }
    step('find_send_btn', true, send_btn.tagName);
    send_btn.click();
    step('click_send', true, null);

    out.finished_at_ms = Date.now();
    return JSON.stringify(out);
  } catch (e) {
    out.error = String(e);
    return JSON.stringify(out);
  }
})();
"""


async def _connect_cdp(cdp_port: int):
    """Connect to Chrome's CDP debugging port.  Returns started CDPClient."""
    from cdp_use import CDPClient

    version_url = f"http://127.0.0.1:{cdp_port}/json/version"
    try:
        with urllib.request.urlopen(version_url, timeout=2.0) as resp:
            version_info = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise RuntimeError(
            f"Cannot reach Chrome CDP at {version_url}: {type(e).__name__}: {e}"
        )

    cdp_ws_url = version_info.get("webSocketDebuggerUrl", "")
    if not cdp_ws_url:
        raise RuntimeError(
            f"No webSocketDebuggerUrl from Chrome at port {cdp_port} "
            f"(got: {list(version_info.keys())})"
        )

    client = CDPClient(url=cdp_ws_url)
    await client.start()
    return client


async def _enumerate_feige_tabs(client) -> List[Dict[str, Any]]:
    """Get all Chrome targets, filter to ones matching Feige URL pattern."""
    targets_result = await client.send_raw("Target.getTargets", {})
    if isinstance(targets_result, dict):
        target_infos = list(targets_result.get("targetInfos") or [])
    else:
        target_infos = list(getattr(targets_result, "targetInfos", None) or [])

    feige_tabs = []
    for ti in target_infos:
        url = str(ti.get("url") or ti.get("URL") or "")
        title = str(ti.get("title") or "")
        ttype = str(ti.get("type") or "")
        # Match Feige by URL fragment.  Tabs hosting the IM page satisfy this.
        if (
            "im.jinritemai.com" in url
            or "feige" in url.lower()
            or "飞鸽" in title
        ):
            feige_tabs.append(
                {
                    "targetId": str(ti.get("targetId") or ""),
                    "url": url,
                    "title": title,
                    "type": ttype,
                    "attached": bool(ti.get("attached") or False),
                    "browserContextId": str(ti.get("browserContextId") or ""),
                    "openerId": str(ti.get("openerId") or ""),
                }
            )
    return feige_tabs


async def _attach_and_eval(
    client,
    target_id: str,
    expression: str,
    *,
    timeout_s: float = 5.0,
) -> Dict[str, Any]:
    """Attach to a target, run JS, detach.  Returns {ok, value|error, eval_ms}."""
    sid = None
    try:
        attach_result = await client.send_raw(
            "Target.attachToTarget",
            {"targetId": target_id, "flatten": True},
        )
        sid = attach_result.get("sessionId") if isinstance(attach_result, dict) else None
        if not sid:
            return {"ok": False, "error": "attach: no sessionId returned"}

        await client.send_raw("Runtime.enable", {}, session_id=sid)

        t0 = time.time()
        eval_result = await asyncio.wait_for(
            client.send_raw(
                "Runtime.evaluate",
                {
                    "expression": expression,
                    "returnByValue": True,
                    "awaitPromise": False,
                },
                session_id=sid,
            ),
            timeout=timeout_s,
        )
        eval_ms = round((time.time() - t0) * 1000, 1)

        result = eval_result.get("result", {}) if isinstance(eval_result, dict) else {}
        # Handle thrown exceptions inside the page
        exception_details = (
            eval_result.get("exceptionDetails")
            if isinstance(eval_result, dict)
            else None
        )
        if exception_details:
            return {
                "ok": False,
                "error": f"page exception: {exception_details}",
                "eval_ms": eval_ms,
            }
        raw_value = result.get("value")
        # Our snapshot JS returns a JSON-string; parse it for convenience.
        if isinstance(raw_value, str):
            try:
                parsed = json.loads(raw_value)
                return {"ok": True, "value": parsed, "eval_ms": eval_ms}
            except Exception:
                return {"ok": True, "value": raw_value, "eval_ms": eval_ms}
        return {"ok": True, "value": raw_value, "eval_ms": eval_ms}
    except asyncio.TimeoutError:
        return {"ok": False, "error": f"eval timeout after {timeout_s}s"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    finally:
        if sid:
            try:
                await client.send_raw("Target.detachFromTarget", {"sessionId": sid})
            except Exception:
                pass


async def _run_inventory_mode(
    client,
    feige_tabs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Mode 1: read-only inventory + cross-tab comparison."""
    # Per-tab snapshot
    per_tab_state: Dict[str, Any] = {}
    for tab in feige_tabs:
        tid = tab["targetId"]
        per_tab_state[tid] = await _attach_and_eval(
            client, tid, _FEIGE_TAB_SNAPSHOT_JS, timeout_s=5.0
        )

    # Cross-tab: sidebar counts
    sidebar_counts: Dict[str, int] = {}
    for tid, r in per_tab_state.items():
        if r.get("ok") and isinstance(r.get("value"), dict):
            sidebar_counts[tid[:8]] = r["value"].get("sidebar_count", -1)
    distinct_counts = sorted(set(sidebar_counts.values())) if sidebar_counts else []
    sidebar_identical = len(distinct_counts) <= 1

    # Cross-tab: browser context grouping
    context_groups: Dict[str, List[str]] = {}
    for tab in feige_tabs:
        ctx = tab.get("browserContextId") or "(none)"
        context_groups.setdefault(ctx, []).append(tab["targetId"][:8])

    # Cross-tab: focused customer per tab
    focused_customers: Dict[str, Optional[str]] = {}
    for tid, r in per_tab_state.items():
        if r.get("ok") and isinstance(r.get("value"), dict):
            v = r["value"]
            focused_customers[tid[:8]] = (
                v.get("focused_customer")
                or v.get("header_text")
                or None
            )
    distinct_focused = sorted(
        {x for x in focused_customers.values() if x is not None}
    )

    return {
        "experiment_A_enumeration": {
            "total_feige_tabs": len(feige_tabs),
            "tabs": feige_tabs,
        },
        "experiment_B_per_tab_state": per_tab_state,
        "experiment_C_sidebar_identity": {
            "sidebar_counts_by_tab8": sidebar_counts,
            "distinct_counts": distinct_counts,
            "identical_across_tabs": sidebar_identical,
        },
        "experiment_D_contexts": {
            "context_groups_by_8": {
                k[:8] if k != "(none)" else k: v for k, v in context_groups.items()
            },
            "all_same_context": len(context_groups) == 1,
        },
        "experiment_E_focused_customers": {
            "focused_per_tab8": focused_customers,
            "distinct_focused_customers": distinct_focused,
            "all_tabs_focus_different_customers": (
                len(distinct_focused) == len(focused_customers)
                and len(focused_customers) > 0
                and all(x is not None for x in focused_customers.values())
            ),
        },
    }


async def _run_concurrent_send_mode(
    client,
    feige_tabs: List[Dict[str, Any]],
    customer_a: str,
    customer_b: str,
    message_text: str,
) -> Dict[str, Any]:
    """Mode 2: simultaneous send from 2 tabs to 2 customers."""
    if len(feige_tabs) < 2:
        return {
            "experiment_F_concurrent_send": {
                "error": f"Need at least 2 Feige tabs; found {len(feige_tabs)}.  "
                f"Manually open a second tab pointed at the same Feige store "
                f"before running this test."
            }
        }

    tab_a = feige_tabs[0]
    tab_b = feige_tabs[1]

    # Build per-tab JS with embedded args.  Escape minimal — we trust caller's text.
    def _escape_js(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    ts_tag = int(time.time())
    msg_a = f"{message_text}-A-{ts_tag}"
    msg_b = f"{message_text}-B-{ts_tag}"
    js_a = _FEIGE_CLICK_SIDEBAR_AND_SEND_JS.replace(
        "__CUSTOMER_NAME__", _escape_js(customer_a)
    ).replace("__MESSAGE_TEXT__", _escape_js(msg_a))
    js_b = _FEIGE_CLICK_SIDEBAR_AND_SEND_JS.replace(
        "__CUSTOMER_NAME__", _escape_js(customer_b)
    ).replace("__MESSAGE_TEXT__", _escape_js(msg_b))

    # Concurrent eval — asyncio.gather sends both CDP requests effectively
    # simultaneously over the WebSocket.
    t0 = time.time()
    results = await asyncio.gather(
        _attach_and_eval(client, tab_a["targetId"], js_a, timeout_s=15.0),
        _attach_and_eval(client, tab_b["targetId"], js_b, timeout_s=15.0),
        return_exceptions=True,
    )
    total_wall_ms = round((time.time() - t0) * 1000, 1)

    def _normalize(r):
        if isinstance(r, Exception):
            return {"ok": False, "error": f"{type(r).__name__}: {r}"}
        return r

    return {
        "experiment_F_concurrent_send": {
            "tab_a": {
                "targetId_8": tab_a["targetId"][:8],
                "customer": customer_a,
                "message_sent": msg_a,
            },
            "tab_b": {
                "targetId_8": tab_b["targetId"][:8],
                "customer": customer_b,
                "message_sent": msg_b,
            },
            "concurrent_wall_clock_ms": total_wall_ms,
            "result_a": _normalize(results[0]),
            "result_b": _normalize(results[1]),
        },
    }


async def _run_async(params: Dict[str, Any]) -> Dict[str, Any]:
    mode = str(params.get("mode") or "inventory").strip()
    cdp_port = int(params.get("cdp_port") or DEFAULT_CDP_PORT)
    customer_a = str(params.get("customer_a") or "").strip()
    customer_b = str(params.get("customer_b") or "").strip()
    message_text = str(params.get("message_text") or f"测试-{int(time.time())}").strip()

    out: Dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mode": mode,
        "cdp_port": cdp_port,
    }

    client = None
    try:
        client = await _connect_cdp(cdp_port)
        feige_tabs = await _enumerate_feige_tabs(client)
        out["total_feige_tabs_found"] = len(feige_tabs)

        if mode == "inventory":
            out.update(await _run_inventory_mode(client, feige_tabs))
        elif mode == "concurrent_send":
            if not customer_a or not customer_b:
                out["error"] = (
                    "concurrent_send mode requires customer_a and customer_b "
                    "params (test-customer names that exist in the Feige sidebar)"
                )
            else:
                # Snapshot first, then concurrent send, then snapshot again
                out["pre_send"] = await _run_inventory_mode(client, feige_tabs)
                out.update(
                    await _run_concurrent_send_mode(
                        client, feige_tabs, customer_a, customer_b, message_text
                    )
                )
                # Wait briefly for server to propagate, then re-snapshot
                await asyncio.sleep(1.2)
                out["post_send"] = await _run_inventory_mode(client, feige_tabs)
        else:
            out["error"] = f"unknown mode: {mode}"
        return out
    finally:
        if client is not None:
            try:
                await client.stop()
            except Exception:
                pass


@IPCHandlerRegistry.background_handler("test_feige_tabs")
def handle_test_feige_tabs(
    request: IPCRequest, params: Optional[Any]
) -> IPCResponse:
    """Run Feige multi-tab diagnostic.  See module docstring for modes."""
    try:
        params_dict: Dict[str, Any] = params if isinstance(params, dict) else {}
        logger.info(f"[test_feige_tabs] starting mode={params_dict.get('mode', 'inventory')}")

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(_run_async(params_dict))
        finally:
            try:
                loop.close()
            except Exception:
                pass
            asyncio.set_event_loop(None)

        logger.info(
            f"[test_feige_tabs] completed mode={params_dict.get('mode', 'inventory')} "
            f"feige_tabs={result.get('total_feige_tabs_found', 0)}"
        )
        return create_success_response(request, result)
    except Exception as e:
        logger.error(
            f"[test_feige_tabs] error: {e}\n{traceback.format_exc()}"
        )
        return create_error_response(
            request, "FEIGE_TAB_TEST_ERROR", f"Error: {str(e)}"
        )
