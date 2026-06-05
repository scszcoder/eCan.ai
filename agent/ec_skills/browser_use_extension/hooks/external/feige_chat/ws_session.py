"""WS session manager — owns live Feige Frontier socket state for OFF-DOM delivery (S1).

Fed by the WS observer (note_sent_frame / note_recv_frame); used by the send path to
deliver a reply over the socket instead of typing it into the DOM (the serial,
typing-lock-gated bottleneck behind the ws002 storms / 1-min delays / 43s placeholders):

    f = frame_for(customer, text)          # clone the customer's conversation template
    if f:
        frame, cid = f
        # caller injects window.__ecan_feige_ws.send(frame) via CDP
        delivered = await wait_confirmed(cid)   # server echoed it back == accepted

Per-conversation template = the latest SENT chat frame for that conversation, keyed by
pigeon_cid (sent .8.9), which equals a recv message's pigeon_cid — so we map
customer_name -> pigeon_cid (from incoming) -> template (from outgoing).

Platform-specific (Feige) -> lives in feige_chat/. Thread-safe: the observer feeds it
from its own CDP loop/thread; senders read it from the agent loop.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid

from . import ws_reader, ws_sender

logger = logging.getLogger("eCan")

_lock = threading.Lock()
_templates: dict = {}    # pigeon_cid -> latest SENT chat-frame bytes (template)
_routing: dict = {}      # customer_name -> pigeon_cid
_pending: dict = {}      # cid -> {"text", "confirmed", "ts"}
_PENDING_TTL = 90.0


def note_sent_frame(raw: bytes) -> None:
    """Observer hook: every binary webSocketFrameSent. Cache reply templates per conv."""
    try:
        if ws_sender.frame_text(raw) is None:        # only real chat-message sends
            return
        pcid = ws_sender.sent_conv(raw)
        if pcid:
            with _lock:
                _templates[str(pcid)] = raw
    except Exception:
        pass


def note_recv_frame(raw: bytes) -> None:
    """Observer hook: every binary webSocketFrameReceived. Update routing + confirmations."""
    try:
        msgs = ws_reader.extract_messages(raw)
    except Exception:
        return
    for m in msgs:
        if m.sender_role == "1" and m.customer_name and m.pigeon_cid:
            with _lock:
                _routing[m.customer_name] = m.pigeon_cid          # name -> conv routing
        with _lock:
            for p in _pending.values():                           # our echo == delivered
                if not p["confirmed"] and p["text"] == m.text:
                    p["confirmed"] = True


def can_send(customer_name: str) -> bool:
    with _lock:
        pcid = _routing.get(customer_name)
        return bool(pcid and pcid in _templates)


def frame_for(customer_name: str, text: str):
    """Build a ready-to-inject send frame for *customer_name*. Returns (frame, cid) or None
    when we have no template/routing for them yet (caller falls back to DOM)."""
    with _lock:
        pcid = _routing.get(customer_name)
        tmpl = _templates.get(pcid) if pcid else None
    if not tmpl:
        return None
    cid = str(uuid.uuid4())
    try:
        frame = ws_sender.build_send_frame(tmpl, text=text, client_msg_id=cid)
    except Exception as exc:
        logger.debug(f"[ws_session] build_send_frame failed for {customer_name!r}: {exc}")
        return None
    now = time.time()
    with _lock:
        for c in [c for c, p in _pending.items() if now - p["ts"] > _PENDING_TTL]:
            _pending.pop(c, None)
        _pending[cid] = {"text": text, "confirmed": False, "ts": now}
    return frame, cid


def is_confirmed(cid: str) -> bool:
    with _lock:
        p = _pending.get(cid)
        return bool(p and p["confirmed"])


async def wait_confirmed(cid: str, timeout_s: float = 8.0) -> bool:
    """Await the server's echo of this send (== delivered/accepted). False on timeout."""
    end = time.time() + timeout_s
    while time.time() < end:
        if is_confirmed(cid):
            return True
        await asyncio.sleep(0.05)
    return is_confirmed(cid)


def inject_js(frame_bytes: bytes) -> str:
    """JS to run on the Feige tab: ensure the socket-capture hook is installed, then
    send our frame on the page's authed Frontier socket. Returns 'SENT' / 'NO_SOCKET'
    (hook just armed; retry next turn) / 'NOT_OPEN'."""
    import base64
    b64 = base64.b64encode(frame_bytes).decode()
    return (
        "(function(){"
        "if(!window.__ecan_ws_hooked){window.__ecan_ws_hooked=1;var o=WebSocket.prototype.send;"
        "WebSocket.prototype.send=function(d){try{if(this.url&&this.url.indexOf('fxg.jinritemai.com')!==-1)"
        "window.__ecan_feige_ws=this;}catch(e){}return o.apply(this,arguments);};}"
        "var s=window.__ecan_feige_ws;if(!s)return 'NO_SOCKET';if(s.readyState!==1)return 'NOT_OPEN';"
        "var bin=atob('" + b64 + "');var u=new Uint8Array(bin.length);"
        "for(var i=0;i<bin.length;i++)u[i]=bin.charCodeAt(i);s.send(u.buffer);return 'SENT';})()"
    )


def stats() -> dict:
    with _lock:
        return {"templates": len(_templates), "routing": len(_routing), "pending": len(_pending)}
