"""Feige (飞鸽) site tools for the browser-use controller.

Moved verbatim from ``extension_tools_service.py`` (round 2, 2026-08-02)
so the platform module carries no site-specific code.  Contains the four
controller actions (``feige_list_sessions`` / ``feige_open_session`` /
``feige_get_chat_thread`` / ``feige_send_message``), their pydantic
action models (moved from ``extension_tools_views.py``), the JS template
constants, and the off-DOM WS send helpers (``feige_ws_send_text`` /
``_feige_ws_try_send``).

Importing this module registers the actions on the shared
``custom_controller`` via decorators.  The bundle ``__init__`` imports it
on package load, and the bundle auto-loads at process start via
``build_node._discover_external_hook_bundles`` — so the tools register
exactly as early as they did when they lived in the platform module.

Import direction: this bundle module imports the generic CDP helpers FROM
``extension_tools_service`` (business → platform is the allowed
direction).  The platform module must never import this one.
"""
import asyncio
import json
import os
from typing import Optional

from pydantic import BaseModel, Field

from browser_use import BrowserSession
from browser_use.agent.views import ActionResult

from utils.logger_helper import logger_helper as logger
from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.sidebar_preview_js import (
    ROW_PREVIEW_FALLBACK_JS as _ROW_PREVIEW_FALLBACK_JS,
)

from agent.ec_skills.browser_use_extension.extension_tools_service import (
    _LIVE_CHAT_SEND_CDP_EVALUATE_TIMEOUT_S,
    _evaluate_js,
    _evaluate_live_chat_js,
    _json_result,
    _live_chat_send_cdp_timeout_remaining,
    _live_chat_send_page_timing_fields,
    _record_live_chat_send_cdp_success,
    _record_live_chat_send_cdp_timeout,
    _resolve_live_chat_tab_target_id_bounded,
    custom_controller,
    live_chat_cdp_health_cooldown_remaining,
)


# ── Action models (moved from extension_tools_views.py) ──────────────────────
class FeigeListSessionsAction(BaseModel):
	"""List all visible customer sessions from the Feige (飞鸽) session panel.
	Returns each session's customer name, last message snippet, timestamp, and unread count.
	Use this instead of generic DOM extraction when operating on Feige customer service pages.
	"""
	include_read: bool = Field(
		default=True,
		description="Include sessions with no unread messages. Set False to return only sessions with unread messages.",
	)
	max_sessions: int = Field(
		default=50,
		description="Maximum number of sessions to return (scrolled into view).",
	)


class FeigeOpenSessionAction(BaseModel):
	"""Click a customer session in the Feige (飞鸽) session list to open the chat thread.
	Use the customer_name or session_index returned by feige_list_sessions.
	"""
	customer_name: Optional[str] = Field(
		default=None,
		description="Customer name as returned by feige_list_sessions. Used for matching.",
	)
	session_index: Optional[int] = Field(
		default=None,
		description="Zero-based index into the session list (fallback when customer_name is ambiguous).",
	)


class FeigeGetChatThreadAction(BaseModel):
	"""Extract visible messages from the currently open Feige (飞鸽) chat thread.
	Returns a list of message objects: {sender, text, timestamp, is_agent}.
	"""
	max_messages: int = Field(
		default=30,
		description="Maximum number of messages to return (most recent).",
	)


class FeigeSendMessageAction(BaseModel):
	"""Type and send a text message in the currently open Feige (飞鸽) chat thread.
	Finds the contenteditable input, types the text, and clicks Send (or presses Enter).
	"""
	text: str = Field(
		description="Message text to send to the customer.",
	)
	customer_name: Optional[str] = Field(
		default=None,
		description="Optional expected active customer name. When provided, the action refuses to type unless the open Feige chat matches.",
	)
	source_customer_msg_id: Optional[str] = Field(
		default=None,
		description="Optional latest customer message id this reply answers. When provided, the action refuses to send if a newer customer bubble is visible.",
	)
	source_latest_message: Optional[str] = Field(
		default=None,
		description="Optional latest customer message text this reply answers. Used as a fallback stale-reply guard when message id is unavailable.",
	)

# ─── Feige (飞鸽) platform-specific tools ─────────────────────────────────────
#
# Selectors confirmed from live DOM captures (Feige customer-service web app).
# Session list panel:
#   Scroll root : #chantListScrollArea
#   Items       : [data-qa-id="qa-conversation-chat-item"]
#   Name        : .MP1bk3ccfHC9V2SnPCGD (title attr) or .Jv6FtqUv5VoYARd2pp4y (text)
#   Last msg    : .lF_M7QiFB0ukHWpMfQde span
#   Timestamp   : .CEnLM8MEGksTdgi_8Lqf (absolute) or .FDBMBK87T0SHSZ_4swP6 (relative "45秒")
#   Last msg ID : data-btm attr on bottom-row div (changes per message, used for change detection)
#   Unread badge: .rxAvaVFJHvpEGMc1ejm1  (div; empty = CSS dot badge, number = count badge;
#                 ALWAYS present in DOM — do NOT use :has() to filter by it)
#   Tab buttons : [data-qa-id="qa-active-chat-tab"]  (当前会话)
#                 [data-qa-id="qa-last-chat-tab"]    (最近联系)
#
# Chat thread (confirmed from live DOM):
#   Message wrappers : [data-qa-id="qa-message-warpper"]  ← Feige typo, NOT "wrapper"
#   Bubble element   : .iD7SHBvMhm4OhfCsBGr1
#   Agent bubble     : .messageIsMe   (flex-direction: row-reverse)
#   Customer bubble  : .messageNotMe  (flex-direction: row)
#   Timestamp        : .O4UWWFoQxgMq4AWHMq25
#   Message id       : data-id attr on child div of wrapper
#   System messages  : .BqNO6cexAGBsZgUmEzIE or .e0Bi5IauHWvUG8773oi9
#
# Chat compose area (confirmed from live DOM):
#   Input   : textarea[data-qa-id="qa-send-message-textarea"]
#   Send btn: [data-qa-id="qa-send-message-button"]  (div, not button)
#
# If a selector stops working, run feige_get_chat_thread or feige_list_sessions with
# extract_dom=True to get fresh HTML snippets and update the constants below.
# ─────────────────────────────────────────────────────────────────────────────

_FEIGE_SESSION_ITEM = '[data-qa-id="qa-conversation-chat-item"]'
_FEIGE_SESSION_SCROLL = '[class*="list_items"], .scroller, #chantListScrollArea'
_FEIGE_NAME_ATTR_PARENT = '[class*="nameLine"], .MP1bk3ccfHC9V2SnPCGD'
_FEIGE_NAME_TEXT = '[class*="NameContent"], .Jv6FtqUv5VoYARd2pp4y'
_FEIGE_LAST_MSG = '[class*="msgContent"], .lF_M7QiFB0ukHWpMfQde span'
_FEIGE_TIMESTAMP = '[class*="timerParticular"], .CEnLM8MEGksTdgi_8Lqf'
_FEIGE_UNREAD = '[class*="badge-count"], .rxAvaVFJHvpEGMc1ejm1'

_FEIGE_LIST_SESSIONS_JS = r"""
(function(includeRead, maxSessions) {
  var __rebuiltFrame = null;
  function rowIsCurrent(row) {
    var btm = row && row.getAttribute ? String(row.getAttribute('data-btm-id') || '') : '';
    if (btm.endsWith('.current')) return true;
    if (btm.endsWith('.systemConv')) return false;
    if (btm.endsWith('.recent')) {
      // ws193 (live-probed 2026-08-28): the REBUILT Feige frame (abtest
      // hitWebFrameRebuild) stamps EVERY sidebar row '.recent' — even unread
      // conversations awaiting a reply — and the old 待回复/最近 split is gone.
      // On that frame '.recent' rows ARE the working set, so admit them; on the
      // old frame ('.current' rows or the 待回复 container present) keep
      // excluding them as before. Computed once per evaluate.
      if (__rebuiltFrame === null) {
        __rebuiltFrame = !document.querySelector('[data-btm-id$=".current"]') &&
                         !document.querySelector('.pigeonChatNotScrollBox');
      }
      return __rebuiltFrame;
    }
    if (row && row.closest && row.closest('.pigeonChatNotScrollBox')) return true;
    if (row && row.closest && row.closest('.pigeonChatScrollBox')) return false;
    return true;
  }
  var allItems = Array.from(document.querySelectorAll('[data-qa-id="qa-conversation-chat-item"]'));
  var items = allItems.filter(rowIsCurrent);
  var results = [];
  for (var i = 0; i < Math.min(items.length, maxSessions); i++) {
    var el = items[i];
    var nameEl = el.querySelector('[class*="nameLine"], .MP1bk3ccfHC9V2SnPCGD');
    var name = (nameEl && (nameEl.getAttribute('title') || nameEl.textContent || '')).trim();
    if (!name) {
      var nameEl2 = el.querySelector('[class*="NameContent"], .Jv6FtqUv5VoYARd2pp4y');
      name = nameEl2 ? nameEl2.textContent.trim() : '';
    }
    var lastMsgEl = el.querySelector('[class*="msgContent"], .lF_M7QiFB0ukHWpMfQde span');
    var lastMsg = lastMsgEl ? lastMsgEl.textContent.trim() : '';
    var tsEl = el.querySelector('[class*="timerParticular"], .CEnLM8MEGksTdgi_8Lqf');
    var ts = tsEl ? tsEl.textContent.trim() : '';
    // Detect unread count and tags from .rxAvaVFJHvpEGMc1ejm1
    // This element can contain either a numeric unread badge OR a warning tag (e.g. 服务态度预警)
    var unread = 0;
    var tags = [];
    var unreadEl = el.querySelector('[class*="badge-count"], .rxAvaVFJHvpEGMc1ejm1');
    if (unreadEl) {
      var rawText = unreadEl.textContent.trim();
      var parsed = parseInt(rawText, 10);
      if (!isNaN(parsed) && String(parsed) === rawText) {
        unread = parsed;
      } else if (rawText) {
        // Non-numeric text = tag (e.g. 服务态度预警)
        tags.push(rawText);
      }
    }
    if (unread === 0) {
      // Fallback: sup element (dot/number badge)
      var supEl = el.querySelector('sup');
      if (supEl) {
        unread = parseInt(supEl.textContent.trim(), 10) || 1;
      }
    }
    // Collect inline tags (e.g. 重复来访)
    var tagEls = el.querySelectorAll('[class*="userLabel"] span, [class*="cardTag"] span, .obeJrSyU4KwAzGeRfcbk span');
    for (var j = 0; j < tagEls.length; j++) {
      var tagText = tagEls[j].textContent.trim();
      if (tagText && tags.indexOf(tagText) < 0) tags.push(tagText);
    }
    if (!includeRead && unread === 0 && tags.length === 0) continue;
    results.push({ index: i, name: name, last_message: lastMsg, timestamp: ts, unread: unread, tags: tags });
  }
  return JSON.stringify({ sessions: results, total_visible: items.length });
})(INCLUDE_READ, MAX_SESSIONS);
"""


@custom_controller.action(
    "List visible customer sessions in the Feige (飞鸽) customer-service session panel.",
    param_model=FeigeListSessionsAction,
)
async def feige_list_sessions(params: FeigeListSessionsAction, browser_session: BrowserSession) -> ActionResult:
    try:
        js = _FEIGE_LIST_SESSIONS_JS.replace("INCLUDE_READ", "true" if params.include_read else "false")
        js = js.replace("MAX_SESSIONS", str(params.max_sessions))
        # Read-only sidebar scrape against the resolved Feige tab, focus=False.
        # A timeout here must not freeze sends or invalidate the shared
        # session (read_only=True) — the agent can simply retry the scan.
        data = await _evaluate_live_chat_js(
            browser_session,
            js,
            trace_label="feige_list_sessions",
            trace_fields={
                "include_read": bool(params.include_read),
                "max_sessions": int(params.max_sessions),
            },
            read_only=True,
        )
        if isinstance(data, str):
            import json as _json
            data = _json.loads(data)
        sessions = data.get("sessions", []) if isinstance(data, dict) else []
        total = data.get("total_visible", 0) if isinstance(data, dict) else 0
        logger.info(f"[Feige] Listed sessions: visible={total}, returned={len(sessions)}")
        return _json_result({"sessions": sessions, "total_visible": total})
    except Exception as e:
        logger.error(f"[Feige] feige_list_sessions error: {e}")
        return ActionResult(error=f"feige_list_sessions failed: {e}")


_FEIGE_OPEN_SESSION_JS = r"""
(function(customerName, sessionIndex) {
  // NOTE (2026-05-13): an earlier "Fix 11" added a click → await sleep
  // → verify → retry loop here to self-heal Feige sidebar misroutes
  // (where clicking row X activates a different customer because the
  // sidebar reshuffled mid-flight).  It REGRESSED throughput badly:
  // under high renderer load — exactly the condition the fix targeted
  // — JS ``setTimeout`` callbacks stretch from their nominal duration
  // by 5-10×.  Three attempts × two sleeps each (250ms + 150ms) became
  // 8-12 second JS executions, busting HOT-PATH-B's 8s ``wait_for``
  // timeout.  Result: ``feige_open_session`` timed out 10× in a 6-min
  // run vs the usual 0-3, deliveries dropped from 18/20 → 4/20.
  //
  // Kept the simple synchronous click here.  Sidebar-misroute recovery
  // happens at the Python layer instead: ``_post_open_verify`` detects
  // the mismatch, and Fix 7b's ``last_dispatched_msg_id`` clear lets
  // PreDispatch re-dispatch on the next loop.  Slower than a JS-level
  // retry would be in isolation, but reliably bounded — doesn't stack
  // sleeps that get amplified by renderer slowdown.
  var __rebuiltFrame = null;
  function rowIsCurrent(row) {
    var btm = row && row.getAttribute ? String(row.getAttribute('data-btm-id') || '') : '';
    if (btm.endsWith('.current')) return true;
    if (btm.endsWith('.systemConv')) return false;
    if (btm.endsWith('.recent')) {
      // ws193 (live-probed 2026-08-28): the REBUILT Feige frame (abtest
      // hitWebFrameRebuild) stamps EVERY sidebar row '.recent' — even unread
      // conversations awaiting a reply — and the old 待回复/最近 split is gone.
      // On that frame '.recent' rows ARE the working set, so admit them; on the
      // old frame ('.current' rows or the 待回复 container present) keep
      // excluding them as before. Computed once per evaluate.
      if (__rebuiltFrame === null) {
        __rebuiltFrame = !document.querySelector('[data-btm-id$=".current"]') &&
                         !document.querySelector('.pigeonChatNotScrollBox');
      }
      return __rebuiltFrame;
    }
    if (row && row.closest && row.closest('.pigeonChatNotScrollBox')) return true;
    if (row && row.closest && row.closest('.pigeonChatScrollBox')) return false;
    return true;
  }
  var allItems = Array.from(document.querySelectorAll('[data-qa-id="qa-conversation-chat-item"]'));
  var items = allItems.filter(rowIsCurrent);
  var target = null;
  if (customerName) {
    for (var i = 0; i < items.length; i++) {
      var nameEl = items[i].querySelector('[class*="nameLine"], .MP1bk3ccfHC9V2SnPCGD');
      var name = (nameEl && (nameEl.getAttribute('title') || nameEl.textContent || '')).trim();
      if (!name) {
        var nameEl2 = items[i].querySelector('[class*="NameContent"], .Jv6FtqUv5VoYARd2pp4y');
        name = nameEl2 ? nameEl2.textContent.trim() : '';
      }
      if (name === customerName) { target = items[i]; break; }
    }
  }
  // ws193: rebuilt-frame fallback — see feige_send_message JS. All rows are
  // '.recent' on the redesigned sidebar, so the current-filter empties `items`;
  // exact-name search of the full list, only when the filtered view is empty.
  if (!target && customerName && items.length === 0 && allItems.length > 0) {
    for (var fb = 0; fb < allItems.length; fb++) {
      var fbEl = allItems[fb].querySelector('[class*="nameLine"], .MP1bk3ccfHC9V2SnPCGD');
      var fbName = (fbEl && (fbEl.getAttribute('title') || fbEl.textContent || '')).trim();
      if (!fbName) {
        var fbEl2 = allItems[fb].querySelector('[class*="NameContent"], .Jv6FtqUv5VoYARd2pp4y');
        fbName = fbEl2 ? fbEl2.textContent.trim() : '';
      }
      if (fbName === customerName) { target = allItems[fb]; break; }
    }
  }
  if (!target && sessionIndex >= 0 && sessionIndex < items.length) {
    target = items[sessionIndex];
  }
  if (!target) return JSON.stringify({
    clicked: false,
    error: 'Session not found in current conversations',
    current_visible: items.length,
    total_visible: allItems.length
  });
  target.click();
  var nameEl = target.querySelector('[class*="nameLine"], .MP1bk3ccfHC9V2SnPCGD');
  var clickedName = (nameEl && (nameEl.getAttribute('title') || nameEl.textContent || '')).trim();
  return JSON.stringify({ clicked: true, name: clickedName });
})(CUSTOMER_NAME, SESSION_INDEX);
"""


@custom_controller.action(
    "Open a customer chat session in Feige (飞鸽) by clicking on it in the session list.",
    param_model=FeigeOpenSessionAction,
)
async def feige_open_session(params: FeigeOpenSessionAction, browser_session: BrowserSession) -> ActionResult:
    try:
        cooldown_remaining = live_chat_cdp_health_cooldown_remaining()
        if cooldown_remaining > 0.0:
            logger.warning(
                f"[Feige] feige_open_session: CDP health cooldown active "
                f"for {cooldown_remaining:.1f}s; skipping open for "
                f"{str(params.customer_name or '')!r}"
            )
            return ActionResult(
                error=(
                    "feige_open_session: cdp_health_cooldown_active "
                    f"{cooldown_remaining:.1f}s"
                )
            )
        name_js = json.dumps(params.customer_name, ensure_ascii=False) if params.customer_name else "null"
        idx_js = str(params.session_index) if params.session_index is not None else "-1"
        js = _FEIGE_OPEN_SESSION_JS.replace("CUSTOMER_NAME", name_js).replace("SESSION_INDEX", idx_js)
        # Run against the resolved Feige tab session with focus=False — the
        # JS clicks the sidebar row itself, so we don't need browser-use's
        # expensive ``ensure_valid_focus`` round-trip (~3s ``session_ms`` in
        # the 2026-05-11 flood trace).  Mirrors feige_send_message.
        data = await _evaluate_live_chat_js(
            browser_session,
            js,
            trace_label="feige_open_session",
            # Phase 1 multi-tab plumbing: pass customer_key so Phase 3
            # routes this open-session click to the typing tab assigned
            # to this customer (when one exists).  Today it still hits
            # the monitor tab — same behavior as before.
            customer_key=str(params.customer_name or ""),
            trace_fields={
                "customer": str(params.customer_name or ""),
                "session_index": int(params.session_index) if params.session_index is not None else -1,
            },
        )
        if isinstance(data, str):
            import json as _json
            # Guard the empty/whitespace case: on a freshly-loaded rebuilt
            # frame the open-session IIFE can return no value (threw or
            # undefined during early paint), so _evaluate_js hands back "".
            # json.loads("") throws "Expecting value: line 1 column 1" — a
            # misleading error that read as a code bug. Treat empty as a
            # clear, retryable "frame not ready" instead (2026-09-03 fresh-
            # machine cold-start).
            if not data.strip():
                logger.warning(
                    f"[Feige] feige_open_session: eval returned empty "
                    f"(frame not ready?) cust={str(params.customer_name or '')!r}")
                return ActionResult(error="feige_open_session: eval_returned_empty (frame not ready)")
            try:
                data = _json.loads(data)
            except Exception as _je:
                logger.warning(
                    f"[Feige] feige_open_session: non-JSON eval result "
                    f"({_je}); raw[:120]={data[:120]!r}")
                return ActionResult(error="feige_open_session: eval_non_json")
        if isinstance(data, dict) and data.get("clicked"):
            logger.info(f"[Feige] Opened session: name={data.get('name')}")
            return ActionResult(extracted_content=f"Opened session: {data.get('name', '(unknown)')}")
        err = data.get("error") if isinstance(data, dict) else str(data)
        return ActionResult(error=f"feige_open_session: {err}")
    except Exception as e:
        logger.error(f"[Feige] feige_open_session error: {e}")
        return ActionResult(error=f"feige_open_session failed: {e}")


# NOTE: Chat thread selectors below are best-effort guesses derived from common
# Feige DOM patterns.  If they stop working, extract a fresh chat thread DOM
# snapshot (e.g. via extract_dom on the right-hand pane) and update the JS.
_FEIGE_GET_THREAD_JS = r"""
(function(maxMessages) {
  // Confirmed selectors from live DOM capture (note Feige typo: "warpper" not "wrapper")
  // Each message wrapper: [data-qa-id="qa-message-warpper"] > div[data-id] > div.tC9ap6QtAyeCD0jfuMns
  // Agent message:   inner div with flex-direction:row-reverse  OR  class containing "messageIsMe"
  // Customer message: inner div with flex-direction:row          OR  class containing "messageNotMe"
  // System/event:    div.tC9ap6QtAyeCD0jfuMns containing no leaveMessageWrapper (just text spans)
  //
  // Image bubbles do NOT have ".iD7SHBvMhm4OhfCsBGr1" — the bubble is a
  // bare <img alt="图片"> inside the row container.  We extract images
  // from the row separately (skipping avatar imgs by class+alt) so an
  // image-only message is no longer silently dropped.
  function _collectAttachments(row) {
    if (!row) return [];
    var atts = [];
    var imgs = Array.from(row.querySelectorAll('img'));
    for (var k = 0; k < imgs.length; k++) {
      var im = imgs[k];
      var cls = (im.className || '').toString();
      var alt = (im.getAttribute('alt') || '').trim();
      if (/Zq9KgucRnc7bRQfikvzQ|qwDH4Hnmk4jmYkYLmHGF/.test(cls)) continue;
      if (alt === '头像') continue;
      // Prefer the resolved ``.src`` property over the raw attribute
      // so relative URLs (``/sample0.png``) become absolute, matching
      // what the downstream aiohttp-based eager-fetch requires.  See
      // ``feige_chat/dom_assets.py`` for the same fix on the bubble
      // scraper.
      var src = im.src || im.getAttribute('src') || '';
      if (!src) continue;
      if (src.indexOf('data:image/svg') === 0) continue;
      atts.push({ kind: 'image', url: src, alt: alt });
    }
    return atts;
  }
  var wrappers = Array.from(document.querySelectorAll('[data-qa-id="qa-message-warpper"]'));
  var results = [];
  var start = Math.max(0, wrappers.length - maxMessages);
  for (var i = start; i < wrappers.length; i++) {
    var wrap = wrappers[i];
    // Row container holds avatar + bubble; flex-direction tells us sender.
    var row = wrap.querySelector('.Ie29C7uLyEjZzd8JeS8A');
    var bubble = wrap.querySelector('.iD7SHBvMhm4OhfCsBGr1, [class*="messageNotMe"], [class*="messageIsMe"]');
    if (!bubble && !row) {
      // System/event message (no bubble, no row) — capture inner text.
      var sysEl = wrap.querySelector('.BqNO6cexAGBsZgUmEzIE, .e0Bi5IauHWvUG8773oi9, .rcHPT4n3TlQD0Nu4sSiv');
      if (sysEl) {
        results.push({ index: i, text: sysEl.textContent.trim(), is_agent: false, is_system: true, timestamp: '', attachments: [] });
      }
      continue;
    }
    var text = bubble ? (bubble.querySelector('pre') || bubble).textContent.trim() : '';
    // Determine sender: prefer the bubble's class, fall back to row direction.
    var isAgent;
    if (bubble) {
      isAgent = bubble.classList.contains('messageIsMe');
    } else {
      isAgent = ((row && row.style.flexDirection) || '').indexOf('reverse') !== -1;
    }
    var attachments = _collectAttachments(row);
    // Drop bubbles with neither text nor attachments (defensive).
    if (!text && attachments.length === 0) continue;
    var tsEl = wrap.querySelector('.O4UWWFoQxgMq4AWHMq25');
    var ts = tsEl ? tsEl.textContent.trim() : '';
    var msgIdEl = wrap.querySelector('[data-id]');
    var msgId = msgIdEl ? msgIdEl.getAttribute('data-id') : '';
    results.push({ index: i, text: text, is_agent: isAgent, is_system: false, timestamp: ts, msg_id: msgId, attachments: attachments });
  }
  return JSON.stringify({ messages: results, total_found: wrappers.length, selector_used: wrappers.length > 0 ? 'matched' : 'none' });
})(MAX_MESSAGES);
"""


@custom_controller.action(
    "Extract visible messages from the currently open Feige (飞鸽) chat thread.",
    param_model=FeigeGetChatThreadAction,
)
async def feige_get_chat_thread(params: FeigeGetChatThreadAction, browser_session: BrowserSession) -> ActionResult:
    try:
        js = _FEIGE_GET_THREAD_JS.replace("MAX_MESSAGES", str(params.max_messages))
        # Read-only thread scrape against the resolved Feige tab, focus=False.
        data = await _evaluate_live_chat_js(
            browser_session,
            js,
            trace_label="feige_get_chat_thread",
            trace_fields={"max_messages": int(params.max_messages)},
            read_only=True,
        )
        if isinstance(data, str):
            import json as _json
            data = _json.loads(data)
        messages = data.get("messages", []) if isinstance(data, dict) else []
        total = data.get("total_found", 0) if isinstance(data, dict) else 0
        selector_used = data.get("selector_used", "unknown") if isinstance(data, dict) else "unknown"
        logger.info(f"[Feige] Got chat thread: total={total}, returned={len(messages)}, selector={selector_used}")
        if selector_used == "none":
            return ActionResult(
                extracted_content="No message elements found. The chat thread selectors may need updating. "
                "Use extract_dom on the right-hand chat pane to get fresh HTML and update _FEIGE_GET_THREAD_JS."
            )
        return _json_result({"messages": messages, "total_found": total})
    except Exception as e:
        logger.error(f"[Feige] feige_get_chat_thread error: {e}")
        return ActionResult(error=f"feige_get_chat_thread failed: {e}")


_FEIGE_SEND_MESSAGE_JS = r"""
(async function(text, expectedCustomer, expectedSourceMsgId, expectedSourceText, bypassOlderBubbleMatch, allowNoMsgIdSend, allowSimilarSource) {
""" + _ROW_PREVIEW_FALLBACK_JS + r"""
  function sleep(ms) { return new Promise(function(resolve) { setTimeout(resolve, ms); }); }
  var __feigeSendStartedAt = Date.now();
  var __feigeSendPhase = 'start';
  var __feigeSendTimings = {};
  var __feigeSendCounters = {};
  function markPhase(name) {
    __feigeSendPhase = name;
    __feigeSendTimings[name] = Date.now() - __feigeSendStartedAt;
  }
  function finish(result) {
    result = result || {};
    result.page_total_ms = Date.now() - __feigeSendStartedAt;
    result.page_phase = __feigeSendPhase;
    result.page_timing_ms = __feigeSendTimings;
    result.page_counters = __feigeSendCounters;
    // ws040c: on the card path, attach a COMPLETE state dump to EVERY exit so any
    // residual card failure is fully diagnosable in ONE run (no more guard-by-guard
    // builds) — the header, sidebar rows, and the actual thread bubbles every guard
    // sees (incl. how the card bubble renders, which is why text-matching fails).
    if (cardRowResolved) {
      try {
        var _diag = { header: readHeaderName(), sidebar: [], bubbles: [] };
        var _sr = document.querySelectorAll('[data-qa-id="qa-conversation-chat-item"]');
        for (var _di = 0; _di < _sr.length && _di < 12; _di++) {
          _diag.sidebar.push({ name: readRowName(_sr[_di]), preview: readRowPreview(_sr[_di]) });
        }
        var _bb = allCustomerBubbles();
        _diag.cust_bubble_count = _bb.length;
        for (var _bi = 0; _bi < _bb.length && _bi < 8; _bi++) {
          _diag.bubbles.push({ msg_id: _bb[_bi].msg_id || '', text: String(_bb[_bi].text || '').slice(0, 50) });
        }
        result.card_diag = _diag;
      } catch (_e) { result.card_diag_err = String(_e); }
    }
    return JSON.stringify(result);
  }
  markPhase('start');
  function visible(el) {
    if (!el || !el.getBoundingClientRect) return false;
    var rect = el.getBoundingClientRect();
    var style = window.getComputedStyle ? window.getComputedStyle(el) : null;
    return rect.width > 0 && rect.height > 0 &&
      (!style || (style.display !== 'none' && style.visibility !== 'hidden'));
  }
  function readValue(el) {
    if (!el) return '';
    if ('value' in el) return String(el.value || '');
    return String(el.textContent || '');
  }
  function setValue(el, val) {
    if (!el) return;
    el.focus();
    if (el.tagName === 'TEXTAREA') {
      var taSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value');
      if (taSetter && taSetter.set) taSetter.set.call(el, val);
      else el.value = val;
    } else if (el.tagName === 'INPUT') {
      var inSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
      if (inSetter && inSetter.set) inSetter.set.call(el, val);
      else el.value = val;
    } else {
      el.textContent = val;
    }
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }
  function latestAgentBubbleText() {
    var wrappers = Array.from(document.querySelectorAll('[data-qa-id="qa-message-warpper"]'));
    for (var i = wrappers.length - 1; i >= 0; i--) {
      var wrap = wrappers[i];
      var bubble = wrap.querySelector('.iD7SHBvMhm4OhfCsBGr1, [class*="messageNotMe"], [class*="messageIsMe"]');
      if (!bubble || !bubble.classList.contains('messageIsMe')) continue;
      return (bubble.querySelector('pre') || bubble).textContent.trim();
    }
    return '';
  }
  // mt024 / 2026-05-24 mt037C: scan agent-side bubbles for the
  // wrapper's data-id (chat-thread bubble msg_id) and return the one
  // matching the text we just typed.  Used post-verify to record OUR
  // typed bubble's msg_id back into the mt017 typed-msg-id set, so
  // subsequent thread-scrape mt017 detections recognise the bubble as
  // ours even after the recent-reply ledger TTL has expired.
  //
  // PRE-mt037C: the function only checked ``.iD7SHBvMhm4OhfCsBGr1`` +
  // ``messageIsMe`` class, and Feige's DOM didn't always set those at
  // verify time → 0 of 57 sends captured a msg_id in the customer's
  // 2026-05-24 13:05-13:34 trace.  That fed back as mt017 false-
  // positive ``mark_handled`` calls + 4 ``human_intervention_skip``
  // drops.
  //
  // POST-mt037C: three improvements stack:
  //   (1) Dual identifier — accept either ``messageIsMe`` class OR
  //       row-level ``flexDirection: row-reverse`` (the test the
  //       working dom_assets.py chat-thread scraper uses).
  //   (2) Text match — among agent bubbles, prefer the one whose
  //       textContent (whitespace-stripped, mt036B-shape) matches the
  //       text we JUST typed.  Falls back to "newest agent bubble" if
  //       no text match.
  //   (3) Brief retry — Feige assigns ``data-id`` asynchronously after
  //       the bubble appears.  We poll up to 5 × 100 ms before giving
  //       up — total worst-case 500 ms inside the verify path.
  function _msgIdStripWs(s) {
    return String(s || '').replace(/\s+/g, '');
  }
  function _isAgentBubble(wrap) {
    // Test 1: row-level flex-direction row-reverse (most reliable —
    // matches the working dom_assets.py chat-thread scraper).
    var row = wrap.querySelector('.Ie29C7uLyEjZzd8JeS8A');
    if (row && ((row.style.flexDirection || '').indexOf('reverse') !== -1)) {
      return true;
    }
    // Test 2: bubble has messageIsMe class.
    var bubble = wrap.querySelector('.iD7SHBvMhm4OhfCsBGr1, [class*="messageNotMe"], [class*="messageIsMe"]');
    if (bubble && bubble.classList.contains('messageIsMe')) {
      return true;
    }
    return false;
  }
  function _bubbleTextOf(wrap) {
    var bubble = wrap.querySelector('.iD7SHBvMhm4OhfCsBGr1, [class*="messageNotMe"], [class*="messageIsMe"]');
    if (!bubble) return '';
    var pre = bubble.querySelector('pre');
    return ((pre || bubble).textContent || '').trim();
  }
  function _walkAgentBubblesNewestFirst() {
    // 2026-05-25 mt040B.1: instrument counters so the Python side can
    // see WHY verified_msg_id capture is empty on real Feige (0/N in
    // the live J14N9 trace).  Counters land in __feigeSendCounters and
    // get serialised into page_counters by finish().
    var out = [];
    var wrappers = document.querySelectorAll('[data-qa-id="qa-message-warpper"]');
    var seen = 0, agentCls = 0, withId = 0;
    for (var i = wrappers.length - 1; i >= 0; i--) {
      seen += 1;
      var wrap = wrappers[i];
      if (!_isAgentBubble(wrap)) continue;
      agentCls += 1;
      var idEl = wrap.querySelector('[data-id]');
      var msgId = idEl ? (idEl.getAttribute('data-id') || '') : '';
      if (msgId) withId += 1;
      out.push({
        wrap: wrap,
        msg_id: msgId,
        text: _bubbleTextOf(wrap),
      });
      if (out.length >= 8) break;  // typed bubble is in the last few
    }
    // Surface the per-walk stats.  We accumulate across polls so the
    // final ledger shows total work done (e.g. 5 polls × N wraps).
    __feigeSendCounters.mt037c_wraps_seen = (__feigeSendCounters.mt037c_wraps_seen || 0) + seen;
    __feigeSendCounters.mt037c_agent_classified = (__feigeSendCounters.mt037c_agent_classified || 0) + agentCls;
    __feigeSendCounters.mt037c_with_data_id = (__feigeSendCounters.mt037c_with_data_id || 0) + withId;
    return out;
  }
  async function latestAgentBubbleMsgId() {
    // 2026-05-25 mt040B.1: track which match strategy (if any)
    // produced the msg_id, how many of the 5 retry polls were spent,
    // and the length of the returned id (0 = capture failed).  Lets
    // us tell apart "no agent bubble found at all" vs "agent bubble
    // found but data-id never assigned within 500 ms" — different
    // root causes, different fixes.
    var expectedNorm = _msgIdStripWs(text);
    var totalAttempts = 0;
    // match_strategy codes (integer so page_counters' int-only
    // serializer keeps them): 0=none, 1=text_match, 2=newest_with_id
    for (var attempt = 0; attempt < 5; attempt++) {
      totalAttempts = attempt + 1;
      var bubbles = _walkAgentBubblesNewestFirst();
      // (1) Prefer the bubble whose text matches what we just typed.
      if (expectedNorm) {
        for (var bi = 0; bi < bubbles.length; bi++) {
          var b = bubbles[bi];
          if (b.msg_id && _msgIdStripWs(b.text) === expectedNorm) {
            __feigeSendCounters.mt037c_total_attempts = totalAttempts;
            __feigeSendCounters.mt037c_match_strategy = 1;
            __feigeSendCounters.mt037c_result_msg_id_len = b.msg_id.length;
            return b.msg_id;
          }
        }
      }
      // (2) Fall back: newest agent bubble whose data-id is populated.
      for (var bj = 0; bj < bubbles.length; bj++) {
        var bb = bubbles[bj];
        if (bb.msg_id) {
          __feigeSendCounters.mt037c_total_attempts = totalAttempts;
          __feigeSendCounters.mt037c_match_strategy = 2;
          __feigeSendCounters.mt037c_result_msg_id_len = bb.msg_id.length;
          return bb.msg_id;
        }
      }
      // (3) data-id might not be assigned yet — brief wait, then retry.
      if (attempt < 4) {
        await sleep(100);
      }
    }
    __feigeSendCounters.mt037c_total_attempts = totalAttempts;
    __feigeSendCounters.mt037c_match_strategy = 0;
    __feigeSendCounters.mt037c_result_msg_id_len = 0;
    return '';
  }
  function latestVisibleBubble() {
    var wrappers = Array.from(document.querySelectorAll('[data-qa-id="qa-message-warpper"]'));
    for (var i = wrappers.length - 1; i >= 0; i--) {
      var wrap = wrappers[i];
      var bubble = wrap.querySelector('.iD7SHBvMhm4OhfCsBGr1, [class*="messageNotMe"], [class*="messageIsMe"]');
      if (!bubble) continue;
      var text = (bubble.querySelector('pre') || bubble).textContent.trim();
      if (bubble.classList.contains('messageIsMe')) {
        if (!text) continue;
        return { found: true, sender: 'agent', text: text };
      }
      if (bubble.classList.contains('messageNotMe')) {
        if (!text) {
          var customerRow = wrap.querySelector('.Ie29C7uLyEjZzd8JeS8A');
          var customerImgs = Array.from((customerRow || wrap).querySelectorAll('img'));
          for (var ci = 0; ci < customerImgs.length; ci++) {
            var cim = customerImgs[ci];
            var ccls = (cim.className || '').toString();
            var calt = (cim.getAttribute('alt') || '').trim();
            if (/Zq9KgucRnc7bRQfikvzQ|qwDH4Hnmk4jmYkYLmHGF/.test(ccls)) continue;
            if (calt === 'å¤´åƒ') continue;
            var csrc = cim.src || cim.getAttribute('src') || '';
            if (csrc && csrc.indexOf('data:image/svg') !== 0) {
              return { found: true, sender: 'customer', text: '' };
            }
          }
          continue;
        }
        return { found: true, sender: 'customer', text: text };
      }
      var row = wrap.querySelector('.Ie29C7uLyEjZzd8JeS8A');
      var direction = row ? String(row.style.flexDirection || '') : '';
      if (!text && direction.indexOf('reverse') === -1) {
        var imgs = Array.from((row || wrap).querySelectorAll('img'));
        for (var k = 0; k < imgs.length; k++) {
          var im = imgs[k];
          var cls = (im.className || '').toString();
          var alt = (im.getAttribute('alt') || '').trim();
          if (/Zq9KgucRnc7bRQfikvzQ|qwDH4Hnmk4jmYkYLmHGF/.test(cls)) continue;
          if (alt === 'å¤´åƒ') continue;
          var src = im.src || im.getAttribute('src') || '';
          if (src && src.indexOf('data:image/svg') !== 0) {
            return { found: true, sender: 'customer', text: '' };
          }
        }
      }
      if (!text) continue;
      return {
        found: true,
        sender: direction.indexOf('reverse') !== -1 ? 'agent' : 'customer',
        text: text
      };
    }
    return { found: false, sender: '', text: '' };
  }
  function latestCustomerBubble() {
    var wrappers = Array.from(document.querySelectorAll('[data-qa-id="qa-message-warpper"]'));
    function isTransferMarker(text) {
      var t = String(text || '').replace(/\s+/g, '').trim();
      return t === '转人工' || t === '转人工客服' || t === '人工客服';
    }
    for (var i = wrappers.length - 1; i >= 0; i--) {
      var wrap = wrappers[i];
      // mt064: side detection prefers the semantic messageIsMe/messageNotMe
      // markers (survive Feige hash redesigns); legacy flex-direction on the
      // hashed .Ie29C7... row is the fallback when no bubble marker exists.
      var bubble = wrap.querySelector('.iD7SHBvMhm4OhfCsBGr1, [class*="messageNotMe"], [class*="messageIsMe"]');
      var row = wrap.querySelector('.Ie29C7uLyEjZzd8JeS8A');
      if (bubble) {
        if (bubble.classList.contains('messageIsMe')) continue;  // agent-side
      } else {
        if (!row) continue;
        if ((row.style.flexDirection || '').indexOf('reverse') !== -1) continue;  // agent-side
      }
      var text = '';
      if (bubble) {
        text = (bubble.querySelector('pre') || bubble).textContent.trim();
      }
      var hasContentImage = false;
      var imgs = Array.from((row || wrap).querySelectorAll('img'));
      for (var k = 0; k < imgs.length; k++) {
        var im = imgs[k];
        var cls = (im.className || '').toString();
        var alt = (im.getAttribute('alt') || '').trim();
        if (/Zq9KgucRnc7bRQfikvzQ|qwDH4Hnmk4jmYkYLmHGF/.test(cls)) continue;
        if (alt === '头像') continue;
        var src = im.src || im.getAttribute('src') || '';
        if (src && src.indexOf('data:image/svg') !== 0) {
          hasContentImage = true;
          break;
        }
      }
      // 2026-05-24 mt038C: see allCustomerBubbles() — same card-bubble
      // recognition fix kept in sync so this twin (currently dead but
      // surfaced via grep when scanners get audited) doesn't reintroduce
      // the stale_reply_source_msg_id 'no_match' drop if it gets wired
      // up by a future change.
      var hasCard = !!wrap.querySelector('.chatd-card');
      if (!text && !hasContentImage && !hasCard) continue;
      if (text && isTransferMarker(text)) continue;
      var idEl = wrap.querySelector('[data-id]');
      return {
        found: true,
        text: text,
        msg_id: idEl ? (idEl.getAttribute('data-id') || '') : ''
      };
    }
    return { found: false, text: '', msg_id: '' };
  }
  function sameText(a, b) {
    function norm(s) { return String(s || '').replace(/\s+/g, ' ').trim(); }
    return norm(a) === norm(b);
  }
  function similarText(a, b) {
    // ws143: a same-question re-scrape (e.g. the connect-banner enrich re-reading the
    // thread) often shifts the msg_id AND adds framing words — '会不会褪色或者是变形' then
    // '穿久了会不会褪色或者是变形啊' — so a strict sameText() miss makes the stale-guard treat
    // the SAME question as a NEWER turn and drop a valid answer. Treat as the same turn when
    // one text FULLY contains the other AND the shorter is the bulk (>=70%) of the longer:
    // only framing/filler differs, no NEW question was piled on (which WOULD be a real newer
    // turn, e.g. '有货吗' vs '有货吗有优惠吗深圳几天到' — 25%, correctly NOT matched).
    function nrm(s) { return String(s || '').replace(/\s+/g, '').trim(); }
    var x = nrm(a), y = nrm(b);
    if (!x || !y) return false;
    if (x === y) return true;
    var sh = x.length <= y.length ? x : y;
    var lo = x.length <= y.length ? y : x;
    return lo.indexOf(sh) !== -1 && sh.length >= 0.7 * lo.length;
  }
  function isSystemSourcePreview(text) {
    var t = String(text || '').replace(/\s+/g, '').trim();
    if (!t) return false;
    return /亲亲，?在哒|很高兴为您服务，请问有什么可以帮您|现在是人工客服为您服务|为了更高效地帮您解决问题|当前会话已长时间未回复|转人工客服|转人工$|^已读$/.test(t);
  }
  var __rebuiltFrame = null;
  function rowIsCurrent(row) {
    var btm = row && row.getAttribute ? String(row.getAttribute('data-btm-id') || '') : '';
    if (btm.endsWith('.current')) return true;
    if (btm.endsWith('.systemConv')) return false;
    if (btm.endsWith('.recent')) {
      // ws193 (live-probed 2026-08-28): the REBUILT Feige frame (abtest
      // hitWebFrameRebuild) stamps EVERY sidebar row '.recent' — even unread
      // conversations awaiting a reply — and the old 待回复/最近 split is gone.
      // On that frame '.recent' rows ARE the working set, so admit them; on the
      // old frame ('.current' rows or the 待回复 container present) keep
      // excluding them as before. Computed once per evaluate.
      if (__rebuiltFrame === null) {
        __rebuiltFrame = !document.querySelector('[data-btm-id$=".current"]') &&
                         !document.querySelector('.pigeonChatNotScrollBox');
      }
      return __rebuiltFrame;
    }
    if (row && row.closest && row.closest('.pigeonChatNotScrollBox')) return true;
    if (row && row.closest && row.closest('.pigeonChatScrollBox')) return false;
    return true;
  }
  function readRowName(row) {
    if (!row || !row.querySelector) return '';
    var wrap = row.querySelector('[class*="nameLine"], .MP1bk3ccfHC9V2SnPCGD');
    if (wrap) {
      var t = (wrap.getAttribute('title') || wrap.textContent || '').trim();
      if (t) return t;
    }
    var span = row.querySelector('[class*="NameContent"], .Jv6FtqUv5VoYARd2pp4y');
    if (span) { var s = (span.textContent || '').trim(); if (s) return s; }
    // Broadened fallbacks (2026-09-03): on the rebuilt Feige frame the hashed
    // classes above stopped matching — every sidebar row read back name-empty,
    // so all by-name matching failed and cold-start delivery died (customer
    // 肽斯特: 2 rows, seen_names ['','']). Name-SPECIFIC selectors only (never
    // generic textContent, which would grab preview/time and risk mis-delivery).
    var cand = row.querySelector('[class*="nickname" i], [class*="nickName"], [class*="userName"], [class*="customerName"], [class*="ConvName"], [class*="convName"]');
    if (cand) { var c = (cand.getAttribute('title') || cand.textContent || '').trim(); if (c) return c; }
    // Last resort: a title-attribute tooltip (Feige puts the full name here);
    // skip elements that look like a message preview container.
    var titled = row.querySelectorAll('[title]');
    for (var ti = 0; ti < titled.length; ti++) {
      var tv = (titled[ti].getAttribute('title') || '').trim();
      var tc = String(titled[ti].className || '');
      if (tv && !/msgContent|preview|content/i.test(tc)) return tv;
    }
    return '';
  }
  function readRowPreview(row) {
    var preview = row && row.querySelector ? row.querySelector('[class*="msgContent"], .lF_M7QiFB0ukHWpMfQde span') : null;
    if (!preview && row && row.querySelector) preview = row.querySelector('[class*="msgContent"], .lF_M7QiFB0ukHWpMfQde');
    var pv = preview ? (preview.textContent || '').trim() : '';
    if (pv) return pv;
    // ws189: selector drift on the rebuilt frame — structural fallback (shared
    // with the backstop scan / card resolver in sidebar_preview_js.py).
    return __ecanRowPreviewFallback(row, readRowName(row));
  }
  function readRowMsgId(row) {
    var idEl = row && row.querySelector ? row.querySelector('[data-btm]') : null;
    return idEl ? String(idEl.getAttribute('data-btm') || '').trim() : '';
  }
  function dumpRowIds(row) {
    // ws038/ws039 diagnostic: id-candidate attributes (data-* / id / href on the
    // row AND descendants) PLUS the row preview + unread state. Card-only convs
    // expose no conv id to map, so a content-anchored delivery matcher needs to
    // know what a card row's preview actually says (e.g. "[商品]") and whether the
    // row is unread — those become the only safe correlators to the WS card.
    var out = { _name: readRowName(row), _preview: readRowPreview(row) };
    try {
      var ub = row.querySelector ? row.querySelector('.rxAvaVFJHvpEGMc1ejm1, [class*="unread"]') : null;
      out._unread = ub ? ((ub.textContent || '').trim() || 'dot') : '';
    } catch (e2) {}
    try {
      var nodes = [row].concat(Array.prototype.slice.call(row.querySelectorAll('*')));
      for (var n = 0; n < nodes.length && n < 80; n++) {
        var el = nodes[n];
        if (!el || !el.attributes) continue;
        for (var a = 0; a < el.attributes.length; a++) {
          var nm = el.attributes[a].name;
          if (nm === 'class' || nm === 'style') continue;
          if (nm.indexOf('data-') === 0 || nm === 'id' || nm === 'href') {
            var v = String(el.attributes[a].value || '');
            if (v && v.length < 160) {
              out[nm] = (out[nm] && out[nm].indexOf(v) < 0) ? (out[nm] + '|' + v) : v;
            }
          }
        }
      }
    } catch (e) {}
    return out;
  }
  function readHeaderName() {
    var topbar = document.querySelector('#topbar-left-info');
    if (!topbar) return '';
    var cands = topbar.querySelectorAll('div, span');
    for (var hi = 0; hi < cands.length; hi++) {
      var ht = (cands[hi].textContent || '').trim();
      if (!ht || ht === '添加备注' || ht.length > 60) continue;
      if (cands[hi].children.length === 0) return ht;
    }
    var btm = topbar.querySelector('div[data-btm-id]');
    return btm ? (btm.textContent || '').trim() : '';
  }
  function currentActiveRowName(items) {
    for (var i = 0; i < items.length; i++) {
      var cn = String(items[i].className || '').toLowerCase();
      if (cn.indexOf('active') >= 0 || items[i].classList.contains('wmvLQcpt39Hk9PSISrlN')) {
        return readRowName(items[i]);
      }
    }
    return '';
  }
  function activeMatches(expected, items) {
    if (!expected) return { ok: true, header: '', sidebar: '' };
    var header = readHeaderName();
    var sidebar = currentActiveRowName(items || []);
    var sidebarConflict = sidebar && sidebar !== expected;
    return {
      ok: header === expected && !sidebarConflict,
      header: header,
      sidebar: sidebar
    };
  }
  var sourceMsgId = String(expectedSourceMsgId || '').trim();
  var sourceText = String(expectedSourceText || '').trim();
  var cardRowResolved = false;   // ws040b: set when we matched a card-only conv by its row
  markPhase('params_ready');
  var allConvRows = Array.from(document.querySelectorAll('[data-qa-id="qa-conversation-chat-item"]'));
  var items = allConvRows.filter(rowIsCurrent);
  markPhase('initial_sidebar_scanned');
  if (expectedCustomer) {
    var target = null;
    for (var oi = 0; oi < items.length; oi++) {
      if (readRowName(items[oi]) === expectedCustomer) { target = items[oi]; break; }
    }
    // ws040: a name-less product card dispatches under a synthetic 'card:<conv>'
    // name (the WS card frame carries no nickname; the display name lives ONLY in
    // the DOM/HTTP, with NO id to map the WS card back to its sidebar row). So when
    // the synthetic name can't be matched by name above, fall back to the card's
    // CONVERSATION ROW: the UNIQUE sidebar row that is a product card needing reply
    // (preview starts '[商品' AND className has 'needReply'). Mis-delivery-safe by
    // construction — if 0 or >1 such rows exist we DON'T guess; we fall through to
    // the not-found return and requeue. Only the synthetic 'card:' name reaches
    // here (named customers + text matched by name above), so normal delivery is
    // untouched. On a hit we rebind expectedCustomer to the row's REAL name so
    // every crosstalk/active-session guard below verifies the actual conversation.
    // ws193: REBUILT-frame fallback (abtest hitWebFrameRebuild, live-probed
    // 2026-08-28). The redesigned sidebar stamps EVERY row's data-btm-id
    // '.recent' — including conversations with an unread dot awaiting a reply —
    // so rowIsCurrent rejects all 16 rows and current_visible is 0 forever.
    // When the current-filter yields NOTHING but rows exist, fall back to an
    // exact-name search of the full list. Mis-delivery-safe: exact name match
    // only, and the Python-side post-open verify still checks the opened
    // conversation header. Old-frame behavior unchanged (its 待回复 box keeps
    // rows passing rowIsCurrent, so the fallback never triggers there).
    if (!target && items.length === 0 && allConvRows.length > 0) {
      for (var rf = 0; rf < allConvRows.length; rf++) {
        if (readRowName(allConvRows[rf]) === expectedCustomer) {
          target = allConvRows[rf];
          markPhase('recent_row_fallback');
          break;
        }
      }
    }
    if (!target && expectedCustomer.indexOf('card:') === 0) {
      // ws091: a COLD-START product card may render in the RECENT/scrollable box
      // (not the 待回复 'current' box) — rowIsCurrent filters those out, so the
      // filtered `items` search misses it (ws090 cold-start: card stranded with
      // current_visible==1, only 'packet' in the current box). Search the FULL
      // sidebar (all rows, unfiltered) for the UNIQUE [商品]needReply row. The
      // needReply class + exactly-one guard keep this mis-delivery-safe (0 or >1
      // card rows -> we DON'T guess, fall through to not-found). Named customers
      // are unaffected (only the synthetic 'card:' name reaches here).
      var cardScanRows = Array.from(document.querySelectorAll('[data-qa-id="qa-conversation-chat-item"]'));
      var cardRows = [];
      for (var ci = 0; ci < cardScanRows.length; ci++) {
        var pv = readRowPreview(cardScanRows[ci]);
        var cls = String(cardScanRows[ci].className || '');
        if (pv && pv.indexOf('[商品') === 0 && /needReply/.test(cls)) {
          cardRows.push(cardScanRows[ci]);
        }
      }
      if (cardRows.length === 1) {
        target = cardRows[0];
        var resolvedCardName = readRowName(target);
        if (resolvedCardName) expectedCustomer = resolvedCardName;
        cardRowResolved = true;
        markPhase('card_row_resolved');
      }
    }
    if (!target) {
      markPhase('target_not_found');
      // ws192: page fingerprint for the current_visible=0 mystery on the rebuilt
      // Feige frame (abtest hitWebFrameRebuild). Distinguishes (a) selector dead /
      // list moved (total_rows=0 — dump the page's data-qa-id inventory + iframes),
      // (b) rows exist but rowIsCurrent filters them all (total_rows>0, dump them),
      // (c) plain render race (rows appear on a later retry, as before).
      var probe = {};
      try {
        probe.total_rows = allConvRows.length;
        probe.page_url = String(location.href || '').slice(0, 160);
        var ifr = Array.from(document.querySelectorAll('iframe'));
        probe.iframe_count = ifr.length;
        probe.iframe_srcs = ifr.slice(0, 3).map(function(f){ return String(f.src || '').slice(0, 120); });
        if (allConvRows.length === 0) {
          var qaSeen = {};
          var qaAll = document.querySelectorAll('[data-qa-id]');
          for (var qi = 0; qi < qaAll.length && Object.keys(qaSeen).length < 40; qi++) {
            qaSeen[String(qaAll[qi].getAttribute('data-qa-id'))] = 1;
          }
          probe.qa_id_inventory = Object.keys(qaSeen);
          probe.qa_id_total = qaAll.length;
        } else {
          probe.unfiltered_rows = allConvRows.slice(0, 10).map(dumpRowIds);
          // 2026-09-03: rows present but readRowName is empty for ALL of them
          // (rebuilt frame — hashed name classes no longer match). Capture the
          // first row's structure so the correct name selector can be written:
          // outerHTML (trimmed) + a text-node inventory (short leaf texts, the
          // likely name/preview) + any title attributes. Only on the all-empty
          // case, so it doesn't bloat normal not-found logs.
          try {
            var namesAllEmpty = allConvRows.length > 0 &&
              allConvRows.slice(0, 10).every(function(r){ return !readRowName(r); });
            probe.names_all_empty = namesAllEmpty;
            if (namesAllEmpty) {
              var r0 = allConvRows[0];
              probe.row0_outer_html = String(r0.outerHTML || '').slice(0, 1400);
              var leaf = [];
              var walk = r0.querySelectorAll('*');
              for (var li = 0; li < walk.length && leaf.length < 24; li++) {
                var el = walk[li];
                if (el.children.length) continue; // leaf only
                var tx = String(el.textContent || '').trim();
                if (tx && tx.length <= 40) leaf.push(tx);
              }
              probe.row0_leaf_texts = leaf;
              var tls = r0.querySelectorAll('[title]');
              probe.row0_titles = Array.prototype.slice.call(tls, 0, 8)
                .map(function(e){ return String(e.getAttribute('title') || '').slice(0, 40); });
            }
          } catch (he) { probe.row0_probe_error = String(he).slice(0, 120); }
        }
      } catch (pe) { probe.probe_error = String(pe).slice(0, 120); }
      return finish({
        sent: false,
        error: 'Session not found in current conversations',
        expected_customer: expectedCustomer,
        current_visible: items.length,
        seen_names: items.slice(0, 20).map(readRowName),
        seen_rows: items.slice(0, 20).map(dumpRowIds),
        page_probe: probe
      });
    }
    var rowMsgId = readRowMsgId(target);
    var rowPreview = readRowPreview(target);
    if (sourceMsgId && rowMsgId && rowMsgId !== sourceMsgId) {
      __feigeSendCounters.sidebar_msg_id_mismatch_ignored = (
        __feigeSendCounters.sidebar_msg_id_mismatch_ignored || 0
      ) + 1;
    }
    // ── Sidebar-latest precheck (Fix #2b, 2026-05-18) ──
    // Previously: when ``expected_source_msg_id`` was empty AND the
    // sidebar's last_message text differed from ``expected_source_text``,
    // we'd drop the reply as stale.  Problem: Feige updates the sidebar
    // ``last_message`` field with whatever message was most recent in the
    // conversation — INCLUDING OUR OWN PREVIOUS AGENT REPLY.  When the
    // last bubble in the conversation is our reply (the normal case
    // after the first round), this precheck always mismatched the
    // customer's earlier source_text and threw away the next-turn reply
    // as a false-positive "stale".  10 of 13 stale_reply_drop events in
    // the customer's 2026-05-18 trace fired this path; customers 0333
    // and 陆地飞鱼 lost the most replies this way.
    //
    // New policy: when sourceMsgId is empty, SKIP the sidebar precheck.
    // The deeper thread-walk check (~line 4480) below opens the
    // conversation and validates against the actual customer bubbles
    // (msg_id strict or text match across any of the last few bubbles),
    // which is the correct source of truth — the sidebar's
    // last_message field is unreliable for stale detection because it
    // gets overwritten by every new bubble (agent or system) in the
    // conversation.
    if (!sourceMsgId && sourceText && rowPreview && !sameText(rowPreview, sourceText) && !isSystemSourcePreview(rowPreview)) {
      markPhase('sidebar_latest_mismatch_ignored');
      __feigeSendCounters.sidebar_precheck_skipped_no_msg_id = (
        __feigeSendCounters.sidebar_precheck_skipped_no_msg_id || 0
      ) + 1;
      // Fall through to deeper thread-walk check; do NOT return stale.
    }
    var beforeMatch = activeMatches(expectedCustomer, items);
    if (!beforeMatch.ok) {
      markPhase('open_click_start');
      target.click();
      await sleep(260);
      markPhase('open_click_wait_done');
      items = Array.from(document.querySelectorAll('[data-qa-id="qa-conversation-chat-item"]'))
        .filter(rowIsCurrent);
    }
    var afterMatch = activeMatches(expectedCustomer, items);
    if (!afterMatch.ok) {
      markPhase('active_customer_mismatch_after_open');
      return finish({
        sent: false,
        error: 'Active customer mismatch after open',
        expected_customer: expectedCustomer,
        header_name: afterMatch.header,
        sidebar_name: afterMatch.sidebar
      });
    }
    markPhase('active_customer_verified');
  }

  // Walk every customer bubble in the chat thread.  Mirrors
  // latestCustomerBubble() but returns the whole list (newest first)
  // so the stale-check can accept a match against ANY bubble, not just
  // the latest one.  Added 2026-05-13 to fix the false-positive
  // stale-drop on chats where Feige re-orders older customer bubbles
  // to the end of the DOM (observed for 客户05: dispatched msg_id
  // mp4ii8aq for "买了一年了出质量问题还能保修吗？" was DROPPED because
  // an earlier message "丢件了怎么处理？" with msg_id mp4ii5ts appeared
  // as the "latest" bubble in DOM — that older question was still
  // unanswered and the customer was waiting for the answer to
  // "买了一年了...".  Silently dropping legitimate replies was costing
  // ~15-30% of deliveries under flood load.
  function allCustomerBubbles() {
    // 2026-05-14 throughput optimization: short-circuit after collecting
    // ``MAX_BUBBLES`` customer bubbles. We only use the result to (a)
    // report the latest customer bubble's text/msg_id and (b) match the
    // source msg_id against any visible customer bubble. The source msg_id
    // we're looking for was just dispatched and is therefore in the LAST
    // few bubbles of the thread — walking all wrappers in a 20-chat
    // flooded DOM was costing 5-7s of CDP eval (the dominant cost in the
    // send path and the window during which the SPA auto-switches active
    // customer, producing the `Active customer drifted between typing
    // and click` failure family). Capping at 8 newest customer bubbles
    // keeps the dedup window intact (a customer rarely has 8 unanswered
    // bubbles in a row) while shrinking the typical scan to <300ms.
    var out = [];
    var MAX_BUBBLES = 8;
    var wrappers = document.querySelectorAll('[data-qa-id="qa-message-warpper"]');
    function isTransferMarker(text) {
      var t = String(text || '').replace(/\s+/g, '').trim();
      return t === '转人工' || t === '转人工客服' || t === '人工客服';
    }
    for (var i = wrappers.length - 1; i >= 0; i--) {
      if (out.length >= MAX_BUBBLES) break;
      var wrap = wrappers[i];
      // mt064: side detection prefers the semantic messageIsMe/messageNotMe
      // markers (survive Feige hash redesigns); legacy flex-direction on the
      // hashed .Ie29C7... row is the fallback when no bubble marker exists.
      var bubble = wrap.querySelector('.iD7SHBvMhm4OhfCsBGr1, [class*="messageNotMe"], [class*="messageIsMe"]');
      var row = wrap.querySelector('.Ie29C7uLyEjZzd8JeS8A');
      if (bubble) {
        if (bubble.classList.contains('messageIsMe')) continue;  // agent-side
      } else {
        if (!row) continue;
        if ((row.style.flexDirection || '').indexOf('reverse') !== -1) continue;  // agent-side
      }
      var text = '';
      if (bubble) {
        text = (bubble.querySelector('pre') || bubble).textContent.trim();
      }
      var hasContentImage = false;
      var imgs = (row || wrap).querySelectorAll('img');
      for (var k = 0; k < imgs.length; k++) {
        var im = imgs[k];
        var cls = (im.className || '').toString();
        var alt = (im.getAttribute('alt') || '').trim();
        if (/Zq9KgucRnc7bRQfikvzQ|qwDH4Hnmk4jmYkYLmHGF/.test(cls)) continue;
        if (alt === '头像') continue;
        var src = im.src || im.getAttribute('src') || '';
        if (src && src.indexOf('data:image/svg') !== 0) {
          hasContentImage = true;
          break;
        }
      }
      // 2026-05-24 mt038C: product-card bubbles have neither a text
      // bubble (.iD7SHBvMhm4OhfCsBGr1) nor an <img> tag — their
      // thumbnail is a CSS background-image on a div, and their
      // payload is a .chatd-card element with data-id="..._template".
      // Without recognising .chatd-card here, the source-guard scans
      // a bubbles[] missing the card entirely, and any reply whose
      // source_customer_msg_id ends in "_template" fails with
      // stale_reason='no_match'.  Live customer trace 2026-05-24
      // 12:19:30 客户18: bot's reply to the 男童短袖球服 card was
      // dropped, mt038A rescue ineffective because the re-scrape
      // returned the SAME card msg_id (same input → same output).
      var hasCard = !!wrap.querySelector('.chatd-card');
      if (!text && !hasContentImage && !hasCard) continue;
      if (text && isTransferMarker(text)) continue;
      var idEl = wrap.querySelector('[data-id]');
      out.push({
        text: text,
        msg_id: idEl ? (idEl.getAttribute('data-id') || '') : ''
      });
    }
    return out;
  }

  // ws040b: skip the source-turn guard for a card-only conv resolved by its row.
  // The guard looks for the customer's SOURCE message in the thread by msg_id or
  // text, but a WS card has an empty msg_id and a synthesized '[商品卡片]…' text
  // that the DOM card widget never renders as a matchable bubble -> it always
  // hits source_turn_not_found. We already verified the conversation (the UNIQUE
  // needReply '[商品]' row + active-customer check), so the thread-level source
  // verification is redundant here. Active-customer drift is still covered by the
  // before/after/final activeMatches checks around the actual send.
  if ((sourceMsgId || sourceText) && !cardRowResolved) {
    var latest = { found: false, text: '', msg_id: '' };
    var sourceOk = false;
    var matchedAt = -1;   // index in bubbles[] (0 = newest); -1 = no match
    markPhase('source_guard_start');
    // Wall-clock budget for the entire source_guard phase. Under flood
    // load `allCustomerBubbles()` can spend 5-7s in the renderer on a
    // single call, so the 10-iteration count cap alone produced a 7s+
    // window during which the active customer would drift (observed
    // 2026-05-14 in the 20-customer emulation: customer 12's send
    // failed with `active_customer_mismatch_before_click` after
    // `source_guard_verified` took 6.4s and 客户10 swapped the sidebar).
    // 1500ms keeps total send wall-clock under ~3s in the common case;
    // if the renderer is so loaded that even one poll exceeds the
    // budget we still get one attempt — the budget just prevents us
    // looping again into a worse failure mode.
    var guardStartT = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
    var GUARD_BUDGET_MS = 1500;
    for (var guardPoll = 0; guardPoll < 10; guardPoll++) {
      __feigeSendCounters.source_guard_polls = guardPoll + 1;
      // Drift-fail-fast: if the active customer changed between polls
      // (a concurrent subtab-switch from another delivery or the DOM
      // monitor), bail now instead of wasting another ~7s typing into
      // the wrong chat. The caller's outer retry already re-focuses,
      // so an early bail here recovers much faster than failing at
      // the click-send stage.
      if (expectedCustomer && guardPoll > 0) {
        var midItems = Array.from(document.querySelectorAll('[data-qa-id="qa-conversation-chat-item"]'))
          .filter(rowIsCurrent);
        var midMatch = activeMatches(expectedCustomer, midItems);
        if (!midMatch.ok) {
          markPhase('active_customer_drifted_during_source_guard');
          return finish({
            sent: false,
            error: 'active_customer_drifted_during_source_guard',
            expected_customer: expectedCustomer,
            header_name: midMatch.header,
            sidebar_name: midMatch.sidebar,
            expected_source_msg_id: sourceMsgId,
            expected_source_text: sourceText,
            phase_when_drift_detected: 'source_guard_loop'
          });
        }
      }
      var bubbles = allCustomerBubbles();
      if (bubbles.length > 0) {
        latest = { found: true, text: bubbles[0].text, msg_id: bubbles[0].msg_id };
        // 2026-05-20: STRICT latest-only match.  Previously accepted ANY
        // visible customer bubble, which let stale Q&A bot replies for
        // older turns get typed AFTER the customer had moved on to a
        // newer question.  Observed in the 22:52 flood: 客户02 sent Q1
        // (婴儿66码) then Q2 (港澳台运费) then Q3 (...); an in-flight Q1
        // reply landed AFTER Q2 was visible and was typed — user saw it
        // as "responding to my 2nd-to-latest msg".  Strict match: bot
        // reply only delivered when its source matches the LATEST
        // customer bubble.  Older replies are dropped as stale.
        var top = bubbles[0];
        if (sourceMsgId && top.msg_id && top.msg_id === sourceMsgId) {
          sourceOk = true;
          matchedAt = 0;
        } else if (sourceText && top.text && (sameText(top.text, sourceText)
                   || (allowSimilarSource && similarText(top.text, sourceText)))) {
          // ws143: exact OR same-question-re-scrape match on the NEWEST bubble → deliver
          // (the answer to the shorter phrasing fully answers the fuller one).
          sourceOk = true;
          matchedAt = 0;
        } else {
          // Did we match an OLDER bubble?  Record it for diagnostics —
          // these dropped replies are visible in the source_guard_stale
          // outcome's matchedAt and matched-bubble fields.
          for (var bi = 1; bi < bubbles.length; bi++) {
            var b = bubbles[bi];
            if (sourceMsgId && b.msg_id && b.msg_id === sourceMsgId) {
              matchedAt = bi;
              break;
            }
            if (sourceText && b.text && sameText(b.text, sourceText)) {
              matchedAt = bi;
              break;
            }
          }
        }
        if (sourceOk) break;
      }
      var nowT = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
      if (nowT - guardStartT > GUARD_BUDGET_MS) {
        markPhase('source_guard_budget_exceeded');
        break;
      }
      if (guardPoll < 9) await sleep(100);
    }
    if (!latest.found) {
      markPhase('source_turn_not_found');
      return finish({
        sent: false,
        error: 'source_turn_not_found',
        expected_source_msg_id: sourceMsgId,
        expected_source_text: sourceText
      });
    }
    if (!sourceOk) {
      // Source not found in the visible chat thread.  Two distinct
      // root causes — must be distinguished because they need
      // different downstream handling:
      //
      // (a) **drift-during-source-guard** — Feige re-shuffled the
      //     sidebar between our pre-source-guard ``active_customer_verified``
      //     and this guard pass; the chat thread DOM is now showing
      //     a DIFFERENT customer's messages.  Of course our dispatched
      //     msg_id won't be in there — it belongs to the customer we
      //     were originally targeting.  This is the same drift family
      //     Fix 8 catches at pre-click, but happens earlier (before
      //     typing).  Observed 2026-05-13 14:15:29 for 客户14:
      //     dispatched msg_id mp4k1e3n ("丢件了怎么处理？") not found in
      //     thread, but the thread's "latest" bubble was mp4k1elt
      //     ("男装XL码适合多高？") — which is 客户18's question.  Same
      //     thing at 14:16:05 for 客户08 (thread showing 客户14's
      //     content).  Treating these as stale_reply silently drops
      //     legitimate replies — the customer's question IS still
      //     unanswered and the answer IS valid.
      //
      // (b) **truly stale** — chat thread DOES belong to the right
      //     customer, but our dispatched msg_id genuinely isn't in
      //     it (deleted bubble — rare; or some session-state issue).
      //     In this case the drop is correct.
      //
      // Distinguish by re-checking active customer:
      //   - if active != expectedCustomer → drift, return
      //     ``active_customer_drifted_during_source_guard`` (HOT-PATH-B's
      //     failure handler + Fix 7b clear last_dispatched_msg_id → retry).
      //   - if active == expectedCustomer → genuine stale, keep old
      //     behavior.
      if (expectedCustomer) {
        var driftItems = Array.from(document.querySelectorAll('[data-qa-id="qa-conversation-chat-item"]'))
          .filter(rowIsCurrent);
        var driftMatch = activeMatches(expectedCustomer, driftItems);
        if (!driftMatch.ok) {
          markPhase('active_customer_drifted_during_source_guard');
          return finish({
            sent: false,
            error: 'active_customer_drifted_during_source_guard',
            expected_customer: expectedCustomer,
            header_name: driftMatch.header,
            sidebar_name: driftMatch.sidebar,
            expected_source_msg_id: sourceMsgId,
            expected_source_text: sourceText,
            visible_thread_latest_msg_id: latest.msg_id || '',
            visible_thread_latest_text: (latest.text || '').slice(0, 160),
            phase_when_drift_detected: 'source_guard'
          });
        }
      }
      // 2026-05-23 mt034: time-gap stale relaxation.  When the bot's
      // reply targets an OLDER customer bubble (matchedAt > 0) AND
      // Python decided the gap between target and latest is within
      // STALE_GAP_S, retry with ``bypassOlderBubbleMatch=true`` so the
      // reply gets typed.  Rationale: customer asked Q1, then Q2 within
      // a few seconds — both deserve answers.  Strict 2026-05-20
      // latest-only match dropped Q1's reply outright (observed
      // 2026-05-23 16:27:29 肽斯特 包邮/顺丰).  ``no_match`` (matchedAt
      // === -1) stays strict — the bubble has genuinely vanished.
      if (matchedAt > 0 && bypassOlderBubbleMatch) {
        markPhase('source_guard_bypassed_older_bubble_match');
        __feigeSendCounters.source_match_index = matchedAt;
        sourceOk = true;
      } else if (!sourceMsgId && matchedAt === -1 && allowNoMsgIdSend) {
        // ws126: no authoritative source msg_id was ever captured for this
        // turn (card / sidebar-preview dispatch, e.g. '[商品卡片]…').  The
        // strict latest-bubble match can NEVER succeed here: a product card
        // renders as a .chatd-card with no matchable text bubble, so the
        // synthesized sourceText never equals any bubble's text and there is
        // no msg_id to compare.  ``no_match`` is therefore a false positive,
        // not evidence of staleness — the customer has NOT moved on to a
        // newer text question (the card IS the latest thing).  Dropping here
        // strands the customer on a valid card-ack (the ws125 1-vs-2 run lost
        // 21 replies this exact way, empty expected_source_msg_id).  The
        // active-customer check already passed (right conversation), so allow
        // the send.  Only strict-drop when we actually HAD a msg_id to verify.
        markPhase('source_guard_pass_no_msgid');
        __feigeSendCounters.source_guard_pass_no_msgid = (
          __feigeSendCounters.source_guard_pass_no_msgid || 0
        ) + 1;
        sourceOk = true;
      } else {
        markPhase(matchedAt > 0 ? 'source_guard_stale_older_bubble' : 'source_guard_stale');
        return finish({
          sent: false,
          error: 'stale_reply_source_msg_id',
          stale_reason: matchedAt > 0 ? 'older_bubble_match' : 'no_match',
          matched_older_bubble_index: matchedAt,
          expected_source_msg_id: sourceMsgId,
          active_source_msg_id: latest.msg_id || '',
          expected_source_text: sourceText,
          active_source_text: (latest.text || '').slice(0, 160)
        });
      }
    }
    // Telemetry: record where in the thread the match was found.
    // matchedAt > 0 means we matched an OLDER (not the absolute latest)
    // customer bubble — useful for spotting Feige DOM-reorder oddities
    // vs genuine "customer typed a new message after dispatch".
    __feigeSendCounters.source_match_index = matchedAt;
    markPhase('source_guard_verified');
  }

  if (expectedCustomer) {
    items = Array.from(document.querySelectorAll('[data-qa-id="qa-conversation-chat-item"]'))
      .filter(rowIsCurrent);
    var finalMatch = activeMatches(expectedCustomer, items);
    if (!finalMatch.ok) {
      markPhase('active_customer_mismatch_before_send');
      return finish({
        sent: false,
        error: 'Active customer mismatch before send',
        expected_customer: expectedCustomer,
        header_name: finalMatch.header,
        sidebar_name: finalMatch.sidebar
      });
    }
    markPhase('final_active_verified');
  }

  var inputSelectors = [
    '[data-qa-id="qa-send-message-textarea"]',
    'textarea[placeholder*="发送"]',
    'textarea',
    '[contenteditable="true"]'
  ];
  var input = null;
  for (var s = 0; s < inputSelectors.length; s++) {
    var candidates = Array.from(document.querySelectorAll(inputSelectors[s]));
    for (var c = 0; c < candidates.length; c++) {
      if (visible(candidates[c])) { input = candidates[c]; break; }
    }
    if (input) break;
  }
  if (!input) {
    markPhase('input_not_found');
    return finish({ sent: false, error: 'Input box not found' });
  }
  markPhase('input_found');

  var beforeAgentText = latestAgentBubbleText();
  var latestBeforeInput = latestVisibleBubble();
  if (
    latestBeforeInput.found &&
    latestBeforeInput.sender === 'agent' &&
    sameText(latestBeforeInput.text, text)
  ) {
    markPhase('dedup_latest_agent_bubble');
    return finish({
      sent: true,
      method: 'dedup_latest_agent_bubble',
      selector: '',
      verified: 'already_sent_bubble'
    });
  }
  setValue(input, text);
  await sleep(80);
  markPhase('input_set_done');
  if (!sameText(readValue(input), text)) {
    markPhase('input_set_failed');
    return finish({
      sent: false,
      error: 'Input did not accept message text',
      input_value_preview: readValue(input).slice(0, 120)
    });
  }

  // ── Pre-click active-customer guard (Fix 8, 2026-05-13) ───────────────
  // Background (incident: 客户20 silent mis-delivery):
  // ``final_active_verified`` runs BEFORE the input lookup + typing.  Under
  // flood load the JS event loop is congested — the inner ``await sleep(80)``
  // between ``setValue(input, text)`` and the subsequent send-button click
  // was observed to stretch from 80ms → 1357ms (12-16× slower) on the
  // 客户20 trace.  During that 1.3s gap Feige's SPA can re-shuffle the
  // sidebar and switch the active chat (Feige does this when newer customer
  // messages land in *any* of the 20 simultaneously-flooding chats).  The
  // existing pre-typing active-verify caught that drift correctly, but by
  // the time of the actual ``sendBtn.click()`` the active customer can
  // have drifted *again* — and the click then lands in the wrong chat,
  // typing the message into customer X's input field.  Then our verify
  // loop sees the input clear (yes — Feige consumed it) but no outgoing
  // bubble appears in OUR (expectedCustomer's) chat — Fix 5's
  // ``input_cleared_no_bubble`` path declares "probable success" — and
  // we silently mis-deliver to customer X while expectedCustomer's reply
  // is lost forever.
  //
  // Defence: do ONE MORE active-customer check RIGHT BEFORE clicking the
  // send button.  If the active customer has drifted away from
  // ``expectedCustomer`` in the meantime, abort the send before it fires.
  // The caller's HOT-PATH-B re-open + retry path then runs (Fix 7b
  // clears last_dispatched_msg_id so PreDispatch will re-dispatch).
  //
  // This check is fast (~10ms) so it adds negligible latency to the
  // happy path.  In the 客户20 scenario it would have aborted instead of
  // mis-delivering.
  if (expectedCustomer) {
    var preClickItems = Array.from(document.querySelectorAll('[data-qa-id="qa-conversation-chat-item"]'))
      .filter(rowIsCurrent);
    var preClickMatch = activeMatches(expectedCustomer, preClickItems);
    if (!preClickMatch.ok) {
      // ── In-place drift recovery (2026-05-14) ──────────────────────
      // Under flood load Feige's SPA auto-switches the active chat
      // when a NEW customer message arrives in a different chat —
      // observed mid-send for 5 of 20 customers across consecutive
      // emulation runs, always at this phase. Instead of aborting and
      // re-doing the whole 7-10s send-JS round-trip from Python, try
      // ONCE to re-focus the expected customer in-page and resume.
      //
      // Cost of failure: ~600-900ms of extra work (one sidebar click +
      // active verify + input re-set). Cost of NOT recovering: ~9s of
      // Python-side fallback to the browser-use loop (which under load
      // often drifts again). The recovery is fast enough that it can't
      // make us late and is structurally bounded to one attempt.
      markPhase('drift_recovery_attempt_start');
      var recoveryTarget = null;
      var recoverySidebar = Array.from(document.querySelectorAll('[data-qa-id="qa-conversation-chat-item"]'));
      for (var ri = 0; ri < recoverySidebar.length; ri++) {
        var row = recoverySidebar[ri];
        var nameNode = row.querySelector('[data-qa-id="qa-conversation-name"], .conversation-name, [class*="name"]');
        var rowName = nameNode ? (nameNode.textContent || '').trim() : '';
        if (rowName && rowName === expectedCustomer) {
          recoveryTarget = row;
          break;
        }
      }
      if (recoveryTarget) {
        recoveryTarget.click();
        await sleep(280);
        markPhase('drift_recovery_click_done');
        var postRecoverItems = Array.from(document.querySelectorAll('[data-qa-id="qa-conversation-chat-item"]'))
          .filter(rowIsCurrent);
        var postRecoverMatch = activeMatches(expectedCustomer, postRecoverItems);
        if (postRecoverMatch.ok) {
          // Re-locate the input (the SPA likely re-rendered it on the
          // chat switch) and re-type. Skip recovery if the input isn't
          // findable — bail with the drift error so the Python caller
          // can fallback cleanly.
          var recoveredInput = null;
          for (var si2 = 0; si2 < inputSelectors.length; si2++) {
            var cand = document.querySelector(inputSelectors[si2]);
            if (cand && visible(cand)) { recoveredInput = cand; break; }
          }
          if (recoveredInput) {
            setValue(recoveredInput, text);
            await sleep(80);
            if (sameText(readValue(recoveredInput), text)) {
              input = recoveredInput;  // continue the rest of the send with the new input handle
              markPhase('drift_recovery_input_reset_ok');
              // fall through to the send-button click below
            } else {
              markPhase('drift_recovery_input_reset_failed');
              return finish({
                sent: false,
                error: 'Active customer drifted between typing and click',
                expected_customer: expectedCustomer,
                header_name: preClickMatch.header,
                sidebar_name: preClickMatch.sidebar,
                recovery: 'input_reset_failed',
                phase_when_drift_detected: 'pre_click_guard',
                input_value_preview: readValue(recoveredInput).slice(0, 120)
              });
            }
          } else {
            markPhase('drift_recovery_input_not_found');
            return finish({
              sent: false,
              error: 'Active customer drifted between typing and click',
              expected_customer: expectedCustomer,
              header_name: preClickMatch.header,
              sidebar_name: preClickMatch.sidebar,
              recovery: 'input_not_found_after_refocus',
              phase_when_drift_detected: 'pre_click_guard'
            });
          }
        } else {
          markPhase('drift_recovery_refocus_failed');
          return finish({
            sent: false,
            error: 'Active customer drifted between typing and click',
            expected_customer: expectedCustomer,
            header_name: postRecoverMatch.header,
            sidebar_name: postRecoverMatch.sidebar,
            recovery: 'refocus_did_not_take',
            phase_when_drift_detected: 'pre_click_guard'
          });
        }
      } else {
        markPhase('drift_recovery_sidebar_row_missing');
        return finish({
          sent: false,
          error: 'Active customer drifted between typing and click',
          expected_customer: expectedCustomer,
          header_name: preClickMatch.header,
          sidebar_name: preClickMatch.sidebar,
          recovery: 'sidebar_row_missing',
          phase_when_drift_detected: 'pre_click_guard'
        });
      }
    }
    markPhase('pre_click_active_verified');
  }

  var sendSelectors = [
    '[data-qa-id="qa-send-message-button"]',
    '[data-qa-id="qa-send-btn"]',
    'button[class*="send"]'
  ];
  var sendBtn = null;
  var selector = '';
  for (var sb = 0; sb < sendSelectors.length; sb++) {
    var btn = document.querySelector(sendSelectors[sb]);
    if (btn && visible(btn)) {
      sendBtn = btn;
      selector = sendSelectors[sb];
      break;
    }
  }

  var method = '';
  if (sendBtn) {
    sendBtn.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
    sendBtn.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
    sendBtn.click();
    method = 'button_click';
  } else {
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true }));
    input.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true }));
    method = 'enter_key';
  }
  markPhase('send_triggered');

  // Verification loop: poll for either (a) our outgoing bubble appearing in
  // the chat thread, or (b) Feige clearing our input box (the only way the
  // input clears between our typing and our verification is Feige's own
  // onSend handler — so a cleared input is itself strong evidence that the
  // message was accepted and sent).
  //
  // 2026-05-13 throughput fix: under flood load the page renders bubbles
  // slowly enough that we time out on bubble-verify even after the message
  // actually went through.  At 24 polls × 100ms (nominal 2.4s, but the
  // ``readValue`` + ``latestAgentBubbleText`` JS eval takes ~280ms each
  // under load → ~6.7s wall-clock per timeout, observed) each false-negative
  // burned 6.7s of front-desk time → queue piled up → flood throughput
  // collapsed to ~3 deliveries / 5 min on a 20-customer test.
  //
  // New behaviour:
  //   1. Cap total polls at 12 (instead of 24) — limits the worst-case wait.
  //   2. After we see the input clear, give the bubble a short grace window
  //      (5 more polls ≈ 0.5s nominal) to render normally.  If the bubble
  //      shows up, return ``verified: 'outgoing_bubble'`` (the previous
  //      strong-success path).
  //   3. If the grace expires with the input still cleared and no bubble,
  //      return ``sent: true, verified: 'input_cleared_no_bubble'`` — a
  //      "probable success" outcome.  Caller treats this as success and
  //      does NOT retry (which would deliver the same message twice if
  //      Feige actually sent it the first time).
  //   4. If the full 12 polls elapse with input never cleared, that's the
  //      only true failure case — input still has our text, send didn't
  //      take.  Return ``sent: false`` as before.
  //
  // The constants are local consts so they're easy to retune from the JS
  // side without touching the Python wrapper.
  // 2026-05-20 chat-scope fix: even when latestAgentBubbleText() returns a
  // matching bubble, we must verify it landed in the EXPECTED customer's
  // chat — not in some other customer's chat that the SPA drifted to
  // mid-click.  The post-send verify now ALWAYS rechecks activeMatches()
  // before declaring success.  Without this guard the emulator/Feige race
  // (state.activeCustomer-style routing inside the SPA) silently misdelivers
  // the reply to whichever chat is visible at click-time and our JS still
  // reports outgoing_bubble because the bubble IS in some visible chat.
  //
  // 2026-05-20 wider window: bumped MAX_VERIFY_POLLS 12→24 so heavy DOMs
  // (240 emulator extra rows + real Feige sidebars) have more headroom.
  var MAX_VERIFY_POLLS = 24;
  var POLLS_AFTER_CLEAR_GRACE = 5;
  var inputClearedDuringVerify = false;
  var pollsSinceClear = 0;

  function chatScopeOk() {
    // Returns {ok, header, sidebar} — used as the final guard on every
    // success branch.  If the expected customer isn't set we can't check,
    // so trust the bubble (best-effort).
    if (!expectedCustomer) return { ok: true, header: '', sidebar: '' };
    var items = Array.from(document.querySelectorAll('[data-qa-id="qa-conversation-chat-item"]'))
      .filter(rowIsCurrent);
    return activeMatches(expectedCustomer, items);
  }

  for (var poll = 0; poll < MAX_VERIFY_POLLS; poll++) {
    __feigeSendCounters.verify_polls = poll + 1;
    await sleep(100);
    var currentValue = readValue(input);
    var afterAgentText = latestAgentBubbleText();
    if (sameText(afterAgentText, text) && !sameText(beforeAgentText, text)) {
      var scope = chatScopeOk();
      if (!scope.ok) {
        // Mis-delivery: bubble appeared in the WRONG customer's chat.
        // This is the silent failure mode we used to mask as success.
        markPhase('mis_delivered_to_wrong_chat');
        return finish({
          sent: false,
          method: method,
          selector: selector,
          verified: 'mis_delivered_to_wrong_chat',
          expected_customer: expectedCustomer,
          header_name: scope.header,
          sidebar_name: scope.sidebar,
          note: 'Outgoing bubble appeared but in a different customer chat — caller must retry.'
        });
      }
      markPhase('verified_outgoing_bubble');
      // 2026-05-24 mt037C: latestAgentBubbleMsgId is now async (polls
      // up to 5×100ms for the data-id assignment race + text-match
      // preference).  Must await before finish() serializes the object,
      // otherwise we'd send a Promise.
      var verifiedMsgId = await latestAgentBubbleMsgId();
      return finish({
        sent: true,
        method: method,
        selector: selector,
        verified: 'outgoing_bubble',
        // mt024: surface the wrapper data-id of the bubble we just
        // typed so Python can register it as "ours" against future
        // mt017 detection passes.  Empty string if the wrapper has
        // no data-id (rare; the bubble is still ours, just untrackable
        // for this fix — falls through to existing text-based ledger).
        verified_msg_id: verifiedMsgId
      });
    }
    if (!currentValue.trim()) {
      if (!inputClearedDuringVerify) {
        inputClearedDuringVerify = true;
        markPhase('verified_input_cleared');
      } else {
        pollsSinceClear++;
        if (pollsSinceClear >= POLLS_AFTER_CLEAR_GRACE) {
          // Grace expired with input cleared and bubble still missing.
          // Demoted from "probable success" to "unverified" on 2026-05-20
          // after live evidence (客户01/11/13/16 trace) showed input_cleared
          // does NOT imply Feige actually rendered/persisted the message.
          // Now classified as a soft failure that the caller may retry.
          markPhase('verified_input_cleared_no_bubble_unverified');
          var scope2 = chatScopeOk();
          return finish({
            sent: false,
            method: method,
            selector: selector,
            verified: 'input_cleared_no_bubble',
            expected_customer: expectedCustomer,
            header_name: scope2.header,
            sidebar_name: scope2.sidebar,
            note: 'Input cleared but no outgoing bubble rendered in expected chat — unverified, caller should retry.'
          });
        }
      }
    }
  }

  markPhase('send_verify_timeout');
  if (inputClearedDuringVerify) {
    var scope3 = chatScopeOk();
    return finish({
      sent: false,
      method: method,
      selector: selector,
      verified: 'input_cleared_no_bubble',
      expected_customer: expectedCustomer,
      header_name: scope3.header,
      sidebar_name: scope3.sidebar,
      note: 'Verification poll cap reached; input cleared but bubble never rendered — unverified, caller should retry.'
    });
  }
  return finish({
    sent: false,
    error: 'Send did not clear input or create outgoing bubble',
    method: method,
    selector: selector,
    input_cleared_without_bubble: false,
    input_value_preview: readValue(input).slice(0, 120)
  });
})(MESSAGE_TEXT, EXPECTED_CUSTOMER, EXPECTED_SOURCE_MSG_ID, EXPECTED_SOURCE_TEXT, BYPASS_OLDER_BUBBLE_MATCH, ALLOW_NOMSGID_SEND, ALLOW_SIMILAR_SOURCE);
"""


async def feige_ws_send_text(customer_name: str, text: str, browser_session: "BrowserSession") -> bool:
    """feige_ws: off-DOM delivery over the Frontier socket. True ONLY when the server
    confirmed it (echo). Best-effort — any issue returns False so the caller falls back
    to the DOM send. No typing lock, no DOM, no renderer contention.

    Shared core: S1 replies (feige_send_message) and S2 placeholders (direct_delivery)
    both route through here so there is a single off-DOM send path."""
    try:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import ws_session as _wss
    except Exception:
        return False
    cust = str(customer_name or "").strip()
    text = str(text or "")
    if not cust or not text:
        return False
    built = _wss.frame_for(cust, text)
    if not built:
        # ws064: split the conflated 'unconfirmed/unavailable' fallback into explicit reasons
        # so a 1-vs-N run shows WHY each WS send fell to DOM. NO-ROUTE = no send template /
        # first-contact route for this customer (e.g. a lone card:<conv> the de-synth couldn't
        # resolve to a real name, or a conv with no captured outgoing frame yet).
        logger.info(
            f"[Feige] WS send fallback reason=NO-ROUTE cust={cust!r}"
            f"{' (synthetic card identity; needs first-contact or a real-name de-synth)' if cust.startswith('card:') else ' (no send template captured yet)'}"
            " -> DOM")
        return False   # no template/routing for this customer yet -> DOM
    frame, cid = built
    # ws011 (spike): off-RENDERER raw send first when ECAN_FEIGE_WS_SEND_RAW=1 —
    # write the frame to eCan's OWN Frontier socket, no Runtime.evaluate. The frame's
    # cid is already registered (frame_for), so confirmation below is identical
    # regardless of which transport put the bytes on the wire. Any failure falls
    # through to the proven eval-inject path. Default OFF (unvalidated anti-bot).
    _raw_sent = False
    if os.environ.get("ECAN_FEIGE_WS_SEND_RAW", "") == "1":
        try:
            from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
                ws_raw_sender as _wsr,
            )
            _raw_sent = await _wsr.raw_send(frame)
        except Exception as _re:
            logger.debug(f"[Feige] WS raw-send branch error (-> eval-inject): {_re}")
    _inject_via_page_socket = False
    _via = ""
    # ws031 (Fix A): try the IDLE detection-tab renderer FIRST so the send doesn't
    # stall behind bubble scrapes / 50KB bootstraps on the main renderer — the
    # audited 12s/35s stalls that are the real cause of the slowness + freezes (the
    # "off-DOM" send was never actually off-renderer). The frame routes by
    # security_receiver_id (ws028), so it delivers to the right customer regardless of
    # which tab's authed socket sends it (same lane as the 100%-reliable read-ack).
    # Gated ECAN_FEIGE_WS_SEND_DET_TAB=1.
    _DET_CONFIRM_TIMEOUT = 4.0
    if not _raw_sent and os.environ.get("ECAN_FEIGE_WS_SEND_DET_TAB", "") == "1":
        try:
            from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
                ws_observer as _wsobs,
            )
            _det = await _wsobs.inject_frame_on_detection_tab(frame)
        except Exception:
            _det = ""
        if _det in ("SENT", "UNKNOWN"):
            # VALIDATION mode: require the server echo on the detection tab (short
            # timeout); if it doesn't confirm, fall back to the main tab (drop-safe).
            # On an idle renderer the echo returns in <1s, so the fallback — and any
            # duplicate — is essentially never hit. Once detection-tab sends prove
            # reliable, ECAN_FEIGE_WS_SEND_DET_TAB_TRUST=1 skips the fallback (presume,
            # zero dup). The tri-state inject means UNKNOWN (bridge timeout) is treated
            # as committed, so we never double-send the same frame.
            _via = "detection-tab"
            if await _wss.wait_confirmed(cid, _DET_CONFIRM_TIMEOUT):
                logger.info(f"[Feige] WS off-DOM send DELIVERED via detection tab cust={cust!r} len={len(text)}")
                return True
            if os.environ.get("ECAN_FEIGE_WS_SEND_DET_TAB_TRUST", "") == "1":
                logger.info(f"[Feige] WS detection-tab send UNCONFIRMED — presuming delivered (trust mode) cust={cust!r} len={len(text)}")
                return True
            logger.info(f"[Feige] WS detection-tab send UNCONFIRMED in {_DET_CONFIRM_TIMEOUT}s — main-tab fallback cust={cust!r}")
            # fall through to the main-tab inject below (same frame/cid, drop-safe)
    if not _raw_sent:
        _inj = _wss.inject_js(frame)
        res = None
        # ws124: route the inject eval onto a dedicated-thread CDP loop (gated, default
        # OFF) so it isn't starved behind the qasync main loop's queue under high
        # concurrency (the HANDOFF-STARVED wall). Additive — any miss returns None and
        # we fall through to the proven shared-loop eval below.
        if os.environ.get("ECAN_FEIGE_DEDICATED_CDP_LOOP", "") == "1":
            try:
                from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
                    feige_cdp_lane as _lane,
                )
                _lane_tid = await _resolve_live_chat_tab_target_id_bounded(browser_session)
                if _lane_tid:
                    res = await _lane.eval_inject(browser_session, _lane_tid, _inj)
            except Exception as _le:
                logger.debug(f"[Feige] dedicated CDP lane error (-> shared loop): {_le}")
                res = None
        if res is None:
            # ws128: cap the in-page inject eval with its OWN short timeout instead of
            # the 12s feige-family default. The inject is a tiny socket.send (median
            # ~0.5s); under 1-vs-N renderer saturation it HANGS (HANDOFF-STARVED) and
            # the 12s wait — multiplied across the serial direct-delivery worker — is
            # what produced the ~3-min dispatch blackout at 1-vs-7 (live 22:32-22:35:
            # feige_ws_send Runtime.evaluate total_ms=12002 -> 4x 35s job timeouts). A
            # true hang means the JS never ran, so socket.send never fired -> the DOM
            # fallback is correct, no duplicate. Fail fast and let DOM take over.
            # Reversible: ECAN_FEIGE_WS_SEND_INJECT_TIMEOUT_S (default 6s; set to 12 for
            # the old behavior).
            try:
                _inj_to = max(1.0, float(
                    os.getenv("ECAN_FEIGE_WS_SEND_INJECT_TIMEOUT_S", "6.0") or 6.0))
            except (TypeError, ValueError):
                _inj_to = 6.0
            res = await _evaluate_live_chat_js(
                browser_session, _inj,
                trace_label="feige_ws_send", read_only=False, lock_free=True,
                timeout_s=_inj_to,
            )
        if "SENT" not in str(res):
            # ws064: INJECT-FAILED = the main-tab Runtime.evaluate that puts the frame on the
            # wire did NOT report SENT (typically it timed out under main-renderer contention —
            # the 1-vs-7 freeze cause). Promote to INFO so the next run shows it distinctly from
            # NO-ROUTE and UNCONFIRMED.
            logger.info(
                f"[Feige] WS send fallback reason=INJECT-FAILED (eval !=SENT: {str(res)[:60]!r}) "
                f"cust={cust!r} -> DOM")
            return False
        _inject_via_page_socket = True
        _via = "main-tab"
    # ws137: first-contact raw does NOT reliably deliver — the ws133 assumption ("fc delivers,
    # echo just slow", from 2 ws131 samples) was WRONG. The ws136 run proved it: 0/27 first-contact
    # sends confirmed, while normal per-talk sends confirm in 0.3-0.9s. ws133's presume-delivered
    # turned that into a SILENT stall — cold-start cards (packet/J14N9/瓦哒嘻哇) were marked
    # answered_strong on an UNDELIVERED reply, so no retry fired and the customers asked
    # 有没有人啊/转人工 for 40 min into silence. DEFAULT NOW: do NOT presume. Wait briefly; if the
    # echo confirms, deliver; otherwise return False so the caller DOM-falls-back / the worker
    # retries instead of masking the drop. Opt back into the old presume with
    # ECAN_FEIGE_WS_FC_PRESUME=1 (default now 0).
    if _raw_sent and _wss.pending_is_fc(cid):
        _fc_ok = await _wss.wait_confirmed(cid, 3.0)
        if _fc_ok:
            logger.info(
                f"[Feige] WS first-contact raw send CONFIRMED cust={cust!r} len={len(text)}")
            return True
        if os.environ.get("ECAN_FEIGE_WS_FC_PRESUME", "0") == "1":
            logger.info(
                f"[Feige] WS first-contact raw send PRESUMED (unconfirmed; presume opt-in) "
                f"cust={cust!r} len={len(text)}")
            return True
        logger.info(
            f"[Feige] WS send fallback reason=FC-UNCONFIRMED (first-contact raw not echoed in 3s — "
            f"ws137: NOT presuming, fc does not reliably deliver) cust={cust!r} "
            f"len={len(text)} -> DOM/retry")
        return False
    ok = await _wss.wait_confirmed(cid, 8.0)
    # ws066: per-frame raw-send staleness diagnostic. For the forced-reconnect experiment, log
    # each RAW send's confirm result alongside the raw socket's token age + whether the page
    # rotated its token since capture — so an UNCONFIRMED raw send can be correlated with a
    # stale token (the dead-end-vs-fixable question). Gated ECAN_FEIGE_WS_RAW_DIAG=1.
    if _raw_sent:
        try:
            from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
                ws_raw_sender as _wsr_diag,
            )
            # ws080: ALWAYS log the raw confirm result + token_age whenever raw sent (cheap, no
            # CDP eval). UNCONFIRMED == the server's echo never reached the page socket == the
            # core raw-viability signal, so it must be visible on every raw run, not just under
            # RAW_DIAG. The HEAVY page_token_changed (a live-url CDP read) stays gated on RAW_DIAG.
            # ws176: the HEAVY diag (a live-url CDP read on the contended main
            # tab) exists to explain UNCONFIRMED sends — running it on CONFIRMED
            # ones added ~14s to the delivery critical path under burst (live
            # 2026-07-13 18:10:39.6 confirm -> 18:10:53.998 DELIVERED, the whole
            # gap inside diag_token_status with page_token_changed=None = the
            # read itself timed out) — while the typing lock was held. Confirmed
            # sends now take the cheap branch (token_age only, no CDP).
            if os.environ.get("ECAN_FEIGE_WS_RAW_DIAG", "") == "1" and not ok:
                _st = await _wsr_diag.diag_token_status()
                logger.info(
                    f"[FEIGE-WS-RAW-DIAG] result={'CONFIRMED' if ok else 'UNCONFIRMED'} "
                    f"cust={cust!r} token_age={_st.get('age_s')}s "
                    f"page_token_changed={_st.get('page_token_changed')} "
                    f"cached=...{_st.get('cached_tail')} live=...{_st.get('live_tail')}")
            else:
                logger.info(
                    f"[FEIGE-WS-RAW-DIAG] result={'CONFIRMED' if ok else 'UNCONFIRMED'} "
                    f"cust={cust!r} token_age={_wsr_diag.token_age()}s")
            # ws067 backstop: an UNCONFIRMED raw send may be a stale token the proactive live-url
            # check missed → force a re-capture + reconnect on the next send.
            if (not ok) and os.environ.get("ECAN_FEIGE_WS_RAW_RESYNC", "1") != "0":
                _wsr_diag.invalidate()
        except Exception as _dge:
            logger.debug(f"[FEIGE-WS-RAW-DIAG/RESYNC] failed: {_dge}")
    if ok:
        logger.info(f"[Feige] WS off-DOM send DELIVERED via {_via or 'wire'} cust={cust!r} len={len(text)}")
        return True
    # ws030 (Fix B): the inject reported SENT — the frame is on the wire via the
    # customer's AUTHED page socket — but the server echo didn't return within the
    # confirm window. Under renderer/network congestion the echo is just slow; the
    # frame almost always delivered. The OLD behavior returned False, so the caller
    # DOM-resends the SAME text → the customer sees it TWICE (live 陆地飞鱼 10:02:37:
    # WS sent, then a DOM resend of the same reply). Presume delivered: do NOT
    # resend. Scoped to the page-socket inject only (NOT the raw path, ws018, which
    # the server may accept-but-ignore). Same tradeoff as ws024 (a slow-confirm dup
    # is worse than a rare drop the customer re-asks). Bonus: also skips the 50KB DOM
    # fallback, cutting renderer load. Kill-switch:
    # ECAN_FEIGE_WS_PRESUME_SENT_ON_UNCONFIRMED=0.
    if (_inject_via_page_socket
            and os.environ.get("ECAN_FEIGE_WS_PRESUME_SENT_ON_UNCONFIRMED", "1") != "0"):
        logger.info(
            f"[Feige] WS off-DOM send UNCONFIRMED but inject was SENT — presuming "
            f"delivered, NOT DOM-resending (avoids duplicate) cust={cust!r} len={len(text)}")
        return True
    logger.info(
        f"[Feige] WS send fallback reason=UNCONFIRMED (inject SENT, echo not confirmed, presume "
        f"OFF or not page-socket) cust={cust!r} len={len(text)} -> DOM")
    return False


async def _feige_ws_try_send(params: "FeigeSendMessageAction", browser_session: "BrowserSession") -> bool:
    """S1 thin wrapper: feige_send_message's WS branch -> shared off-DOM core."""
    return await feige_ws_send_text(
        getattr(params, "customer_name", ""), getattr(params, "text", ""), browser_session)


@custom_controller.action(
    "Type and send a message in the currently open Feige (飞鸽) chat thread.",
    param_model=FeigeSendMessageAction,
)
async def feige_send_message(params: FeigeSendMessageAction, browser_session: BrowserSession) -> ActionResult:
    # HumanMode: drop this reply if a competing bot (智能客服/机器人) already answered
    # this customer's current turn. Covers BOTH the 过渡句 placeholder and the final
    # response (both route through here). The configured ack smiley is exempt so the
    # 人工 short-circuit still sends. No-op unless ECAN_FEIGE_HUMAN_MODE=1.
    try:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
            human_mode as _hm,
        )
        if _hm.enabled():
            _hm_cust = str(getattr(params, "customer_name", "") or "").strip()
            _hm_text = str(getattr(params, "text", "") or "")
            if _hm_cust and _hm.is_suppressed(_hm_cust) and not _hm.is_ack_text(_hm_text):
                logger.info(
                    f"[HumanMode] suppress reply to {_hm_cust!r} — competing bot already "
                    f"answered this turn; dropping text={_hm_text[:60]!r}")
                return ActionResult(extracted_content="suppressed_competing_answer")
    except Exception as _hm_e:
        logger.debug(f"[HumanMode] suppression check error (non-fatal): {_hm_e}")
    # ws060 (Option A — card-identity delivery): a name-less product card is dispatched under
    # a synthetic 'card:<talk_id>' identity (the WS card frame carries no nickname). Delivery
    # by that name fails — no sidebar row is named 'card:<talk_id>', so the DOM
    # feige_open_session returns "Session not found", and the WS send can't route a name that
    # was never registered in _routing. The talk_id is embedded in the name and is
    # AUTHORITATIVE (it survives even when item.talk_id is dropped somewhere in the pipeline,
    # which is why the enrich de-synthesis kept returning '' — live 2026-06-14 packet's
    # 男童短袖球服 card). Resolve it to the real customer via name_for_talk so BOTH transports
    # key on the real sidebar conversation. (For a TRUE lone card where no named frame ever
    # arrived, name_for_talk is empty and we keep the synthetic name; ws_session.frame_for then
    # routes the WS send by talk_id directly — requires ECAN_FEIGE_WS_FIRST_CONTACT=1.)
    try:
        _snd_name = str(getattr(params, "customer_name", "") or "")
        if _snd_name.startswith("card:"):
            from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
                ws_session as _wss_desyn,
            )
            _snd_talk = _snd_name[len("card:"):].strip()
            _snd_real = str(_wss_desyn.name_for_talk(_snd_talk) or "").strip()
            # ws141: bounded name-resolving wait for a nameless cold-start card. It can't
            # DOM-deliver (no sidebar row named 'card:<talk>'); its real nickname resolves LATE
            # via the WS uid->name bridge (on the next named frame for that uid). ws127 fail-fast
            # then DROPPED it, so it only delivered when the customer sent ANOTHER message (talk
            # 209615 live: card at 13:46 delivered only at 13:48 after a follow-up text). Instead,
            # wait up to ~15s (NO typing lock held here — this is before the lock acquire, so no
            # storm) re-checking the AUTHORITATIVE WS bridge (talk_id->name, never a guess), then
            # deliver under the resolved name via the normal nickname DOM open. Skipped for the
            # placeholder (must stay fast). Gated ECAN_FEIGE_CARD_RESOLVE_WAIT=1 (default on).
            _snd_text = str(getattr(params, "text", "") or "")
            if ((not _snd_real or _snd_real.startswith("card:"))
                    and "正在回复中" not in _snd_text
                    and os.environ.get("ECAN_FEIGE_CARD_RESOLVE_WAIT", "1") != "0"):
                # Keep total wait WELL under DIRECT_FEIGE_JOB_TIMEOUT_S (default 15s here) so the
                # job doesn't time out mid-wait and presume-drop: 4 x 2.0s = 8s, leaving room for
                # the WS/DOM send. Catches the common "resolves within seconds" case; a name that
                # only arrives minutes later (pure card, late follow-up) still falls through.
                _cw_max = int(os.getenv("ECAN_FEIGE_CARD_RESOLVE_WAIT_TRIES", "4") or 4)
                _cw_i = 0
                while _cw_i < _cw_max:
                    await asyncio.sleep(2.0)
                    _cw_i += 1
                    _snd_real = str(_wss_desyn.name_for_talk(_snd_talk) or "").strip()
                    if _snd_real and not _snd_real.startswith("card:"):
                        break
                logger.info(
                    f"[Feige] ws141 card-resolve-wait cust={_snd_name!r} -> "
                    f"{(_snd_real or '(unresolved)')!r} (talk={_snd_talk}) after {_cw_i} tries")
            if _snd_real and not _snd_real.startswith("card:"):
                logger.info(
                    f"[Feige] ws060 card-identity de-synthesized {_snd_name!r} -> "
                    f"{_snd_real!r} (talk={_snd_talk}) for delivery")
                params.customer_name = _snd_real
    except Exception as _desyn_e:
        logger.debug(f"[Feige] card de-synthesis skipped (non-fatal): {_desyn_e}")
    # feige_ws S1: off-DOM WS send FIRST (ECAN_FEIGE_WS_SEND=1, or the S4 master
    # ECAN_FEIGE_WS=1). When the socket delivery is confirmed by the server echo, skip
    # ALL the DOM/typing-lock machinery below (the serial bottleneck behind ws002
    # storms/delays). Else fall through to DOM — which is now the fallback path.
    if os.environ.get("ECAN_FEIGE_WS_SEND", "") == "1" or os.environ.get("ECAN_FEIGE_WS", "") == "1":
        try:
            if await _feige_ws_try_send(params, browser_session):
                return ActionResult(extracted_content="ws_delivered")
            logger.info(
                f"[Feige] WS send unconfirmed/unavailable for "
                f"cust={str(getattr(params, 'customer_name', '') or '')!r} — DOM fallback")
        except Exception as _ws_err:
            logger.debug(f"[Feige] WS send branch error (fallback to DOM): {_ws_err}")
    # Process-global typing-lock serialization (added 2026-04-30 21:00).
    # Concurrent feige_send_message calls from different callers (Q&A
    # workers, direct-delivery, HOT-PATH-B) all run JS through Chrome's
    # single-threaded renderer.  When two sends overlap the renderer
    # saturates and unrelated CDP Runtime.evaluate calls (e.g. PreDispatch
    # sidebar-click scrapes) timeout at 6s.  The process-wide typing_lock
    # module already exists for the cross-customer race guard; acquire it
    # here so all callers serialize regardless of whether they remembered
    # to lock at their level.  Re-entrant for same key, so callers that
    # already hold it (HOT-PATH-B / direct-delivery) pass straight through.
    # The finally: block below calls release(_send_lock_key) when this
    # function acquired the lock itself.
    try:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
            typing_lock as _send_typing_lock,
        )
    except Exception:
        _send_typing_lock = None
    _send_lock_key = str(getattr(params, "customer_name", "") or "").strip()
    _send_acquired = False
    _send_has_lock = False
    _feige_ledger = None
    # Phase 3.5 hotfix (2026-05-21): when the customer is being routed
    # to a pool typing tab, skip the GLOBAL typing-lock acquisition.
    # The pool's ``in_use`` flag already serializes within each tab
    # (one customer per tab at a time), and the per-tab CDP session is
    # independent of the monitor tab's CDP session, so the global lock
    # only causes false serialization across customers that should be
    # parallel.  Live data 2026-05-20 16:35 showed 6 concurrent
    # pool-routed sends queueing on this global lock for 10s each, then
    # racing into CDP and timing out at 30s.
    _send_use_pool_route = False
    if _send_lock_key:
        try:
            from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
                tab_pool as _send_tab_pool,
            )
            if _send_tab_pool.get_pool().get_typing_tab_for_customer(_send_lock_key):
                _send_use_pool_route = True
        except Exception:
            pass
    if _send_use_pool_route:
        logger.debug(
            f"[Feige] feige_send_message: skipping global typing-lock for "
            f"cust={_send_lock_key!r} (pool tab is the per-tab exclusion)"
        )
    elif _send_typing_lock is not None and _send_lock_key:
        import asyncio as _send_asyncio
        try:
            _already_holding = _send_typing_lock.holder() == _send_lock_key
        except Exception:
            _already_holding = False
        # Poll up to 10s for the lock; the Feige typing-lock TTL self-heals
        # stale holders after the guarded send timeout window.
        for _send_attempt in range(100):
            if _send_typing_lock.try_acquire(_send_lock_key):
                _send_has_lock = True
                _send_acquired = not _already_holding
                break
            await _send_asyncio.sleep(0.1)
        if not _send_has_lock:
            logger.warning(
                f"[Feige] feige_send_message: typing-lock contention persisted "
                f"10s for {_send_lock_key!r} (current holder={_send_typing_lock.holder()!r}); "
                f"proceeding without lock"
            )
    try:
        expected_customer = str(params.customer_name or "").strip()
        try:
            from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.trace_ledger import (
                log_event as _feige_ledger,
            )
        except Exception:
            _feige_ledger = None
        if _feige_ledger is not None:
            _feige_ledger(
                "feige_send_tool_start",
                customer=expected_customer,
                source_msg_id=str(getattr(params, "source_customer_msg_id", "") or "").strip(),
                latest_preview=str(getattr(params, "source_latest_message", "") or "").strip(),
                response_preview=str(getattr(params, "text", "") or ""),
                response_len=len(str(getattr(params, "text", "") or "")),
            )
        # ── CDP cooldown: wait, don't fail-fast ──
        # When a prior send triggered the 4 s shared CDP-health cooldown,
        # earlier behaviour was to return tool_failed immediately.  Under
        # a 20-customer flood this turned a single CDP timeout (e.g. 客户
        # 04 at 16:48:50) into 5+ collateral failures (客户12/06/17/19/02
        # all `cdp_timeout_cooldown_active`) — the cooldown's purpose is
        # to let CDP recover, not to drop replies that are already in
        # flight.  Now we await the cooldown (capped by
        # ``_FEIGE_SEND_CDP_COOLDOWN_WAIT_CAP_S`` so a runaway cooldown
        # can't stall a turn forever) and then proceed with the send.
        # If the cooldown extends *past* the cap (which would only
        # happen if another concurrent failure re-armed it while we
        # waited), we fall back to the original fail-fast path so the
        # caller can re-queue rather than block the worker indefinitely.
        cooldown_remaining = max(
            _live_chat_send_cdp_timeout_remaining(),
            live_chat_cdp_health_cooldown_remaining(),
        )
        if cooldown_remaining > 0.0:
            try:
                _wait_cap = float(os.getenv(
                    "ECAN_FEIGE_SEND_CDP_COOLDOWN_WAIT_CAP_S", "8.0",
                ))
            except (TypeError, ValueError):
                _wait_cap = 8.0
            _wait_cap = max(0.0, _wait_cap)
            if cooldown_remaining <= _wait_cap:
                wait_s = cooldown_remaining + 0.1
                logger.info(
                    f"[Feige] feige_send_message: CDP cooldown active "
                    f"{cooldown_remaining:.1f}s; waiting then proceeding "
                    f"for {expected_customer!r} (cap={_wait_cap:.1f}s)"
                )
                if _feige_ledger is not None:
                    _feige_ledger(
                        "feige_send_tool_cdp_cooldown_wait",
                        customer=expected_customer,
                        source_msg_id=str(getattr(params, "source_customer_msg_id", "") or "").strip(),
                        latest_preview=str(getattr(params, "source_latest_message", "") or "").strip(),
                        response_preview=str(getattr(params, "text", "") or ""),
                        cooldown_remaining_s=round(cooldown_remaining, 3),
                        wait_s=round(wait_s, 3),
                    )
                try:
                    await asyncio.sleep(wait_s)
                except Exception:
                    # If the wait is cancelled mid-sleep, fall through —
                    # the re-check below will short-circuit if the
                    # cooldown is still active.
                    pass
                # Re-check after the wait — a concurrent failure may
                # have re-armed the cooldown while we slept.
                cooldown_remaining = max(
                    _live_chat_send_cdp_timeout_remaining(),
                    live_chat_cdp_health_cooldown_remaining(),
                )
            if cooldown_remaining > 0.0:
                logger.warning(
                    f"[Feige] feige_send_message: CDP cooldown still "
                    f"active for {cooldown_remaining:.1f}s after wait; "
                    f"skipping send for {expected_customer!r} (caller "
                    f"can re-queue)"
                )
                if _feige_ledger is not None:
                    _feige_ledger(
                        "feige_send_tool_cdp_cooldown_bypass",
                        customer=expected_customer,
                        source_msg_id=str(getattr(params, "source_customer_msg_id", "") or "").strip(),
                        latest_preview=str(getattr(params, "source_latest_message", "") or "").strip(),
                        response_preview=str(getattr(params, "text", "") or ""),
                        cooldown_remaining_s=round(cooldown_remaining, 3),
                    )
                return ActionResult(
                    error=(
                        "feige_send_message: cdp_timeout_cooldown_active "
                        f"{cooldown_remaining:.1f}s"
                    )
                )
        # ws173: mis-delivery guard for the ws091 card-row fallback. For a
        # card:<talk> target the send JS falls back to "the UNIQUE [商品]needReply
        # sidebar row" — a guess by CARD-NESS, not by conversation identity (rows
        # carry no conv id, ws038 probe confirmed). With TWO unnamed card
        # conversations in flight the "unique" row can belong to the OTHER one:
        # live 2026-07-12 21:49:42, 肽斯特's card-ack was typed into 陆地飞鱼's
        # thread (FEIGE-CARD-DIAG header=陆地飞鱼) after a second card arrived at
        # 21:49:37. The guess is only safe 1:1 — allow the DOM fallback ONLY when
        # the WS-side population of fresh unnamed card conversations is exactly
        # {this talk}. Otherwise fail honestly (the ws169 chain parks the reply;
        # ws170/171 flush it if the conv ever gains a name). No reply beats a
        # wrong-customer reply. Reversible: ECAN_FEIGE_CARD_ROW_AMBIGUITY_GUARD=0.
        if (
            expected_customer.startswith("card:")
            and os.getenv("ECAN_FEIGE_CARD_ROW_AMBIGUITY_GUARD", "1") != "0"
        ):
            _ws173_talk = expected_customer[len("card:"):].strip()
            _ws173_pop = None
            try:
                from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.ws_session import (
                    unnamed_card_talks as _ws173_unnamed,
                )
                _ws173_pop = set(_ws173_unnamed())
            except Exception:
                _ws173_pop = None
            if _ws173_pop is not None and _ws173_pop != {_ws173_talk}:
                logger.warning(
                    f"[Feige] ws173 card-row fallback REFUSED for "
                    f"{expected_customer!r}: unnamed card convs in flight = "
                    f"{sorted(_ws173_pop)[:4]} (need exactly this talk) — the "
                    f"unique-card-row guess is not 1:1; failing honestly so the "
                    f"reply parks instead of typing into another customer's thread"
                )
                if _feige_ledger is not None:
                    _feige_ledger(
                        "feige_send_card_row_ambiguous",
                        customer=expected_customer,
                        unnamed_card_talks=len(_ws173_pop),
                    )
                return ActionResult(
                    error="feige_send_message: card_row_ambiguous (ws173)"
                )
        # JSON-encode the text so any quotes/newlines are safe inside the JS string
        text_json = json.dumps(params.text, ensure_ascii=False)
        expected_json = json.dumps(expected_customer, ensure_ascii=False)
        source_msg_id = str(getattr(params, "source_customer_msg_id", "") or "").strip()
        source_text = str(getattr(params, "source_latest_message", "") or "").strip()
        source_msg_id_json = json.dumps(source_msg_id, ensure_ascii=False)
        source_text_json = json.dumps(source_text, ensure_ascii=False)
        # 2026-05-23 mt034: ``bypass_older_bubble_match`` toggles the
        # time-gap stale relaxation.  False on the first attempt → strict
        # source guard.  Set True only on the retry after Python has
        # confirmed the gap between target and latest customer bubbles
        # is within ECAN_FEIGE_STALE_GAP_S (default 300s).  See the
        # _retry_after_older_bubble_match branch below.
        bypass_older_bubble_match = bool(
            getattr(params, "_mt034_bypass_older_bubble_match", False)
        )
        bypass_json = json.dumps(bypass_older_bubble_match, ensure_ascii=False)
        # ws126: when the dispatch carried NO authoritative source msg_id
        # (card / '[商品]' sidebar-preview turn), the JS source-guard cannot
        # verify staleness by msg_id and the synthesized card text never
        # matches a bubble → it drops the reply as ``no_match`` (false pos).
        # Allow the send in that specific case (right conversation already
        # verified). Reversible: ECAN_FEIGE_NOMSGID_SOURCEGUARD_RELAX=0.
        allow_nomsgid_send = os.environ.get(
            "ECAN_FEIGE_NOMSGID_SOURCEGUARD_RELAX", "1"
        ) != "0"
        allow_nomsgid_json = json.dumps(allow_nomsgid_send, ensure_ascii=False)
        # ws143: accept a same-question re-scrape (shifted msg_id + added framing words) as
        # a match on the NEWEST bubble, so the stale-guard doesn't false-drop a valid answer
        # (live 肽斯特 15:38: '会不会褪色…' answer stale-dropped vs '穿久了会不会褪色…啊').
        # Reversible: ECAN_FEIGE_STALE_SIMILAR_MATCH=0.
        allow_similar_source = os.environ.get(
            "ECAN_FEIGE_STALE_SIMILAR_MATCH", "1"
        ) != "0"
        allow_similar_json = json.dumps(allow_similar_source, ensure_ascii=False)
        js = (
            _FEIGE_SEND_MESSAGE_JS
            .replace("MESSAGE_TEXT", text_json)
            .replace("EXPECTED_CUSTOMER", expected_json)
            .replace("EXPECTED_SOURCE_MSG_ID", source_msg_id_json)
            .replace("EXPECTED_SOURCE_TEXT", source_text_json)
            .replace("BYPASS_OLDER_BUBBLE_MATCH", bypass_json)
            .replace("ALLOW_NOMSGID_SEND", allow_nomsgid_json)
            .replace("ALLOW_SIMILAR_SOURCE", allow_similar_json)
        )
        target_id = await _resolve_live_chat_tab_target_id_bounded(
            browser_session,
            # Phase 1 multi-tab plumbing: pass customer name so Phase 3's
            # typing-tab routing picks the right tab.  ``expected_customer``
            # was computed earlier in this function from
            # params.customer_name / params.customer_id.
            customer_key=str(expected_customer or ""),
        )
        if target_id:
            data = await _evaluate_js(
                browser_session,
                js,
                target_id=target_id,
                focus=False,
                trace_label="feige_send_message",
                trace_fields={
                    "customer": expected_customer,
                    "source_msg_id": source_msg_id,
                    "latest_preview": source_text,
                    "response_len": len(str(getattr(params, "text", "") or "")),
                },
                timeout_s=_LIVE_CHAT_SEND_CDP_EVALUATE_TIMEOUT_S,
            )
        else:
            logger.warning(
                "[Feige] feige_send_message: no Feige target id resolved; "
                "falling back to focused tab evaluation"
            )
            data = await _evaluate_js(
                browser_session,
                js,
                trace_label="feige_send_message",
                trace_fields={
                    "customer": expected_customer,
                    "source_msg_id": source_msg_id,
                    "latest_preview": source_text,
                    "response_len": len(str(getattr(params, "text", "") or "")),
                    "fallback_target": True,
                },
                timeout_s=_LIVE_CHAT_SEND_CDP_EVALUATE_TIMEOUT_S,
            )
        if isinstance(data, str):
            data = json.loads(data)
        # ws012: cold-start render-race self-heal. The send JS scans the sidebar for
        # the customer's row; if the conversation list hasn't painted yet
        # (current_visible==0 → "Session not found") the row is NOT missing, it just
        # isn't rendered yet. Seen live 2026-06-06 15:38: the first reply landed
        # seconds after boot under the dedicated-detection-tab split (detection tab had
        # the list, the send tab E6D037 did not) → 13 "Session not found" with
        # current_visible:0, yet feige_open_session found the SAME row on the SAME tab
        # 9s later. The list populates within a few seconds, and the send JS self-opens
        # the row once it exists (executor feige_send_message_self_open), so just wait
        # briefly and re-run the send instead of stranding the reply. Bounded +
        # empty-list-only (current_visible>0 with no match is a real miss, left alone).
        # Reversible: ECAN_FEIGE_SEND_RETRY_ON_EMPTY=0.
        _empty_retries = 0
        try:
            # ~10s budget: in the 15:38 trace the send tab's list took ~9s to paint
            # (open_session found the row 9s after the first failed send).
            _empty_max = int(os.environ.get("ECAN_FEIGE_SEND_RETRY_ON_EMPTY_MAX", "5") or 5)
            _empty_wait = float(os.environ.get("ECAN_FEIGE_SEND_RETRY_ON_EMPTY_WAIT_S", "2.0") or 2.0)
        except (TypeError, ValueError):
            _empty_max, _empty_wait = 5, 2.0
        # ws091: ws012 only retried the FULLY-empty sidebar (current_visible==0). But a
        # cold-start name-less product card strands with current_visible>0 once ANY other
        # row has painted (ws090: current_visible==1, only 'packet' in the 待回复 box; the
        # card hadn't rendered yet, or rendered in the recent box). The card conv IS coming
        # (WS detected it), and reply #1 has no template so it MUST go via DOM — so retry
        # for 'card:' targets regardless of current_visible, same bounded budget. Once the
        # row paints, the widened card-row fallback above (full-sidebar [商品]needReply scan)
        # finds it and the send self-opens it. Then the template seeds and #2+ go raw.
        _is_card_target = str(expected_customer or "").startswith("card:")
        # ws170: with the undeliverable parking lot in place, a long row-wait for a
        # card:<talk> target is wasted lock-held time — if the row hasn't painted
        # within ~2 retries it usually WON'T until the conversation gains a name,
        # and the parked reply is flushed then anyway. Each retry cycle holds the
        # global typing lock, deferring every other customer's turn (the 1-vs-N
        # contention the ws169 honest-retry chain amplifies), so fail fast to the
        # park instead. Real-name/empty-sidebar targets keep the full budget.
        if _is_card_target:
            try:
                _empty_max = min(_empty_max, int(
                    os.environ.get("ECAN_FEIGE_SEND_CARD_ROW_RETRY_MAX", "2") or 2
                ))
            except (TypeError, ValueError):
                _empty_max = min(_empty_max, 2)
        while (
            os.environ.get("ECAN_FEIGE_SEND_RETRY_ON_EMPTY", "1") != "0"
            and target_id
            and isinstance(data, dict)
            and not data.get("sent")
            and (int(data.get("current_visible") or 0) == 0 or _is_card_target)
            and "Session not found" in str(data.get("error") or "")
            and _empty_retries < _empty_max
        ):
            _empty_retries += 1
            logger.info(
                f"[Feige] feige_send_message: target row not rendered yet "
                f"(current_visible={int(data.get('current_visible') or 0)}, "
                f"card={_is_card_target}) for {expected_customer!r} — waiting "
                f"{_empty_wait:.1f}s for the list, retry send {_empty_retries}/{_empty_max}"
            )
            # ws192: dump the page fingerprint on the FIRST empty retry — an outer
            # caller timeout (placeholder_timer's 8s CDP-invoke cap) can cancel this
            # coroutine mid-loop, so the post-loop [FEIGE-SIDEBAR-PROBE] never ran
            # in the 95v run. Logging here guarantees one probe per failed send.
            if _empty_retries == 1 and isinstance(data.get("page_probe"), dict):
                try:
                    logger.warning(
                        f"[FEIGE-SIDEBAR-PROBE] cust={expected_customer!r} "
                        f"probe={json.dumps(data.get('page_probe'), ensure_ascii=False)}"
                    )
                except Exception:
                    pass
            await asyncio.sleep(_empty_wait)
            data = await _evaluate_js(
                browser_session,
                js,
                target_id=target_id,
                focus=False,
                trace_label="feige_send_message",
                trace_fields={
                    "customer": expected_customer,
                    "source_msg_id": source_msg_id,
                    "latest_preview": source_text,
                    "response_len": len(str(getattr(params, "text", "") or "")),
                    "empty_sidebar_retry": _empty_retries,
                },
                timeout_s=_LIVE_CHAT_SEND_CDP_EVALUATE_TIMEOUT_S,
            )
            if isinstance(data, str):
                data = json.loads(data)
        page_timing_fields = _live_chat_send_page_timing_fields(data)
        # ws038 diagnostic: on a name-match miss, dump every conversation row's
        # id-candidate attributes UNTRUNCATED so we can search the next run for the
        # talk_id and decide whether delivery-by-conv is even possible.
        if (
            isinstance(data, dict)
            and not data.get("sent")
            and "Session not found" in str(data.get("error") or "")
        ):
            try:
                logger.warning(
                    f"[FEIGE-SIDEBAR-PROBE] expected_cust={expected_customer!r} "
                    f"source_msg_id={source_msg_id!r} "
                    f"rows={json.dumps(data.get('seen_rows') or [], ensure_ascii=False)} "
                    f"probe={json.dumps(data.get('page_probe') or {}, ensure_ascii=False)}"
                )
            except Exception:
                pass
        # ws040c: untruncated card-path state dump (success OR failure) so any
        # residual card delivery issue is fully visible in a single run.
        if isinstance(data, dict) and data.get("card_diag"):
            try:
                logger.warning(
                    f"[FEIGE-CARD-DIAG] cust={expected_customer!r} sent={data.get('sent')} "
                    f"phase={data.get('page_phase')!r} err={data.get('error')!r} "
                    f"diag={json.dumps(data.get('card_diag'), ensure_ascii=False)}"
                )
            except Exception:
                pass
        if isinstance(data, dict) and data.get("sent"):
            method = data.get("method", "unknown")
            verified = data.get("verified", "unknown")
            logger.info(
                f"[Feige] Sent message via {method}/{verified}: {params.text[:60]}"
            )
            # Grep-friendly success marker — search [FEIGE-SEND-OUTCOME]
            # to see every send's verified outcome (success or otherwise)
            logger.info(
                f"[FEIGE-SEND-OUTCOME] cust={expected_customer!r} "
                f"verified={verified!r} STRONG OK"
            )
            # 2026-05-22 mt024: register the verified bubble's data-id
            # as "ours" so future mt017 thread-scrape detections don't
            # mark this customer as human-handled when our typed bubble
            # is the latest visible agent bubble after the recent-reply
            # text ledger has TTL-aged out.  Live trace 08:19:40 packet
            # / 08:19:41 肽斯特 — both real replies dropped because the
            # 90 s ledger had expired on their earlier placeholders.
            _verified_msg_id = str(data.get("verified_msg_id") or "").strip()
            _verified_text = str(getattr(params, "text", "") or "").strip()
            if _verified_msg_id or _verified_text:
                try:
                    from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
                        human_intervention as _hi_record,
                    )
                    if _verified_msg_id:
                        _hi_record.record_typed_msg_id(
                            expected_customer, _verified_msg_id,
                        )
                    # 2026-05-23 mt028: also register the TEXT in the
                    # no-TTL typed-text set so the front-desk's text-
                    # based supersede / dom-echo guards recognise this
                    # bubble as ours even after the 90 s recent-reply
                    # ledger has aged it out OR the process restarted.
                    if _verified_text:
                        _hi_record.record_typed_text(
                            expected_customer, _verified_text,
                        )
                except Exception:
                    pass
            if _feige_ledger is not None:
                _feige_ledger(
                    "feige_send_tool_success",
                    customer=expected_customer,
                    source_msg_id=source_msg_id,
                    latest_preview=source_text,
                    response_preview=str(getattr(params, "text", "") or ""),
                    method=str(method),
                    verified=str(verified),
                    **page_timing_fields,
                )
            _record_live_chat_send_cdp_success()
            try:
                from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.delivery_durability import clear_pending_delivery
                clear_pending_delivery(
                    {
                        "customer_name": expected_customer,
                        "customer_id": expected_customer,
                        "response_text": str(getattr(params, "text", "") or ""),
                        "source_customer_msg_id": source_msg_id,
                    }
                )
            except Exception:
                pass
            return ActionResult(
                extracted_content=f"Message sent (method: {method}, verified: {verified})."
            )
        err = data.get("error") if isinstance(data, dict) else str(data)
        verified = (data.get("verified") if isinstance(data, dict) else "") or ""
        # 2026-05-20: distinguish hard failure from "soft" (unverified /
        # mis-delivered) outcomes so the caller can decide retry policy
        # and ops can grep them apart from real catastrophes.
        unverified_outcome = verified in (
            "input_cleared_no_bubble",
            "mis_delivered_to_wrong_chat",
        )
        if not err and unverified_outcome:
            err = f"feige_send_unverified:{verified}"
        if "stale_reply_source_msg_id" in str(err):
            # 2026-05-23 mt034: time-gap stale relaxation.  If the only
            # reason for rejection is that an OLDER customer bubble
            # matched (i.e. the customer added a new question before we
            # could reply), AND the gap between that older bubble and
            # the current latest is within STALE_GAP_S (default 300),
            # retry the send once with bypass_older_bubble_match=True
            # so Q1's answer doesn't get silently dropped.  Live trace
            # 2026-05-23 16:26:16 肽斯特 "能不能包邮，能发顺丰吗" → bot
            # answer discarded at 16:27:29 because 肽斯特 typed Q2
            # "110cm衣服尺码" at 16:27:13 (74s gap, well under 5min).
            if (
                isinstance(data, dict)
                and data.get("stale_reason") == "older_bubble_match"
                and not bypass_older_bubble_match  # don't infinite-retry
            ):
                latest_msg_id = str(data.get("active_source_msg_id") or "").strip()
                if (
                    source_msg_id
                    and latest_msg_id
                    and source_msg_id != latest_msg_id
                ):
                    try:
                        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
                            placeholder_timer as _mt034_pt,
                        )
                        _target_ts = _mt034_pt.get_message_first_seen(
                            str(expected_customer), source_msg_id,
                        )
                        _latest_ts = _mt034_pt.get_message_first_seen(
                            str(expected_customer), latest_msg_id,
                        )
                        if _target_ts > 0 and _latest_ts > _target_ts:
                            _gap_s = _latest_ts - _target_ts
                            try:
                                _stale_gap_s = float(
                                    os.environ.get("ECAN_FEIGE_STALE_GAP_S", "300") or 300
                                )
                            except Exception:
                                _stale_gap_s = 300.0
                            if 0 < _gap_s <= _stale_gap_s:
                                logger.info(
                                    f"[Feige] mt034: relaxing stale guard, "
                                    f"gap={_gap_s:.1f}s <= {_stale_gap_s:.0f}s "
                                    f"cust={expected_customer!r} "
                                    f"target=...{source_msg_id[-8:]} "
                                    f"latest=...{latest_msg_id[-8:]}"
                                )
                                if _feige_ledger is not None:
                                    _feige_ledger(
                                        "feige_send_mt034_stale_relaxed",
                                        customer=expected_customer,
                                        source_msg_id=source_msg_id,
                                        latest_msg_id=latest_msg_id,
                                        gap_s=round(_gap_s, 1),
                                        stale_gap_s=_stale_gap_s,
                                    )
                                # Flip the bypass flag on params and retry
                                # the entire send via recursive call.  The
                                # bypass flag is read at the top of this
                                # function on the JS-string assembly step.
                                setattr(
                                    params,
                                    "_mt034_bypass_older_bubble_match",
                                    True,
                                )
                                return await feige_send_message(
                                    params, browser_session,
                                )
                    except Exception as _mt034_err:
                        logger.debug(
                            f"[Feige] mt034 time-gap check failed "
                            f"(non-fatal, will fail-stale): {_mt034_err}"
                        )
            # 2026-05-24 mt038A: re-scrape-and-retry rescue path.
            #
            # If mt034's time-gap relaxation didn't fire (or didn't
            # apply), the bot's reply is otherwise about to be dropped.
            # Before giving up, re-scrape the customer's chat thread
            # for the LATEST customer bubble (which carries a real
            # data-id), patch params.source_customer_msg_id with it,
            # and recursively retry the send ONCE.
            #
            # Live customer trace 2026-05-24 17:11:06 J14N9: the
            # original dispatch carried no source_msg_id (sidebar
            # preview was "[商品]"); JS source-guard returned
            # stale_reason='no_match' + expected_source_msg_id=''
            # → bot reply "您好，我这边暂时看不到具体商品信息..." was
            # dropped → customer permanently stranded, session
            # auto-closed at 17:25.
            #
            # mt038A rescue: re-scrape thread finds the actual text
            # bubble (e.g. "透气吗？面料舒适吗"), retry with that
            # msg_id, source-guard passes, bot's reply gets typed.
            # The bot's answer is at worst a generic clarification
            # ask — still strictly better than nothing.
            mt038a_already_retried = bool(
                getattr(params, "_mt038A_retry_attempted", False)
            )
            if not mt038a_already_retried and expected_customer:
                try:
                    from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.dom_assets import (
                        scrape_latest_customer_bubble as _mt038a_scrape,
                    )
                    _rescue = await _mt038a_scrape(
                        browser_session,
                        expected_customer,
                    )
                    _rescue_msg_id = str(_rescue.get("msg_id") or "").strip() if isinstance(_rescue, dict) else ""
                    _rescue_text = str(_rescue.get("text") or "").strip() if isinstance(_rescue, dict) else ""
                    if (
                        _rescue.get("scrape_ok")
                        and _rescue_msg_id
                        and _rescue_msg_id != source_msg_id
                    ):
                        logger.info(
                            f"[Feige] mt038A: re-scrape rescue, "
                            f"cust={expected_customer!r} "
                            f"old_src=...{(source_msg_id or '')[-8:]!r} "
                            f"new_src=...{_rescue_msg_id[-8:]!r} "
                            f"latest_text={_rescue_text[:30]!r}"
                        )
                        if _feige_ledger is not None:
                            _feige_ledger(
                                "feige_send_mt038A_rescue_retry",
                                customer=expected_customer,
                                old_source_msg_id=source_msg_id,
                                new_source_msg_id=_rescue_msg_id,
                                latest_text=_rescue_text[:120],
                            )
                        # Patch params for the retry.  Both fields are
                        # passed through to the JS source-guard.
                        try:
                            setattr(
                                params, "source_customer_msg_id", _rescue_msg_id,
                            )
                            setattr(
                                params, "source_latest_message", _rescue_text,
                            )
                        except Exception:
                            pass
                        setattr(params, "_mt038A_retry_attempted", True)
                        return await feige_send_message(
                            params, browser_session,
                        )
                except Exception as _mt038a_err:
                    logger.debug(
                        f"[Feige] mt038A re-scrape rescue failed "
                        f"(non-fatal, will fail-stale): {_mt038a_err}"
                    )
            try:
                from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.delivery_durability import clear_pending_delivery
                clear_pending_delivery(
                    {
                        "customer_name": expected_customer,
                        "customer_id": expected_customer,
                        "response_text": str(getattr(params, "text", "") or ""),
                        "source_customer_msg_id": source_msg_id,
                    }
                )
            except Exception:
                pass
            # 2026-05-22 mt023: also wipe the recent-agent-reply ledger
            # for this customer so PreDispatch's recent-echo guard
            # doesn't keep skipping the customer's new (un-answered)
            # bubble on every subsequent cycle.  Without this clear,
            # customer 陆地飞鱼 sat un-answered for 173 s on the
            # 2026-05-22 08:19-08:22 trace because the placeholder text
            # ("您好，稍等一下哦~") remained in the ledger and the
            # sidebar preview kept matching it.  Also cancel any
            # in-flight placeholder timers for this turn since the
            # underlying reply is rejected.
            try:
                from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
                    dispatch_state as _stale_ds,
                )
                _stale_ds.clear_recent_replies(expected_customer)
            except Exception:
                pass
            try:
                from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
                    placeholder_timer as _stale_pt,
                )
                _stale_pt.cancel_any_for_customer(expected_customer)
            except Exception:
                pass
        # On mis-delivery, drop the cached tab-focus so the next retry
        # re-clicks the customer's sidebar row (and re-verifies header).
        if verified == "mis_delivered_to_wrong_chat":
            try:
                from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.dom_assets import (
                    clear_feige_tab_focus_cache,
                )
                clear_feige_tab_focus_cache(
                    browser_session, "mis_delivered_to_wrong_chat"
                )
            except Exception:
                pass
        if _feige_ledger is not None:
            ledger_stage = (
                "feige_send_tool_unverified" if unverified_outcome
                else "feige_send_tool_failed"
            )
            _feige_ledger(
                ledger_stage,
                customer=expected_customer,
                source_msg_id=source_msg_id,
                latest_preview=source_text,
                response_preview=str(getattr(params, "text", "") or ""),
                verified=str(verified),
                error=str(err),
                result_preview=str(data)[:400],
                **page_timing_fields,
            )
        logger.warning(
            f"[FEIGE-SEND-OUTCOME] cust={expected_customer!r} "
            f"verified={verified!r} err={str(err)[:120]!r}"
        )
        return ActionResult(error=f"feige_send_message: {err}")
    except Exception as e:
        err_text = str(e)
        cooldown_remaining = 0.0
        if "CDP Runtime.evaluate timed out" in err_text:
            # ws011: a send-eval Runtime.evaluate timeout is RENDERER-SLOW, not a
            # transport failure — arming the 3s send cooldown just delays the next
            # send into the same busy renderer. Skip it by default (same rationale
            # and flag as the health-cooldown gate above). Reversible:
            # ECAN_FEIGE_COOLDOWN_RENDERER_SLOW_SKIP=0.
            if os.getenv("ECAN_FEIGE_COOLDOWN_RENDERER_SLOW_SKIP", "1") != "0":
                logger.warning(
                    "[Feige] feige_send_message: send-eval RENDERER-SLOW "
                    "(Runtime.evaluate timeout) — NO send cooldown armed "
                    "(renderer-slow != transport failure)"
                )
            else:
                cooldown_remaining = _record_live_chat_send_cdp_timeout()
            try:
                from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.dom_assets import (
                    clear_feige_tab_focus_cache,
                )
                clear_feige_tab_focus_cache(browser_session, "send Runtime.evaluate timeout")
            except Exception:
                pass
        logger.error(f"[Feige] feige_send_message error: {e}")
        try:
            if _feige_ledger is not None:
                _feige_ledger(
                    "feige_send_tool_exception",
                    customer=str(getattr(params, "customer_name", "") or ""),
                    source_msg_id=str(getattr(params, "source_customer_msg_id", "") or ""),
                    latest_preview=str(getattr(params, "source_latest_message", "") or ""),
                    response_preview=str(getattr(params, "text", "") or ""),
                    error=err_text,
                    cooldown_remaining_s=round(cooldown_remaining, 3),
                )
        except Exception:
            pass
        return ActionResult(error=f"feige_send_message failed: {e}")
    finally:
        if _send_acquired and _send_typing_lock is not None:
            try:
                _send_typing_lock.release(_send_lock_key)
            except Exception:
                pass
