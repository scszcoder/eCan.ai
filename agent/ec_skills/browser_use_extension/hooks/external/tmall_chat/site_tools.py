"""Tmall/Qianniu (千牛) site tools for the browser-use controller.

Phase 1 DOM-first port of ``feige_chat/site_tools.py`` (lean: no WS send
lane, no card-identity de-synthesis, no staleness guards yet).  Contains
the four controller actions (``tmall_list_sessions`` /
``tmall_open_session`` / ``tmall_get_chat_thread`` /
``tmall_send_message``), their pydantic action models, and the JS
template constants.

Importing this module registers the actions on the shared
``custom_controller`` via decorators; the bundle ``__init__`` imports it
only when this is the active live-chat site (``ECAN_LIVE_CHAT_SITE``).

Import direction: this bundle module imports the generic CDP helpers FROM
``extension_tools_service`` (business → platform is the allowed
direction).  The platform module must never import this one.

⚠️ SELECTOR STATUS: SPECULATIVE — NOT YET CALIBRATED AGAINST THE LIVE
QIANNIU WEB WORKBENCH.  Every ``_TMALL_*`` selector constant below is an
educated placeholder built from common Qianniu/Taobao IM DOM patterns.
On the first live run, follow the calibration playbook in this bundle's
README: run each tool, and where it returns empty/no-match, extract the
real DOM and pin exact selectors here (Feige's header comment in
``feige_chat/site_tools.py`` shows the end state — captured selectors
documented per element).
"""
import json
from typing import Optional

from pydantic import BaseModel, Field

from browser_use import BrowserSession
from browser_use.agent.views import ActionResult

from utils.logger_helper import logger_helper as logger

from agent.ec_skills.browser_use_extension.extension_tools_service import (
    _evaluate_live_chat_js,
    _json_result,
    custom_controller,
    live_chat_cdp_health_cooldown_remaining,
)

from . import typing_lock
from .tunables import (
    resolve_float,
    DEFAULT_TMALL_TYPING_LOCK_WAIT_S,
    DEFAULT_TMALL_SEND_CDP_EVALUATE_TIMEOUT_S,
)


# ── Action models (field-compatible with the Feige ones so prompts and
#    platform tooling transfer unchanged) ─────────────────────────────────────
class TmallListSessionsAction(BaseModel):
	"""List all visible buyer sessions from the Qianniu (千牛) session panel.
	Returns each session's customer name, last message snippet, timestamp, and unread count.
	Use this instead of generic DOM extraction when operating on Tmall customer service pages.
	"""
	include_read: bool = Field(
		default=True,
		description="Include sessions with no unread messages. Set False to return only sessions with unread messages.",
	)
	max_sessions: int = Field(
		default=50,
		description="Maximum number of sessions to return (scrolled into view).",
	)


class TmallOpenSessionAction(BaseModel):
	"""Click a buyer session in the Qianniu (千牛) session list to open the chat thread.
	Use the customer_name or session_index returned by tmall_list_sessions.
	"""
	customer_name: Optional[str] = Field(
		default=None,
		description="Customer name as returned by tmall_list_sessions. Used for matching.",
	)
	session_index: Optional[int] = Field(
		default=None,
		description="Zero-based index into the session list (fallback when customer_name is ambiguous).",
	)


class TmallGetChatThreadAction(BaseModel):
	"""Extract visible messages from the currently open Qianniu (千牛) chat thread.
	Returns a list of message objects: {sender, text, timestamp, is_agent}.
	"""
	max_messages: int = Field(
		default=30,
		description="Maximum number of messages to return (most recent).",
	)


class TmallSendMessageAction(BaseModel):
	"""Type and send a text message in the currently open Qianniu (千牛) chat thread.
	Finds the compose input, types the text, and clicks Send (or presses Enter).
	"""
	text: str = Field(
		description="Message text to send to the customer.",
	)
	customer_name: Optional[str] = Field(
		default=None,
		description="Optional expected active customer name. When provided and the open chat header is readable, the action refuses to type unless it matches.",
	)
	source_customer_msg_id: Optional[str] = Field(
		default=None,
		description="Accepted for contract compatibility; staleness guarding lands with the Phase 2 thread instrumentation.",
	)
	source_latest_message: Optional[str] = Field(
		default=None,
		description="Accepted for contract compatibility; staleness guarding lands with the Phase 2 thread instrumentation.",
	)


# ── Selector constants (SPECULATIVE — see module header) ─────────────────────
# Sidebar rows / fields:
_TMALL_ROW = ('[class*="conversation-item"], [class*="session-item"], '
              '[class*="conv-item"], li[class*="im-conversation"]')
_TMALL_ROW_NAME = '[class*="nick"], [class*="user-name"], [class*="name"]'
_TMALL_ROW_PREVIEW = '[class*="last-msg"], [class*="latest"], [class*="content"], [class*="abstract"]'
_TMALL_ROW_TIME = '[class*="time"]'
_TMALL_ROW_UNREAD = '[class*="unread"], [class*="badge"], sup'
# Thread pane:
_TMALL_MSG_ITEM = '[class*="message-item"], [class*="msg-item"], [class*="im-message"]'
_TMALL_MSG_SELF_TOKENS = "('self','me','right','mine','send')"
_TMALL_MSG_TEXT = '[class*="text"], [class*="content"], pre, p'
_TMALL_MSG_TIME = '[class*="time"]'
# Compose area:
_TMALL_INPUT = ('textarea[class*="input"], textarea[class*="editor"], '
                'div[contenteditable="true"], textarea')
_TMALL_SEND_BTN = 'button[class*="send"], div[class*="send-btn"], [class*="send-button"]'
# Chat header (active buyer nick):
_TMALL_HEADER = '[class*="chat-header"], [class*="im-header"], [class*="header-nick"]'


_TMALL_LIST_SESSIONS_JS = r"""
(function(includeRead, maxSessions) {
  var items = Array.from(document.querySelectorAll('ROW_SELECTOR'));
  var results = [];
  for (var i = 0; i < Math.min(items.length, maxSessions); i++) {
    var el = items[i];
    var nameEl = el.querySelector('ROW_NAME');
    var name = nameEl ? ((nameEl.getAttribute('title') || nameEl.textContent || '')).trim() : '';
    var prevEl = el.querySelector('ROW_PREVIEW');
    var lastMsg = prevEl ? prevEl.textContent.trim() : '';
    var tsEl = el.querySelector('ROW_TIME');
    var ts = tsEl ? tsEl.textContent.trim() : '';
    var unread = 0;
    var unreadEl = el.querySelector('ROW_UNREAD');
    if (unreadEl) {
      var raw = unreadEl.textContent.trim();
      var parsed = parseInt(raw, 10);
      if (!isNaN(parsed)) unread = parsed;
      else if (raw) unread = 1;
    }
    if (!includeRead && unread === 0) continue;
    results.push({ index: i, name: name, last_message: lastMsg, timestamp: ts, unread: unread, tags: [] });
  }
  return JSON.stringify({ sessions: results, total_visible: items.length });
})(INCLUDE_READ, MAX_SESSIONS);
"""


@custom_controller.action(
    "List visible buyer sessions in the Tmall/Qianniu (千牛) customer-service session panel.",
    param_model=TmallListSessionsAction,
)
async def tmall_list_sessions(params: TmallListSessionsAction, browser_session: BrowserSession) -> ActionResult:
    try:
        js = (_TMALL_LIST_SESSIONS_JS
              .replace("ROW_SELECTOR", _TMALL_ROW)
              .replace("ROW_NAME", _TMALL_ROW_NAME)
              .replace("ROW_PREVIEW", _TMALL_ROW_PREVIEW)
              .replace("ROW_TIME", _TMALL_ROW_TIME)
              .replace("ROW_UNREAD", _TMALL_ROW_UNREAD)
              .replace("INCLUDE_READ", "true" if params.include_read else "false")
              .replace("MAX_SESSIONS", str(params.max_sessions)))
        data = await _evaluate_live_chat_js(
            browser_session,
            js,
            trace_label="tmall_list_sessions",
            trace_fields={
                "include_read": bool(params.include_read),
                "max_sessions": int(params.max_sessions),
            },
            read_only=True,
        )
        if isinstance(data, str):
            data = json.loads(data)
        sessions = data.get("sessions", []) if isinstance(data, dict) else []
        total = data.get("total_visible", 0) if isinstance(data, dict) else 0
        logger.info(f"[Tmall] Listed sessions: visible={total}, returned={len(sessions)}")
        if total == 0:
            return ActionResult(
                extracted_content="No session rows found. The Qianniu sidebar selectors are "
                "uncalibrated — use extract_dom on the left session panel and update the "
                "_TMALL_ROW* constants in tmall_chat/site_tools.py."
            )
        return _json_result({"sessions": sessions, "total_visible": total})
    except Exception as e:
        logger.error(f"[Tmall] tmall_list_sessions error: {e}")
        return ActionResult(error=f"tmall_list_sessions failed: {e}")


_TMALL_OPEN_SESSION_JS = r"""
(function(customerName, sessionIndex) {
  // Simple synchronous click, no retry loops — Feige's "Fix 11" lesson:
  // JS-level sleep/verify/retry stacks amplify 5-10x under renderer load
  // and bust caller timeouts; misroute recovery belongs in Python.
  var items = Array.from(document.querySelectorAll('ROW_SELECTOR'));
  var target = null;
  if (customerName) {
    for (var i = 0; i < items.length; i++) {
      var nameEl = items[i].querySelector('ROW_NAME');
      var name = nameEl ? ((nameEl.getAttribute('title') || nameEl.textContent || '')).trim() : '';
      if (name === customerName) { target = items[i]; break; }
    }
  }
  if (!target && sessionIndex >= 0 && sessionIndex < items.length) {
    target = items[sessionIndex];
  }
  if (!target) return JSON.stringify({
    clicked: false,
    error: 'Session not found in session list',
    total_visible: items.length
  });
  target.click();
  var nameEl2 = target.querySelector('ROW_NAME');
  var clickedName = nameEl2 ? ((nameEl2.getAttribute('title') || nameEl2.textContent || '')).trim() : '';
  return JSON.stringify({ clicked: true, name: clickedName });
})(CUSTOMER_NAME, SESSION_INDEX);
"""


@custom_controller.action(
    "Open a buyer chat session in Tmall/Qianniu (千牛) by clicking on it in the session list.",
    param_model=TmallOpenSessionAction,
)
async def tmall_open_session(params: TmallOpenSessionAction, browser_session: BrowserSession) -> ActionResult:
    try:
        cooldown_remaining = live_chat_cdp_health_cooldown_remaining()
        if cooldown_remaining > 0.0:
            logger.warning(
                f"[Tmall] tmall_open_session: CDP health cooldown active "
                f"for {cooldown_remaining:.1f}s; skipping open for "
                f"{str(params.customer_name or '')!r}"
            )
            return ActionResult(
                error=(
                    "tmall_open_session: cdp_health_cooldown_active "
                    f"{cooldown_remaining:.1f}s"
                )
            )
        name_js = json.dumps(params.customer_name, ensure_ascii=False) if params.customer_name else "null"
        idx_js = str(params.session_index) if params.session_index is not None else "-1"
        js = (_TMALL_OPEN_SESSION_JS
              .replace("ROW_SELECTOR", _TMALL_ROW)
              .replace("ROW_NAME", _TMALL_ROW_NAME)
              .replace("CUSTOMER_NAME", name_js)
              .replace("SESSION_INDEX", idx_js))
        data = await _evaluate_live_chat_js(
            browser_session,
            js,
            trace_label="tmall_open_session",
            customer_key=str(params.customer_name or ""),
            trace_fields={
                "customer": str(params.customer_name or ""),
                "session_index": int(params.session_index) if params.session_index is not None else -1,
            },
        )
        if isinstance(data, str):
            data = json.loads(data)
        if isinstance(data, dict) and data.get("clicked"):
            logger.info(f"[Tmall] Opened session: name={data.get('name')}")
            return ActionResult(extracted_content=f"Opened session: {data.get('name', '(unknown)')}")
        err = data.get("error") if isinstance(data, dict) else str(data)
        return ActionResult(error=f"tmall_open_session: {err}")
    except Exception as e:
        logger.error(f"[Tmall] tmall_open_session error: {e}")
        return ActionResult(error=f"tmall_open_session failed: {e}")


_TMALL_GET_THREAD_JS = r"""
(function(maxMessages) {
  function isSelfMessage(el) {
    var cls = (el.className || '').toString().toLowerCase();
    var tokens = SELF_TOKENS;
    for (var t = 0; t < tokens.length; t++) {
      if (cls.indexOf(tokens[t]) !== -1) return true;
    }
    var style = window.getComputedStyle ? window.getComputedStyle(el) : null;
    if (style && (style.flexDirection || '').indexOf('reverse') !== -1) return true;
    return false;
  }
  var wrappers = Array.from(document.querySelectorAll('MSG_ITEM'));
  var results = [];
  var start = Math.max(0, wrappers.length - maxMessages);
  for (var i = start; i < wrappers.length; i++) {
    var wrap = wrappers[i];
    var textEl = wrap.querySelector('MSG_TEXT');
    var text = textEl ? textEl.textContent.trim() : wrap.textContent.trim();
    var atts = [];
    var imgs = Array.from(wrap.querySelectorAll('img'));
    for (var k = 0; k < imgs.length; k++) {
      var im = imgs[k];
      var alt = (im.getAttribute('alt') || '').trim();
      if (alt === '头像' || /avatar|head/i.test((im.className || '').toString())) continue;
      var src = im.src || im.getAttribute('src') || '';
      if (!src || src.indexOf('data:image/svg') === 0) continue;
      atts.push({ kind: 'image', url: src, alt: alt });
    }
    if (!text && atts.length === 0) continue;
    var tsEl = wrap.querySelector('MSG_TIME');
    var ts = tsEl ? tsEl.textContent.trim() : '';
    var msgIdEl = wrap.querySelector('[data-id], [data-msg-id]');
    var msgId = msgIdEl ? (msgIdEl.getAttribute('data-id') || msgIdEl.getAttribute('data-msg-id') || '') : '';
    results.push({ index: i, text: text, is_agent: isSelfMessage(wrap), is_system: false,
                   timestamp: ts, msg_id: msgId, attachments: atts });
  }
  return JSON.stringify({ messages: results, total_found: wrappers.length,
                          selector_used: wrappers.length > 0 ? 'matched' : 'none' });
})(MAX_MESSAGES);
"""


@custom_controller.action(
    "Extract visible messages from the currently open Tmall/Qianniu (千牛) chat thread.",
    param_model=TmallGetChatThreadAction,
)
async def tmall_get_chat_thread(params: TmallGetChatThreadAction, browser_session: BrowserSession) -> ActionResult:
    try:
        self_tokens_js = "[" + ",".join(
            f"'{t}'" for t in ("self", "me", "right", "mine", "send")
        ) + "]"
        js = (_TMALL_GET_THREAD_JS
              .replace("SELF_TOKENS", self_tokens_js)
              .replace("MSG_ITEM", _TMALL_MSG_ITEM)
              .replace("MSG_TEXT", _TMALL_MSG_TEXT)
              .replace("MSG_TIME", _TMALL_MSG_TIME)
              .replace("MAX_MESSAGES", str(params.max_messages)))
        data = await _evaluate_live_chat_js(
            browser_session,
            js,
            trace_label="tmall_get_chat_thread",
            trace_fields={"max_messages": int(params.max_messages)},
            read_only=True,
        )
        if isinstance(data, str):
            data = json.loads(data)
        messages = data.get("messages", []) if isinstance(data, dict) else []
        total = data.get("total_found", 0) if isinstance(data, dict) else 0
        selector_used = data.get("selector_used", "unknown") if isinstance(data, dict) else "unknown"
        logger.info(f"[Tmall] Got chat thread: total={total}, returned={len(messages)}, selector={selector_used}")
        if selector_used == "none":
            return ActionResult(
                extracted_content="No message elements found. The Qianniu thread selectors are "
                "uncalibrated — use extract_dom on the right-hand chat pane and update the "
                "_TMALL_MSG* constants in tmall_chat/site_tools.py."
            )
        return _json_result({"messages": messages, "total_found": total})
    except Exception as e:
        logger.error(f"[Tmall] tmall_get_chat_thread error: {e}")
        return ActionResult(error=f"tmall_get_chat_thread failed: {e}")


_TMALL_SEND_MESSAGE_JS = r"""
(function(text, expectedCustomer) {
  function visible(el) {
    if (!el || !el.getBoundingClientRect) return false;
    var rect = el.getBoundingClientRect();
    var style = window.getComputedStyle ? window.getComputedStyle(el) : null;
    return rect.width > 0 && rect.height > 0 &&
      (!style || (style.display !== 'none' && style.visibility !== 'hidden'));
  }
  // Light active-chat guard: only enforced when the header is readable.
  if (expectedCustomer) {
    var headerEl = document.querySelector('HEADER_SELECTOR');
    var headerText = headerEl ? headerEl.textContent.trim() : '';
    if (headerText && headerText.indexOf(expectedCustomer) === -1) {
      return JSON.stringify({ sent: false, error: 'active_chat_mismatch', header: headerText.slice(0, 60) });
    }
  }
  var input = null;
  var candidates = Array.from(document.querySelectorAll('INPUT_SELECTOR'));
  for (var i = 0; i < candidates.length; i++) {
    if (visible(candidates[i])) { input = candidates[i]; break; }
  }
  if (!input) return JSON.stringify({ sent: false, error: 'tmall_send_failed:input_not_found' });
  input.focus();
  if (input.tagName === 'TEXTAREA' || input.tagName === 'INPUT') {
    var proto = input.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
    var setter = Object.getOwnPropertyDescriptor(proto, 'value');
    if (setter && setter.set) setter.set.call(input, text);
    else input.value = text;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  } else {
    // contenteditable — replace content via insertText so framework
    // listeners observe a native-like edit.
    var sel = window.getSelection();
    var range = document.createRange();
    range.selectNodeContents(input);
    sel.removeAllRanges();
    sel.addRange(range);
    document.execCommand('insertText', false, text);
  }
  // Prefer the send button; fall back to Enter on the input.
  var sent = false, method = '';
  var btns = Array.from(document.querySelectorAll('SEND_BTN_SELECTOR'));
  var btn = null;
  for (var b = 0; b < btns.length; b++) {
    if (visible(btns[b])) { btn = btns[b]; break; }
  }
  if (!btn) {
    // Generic fallback: any visible button whose text is exactly 发送
    var allBtns = Array.from(document.querySelectorAll('button, div[role="button"]'));
    for (var a = 0; a < allBtns.length; a++) {
      if (visible(allBtns[a]) && allBtns[a].textContent.trim() === '发送') { btn = allBtns[a]; break; }
    }
  }
  if (btn) {
    btn.click();
    sent = true; method = 'button';
  } else {
    var kd = { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true };
    input.dispatchEvent(new KeyboardEvent('keydown', kd));
    input.dispatchEvent(new KeyboardEvent('keypress', kd));
    input.dispatchEvent(new KeyboardEvent('keyup', kd));
    sent = true; method = 'enter';
  }
  var remaining = ('value' in input) ? String(input.value || '') : String(input.textContent || '');
  return JSON.stringify({ sent: sent, method: method, input_cleared: remaining.trim() === '' });
})(TEXT_ARG, EXPECTED_CUSTOMER);
"""


@custom_controller.action(
    "Type and send a text message in the currently open Tmall/Qianniu (千牛) chat thread.",
    param_model=TmallSendMessageAction,
)
async def tmall_send_message(params: TmallSendMessageAction, browser_session: BrowserSession) -> ActionResult:
    owner = f"tmall_send:{params.customer_name or '?'}"
    lock_wait = resolve_float("TMALL_TYPING_LOCK_WAIT_S", DEFAULT_TMALL_TYPING_LOCK_WAIT_S, None)
    got_lock = await typing_lock.acquire(owner, timeout_s=lock_wait)
    if not got_lock:
        return ActionResult(error="tmall_send_message: typing lock busy")
    try:
        js = (_TMALL_SEND_MESSAGE_JS
              .replace("HEADER_SELECTOR", _TMALL_HEADER)
              .replace("INPUT_SELECTOR", _TMALL_INPUT)
              .replace("SEND_BTN_SELECTOR", _TMALL_SEND_BTN)
              .replace("TEXT_ARG", json.dumps(params.text, ensure_ascii=False))
              .replace("EXPECTED_CUSTOMER",
                       json.dumps(params.customer_name, ensure_ascii=False)
                       if params.customer_name else "null"))
        timeout_s = resolve_float(
            "TMALL_SEND_CDP_EVALUATE_TIMEOUT_S", DEFAULT_TMALL_SEND_CDP_EVALUATE_TIMEOUT_S, None
        )
        data = await _evaluate_live_chat_js(
            browser_session,
            js,
            trace_label="tmall_send_message",
            customer_key=str(params.customer_name or ""),
            trace_fields={
                "customer": str(params.customer_name or ""),
                "text_len": len(params.text or ""),
            },
            timeout_s=timeout_s,
        )
        if isinstance(data, str):
            data = json.loads(data)
        if isinstance(data, dict) and data.get("sent"):
            logger.info(
                f"[Tmall] Sent message: customer={params.customer_name!r} "
                f"method={data.get('method')} cleared={data.get('input_cleared')}"
            )
            return ActionResult(
                extracted_content=f"Message sent via {data.get('method', '?')}"
            )
        err = data.get("error") if isinstance(data, dict) else str(data)
        logger.warning(f"[Tmall] tmall_send_message failed: {err}")
        return ActionResult(error=f"tmall_send_message: {err}")
    except Exception as e:
        logger.error(f"[Tmall] tmall_send_message error: {e}")
        return ActionResult(error=f"tmall_send_message failed: {e}")
    finally:
        typing_lock.release(owner)
