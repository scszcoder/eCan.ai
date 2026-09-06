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

# CN builds name the app logger "eCan.cn" (propagate=False) — a bare
# getLogger("eCan") record never reaches its handlers, silencing this
# module's entire log output in packaged CN apps (v0.9.95u incident:
# the WS reader looked dead because none of its lines could land).
from utils.logger_helper import logger_helper as logger

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
_card_bridged_names: set = set()  # ws130: names whose _routing entry came from a CARD bridge
                         # (not an authoritative named frame). Lets a later card on a newer talk
                         # update the route, while a real named frame always wins and is sticky.
_pending: dict = {}      # cid -> {"text", "talk", "confirmed", "ts"}
_session_template: bytes | None = None   # S3: any sent chat frame (session-wide donor)
_read_template: bytes | None = None      # tier0: a captured read-ack (cmd 2002) to clone
_recv_dumped_talks: set = set()          # ws139: cold-start inbound-frame dump dedupe (one/talk)
_framedump_seen: set = set()             # ws140: send-frame dump dedupe by (kind, talk) — 1 fc + 1 warm/conv
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


def name_for_talk_verified(talk_id: str) -> str:
    """ws192: :func:`name_for_talk` with a talk-match guard.

    Returns the resolved real name ONLY when its own talk is *talk_id* (or is
    unknown, i.e. not yet routed). A stale or cross-contaminated
    ``_talk_to_name`` / uid-bridge entry can make ``name_for_talk`` return a
    DIFFERENT customer's name; binding a card to it mis-delivers the answer and
    splits the dedup keys (live 96z: card talk …808602 '钛斯特' resolved to
    '陆地飞鱼' / talk …179238 → duplicate + wrong-conversation delivery). When
    the candidate provably belongs to another talk, return '' so the caller
    keeps the synthetic ``card:<talk>`` identity (talk-keyed delivery still
    reaches the right conversation)."""
    nm = str(name_for_talk(talk_id) or "")
    if not nm or nm.startswith("card:"):
        return ""
    kt = str(talk_for_name(nm) or "").strip()
    if kt and kt != str(talk_id):
        return ""
    return nm


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


def unnamed_card_talks(window_s: float = 120.0) -> list:
    """ws173: talks whose latest customer message is a NON-text (card/image)
    frame and which have no resolved name — the in-flight population the send
    JS's ws091 unique-card-row fallback implicitly guesses over. The fallback
    is only mis-delivery-safe when this list is exactly [the target talk]
    (see the guard in feige_send_message)."""
    now_ms = time.time() * 1000.0
    out = []
    with _lock:
        for talk, th in _thread.items():
            if _talk_to_name.get(talk):
                continue
            cust = (th or {}).get("cust") or {}
            if not cust.get("text"):
                continue
            if cust.get("type") == "text":
                continue  # text convs are named directly or bind via ws171
            ts = int(cust.get("ts") or 0)
            if ts and (now_ms - ts) > window_s * 1000.0:
                continue
            out.append(str(talk))
    return out


def bind_unnamed_conv_by_preview(rows, max_age_s: float = 180.0) -> int:
    """ws171: sidebar-preview correlation bridge — the missing talk->name join.

    A conversation whose frames NEVER carry a nickname (first message is a
    name-less card; some clients' text frames are name-less too) is stuck
    under the synthetic ``card:<talk>`` identity: every reply is undeliverable
    and the ws170 parking lot can never flush (live 2026-07-12 19:39-19:56:
    conv 7661603930148767011 texted for 17 minutes, consumed two QA workers,
    zero replies delivered). But the customer's texts ARE on screen — the
    sidebar row shows the latest message as its preview under the customer's
    REAL name. Exact-match the WS-captured text against the scanned sidebar
    previews to bind talk->name.

    *rows* is the backstop scan's [(name, preview), ...]. Mis-delivery safety
    (the ws165 lesson): bind only on an EXACT preview==text match that is
    UNIQUE in BOTH directions (one candidate conv, one sidebar row), text
    length >= 4, and the conv's text fresh (<= max_age_s). Truncated/ellipsed
    previews simply don't match — safe misses.
    Gated ECAN_FEIGE_PREVIEW_NAME_BRIDGE=1 (default on).
    """
    if os.environ.get("ECAN_FEIGE_PREVIEW_NAME_BRIDGE", "1") == "0":
        return 0
    now_ms = time.time() * 1000.0
    bound = 0
    with _lock:
        cands = []
        for talk, th in _thread.items():
            if _talk_to_name.get(talk):
                continue  # already named
            cust = (th or {}).get("cust") or {}
            txt = str(cust.get("text") or "").strip()
            ts = int(cust.get("ts") or 0)
            if not txt or cust.get("type") != "text":
                continue
            if ts and (now_ms - ts) > max_age_s * 1000.0:
                continue
            cands.append((str(talk), txt))
        if not cands:
            return 0
        previews = [str(p or "").strip() for _n, p in rows]
        for name, prev in rows:
            n = str(name or "").strip()
            p = str(prev or "").strip()
            if len(p) < 4 or not n or n.startswith("card:"):
                continue
            if previews.count(p) != 1:
                continue  # ambiguous across rows
            matches = [t for t, txt in cands if txt == p]
            if len(matches) != 1:
                continue  # ambiguous across convs (or none)
            talk = matches[0]
            _routing[n] = talk
            _talk_to_name[talk] = n
            bound += 1
            logger.info(
                f"[ws171] preview-bridge bound conv {talk} -> {n!r} "
                f"(sidebar preview exactly matches the conv's WS text)"
            )
    return bound


# ── ws167: per-CONVERSATION live/dormant state ─────────────────────────────
# The Feige server does NOT push frames for a conversation that wasn't active
# when the page's socket connected, and stops pushing after a 关闭会话 close —
# so WS blindness is PER-CONVERSATION while the old is_dispatch_live() flag is
# per-SOCKET (sticky after the first frame from ANY conversation). Cold-start
# algorithm (2026-07-10, docs/FEIGE_COLDSTART_DETECTION.md):
#   dormant(X) = no WS frame seen for X's conversation since process start OR
#                since X's last 关闭会话 close marker.
# A dormant customer's next message MUST be caught by the DOM side (the ws108
# light sidebar scan); once a frame arrives for the conversation it is LIVE and
# WS owns its realtime detection until the next close marker.
_talk_last_frame: dict[str, float] = {}


def _stamp_conv_live(talk_id: str) -> None:
    """Caller must hold ``_lock``."""
    if talk_id:
        _talk_last_frame[str(talk_id)] = time.time()


def is_conv_live(name_or_talk: str) -> bool:
    """ws167: True when THIS conversation has received at least one WS frame
    since process start / its last 关闭会话 marker (i.e. WS will deliver its
    next message; the DOM watcher may defer to WS). Accepts a customer name or
    a talk_id ('card:<talk>' synthetic names are unwrapped)."""
    k = str(name_or_talk or "").strip()
    if not k:
        return False
    if k.startswith("card:"):
        k = k[5:]
    with _lock:
        if k in _talk_last_frame:
            return True
        _talk = str(_routing.get(k) or "")
        return bool(_talk) and _talk in _talk_last_frame


def mark_conv_dormant(name_or_talk: str) -> None:
    """ws167: re-enter dormant on a 关闭会话 close marker — the server stops
    pushing this conversation's frames after a close (verified live 2026-07-10:
    'sc' WS-live at 19:44, manually closed, 21:38 转人工 arrived with ZERO
    frames), so the DOM watcher must own its next (cold-start) message."""
    k = str(name_or_talk or "").strip()
    if not k:
        return
    if k.startswith("card:"):
        k = k[5:]
    with _lock:
        _talk_last_frame.pop(k, None)
        _talk = str(_routing.get(k) or "")
        if _talk:
            _talk_last_frame.pop(_talk, None)


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


# ws184: click-window talk->name bind. When OUR automation clicks a named sidebar
# row, the page itself sends a read-ack for that row's conversation on its own
# socket within ~2s. Correlating the two binds talk->name WITHOUT waiting for the
# thread DOM to paint — on the 2026-07-26 17:51 dormant-reopen burst the fresh
# messages took 25-44s to paint, which starved every DOM-based binder (ws177
# cmid-join attributed 0) and left the parked card dispatches unresolvable.
# Ambiguity-safe: a click on a DIFFERENT name inside the window clears the record,
# and read-acks WE injected (read_frame_for) are stamped and skipped.
_row_click: dict = {"name": "", "ts": 0.0}
_our_read_ack_ts: dict = {}          # talk_id -> ts of our own injected ack
# ws185: talk_id -> ts of our latest WIRE send into that conv. The 2026-07-26
# 20:56 mis-bind: our wire-delivered placeholder into conv ...690 made the PAGE
# emit a read-ack for that conv 100ms later, which landed inside packet's click
# window → conv bound to the WRONG customer → packet's reply wire-routed into
# 肽斯特's conversation (packet 卡死, 肽斯特 got a stray greeting). Any page
# read-ack for a conv we recently wire-sent into is OUR echo, not click evidence.
_our_wire_send_ts: dict = {}
_last_other_click_ts: dict = {"ts": 0.0}   # most recent click of a DIFFERENT row


def _click_bind_window_s() -> float:
    try:
        return float(os.environ.get("ECAN_FEIGE_CLICK_TALK_BIND_WINDOW_S", "3") or 3)
    except (TypeError, ValueError):
        return 3.0


def note_row_click(name: str) -> None:
    """ws184: record that our automation just clicked/activated *name*'s sidebar row."""
    n = str(name or "")
    if not n or n.startswith("card:"):
        return
    now = time.time()
    with _lock:
        if _row_click["name"] and _row_click["name"] != n:
            # ws185: remember when we last clicked a DIFFERENT row — a page ack can
            # arrive SECONDS after its causing click (they are lazy/batched), so any
            # ack while two rows were clicked close together is unattributable.
            _last_other_click_ts["ts"] = _row_click["ts"]
            if (now - _row_click["ts"]) < _click_bind_window_s():
                # two different rows inside one window — ambiguous, drop both
                _row_click["name"] = ""
                _row_click["ts"] = 0.0
                return
        _row_click["name"] = n
        _row_click["ts"] = now


def _maybe_click_bind(raw: bytes) -> None:
    """ws184: bind the read-ack's talk to the row we just clicked (see _row_click).
    ws185 hardening (after the 2026-07-26 20:56 mis-bind): skip acks for convs we
    recently wire-sent into (our own delivery echo), require a quiet period since
    the last DIFFERENT-row click (late acks are unattributable in bursts), and
    bind identity-only (no _routing) so a wrong bind can never wire-route a
    customer's reply into another conversation — delivery under the real name
    stays on the DOM-by-name lane until a deterministic bind sets routing."""
    if os.environ.get("ECAN_FEIGE_CLICK_TALK_BIND", "1") == "0":
        return
    try:
        now = time.time()
        with _lock:
            nm, ts = _row_click["name"], _row_click["ts"]
            other_ts = _last_other_click_ts["ts"]
        if not nm or (now - ts) > _click_bind_window_s():
            return
        try:
            _quiet_s = float(os.environ.get("ECAN_FEIGE_CLICK_TALK_BIND_QUIET_S", "8") or 8)
        except (TypeError, ValueError):
            _quiet_s = 8.0
        if other_ts and (now - other_ts) < _quiet_s:
            return                           # burst: two rows clicked recently — unattributable
        talk = str(ws_sender.read_ack_talk(raw) or "")
        if not talk:
            return
        with _lock:
            if _talk_to_name.get(talk):
                return                       # already named — nothing to learn
            _ours = _our_read_ack_ts.get(talk)
            _wire = _our_wire_send_ts.get(talk)
        if _ours is not None and (now - _ours) < 10.0:
            return                           # our own injected ack, not the page's
        if _wire is not None and (now - _wire) < 15.0:
            return                           # page acking OUR wire-delivered message
        if bind_talk_name(talk, nm, source="ws184_click_bind", set_routing=False):
            logger.info(
                f"[ws184] click-bind: page read-ack for conv {talk} within "
                f"{now - ts:.1f}s of clicking row {nm!r} — bound identity-only "
                f"(delivery stays DOM-by-name until a deterministic bind)")
    except Exception:
        pass


def restick_identity(talk_id: str, name: str) -> None:
    """ws184: upgrade a talk's sticky dispatch identity from the synthetic
    ``card:<talk>`` to the resolved real *name* (only that direction), so
    follow-up frames don't remap back into the synthetic session."""
    t, n = str(talk_id or ""), str(name or "")
    if not t or not n or n.startswith("card:"):
        return
    with _lock:
        prev = _talk_identity.get(t)
        if prev is None or str(prev).startswith("card:"):
            _talk_identity[t] = n


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
        frame = ws_sender.build_read_ack(tmpl, talk_id=talk_id, cursor=cur)
        if frame is not None:
            with _lock:
                _our_read_ack_ts[talk_id] = time.time()   # ws184: don't click-bind our own ack
                if len(_our_read_ack_ts) > 200:
                    _our_read_ack_ts.pop(next(iter(_our_read_ack_ts)))
        return frame
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
            _maybe_click_bind(raw)                   # ws184: page ack right after our row click
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
    # ws139 DIAG: dump one INBOUND customer frame per conversation (capped) so the fc-send diff
    # has the SAME conversation's inbound reference even if the DOM fallback ALSO fails (no
    # warm-send to compare against). Gated with the ws138 flag. Sensitive: full frame bytes.
    if os.environ.get("ECAN_FEIGE_FC_FRAME_DUMP", "") == "1":
        try:
            for _rm in msgs:
                if (_rm.sender_role == "1" and _rm.conversation_id
                        and _rm.conversation_id not in _recv_dumped_talks
                        and len(_recv_dumped_talks) < 10):
                    import base64 as _b64_rd
                    _recv_dumped_talks.add(_rm.conversation_id)
                    logger.info(
                        f"[FEIGE-FC-RECVDUMP] talk={_rm.conversation_id} "
                        f"uid=...{str(getattr(_rm, 'sender_uid', '') or '')[-8:]} "
                        f"type={_rm.msg_type} name={_rm.customer_name!r} len={len(raw)} "
                        f"b64={_b64_rd.b64encode(raw).decode('ascii')}")
        except Exception:
            pass
    for m in msgs:
        # talk_id is the PER-CONVERSATION id; pigeon_cid is merchant-level (shared by ALL
        # customers of this shop), so routing/confirmation MUST key on talk_id (ws003d).
        talk = m.conversation_id
        # ws167: ANY frame on this conversation proves the socket currently delivers
        # for it — mark LIVE (per-conv dormant/live drives the DOM↔WS cold-start
        # handoff; see is_conv_live/mark_conv_dormant).
        if talk:
            with _lock:
                _stamp_conv_live(talk)
        if m.sender_role == "1" and m.customer_name and talk:
            with _lock:
                _routing[m.customer_name] = talk                  # name -> conversation
                _talk_to_name[talk] = m.customer_name             # reverse, for integrity guard
                _card_bridged_names.discard(m.customer_name)      # ws130: real named frame is authoritative
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
                # ws130: seed the FORWARD route for a name-less card frame via the uid bridge.
                # ws127 made cards RESOLVE to a name (name_for_talk via uid) so DOM delivery
                # finds the sidebar row — but it stripped the talk_id that frame_for used to
                # extract from the 'card:<talk>' identity, so the reply hit no_talk_id ->
                # NO-ROUTE -> DOM (ws129 proved 62/62 NO-ROUTE = no_talk_id, all card-only
                # customers like 'packet' who never sent a named frame). Bridge name->talk here
                # so the reply RAW-routes. Same-customer-safe: talk and name are bound by the
                # customer's unique uid; a real named frame always wins (never overridden — see
                # the discard above). Reversible: ECAN_FEIGE_UID_NAME_BRIDGE=0.
                if (not m.customer_name
                        and os.environ.get("ECAN_FEIGE_UID_NAME_BRIDGE", "1") != "0"):
                    _bn = _name_by_uid.get(m.sender_uid, "")
                    if _bn and not _bn.startswith("card:") and (
                            _bn not in _routing or _bn in _card_bridged_names):
                        _routing[_bn] = talk
                        _talk_to_name.setdefault(talk, _bn)
                        _card_bridged_names.add(_bn)
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
                _hit = None
                if m.client_msg_id and m.client_msg_id == c:
                    _hit = "cid"                                   # exact: our cid echoed back
                elif p.get("talk") and talk == p["talk"] and m.text == p["text"]:
                    _hit = "text"                                  # scoped: same conv + same text
                if _hit:
                    p["confirmed"] = True
                    # ws131 DIAG: log the confirm latency + first-contact tag. A first-contact
                    # send that confirms HERE (even late, past the 8s wait_confirmed window)
                    # PROVES it delivered — the 15s timeout was a slow-echo problem, not loss.
                    # If fc sends never appear here, they are IGNORED by the server (lost).
                    try:
                        _age = time.time() - p.get("ts", 0)
                        logger.info(
                            f"[FEIGE-WS-FC-CONFIRM] fc={p.get('fc')} via={_hit} "
                            f"confirm_latency={_age:.1f}s talk={p.get('talk')} "
                            f"(fc=True + high latency => first-contact DELIVERS but echo is slow)")
                    except Exception:
                        pass


def talk_for_cmid(cmid: str) -> str:
    """ws177: reverse lookup by client_message_id — the deterministic DOM<->WS
    join for card-only cold starts. The 2026-07-13 20:51:59 card-DOM dump
    proved the thread wrap's ``data-id`` for an assistant-recommendation card
    (e.g. ``2_<uuid>_template``) IS the WS frame's ``s:client_message_id``, so
    a named-row thread scrape can identify WHICH conversation the on-screen
    card belongs to — globally unique per message, mis-delivery-proof."""
    c = str(cmid or "").strip()
    if not c:
        return ""
    with _lock:
        for talk, th in _thread.items():
            cust = (th or {}).get("cust") or {}
            if str(cust.get("cmid") or "") == c:
                return str(talk)
    return ""


def bind_talk_name(talk_id: str, name: str, source: str = "",
                   set_routing: bool = True) -> bool:
    """ws177: safely bind an unnamed conversation to a real customer name.
    Refuses card:/empty names and never overwrites an existing binding.

    ws185: *set_routing=False* binds identity only (_talk_to_name, used by
    name_for_talk / de-synthesis / park resolution) WITHOUT the name->talk
    _routing entry that wire sends key on. Correlational binders (click-bind)
    must use it: a wrong _routing entry wire-routes the customer's own replies
    into someone else's conversation (2026-07-26 20:56 packet->肽斯特), while a
    wrong identity-only bind degrades to the guarded DOM-by-name lane."""
    t = str(talk_id or "").strip()
    n = str(name or "").strip()
    if not t or not n or n.startswith("card:"):
        return False
    with _lock:
        if _talk_to_name.get(t):
            return False
        if set_routing:
            _routing[n] = t
        _talk_to_name[t] = n
    logger.info(
        f"[ws177] bound conv {t} -> {n!r} (source={source or 'manual'}"
        f"{'' if set_routing else ', identity-only'})"
    )
    return True


def can_send_warm_card(customer_name: str) -> bool:
    """ws176: True iff *customer_name* is a synthetic ``card:<talk>`` identity whose
    embedded talk has a WARM per-talk template — i.e. frame_for() will build a
    normal (non-first-contact) raw frame that echo-confirms in <1s. Used by
    hot_path_v2 to skip the DOM typing lock for such sends: live 2026-07-13
    18:10:29-18:10:54 two raw-confirmed card sends held the global typing lock
    ~25s total (open_session no-op + diag overhead) and starved a cold-start
    text customer's enrich to a 42s first reply. Deliberately NARROW — no
    first-contact leg (ws137: fc does not reliably deliver), no WIDE semantics
    (the ws071 placeholder-flood lesson)."""
    ck = str(customer_name or "")
    if not ck.startswith("card:"):
        return False
    talk = ck[len("card:"):].strip()
    if not talk:
        return False
    with _lock:
        return talk in _templates


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
        # ⚠ ws131 (2026-07-05): first-contact raw is PROVEN not to echo-confirm — a cold-start
        # A/B showed 9/9 first-contact sends UNCONFIRMED (each burned the 15s job timeout) vs
        # 2/2 warm per-talk sends confirmed. Keep ECAN_FEIGE_WS_FIRST_CONTACT OFF (default):
        # cold-start reply-#1 then falls to DOM, which delivers reliably AND seeds the per-talk
        # template so reply-#2+ warm-raw-confirm in <1s. The old reason to keep first-contact on
        # (ws092 cold-start typing-lock self-block) is moot — ws127-130 unloaded the lock. Only
        # re-enable after fixing first-contact confirmation (see [FEIGE-WS-FC-CONFIRM], ws131).
        # ws028: no per-conversation template yet — clone the session-wide donor and FULLY
        # retarget it to THIS customer. Chat sends route by security_receiver_id (verified
        # 2026-06-08: the .8.8.100 envelope carries security_receiver_id, no talk_id), and
        # that id == the customer's inbound security_sender_id, captured in _uid_by_talk. We
        # need it to retarget safely; without it we CANNOT first-contact (would mis-deliver
        # to the donor) → fall back to DOM. build_first_contact_frame swaps the receiver id
        # 1:1 (same 88-char length) and returns None if it can't, so it's safe-by-construction.
        if not target_uid:
            # ws129 DIAG: first-contact is the ONLY raw path for a conversation whose
            # reply-#1 hasn't seeded a per-talk template. It needs the customer's
            # security_sender_id (captured from an inbound role=1 frame). Missing uid =>
            # this conv can NEVER raw-route reply-#1 => every send goes DOM. At 1-vs-7
            # with many new/reopened convs that is the NO-ROUTE flood feeding the blackout.
            logger.info(
                f"[FEIGE-WS-NOROUTE] cust={customer_name!r} talk={talk or '?'} "
                f"reason=first_contact_but_no_receiver_uid "
                f"(per_talk_tmpl=N session_tmpl=Y uid=N) — DOM fallback")
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
        # ws129 DIAG: name the exact bootstrap gap behind every "no send template
        # captured yet" NO-ROUTE (read-only; the send still falls to DOM). Lets the next
        # 1-vs-7 run bucket WHY the raw lane can't route — is it a missing session donor
        # (observer not capturing outgoing frames post-reconnect), first-contact disabled,
        # or a talk-id gap — instead of guessing at the raw internals. Kill: ECAN_FEIGE_WS_NOROUTE_DIAG=0.
        if os.environ.get("ECAN_FEIGE_WS_NOROUTE_DIAG", "1") != "0":
            if not talk:
                _r = "no_talk_id"
            elif tmpl is not None:
                _r = "per_talk_template_build_failed"
            elif not ws_enabled("first_contact"):
                _r = "no_per_talk_template_and_first_contact_disabled"
            elif session_tmpl is None:
                _r = "no_session_donor_captured (observer not seeing outgoing frames?)"
            else:
                _r = "first_contact_build_returned_none"
            logger.info(
                f"[FEIGE-WS-NOROUTE] cust={customer_name!r} talk={talk or '?'} reason={_r} "
                f"(per_talk_tmpl={'Y' if tmpl else 'N'} session_tmpl={'Y' if session_tmpl else 'N'} "
                f"uid={'Y' if target_uid else 'N'})")
        return None
    # ws138 DIAG: dump the built send frame so a CONFIRMED warm frame and an UNCONFIRMED
    # first-contact frame from the SAME run can be diffed offline to find exactly what the
    # retarget leaves mis-addressed (the reason first-contact raw never echo-confirms — 0/27
    # in the ws136 run). Correlate with [FEIGE-WS-FC-CONFIRM] by cid. Opt-in, sensitive (full
    # frame bytes incl. ids): ECAN_FEIGE_FC_FRAME_DUMP=1, default OFF.
    _fd_kind = "fc" if tmpl is None else "warm"
    if (os.environ.get("ECAN_FEIGE_FC_FRAME_DUMP", "") == "1"
            and (_fd_kind, str(talk)) not in _framedump_seen):
        try:
            import base64 as _b64_fd
            _framedump_seen.add((_fd_kind, str(talk)))
            _dd = ws_sender._wr().decode(frame)
            _ftalk = ws_sender.get_path(_dd, ws_sender.SENT_TALK_PATH) if _dd else None
            _fconv = ws_sender.get_path(_dd, ws_sender.SENT_CONV_PATH) if _dd else None
            _frid = ws_sender.frame_receiver_id(frame)
            logger.info(
                f"[FEIGE-FC-FRAMEDUMP] kind={_fd_kind} cid={cid} "
                f"talk={talk} frame_talk={_ftalk!r} pigeon_cid={_fconv!r} "
                f"rid_tail=...{(_frid[-8:] if _frid else b'').decode('latin-1', 'replace')} "
                f"len={len(frame)} b64={_b64_fd.b64encode(frame).decode('ascii')}")
        except Exception as _fd_e:
            logger.debug(f"[FEIGE-FC-FRAMEDUMP] failed: {_fd_e}")
    _note_our_cmid(cid)   # ws008: our WS send -> echo with this cid is definitively ours
    now = time.time()
    with _lock:
        for c in [c for c, p in _pending.items() if now - p["ts"] > _PENDING_TTL]:
            _pending.pop(c, None)
        # ws131 DIAG: tag WHETHER this send is a first-contact (retargeted donor, no
        # per-talk template) vs a warm per-talk send. The 2026-07-05 data showed ALL 9
        # first-contact raw sends went UNCONFIRMED while warm sends confirmed 2/2 — so we
        # need to know if first-contact frames actually DELIVER (a LATE echo eventually
        # confirms = latency only) or are IGNORED by the server (no echo ever = message
        # LOST behind presume-delivered). note_recv_frame logs the confirm latency + fc tag.
        _pending[cid] = {"text": text, "talk": str(talk or ""), "confirmed": False,
                         "ts": now, "fc": tmpl is None}
        # ws185: stamp the wire send per conv — the page reacts to OUR delivered
        # message with a read-ack for that conv, which must never be mistaken for
        # row-click evidence by _maybe_click_bind (the 20:56 packet mis-bind).
        if talk:
            _our_wire_send_ts[str(talk)] = now
            if len(_our_wire_send_ts) > 200:
                _our_wire_send_ts.pop(next(iter(_our_wire_send_ts)))
    return frame, cid


def pending_is_fc(cid: str) -> bool:
    """ws133: True if the pending send for *cid* was a first-contact (retargeted donor)
    frame (no per-talk template). ws131's [FEIGE-WS-FC-CONFIRM] proved first-contact raw
    DELIVERS (fc=True confirms at 0.6s AND 15.6s) — the echo just often lands past the 8s
    wait_confirmed window, so it looked UNCONFIRMED and burned the 15s job timeout. This lets
    the send path PRESUME-deliver a first-contact raw send instead of waiting."""
    with _lock:
        p = _pending.get(str(cid))
        return bool(p and p.get("fc"))


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
    # ws169: freshness gate. A legit fast-path hit is seconds old (enrich runs right
    # after the frame); a minutes-old entry means the WS stream went quiet for this
    # conversation (close/dormant) and the cache is the PRE-close message — serving
    # it short-circuits the DOM scrape with stale data (live 2026-07-12 09:46: the
    # 09:23 bubble answered a 09:46 reopen). Stale -> None -> DOM scrape.
    try:
        _max_age_s = float(os.environ.get("ECAN_FEIGE_WS_SCRAPE_MAX_AGE_S", "180") or 180)
    except (TypeError, ValueError):
        _max_age_s = 180.0
    _cust_ts_ms = int(cust.get("ts") or 0)
    if (_max_age_s > 0 and _cust_ts_ms > 0
            and (time.time() * 1000.0 - _cust_ts_ms) > _max_age_s * 1000.0):
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
