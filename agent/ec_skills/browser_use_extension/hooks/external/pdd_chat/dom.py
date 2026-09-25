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


async def send_text(evaluate: Evaluate, uid: str, text: str, settle=None) -> Dict[str, Any]:
    """Open *uid*'s conversation if needed, type *text*, click Send.

    Refuses to type into the wrong conversation: after opening, the thread's
    ``currentuid`` must be *uid*. ``settle`` is an awaitable factory used to
    wait between steps (the page re-renders on open).
    """
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
