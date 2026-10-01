"""Pinduoduo chat page (mms.pinduoduo.com/chat-merchant/): read and act through the DOM.

Selectors come from real page snapshots (2026-09-25). Every read returns plain
JSON; the one write (send) types into the reply box and clicks Send exactly as
a person would -- the HTTP send needs an anti-bot token only the page can mint.

The customer uid used here is the same one the titan WebSocket carries
(``conversation_id`` in ws_protocol), read from a row's ``data-random``
(``<uid>-0-<group>``) and from the thread's ``currentuid``.
"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable, Dict, List

CHAT_URL_MARKER = "mms.pinduoduo.com/chat-merchant"

Evaluate = Callable[[str], Awaitable[Any]]    # runs JS in the chat page, returns its value
Cdp = Callable[[str, Dict[str, Any]], Awaitable[Any]]   # sends one CDP command to the chat tab


def is_chat_url(url: str) -> bool:
    return CHAT_URL_MARKER in (url or "")


LIST_SESSIONS_JS = r"""(() => {
  const seen = new Map();
  document.querySelectorAll('.chat-item-box[data-random]').forEach(box => {
    const uid = (box.getAttribute('data-random') || '').split('-')[0];
    if (!uid || seen.has(uid)) return;
    const q = s => { const n = box.querySelector(s); return n ? n.textContent.trim() : ''; };
    seen.set(uid, {
      uid, name: q('.nickname-span'), last_message: q('.chat-message-content'),
      time: q('.item-note'), waiting: q('.chat-unreply-over-time'),
      active: box.classList.contains('active'),
      group: (box.getAttribute('data-random') || '').split('-').slice(2).join('-'),
    });
  });
  return JSON.stringify([...seen.values()]);
})()"""


def open_session_js(uid: str) -> str:
    return r"""((uid) => {
  const box = [...document.querySelectorAll('.chat-item-box[data-random]')]
    .find(b => (b.getAttribute('data-random') || '').split('-')[0] === uid && b.offsetParent !== null)
    || [...document.querySelectorAll('.chat-item-box[data-random]')]
    .find(b => (b.getAttribute('data-random') || '').split('-')[0] === uid);
  if (!box) return JSON.stringify({ok: false, error: 'no conversation row for ' + uid});
  box.click();
  return JSON.stringify({ok: true});
})(%s)""" % json.dumps(uid)


# The open conversation: whose it is, and its messages in order.
THREAD_JS = r"""(() => {
  const any = document.querySelector('#msgListContainer [currentuid]');
  const uid = any ? any.getAttribute('currentuid') : '';
  const nameEl = document.querySelector('.chatWindowHeader .base-info .name');
  const out = [];
  document.querySelectorAll('#msgListContainer li.onemsg').forEach(li => {
    const id = (li.id || '').replace('middlePanel_list_', '');
    const buyer = li.querySelector('.buyer-item'), cs = li.querySelector('.cs-item');
    const sys = li.querySelector('.msg-system, [class^="system-msg"], [class*=" system-msg"]');
    const text = n => n ? n.textContent.replace(/\s+/g, ' ').trim() : '';
    let who = buyer ? 'customer' : cs ? (cs.querySelector('.robot-text') ? 'robot' : 'agent') : sys ? 'system' : 'other';
    const box = li.querySelector('.msg-content-box');
    const card = li.querySelector('.good-card, .commonCard');
    const img = card ? null : li.querySelector('.msg-content img, .image-msg img');
    out.push({msg_id: id, who, text: box ? text(box) : text(card || sys || li),
              card: card ? text(card) : '', image: img ? img.src : '',
              time: text(li.querySelector('.message-time'))});
  });
  return JSON.stringify({uid, name: nameEl ? nameEl.textContent.trim() : '', messages: out});
})()"""


def type_reply_js(text: str) -> str:
    # Vue's v-model listens for `input`; setting .value alone leaves the model empty.
    return r"""((text) => {
  const ta = document.querySelector('#replyTextarea');
  if (!ta) return JSON.stringify({ok: false, error: 'reply box not found'});
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
  ta.focus();
  setter.call(ta, text);
  ta.dispatchEvent(new Event('input', {bubbles: true}));
  return JSON.stringify({ok: ta.value === text});
})(%s)""" % json.dumps(text)


# ── trusted input ────────────────────────────────────────────────────
# The page ignores synthetic events: a row ``.click()`` never switched the
# conversation and a ``.send-btn`` ``.click()`` never sent (first live run,
# 2026-10-01: 13 replies, 0 delivered). The rows are draggable
# (``data-move-dom``) and react to a real press/release. So the send path uses
# CDP Input -- real mouse events and real text insertion -- like a person.

def row_point_js(uid: str) -> str:
    """Scroll *uid*'s conversation row into view; its click point (left part,
    nickname area -- clear of the row's 转移会话 button)."""
    return r"""((uid) => {
  const rows = [...document.querySelectorAll('.chat-item-box[data-random]')]
    .filter(b => (b.getAttribute('data-random') || '').split('-')[0] === uid);
  const box = rows.find(b => b.offsetParent !== null) || rows[0];
  if (!box) return JSON.stringify({ok: false, error: 'no conversation row for ' + uid});
  box.scrollIntoView({block: 'center'});
  const r = box.getBoundingClientRect();
  if (!r.width || !r.height) return JSON.stringify({ok: false, error: 'conversation row for ' + uid + ' is not visible'});
  const x = r.left + Math.min(r.width * 0.35, 120), y = r.top + r.height / 2;
  const at = document.elementFromPoint(x, y);
  return JSON.stringify({ok: true, x, y, visibility: document.visibilityState, hit: !!at && box.contains(at)});
})(%s)""" % json.dumps(uid)


def point_js(selector: str) -> str:
    """Scroll the first visible match of *selector* into view; its centre."""
    return r"""((sel) => {
  const all = [...document.querySelectorAll(sel)];
  const el = all.find(e => e.offsetParent !== null) || all[0];
  if (!el) return JSON.stringify({ok: false, error: 'not found: ' + sel});
  el.scrollIntoView({block: 'nearest'});
  const r = el.getBoundingClientRect();
  if (!r.width || !r.height) return JSON.stringify({ok: false, error: 'not visible: ' + sel});
  return JSON.stringify({ok: true, x: r.left + r.width / 2, y: r.top + r.height / 2});
})(%s)""" % json.dumps(selector)


REPLY_BOX = "#replyTextarea"
SEND_BUTTON = ".reply-box .send-btn, .send-btn"

READ_REPLY_JS = r"""(() => {
  const ta = document.querySelector('#replyTextarea');
  return JSON.stringify({ok: !!ta, value: ta ? ta.value : ''});
})()"""

# Empty the box first (left-over text would be sent with the reply); the model
# follows the input event.
CLEAR_REPLY_JS = r"""(() => {
  const ta = document.querySelector('#replyTextarea');
  if (!ta) return JSON.stringify({ok: false, error: 'reply box not found'});
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
  setter.call(ta, '');
  ta.dispatchEvent(new Event('input', {bubbles: true}));
  return JSON.stringify({ok: true});
})()"""


# Where the last real mousedown landed (the customer's store Chrome ignores our
# clicks while text insertion works -- 2026-10-01 runs; this says why).
CLICK_PROBE_JS = r"""(() => {
  if (!window.__ecanDown) {
    window.__ecanDown = {n: 0};
    document.addEventListener('mousedown', e => {
      const t = e.target, d = window.__ecanDown;
      d.n += 1; d.x = Math.round(e.clientX); d.y = Math.round(e.clientY); d.trusted = e.isTrusted;
      d.target = t ? (t.tagName + (t.id ? '#' + t.id : '') + '.' + String(t.className || '').split(' ')[0]) : '';
    }, true);
  }
  return JSON.stringify(window.__ecanDown);
})()"""

FOCUS_STATE_JS = r"""(() => {
  const a = document.activeElement;
  return JSON.stringify({active: a ? (a.id || a.tagName) : '', visibility: document.visibilityState,
                         focus: document.hasFocus(), dpr: window.devicePixelRatio});
})()"""

FOCUS_REPLY_JS = r"""(() => {
  const ta = document.querySelector('#replyTextarea');
  if (!ta) return JSON.stringify({ok: false});
  ta.focus();
  return JSON.stringify({ok: document.activeElement === ta});
})()"""


async def trusted_click(cdp: Cdp, x: float, y: float) -> None:
    for kind in ("mouseMoved", "mousePressed", "mouseReleased"):
        params: Dict[str, Any] = {"type": kind, "x": x, "y": y}
        if kind != "mouseMoved":
            params.update(button="left", clickCount=1)
        await cdp("Input.dispatchMouseEvent", params)


async def press_enter(cdp: Cdp) -> None:
    # No ``text``: the key event alone, so a box that does not send on Enter gets no newline.
    for kind in ("keyDown", "keyUp"):
        await cdp("Input.dispatchKeyEvent", {"type": kind, "key": "Enter", "code": "Enter",
                                             "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})


async def _click_probe(evaluate: Evaluate, cdp: Cdp, x: float, y: float) -> str:
    """Click at (x, y); describe where the page saw the mousedown, if at all."""
    before = (_parse(await evaluate(CLICK_PROBE_JS)) or {}).get("n", 0)
    await trusted_click(cdp, x, y)
    after = _parse(await evaluate(CLICK_PROBE_JS)) or {}
    if after.get("n", 0) == before:
        return f"click at ({x:.0f},{y:.0f}) never reached the page"
    return (f"click at ({x:.0f},{y:.0f}) landed at ({after.get('x')},{after.get('y')}) "
            f"on {after.get('target')} trusted={after.get('trusted')}")


async def open_conversation(evaluate: Evaluate, uid: str, cdp: Cdp, settle=None) -> Dict[str, Any]:
    """Switch the page to *uid*'s conversation with a real click; wait until it shows."""
    thread = await get_thread(evaluate)
    if thread.get("uid") == uid:
        return {"ok": True}
    await cdp("Page.bringToFront", {})
    point = _parse(await evaluate(row_point_js(uid))) or {}
    if not point.get("ok"):
        return {"ok": False, "error": point.get("error") or "conversation row not found"}
    probe = await _click_probe(evaluate, cdp, point["x"], point["y"])
    for _ in range(15):
        if settle:
            await settle()
        thread = await get_thread(evaluate)
        if thread.get("uid") == uid:
            return {"ok": True}
    state = _parse(await evaluate(FOCUS_STATE_JS)) or {}
    return {"ok": False, "error": f"conversation {uid} did not open (showing {thread.get('uid')!r}; "
                                  f"{probe}; page {state})"}


async def _send_text_trusted(evaluate: Evaluate, cdp: Cdp, uid: str, text: str, settle=None) -> Dict[str, Any]:
    opened = await open_conversation(evaluate, uid, cdp, settle=settle)
    if not opened.get("ok"):
        return opened
    box = _parse(await evaluate(point_js(REPLY_BOX))) or {}
    if not box.get("ok"):
        return {"ok": False, "error": box.get("error") or "reply box not found"}
    diag = [await _click_probe(evaluate, cdp, box["x"], box["y"])]
    if (_parse(await evaluate(FOCUS_STATE_JS)) or {}).get("active") != "replyTextarea":
        # The click did not focus the box; focus is not gated on trusted input.
        diag.append("focused by script" if (_parse(await evaluate(FOCUS_REPLY_JS)) or {}).get("ok")
                    else "could not focus the box")
    cleared = _parse(await evaluate(CLEAR_REPLY_JS)) or {}
    if not cleared.get("ok"):
        return {"ok": False, "error": cleared.get("error") or "could not clear the reply box"}
    await cdp("Input.insertText", {"text": text})
    typed = _parse(await evaluate(READ_REPLY_JS)) or {}
    if typed.get("value") != text:
        diag.append("typed by setter")
        await evaluate(type_reply_js(text))
        typed = _parse(await evaluate(READ_REPLY_JS)) or {}
    if typed.get("value") != text:
        state = _parse(await evaluate(FOCUS_STATE_JS)) or {}
        return {"ok": False, "error": f"reply box holds {str(typed.get('value'))[:40]!r}, not the reply "
                                      f"({'; '.join(diag)}; page {state})"}
    await press_enter(cdp)
    if settle:
        await settle()
    after = _parse(await evaluate(READ_REPLY_JS)) or {}
    if after.get("value") != "":
        diag.append("Enter did not send")
        button = _parse(await evaluate(point_js(SEND_BUTTON))) or {}
        if not button.get("ok"):
            return {"ok": False, "error": button.get("error") or "send button not found"}
        diag.append("send " + await _click_probe(evaluate, cdp, button["x"], button["y"]))
        if settle:
            await settle()
        after = _parse(await evaluate(READ_REPLY_JS)) or {}
    return {"ok": True, "uid": uid, "cleared": after.get("value") == "", "diag": "; ".join(diag)}


CLICK_SEND_JS = r"""(() => {
  const btn = document.querySelector('.reply-box .send-btn, .send-btn');
  if (!btn) return JSON.stringify({ok: false, error: 'send button not found'});
  btn.click();
  const ta = document.querySelector('#replyTextarea');
  return JSON.stringify({ok: true, cleared: !!ta && ta.value === ''});
})()"""


def _parse(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


async def list_sessions(evaluate: Evaluate) -> List[Dict[str, Any]]:
    return _parse(await evaluate(LIST_SESSIONS_JS)) or []


async def open_session(evaluate: Evaluate, uid: str) -> Dict[str, Any]:
    return _parse(await evaluate(open_session_js(uid)))


async def get_thread(evaluate: Evaluate) -> Dict[str, Any]:
    return _parse(await evaluate(THREAD_JS)) or {}


async def send_text(evaluate: Evaluate, uid: str, text: str, settle=None, cdp: "Cdp | None" = None) -> Dict[str, Any]:
    """Open *uid*'s conversation if needed, type *text*, click Send.

    Refuses to type into the wrong conversation: after opening, the thread's
    ``currentuid`` must be *uid*. ``settle`` is an awaitable factory used to
    wait between steps (the page re-renders on open). With *cdp* (the normal
    case) every step is real input; without it, the synthetic-event path the
    page is known to ignore -- kept only as a last resort.
    """
    if cdp is not None:
        return await _send_text_trusted(evaluate, cdp, uid, text, settle=settle)
    thread = await get_thread(evaluate)
    if thread.get("uid") != uid:
        opened = await open_session(evaluate, uid)
        if not opened.get("ok"):
            return {"ok": False, "error": opened.get("error") or "could not open conversation"}
        for _ in range(10):
            if settle:
                await settle()
            thread = await get_thread(evaluate)
            if thread.get("uid") == uid:
                break
        else:
            return {"ok": False, "error": f"conversation {uid} did not open (showing {thread.get('uid')!r})"}
    typed = _parse(await evaluate(type_reply_js(text)))
    if not typed.get("ok"):
        return {"ok": False, "error": typed.get("error") or "could not type the reply"}
    sent = _parse(await evaluate(CLICK_SEND_JS))
    if not sent.get("ok"):
        return sent
    return {"ok": True, "uid": uid, "cleared": sent.get("cleared")}


# ── which tab is the chat page ───────────────────────────────────────

_TAB_ATTR = "_ecan_pdd_chat_tab"


async def resolve_tab_target_id(browser_session: Any, customer_key: str = "", **_: Any) -> str:
    """The chat-merchant tab's target id, without changing focus. "" if none is open.

    One reply box per page, so every customer resolves to the same tab.
    """
    try:
        sm = getattr(browser_session, "session_manager", None)
        targets = sm.get_all_targets() if sm else {}
    except Exception:
        targets = {}
    cached = str(getattr(browser_session, _TAB_ATTR, "") or "")
    if cached and cached in (targets or {}) and is_chat_url(getattr(targets[cached], "url", "")):
        return cached
    for tid, tgt in (targets or {}).items():
        if getattr(tgt, "target_type", "") in ("page", "tab") and is_chat_url(getattr(tgt, "url", "")):
            try:
                setattr(browser_session, _TAB_ATTR, str(tid))
            except Exception:
                pass
            return str(tid)
    return ""
