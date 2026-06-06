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
import os
import threading
import time
import uuid

from . import ws_reader, ws_sender

logger = logging.getLogger("eCan")

_lock = threading.Lock()
_templates: dict = {}    # talk_id -> latest SENT chat-frame bytes (template) [PER-CONVERSATION]
_routing: dict = {}      # customer_name -> talk_id
_talk_to_name: dict = {} # talk_id -> customer_name (reverse, for routing-integrity guard)
_pending: dict = {}      # cid -> {"text", "talk", "confirmed", "ts"}
_session_template: bytes | None = None   # S3: any sent chat frame (session-wide donor)
_read_template: bytes | None = None      # tier0: a captured read-ack (cmd 2002) to clone
_read_cursor: dict = {}  # talk_id -> latest recv read_cursor (the "read up to" server id)
# ws008: per-conversation thread snapshot built from the frame stream, so a WS-based
# "scrape tool" can produce the SAME shape the DOM scrape does — letting the unchanged
# downstream suite (dedup / supersede / echo / human-intervention) run source-agnostic.
#   _thread[talk] = {"cust": {text,cmid,type,ts}, "agent": {text,cmid,is_ours,ts}}
_thread: dict = {}
_our_cmids: set = set()  # client_message_ids WE generated (our WS sends) -> definitive is_ours
_OUR_CMIDS_MAX = 512
_PENDING_TTL = 90.0


def _note_our_cmid(cid: str) -> None:
    """Record a client_message_id we generated, so an echo carrying it is definitively
    OUR reply (not a human agent's) — the reliable is_ours signal for ws008 stage 3."""
    if not cid:
        return
    with _lock:
        _our_cmids.add(cid)
        if len(_our_cmids) > _OUR_CMIDS_MAX:
            # cheap bound: drop ~half (arbitrary; these are short-lived correlation ids)
            for _ in range(len(_our_cmids) - _OUR_CMIDS_MAX // 2):
                _our_cmids.pop()
_dispatch_live = False    # True ONLY while the WS observer is actively dispatching


def set_dispatch_live(v: bool) -> None:
    """Observer signals whether it is actually carrying detection dispatch right now."""
    global _dispatch_live
    _dispatch_live = bool(v)


def is_dispatch_live() -> bool:
    """The DOM monitor suppresses its own dispatch ONLY when this is True — i.e. when
    the WS observer is confirmed live and dispatching. Prevents the deadlock where a
    dispatch flag is set but the observer never started, so nothing delivers at all."""
    return _dispatch_live


def ws_enabled(kind: str) -> bool:
    """S4 master-switch resolver. ``ECAN_FEIGE_WS=1`` turns on reader+dispatch+send
    together; the per-feature flags (ECAN_FEIGE_WS_READER/_DISPATCH/_SEND) still work
    and override-on individually. ``first_contact`` stays opt-in even under the master
    because its cross-conversation routing is unvalidated. kind in
    {'reader','dispatch','send','first_contact'}."""
    if kind != "first_contact" and os.environ.get("ECAN_FEIGE_WS", "") == "1":
        return True
    return os.environ.get(f"ECAN_FEIGE_WS_{kind.upper()}", "") == "1"


def read_frame_for(talk_id: str, cursor: str = ""):
    """tier0 已读: build a read-ack frame marking *talk_id* read up to *cursor* (a recv
    message's read_cursor). Falls back to the latest cached cursor for the conversation.
    Returns frame bytes or None (no template/cursor yet, or build failed)."""
    talk_id = str(talk_id or "")
    with _lock:
        tmpl = _read_template
        cur = str(cursor or _read_cursor.get(talk_id) or "")
    if not tmpl or not talk_id or not cur:
        return None
    try:
        return ws_sender.build_read_ack(tmpl, talk_id=talk_id, cursor=cur)
    except Exception as exc:
        logger.debug(f"[ws_session] build_read_ack failed for talk={talk_id}: {exc}")
        return None


def note_sent_frame(raw: bytes) -> None:
    """Observer hook: every binary webSocketFrameSent. Cache reply templates per conv,
    and keep the latest as the session-wide donor for S3 first-contact frames."""
    global _session_template, _read_template
    try:
        if ws_sender.is_read_ack(raw):               # tier0: cache a read-ack to clone
            with _lock:
                _read_template = raw
            return
        if ws_sender.frame_text(raw) is None:        # only real chat-message sends
            return
        talk = ws_sender.sent_talk(raw)              # PER-CONVERSATION key (not pigeon_cid!)
        with _lock:
            _session_template = raw                   # S3 donor (pigeon_sign + envelope)
            if talk:
                _templates[str(talk)] = raw
    except Exception:
        pass


def note_recv_frame(raw: bytes) -> None:
    """Observer hook: every binary webSocketFrameReceived. Update routing + confirmations."""
    try:
        msgs = ws_reader.extract_messages(raw)
    except Exception:
        return
    for m in msgs:
        # talk_id is the PER-CONVERSATION id; pigeon_cid is merchant-level (shared by ALL
        # customers of this shop), so routing/confirmation MUST key on talk_id (ws003d).
        talk = m.conversation_id
        if m.sender_role == "1" and m.customer_name and talk:
            with _lock:
                _routing[m.customer_name] = talk                  # name -> conversation
                _talk_to_name[talk] = m.customer_name             # reverse, for integrity guard
                if m.read_cursor:
                    _read_cursor[talk] = m.read_cursor            # tier0: "read up to" id
        # ws008: maintain the per-conversation thread snapshot from the stream so a WS
        # scrape tool can reproduce the DOM snapshot. Customer bubble (role 1) and agent
        # bubble (role 2) tracked separately; agent is_ours is definitive when the echo
        # carries a client_message_id WE generated.
        if talk and m.text:
            with _lock:
                th = _thread.setdefault(talk, {})
                if m.sender_role == "1":
                    cur = th.get("cust")
                    if not cur or m.ts_ms >= cur.get("ts", 0):
                        th["cust"] = {"text": m.text, "cmid": m.client_msg_id,
                                      "type": m.msg_type, "ts": m.ts_ms}
                elif m.sender_role == "2":
                    cur = th.get("agent")
                    if not cur or m.ts_ms >= cur.get("ts", 0):
                        th["agent"] = {"text": m.text, "cmid": m.client_msg_id,
                                       "is_ours": bool(m.client_msg_id and m.client_msg_id in _our_cmids),
                                       "ts": m.ts_ms}
        # Confirm a pending send ONLY when the echo returns on the SAME conversation we
        # targeted (talk_id) AND carries our client_message_id, or (fallback) matches the
        # text. The talk_id scope is the safety net: an echo on a DIFFERENT conversation —
        # a mis-delivery, or another customer's identical placeholder echo — can NEVER
        # confirm our send. It stays unconfirmed and the caller falls back to the guarded
        # DOM path. (ws003c matched text alone -> cross-customer false "DELIVERED"; ws003d
        # scoped by talk_id after pigeon_cid turned out to be shared across customers.)
        with _lock:
            for c, p in _pending.items():
                if p["confirmed"]:
                    continue
                if m.client_msg_id and m.client_msg_id == c:
                    p["confirmed"] = True                          # exact: our cid echoed back
                elif p.get("talk") and talk == p["talk"] and m.text == p["text"]:
                    p["confirmed"] = True                          # scoped: same conv + same text


def can_send(customer_name: str) -> bool:
    with _lock:
        talk = _routing.get(customer_name)
        return bool(talk and talk in _templates)


def frame_for(customer_name: str, text: str):
    """Build a ready-to-inject send frame for *customer_name*. Returns (frame, cid) or None
    when we can't build one yet (caller falls back to DOM)."""
    with _lock:
        talk = _routing.get(customer_name)
        tmpl = _templates.get(talk) if talk else None
        session_tmpl = _session_template
        owner = _talk_to_name.get(talk) if talk else None
    # Routing-integrity guard: the conversation we're about to target must currently be
    # known as THIS customer's. If the reverse map says it belongs to someone else (stale
    # or colliding routing), refuse WS — fall back to the guarded DOM path. Cheap defense
    # against name-keyed routing sending into the wrong thread.
    if talk and owner is not None and owner != customer_name:
        logger.warning(
            f"[ws_session] routing-integrity: conv {talk} is owned by {owner!r}, not "
            f"{customer_name!r} — refusing WS send, DOM fallback")
        return None
    cid = str(uuid.uuid4())
    frame = None
    if tmpl:
        try:
            frame = ws_sender.build_send_frame(tmpl, text=text, client_msg_id=cid)
        except Exception as exc:
            logger.debug(f"[ws_session] build_send_frame failed for {customer_name!r}: {exc}")
            return None
    elif ws_enabled("first_contact") and session_tmpl is not None and talk:
        # S3: no per-conversation template yet — retarget the session-wide donor to this
        # customer's talk_id. Fires at most once per conversation (the resulting send,
        # once observed, caches a real per-conv template). UNVERIFIED: also does NOT swap
        # security_receiver_id, so cross-conversation routing is not proven — gated off.
        try:
            frame = ws_sender.build_first_contact_frame(
                session_tmpl, talk_id=talk, text=text, client_msg_id=cid)
        except Exception as exc:
            logger.debug(f"[ws_session] first-contact build failed for {customer_name!r}: {exc}")
            return None
        if frame is None:
            return None
        logger.info(
            f"[ws_session] S3 VALIDATE first-contact frame cust={customer_name!r} "
            f"talk={talk} len={len(text)} — cross-conv routing UNVERIFIED, confirm via echo")
    if frame is None:
        return None
    _note_our_cmid(cid)   # ws008: our WS send -> echo with this cid is definitively ours
    now = time.time()
    with _lock:
        for c in [c for c, p in _pending.items() if now - p["ts"] > _PENDING_TTL]:
            _pending.pop(c, None)
        _pending[cid] = {"text": text, "talk": str(talk or ""), "confirmed": False, "ts": now}
    return frame, cid


def ws_text_scrape(customer_name: str):
    """ws008 (the swappable WS 'scrape tool'): produce a DOM-scrape-compatible customer-
    bubble result for *customer_name* PURELY from the WS frame stream — but ONLY for
    plain TEXT messages. Returns a dict shaped like ScrapeResult
    ({scrape_ok, msg_id, text, attachments}) or None when the latest message is a card /
    image / unknown type or we have no data — in which case the caller falls back to the
    DOM scrape. msg_id is the client_message_id (== the DOM bubble's data-id) so all the
    downstream dedup/stale-guard keys stay consistent with the DOM path."""
    with _lock:
        talk = _routing.get(customer_name)
        th = _thread.get(talk) if talk else None
        cust = dict(th.get("cust") or {}) if th else None
        agent = dict(th.get("agent") or {}) if th else None
    if not cust or not cust.get("text"):
        return None
    if cust.get("type") != "text":          # card / image / unknown -> DOM scrape
        return None
    # Reproduce the SAME fields the DOM scrape provides so the unchanged downstream
    # semantics keep working: `index` (mt030 agent-already-replied) + `latest_agent_bubble`
    # (echo / human-intervention). DOM `index` is bubble position (higher = newer); we map
    # it from arrival ts — agent index 1 (after customer) iff the agent bubble is newer
    # than this customer bubble, else -1 (an older reply, i.e. THIS message is unanswered).
    cust_ts = int(cust.get("ts") or 0)
    out = {
        "scrape_ok": True,
        "msg_id": str(cust.get("cmid") or ""),
        "text": str(cust.get("text") or ""),
        "attachments": [],
        "index": 0,
    }
    if agent and agent.get("text"):
        agent_ts = int(agent.get("ts") or 0)
        out["latest_agent_bubble"] = {
            "text": str(agent.get("text") or ""),
            "msg_id": str(agent.get("cmid") or ""),
            "is_ours": bool(agent.get("is_ours")),
            "index": 1 if agent_ts > cust_ts else -1,
        }
    return out


def ws_thread_snapshot(customer_name: str):
    """ws008: the fuller per-conversation snapshot for the echo / human-intervention
    consumers — latest customer bubble + latest agent bubble with a DEFINITIVE is_ours
    (True only when the agent echo carried a client_message_id we generated). Returns
    {"customer": {...}, "agent": {...}} or None when no data yet."""
    with _lock:
        talk = _routing.get(customer_name)
        th = _thread.get(talk) if talk else None
        if not th:
            return None
        return {"customer": dict(th.get("cust") or {}), "agent": dict(th.get("agent") or {})}


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


# Page hook: tap WebSocket.prototype.send so the next frame the page sends on the
# Frontier socket captures the authed socket handle into window.__ecan_feige_ws.
# Idempotent. Armed proactively by the observer at startup (so a heartbeat fills the
# handle before any reply needs it) AND re-ensured inside inject_js.
_HOOK_INSTALLER = (
    "if(!window.__ecan_ws_hooked){window.__ecan_ws_hooked=1;var o=WebSocket.prototype.send;"
    "WebSocket.prototype.send=function(d){try{if(this.url&&this.url.indexOf('fxg.jinritemai.com')!==-1)"
    "window.__ecan_feige_ws=this;}catch(e){}return o.apply(this,arguments);};}"
)


def arm_socket_hook_js() -> str:
    """Standalone IIFE that installs the socket-capture hook (no send). Run once at
    observer startup so window.__ecan_feige_ws is populated from a heartbeat early."""
    return "(function(){" + _HOOK_INSTALLER + "return window.__ecan_feige_ws?'HOOKED_LIVE':'HOOKED';})()"


def inject_js(frame_bytes: bytes) -> str:
    """JS to run on the Feige tab: ensure the socket-capture hook is installed, then
    send our frame on the page's authed Frontier socket. Returns 'SENT' / 'NO_SOCKET'
    (hook just armed; retry next turn) / 'NOT_OPEN'."""
    import base64
    b64 = base64.b64encode(frame_bytes).decode()
    return (
        "(function(){" + _HOOK_INSTALLER +
        "var s=window.__ecan_feige_ws;if(!s)return 'NO_SOCKET';if(s.readyState!==1)return 'NOT_OPEN';"
        "var bin=atob('" + b64 + "');var u=new Uint8Array(bin.length);"
        "for(var i=0;i<bin.length;i++)u[i]=bin.charCodeAt(i);s.send(u.buffer);return 'SENT';})()"
    )


def stats() -> dict:
    with _lock:
        return {"templates": len(_templates), "routing": len(_routing), "pending": len(_pending)}
