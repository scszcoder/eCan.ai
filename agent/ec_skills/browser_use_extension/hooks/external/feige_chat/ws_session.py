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
_talk_identity: dict = {} # ws070: talk_id -> the STICKY dispatch identity (first non-empty
                         # customer_name seen). Collapses a name-less entry card and the
                         # customer's later named frames onto ONE QA session (the 肽斯特 split).
_uid_by_talk: dict = {}  # ws028: talk_id -> customer's security_sender_id (== our send's
                         # security_receiver_id). Captured from inbound role=1 frames; used to
                         # FULLY retarget a first-contact send so it can't mis-deliver.
_name_by_uid: dict = {}  # ws127: security_sender_id (stable per-customer uid) -> customer_name.
                         # Seeded ONLY from NAMED frames. Bridges a name-less product card back
                         # to the real customer when its OWN talk_id never received a named frame
                         # (first-contact / product-consult talk fragmentation) — the card talk
                         # still carries the same uid, so name_for_talk can resolve via the uid.
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


# ws011 (raw-send spike): the observer owns an isolated CDP client attached to the
# Feige tab(s). The RAW sender (ws_raw_sender) needs ONE cheap eval to bootstrap —
# read window.__ecan_feige_ws.url + Origin/UA/Cookie off the page — before it can
# open eCan's OWN websockets connection to the Frontier server (fully off-renderer).
# The observer parks its client + session-ids here so the raw sender can do that
# one-time capture without standing up its own CDP attach.
_observer_client = None
_observer_sids: list = []


def set_observer_cdp(client, sids) -> None:
    """Observer parks its CDP client + attached session-ids for the raw sender's
    one-time connection-param capture. Best-effort; cleared on observer teardown."""
    global _observer_client, _observer_sids
    _observer_client = client
    _observer_sids = list(sids or [])


def get_observer_cdp():
    """(client, sids) the observer parked, or (None, []) when no observer is live."""
    return _observer_client, list(_observer_sids)


def ws_enabled(kind: str) -> bool:
    """S4 master-switch resolver. ``ECAN_FEIGE_WS=1`` turns on reader+dispatch+send
    together; the per-feature flags (ECAN_FEIGE_WS_READER/_DISPATCH/_SEND) still work
    and override-on individually. ``first_contact`` stays opt-in even under the master
    because its cross-conversation routing is unvalidated. kind in
    {'reader','dispatch','send','first_contact'}."""
    if kind != "first_contact" and os.environ.get("ECAN_FEIGE_WS", "") == "1":
        return True
    return os.environ.get(f"ECAN_FEIGE_WS_{kind.upper()}", "") == "1"


def name_for_talk(talk_id: str) -> str:
    """ws025: reverse lookup — the customer name last seen on *talk_id*.

    Product cards carry no nickname/uname, so the reader leaves their
    ``customer_name`` empty.  This attributes such name-less frames to the
    conversation's known customer (seeded by prior text frames) so they aren't
    dropped at the actionable ``required_field_missing:customer`` gate.
    """
    if not talk_id:
        return ""
    with _lock:
        _direct = str(_talk_to_name.get(str(talk_id)) or "")
        if _direct:
            return _direct
        # ws127: the card's OWN talk never received a named frame (first-contact /
        # product-consult talk fragmentation), so _talk_to_name misses. Bridge via the
        # stable per-customer uid: this talk's uid -> the name seen on ANY of that
        # customer's named frames. This is what lets a name-less card resolve to the real
        # customer so its reply raw-routes (off the DOM typing lock) instead of failing
        # `Session not found`. Gated ECAN_FEIGE_UID_NAME_BRIDGE=1 (default ON). Mis-delivery
        # safe: the uid is the customer's unique Douyin id; we only map to a name that was
        # already observed for that exact uid.
        if os.environ.get("ECAN_FEIGE_UID_NAME_BRIDGE", "1") != "0":
            _uid = str(_uid_by_talk.get(str(talk_id)) or "")
            if _uid:
                _via_uid = str(_name_by_uid.get(_uid) or "")
                if _via_uid and not _via_uid.startswith("card:"):
                    return _via_uid
        return ""


def talk_for_name(customer_name: str) -> str:
    """ws046: forward lookup — the talk_id (conversation id) last seen for
    *customer_name*.  Inverse of :func:`name_for_talk`.  Used to bridge a
    product card (dispatched under the synthetic ``card:<talk_id>`` identity
    because cards carry no nickname) back to the customer's named conversation
    so the card's content rides into the context of later text questions
    (otherwise the Q&A worker answers "这件适合夏天穿吗" about a 秋冬加厚 jacket
    with zero product grounding)."""
    if not customer_name:
        return ""
    with _lock:
        return str(_routing.get(str(customer_name)) or "")


def sticky_identity(talk_id: str, customer_name: str) -> str:
    """ws070: collapse a conversation onto ONE dispatch identity so a single human is
    never answered by two parallel QA pipelines.

    The 肽斯特 split: a product card shared ON ENTRY arrives before any named frame, so it
    is dispatched under the synthetic ``card:<talk_id>`` identity; the customer's follow-up
    text question (~20s later, name now resolved) dispatches under the real nickname. Both
    carry the SAME talk_id, but because every downstream key (QA session_id, placeholder
    timer, customer-state, delivery) is derived from ``customer_name``, the one human forks
    into two sessions — duplicate reply, fragmented context, doubled renderer load.

    FIRST non-empty identity seen for a talk_id WINS and is sticky: a later real name routes
    back into the synthetic session instead of forking a new one. Delivery is unaffected —
    :func:`frame_for`/:func:`can_send` already de-synthesize the ``card:<talk_id>`` prefix to
    the talk_id (ws060), and the real nickname stays in ``_routing`` for the wire send.
    Returns the canonical identity (the input unchanged when talk_id is empty)."""
    talk = str(talk_id or "")
    name = str(customer_name or "")
    if not talk:
        return name
    with _lock:
        prev = _talk_identity.get(talk)
        if prev:
            return prev
        if name:
            _talk_identity[talk] = name
        return name


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
        # ws048: ANY outgoing chat frame (real reply OR placeholder) proves the
        # turn for this conversation is alive — tell the watchdog so it clears the
        # pending record and never re-dispatches a turn that already responded.
        if talk:
            try:
                from . import ws_inbound_watchdog as _ws_wd
                _ws_wd.note_outgoing(str(talk))
            except Exception:
                pass
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
                # ws127: a NAMED frame with a uid seeds the uid->name bridge so a later
                # name-less card on a DIFFERENT talk (same customer, same uid) resolves.
                _u = getattr(m, "sender_uid", "")
                if _u:
                    _name_by_uid[_u] = m.customer_name
        # ws028: capture the customer's security_sender_id per conversation (may arrive on a
        # frame with no nickname, so key on talk independently of the name block above). This
        # is the receiver id a first-contact send retargets to.
        if m.sender_role == "1" and talk and getattr(m, "sender_uid", ""):
            with _lock:
                _uid_by_talk[talk] = m.sender_uid
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
    """True iff frame_for() could build a send frame — MUST mirror frame_for's routing,
    including ws060's card:<talk_id> extraction and the first-contact path.

    ws065: can_send previously did only ``_routing.get(name)``, so a synthetic ``card:<conv>``
    identity (never registered in _routing) always returned False — EVEN when frame_for can
    route it by the talk_id embedded in the name. The placeholder's off-renderer WS lane is
    gated on can_send (direct_delivery.py:130), so this silently forced EVERY card customer's
    过渡句 onto the contended DOM path → '过渡句出不来' under load. Now it agrees with frame_for.

    ws071 (REGRESSION GATE): the ws065 widening is the only always-on send-path change between
    the swift ws063 1-vs-5 and the stuck ws070 1-vs-2 (same flags). Suspected cascade: letting
    card placeholders onto the off-renderer WS lane floods/saturates the pool (pool-saturated
    7 vs 2, placeholder-timeouts 14 vs 2), starving the reply path's template capture → replies
    fall to NO-ROUTE→DOM → typing-lock pile-up → stuck. DEFAULT to the strict ws063 behavior;
    set ECAN_FEIGE_WS_CAN_SEND_WIDE=1 to restore the ws065 widening for a clean A/B."""
    # ws092: allow the card:<conv> FIRST-CONTACT route even when the global WIDE flag is off.
    # Cold-start split (2026-06-18): a name-less card's conversation is also seen under its real
    # name (e.g. card:<conv> AND 肽斯特 = the SAME talk). The real-name reply goes WS first-contact
    # AND holds the typing lock; the card:<conv> reply — with WIDE off, can_send returns False
    # (synthetic name not in _routing) — is forced onto the DOM-guarded path and STARVES 12s on
    # its own conversation's typing lock (holder=肽斯特) → typing_lock_busy, undelivered. Routing
    # the card reply off-DOM via first-contact sidesteps the typing lock entirely. SCOPED to
    # 'card:' names so it does NOT re-open the ws071 placeholder-flood concern for named customers.
    # Reversible: default off; ECAN_FEIGE_WS_CARD_FIRST_CONTACT=1 to enable.
    _card_fc = (
        os.environ.get("ECAN_FEIGE_WS_CARD_FIRST_CONTACT", "") == "1"
        and str(customer_name or "").startswith("card:")
    )
    if os.environ.get("ECAN_FEIGE_WS_CAN_SEND_WIDE", "") != "1" and not _card_fc:
        with _lock:                                   # ws063 strict behavior (the swift baseline)
            talk = _routing.get(customer_name)
            return bool(talk and talk in _templates)
    _synthetic_card = False
    with _lock:
        talk = _routing.get(customer_name)
        if not talk and customer_name.startswith("card:"):
            _ct = customer_name[len("card:"):].strip()
            if _ct:
                talk = _ct
                _synthetic_card = True
        if not talk:
            return False
        tmpl = _templates.get(talk)
        owner = _talk_to_name.get(talk)
        target_uid = _uid_by_talk.get(talk)
        session_tmpl = _session_template
    # mirror frame_for's routing-integrity guard (skipped for the synthetic-card case)
    if not _synthetic_card and owner is not None and owner != customer_name:
        return False
    if tmpl is not None:
        return True
    # first-contact path (ws028): donor template + the customer's captured receiver-id
    if ws_enabled("first_contact") and session_tmpl is not None and target_uid:
        return True
    return False


def frame_for(customer_name: str, text: str):
    """Build a ready-to-inject send frame for *customer_name*. Returns (frame, cid) or None
    when we can't build one yet (caller falls back to DOM)."""
    _synthetic_card = False
    with _lock:
        talk = _routing.get(customer_name)
        # ws060 (Option A): a name-less product card is keyed on a synthetic 'card:<talk_id>'
        # identity that was never registered in _routing (only real nicknames are). The
        # talk_id is in the name — extract it so the WS send routes by CONVERSATION (talk_id)
        # directly instead of bailing because the synthetic name has no routing entry.
        if not talk and customer_name.startswith("card:"):
            _ct = customer_name[len("card:"):].strip()
            if _ct:
                talk = _ct
                _synthetic_card = True
        tmpl = _templates.get(talk) if talk else None
        session_tmpl = _session_template
        owner = _talk_to_name.get(talk) if talk else None
        target_uid = _uid_by_talk.get(talk) if talk else None   # ws028: for first-contact retarget
    # Routing-integrity guard: the conversation we're about to target must currently be
    # known as THIS customer's. If the reverse map says it belongs to someone else (stale
    # or colliding routing), refuse WS — fall back to the guarded DOM path. Cheap defense
    # against name-keyed routing sending into the wrong thread. (Skipped for a synthetic-card
    # identity: there we routed by the talk_id embedded in the name itself, so an 'owner'
    # under the real nickname is the SAME conversation, not a collision.)
    if talk and not _synthetic_card and owner is not None and owner != customer_name:
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
        # ws028: no per-conversation template yet — clone the session-wide donor and FULLY
        # retarget it to THIS customer. Chat sends route by security_receiver_id (verified
        # 2026-06-08: the .8.8.100 envelope carries security_receiver_id, no talk_id), and
        # that id == the customer's inbound security_sender_id, captured in _uid_by_talk. We
        # need it to retarget safely; without it we CANNOT first-contact (would mis-deliver
        # to the donor) → fall back to DOM. build_first_contact_frame swaps the receiver id
        # 1:1 (same 88-char length) and returns None if it can't, so it's safe-by-construction.
        if not target_uid:
            logger.debug(
                f"[ws_session] first-contact: no captured receiver-id for {customer_name!r} "
                f"(talk={talk}) yet — DOM fallback")
            return None
        try:
            frame = ws_sender.build_first_contact_frame(
                session_tmpl, receiver_id=str(target_uid), text=text,
                client_msg_id=cid, talk_id=str(talk))
        except Exception as exc:
            logger.debug(f"[ws_session] first-contact build failed for {customer_name!r}: {exc}")
            return None
        if frame is None:
            return None
        logger.info(
            f"[ws_session] ws028 first-contact frame cust={customer_name!r} talk={talk} "
            f"len={len(text)} — receiver-id retargeted (safe-by-construction); confirm via echo")
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


# ws069 DIAGNOSTIC ONLY (gated on ECAN_FEIGE_WS_RAW_DIAG=1): wrap the page WebSocket
# CONSTRUCTOR and tap each Frontier socket's open/close so every (re)connect records
# {t, url, cookie, ts, code} into a ring buffer. The drain loop logs whether the
# url-token and/or cookie ACTUALLY change on reconnect — settling the ws068 "expires by
# age, not by url change" inference with event evidence (does the page even rotate? is the
# real credential the cookie?). Catches only sockets created AFTER arming, i.e. reconnects
# — exactly what we want; the already-open socket's url is already known via the send-hook.
# Distinct idempotency flag from the send-hook so the two compose. Best-effort, preserves
# the prototype + static constants so the page's IM client is unaffected.
_CTOR_DIAG_INSTALLER = (
    "if(!window.__ecan_ws_ctor_hooked){window.__ecan_ws_ctor_hooked=1;"
    "window.__ecan_feige_ws_diag=window.__ecan_feige_ws_diag||[];"
    "var D=window.__ecan_feige_ws_diag;"
    "var P=function(ev){try{D.push(ev);if(D.length>300)D.shift();}catch(e){}};"
    "var OW=window.WebSocket;"
    "var W=function(u,p){var ws=(p!==undefined)?new OW(u,p):new OW(u);try{"
    "if(u&&String(u).indexOf('fxg.jinritemai.com')!==-1){var us=String(u);"
    "P({t:'ctor',url:us,ts:Date.now(),cookie:document.cookie});"
    "ws.addEventListener('open',function(){P({t:'open',url:us,ts:Date.now(),cookie:document.cookie});});"
    "ws.addEventListener('close',function(e){P({t:'close',url:us,ts:Date.now(),code:(e&&e.code)||0,cookie:document.cookie});});"
    "}}catch(e){}return ws;};"
    "W.prototype=OW.prototype;"
    "try{W.CONNECTING=OW.CONNECTING;W.OPEN=OW.OPEN;W.CLOSING=OW.CLOSING;W.CLOSED=OW.CLOSED;}catch(e){}"
    "window.WebSocket=W;}"
)


def arm_socket_ctor_diag_js() -> str:
    """ws069 diag: install the WebSocket-constructor + open/close tap (idempotent)."""
    return ("(function(){try{" + _CTOR_DIAG_INSTALLER +
            "return 'CTOR_DIAG_OK';}catch(e){return 'CTOR_DIAG_ERR:'+e;}})()")


def drain_ctor_diag_js() -> str:
    """ws069 diag: return + clear the reconnect-event ring buffer as a JSON array."""
    return ("(function(){try{var d=window.__ecan_feige_ws_diag||[];"
            "window.__ecan_feige_ws_diag=[];return JSON.stringify(d);}catch(e){return '[]';}})()")


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
