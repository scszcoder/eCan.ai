"""Live SHADOW-mode Feige (飞鸽 / jinritemai) WebSocket observer — PLATFORM-SPECIFIC HOOK.

Attaches an isolated CDP client to the Feige tab(s), decodes incoming Frontier
frames via :mod:`ws_reader`, and LOGS the customer messages it finds.

SHADOW mode: log-only. It runs ALONGSIDE the DOM 新消息 monitor and dispatches
NOTHING — so WS-detection latency can be compared head-to-head with the
renderer-saturating scrape path before anything depends on it. Each detection is
logged as ``[FEIGE-WS-SHADOW] ...`` with the message text + msg_id; the log
timestamp is when the socket delivered it, so diffing against the DOM monitor's
``dom_observed`` for the same text gives the real detection-latency delta.

Entirely Feige-specific (Frontier frame schema, jinritemai WS) so it lives in
``hooks/external/feige_chat/`` — the generic ``event_monitor`` only thin-calls
:func:`start_ws_shadow_observer`. Env-gated (``ECAN_FEIGE_WS_READER=1``), fully
isolated on its own CDP client, and best-effort: any failure is swallowed and
never touches the live monitor.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
from typing import Any

from . import human_mode, ws_coverage, ws_reader, ws_session

logger = logging.getLogger("eCan")

# ws029: the observer owns the only CDP handle to the dedicated DETECTION tab's
# authed page socket — an IDLE renderer (sidebar poll only). Register an injector
# here so OTHER subsystems (notably the placeholder sender, running on a different
# loop) can deliver a frame on that congestion-immune lane, the same way the
# read-ack does. Populated by the observer once attached; cleared is harmless
# (the bridge fails closed -> caller falls back).
_DET_TAB_INJECTOR: dict = {"fn": None, "loop": None}


async def inject_frame_on_detection_tab(frame_bytes: bytes, timeout: float = 3.0) -> str:
    """ws029/ws031: send *frame_bytes* on the detection tab's authed page socket
    (idle renderer), bridging from the caller's loop to the observer's loop.

    Returns a TRI-STATE so the caller never double-sends (the ws029 duplicate trap):
      'SENT'    — the page-socket eval confirmed the frame is on the wire.
      'UNKNOWN' — the bridge timed out: the eval was DISPATCHED to the (idle)
                  detection renderer and most likely sent, so the caller MUST treat
                  it as committed and NOT re-send the same frame elsewhere.
      ''        — definitely not sent (no observer attached / no detection socket /
                  eval returned non-SENT); the caller may safely send on another tab.
    """
    reg = _DET_TAB_INJECTOR
    fn = reg.get("fn")
    loop = reg.get("loop")
    if fn is None or loop is None:
        return ""
    try:
        cur = asyncio.get_running_loop()
    except RuntimeError:
        cur = None
    try:
        if cur is loop:
            return "SENT" if await asyncio.wait_for(fn(frame_bytes), timeout) else ""
        fut = asyncio.run_coroutine_threadsafe(fn(frame_bytes), loop)
        return "SENT" if await asyncio.wait_for(asyncio.wrap_future(fut), timeout) else ""
    except asyncio.TimeoutError:
        return "UNKNOWN"
    except Exception:
        return ""


_ENV = "ECAN_FEIGE_WS_READER"


_DISPATCH_ENV = "ECAN_FEIGE_WS_DISPATCH"


async def start_ws_shadow_observer(session: Any, target_id: str, label: str = "",
                                   dispatch_fn=None) -> Any:
    """Start the WS observer.  Returns the CDP client (so the caller can stop it on
    monitor teardown) or ``None`` when disabled / on any failure.

    ``dispatch_fn`` (optional): a callable ``(item: dict) -> None`` that injects a
    detected message into the normal browser_event dispatch.  It is invoked ONLY
    when ``ECAN_FEIGE_WS_DISPATCH=1`` — otherwise the observer stays pure shadow
    (log-only).  When dispatch is on, the caller is expected to suppress the DOM
    monitor's own dispatch so the two paths don't double-fire (the WS text is
    full while the DOM sidebar preview can be truncated, so they don't dedup)."""
    ws_session.set_dispatch_live(False)   # reset; only flips True once we confirm-start below
    if not ws_session.ws_enabled("reader"):
        return None
    do_dispatch = dispatch_fn is not None and ws_session.ws_enabled("dispatch")
    do_read_ack = ws_session.ws_enabled("read_ack")

    cdp_url = getattr(session, "cdp_url", None)
    if not cdp_url:
        bp = getattr(session, "browser_profile", None)
        cdp_url = getattr(bp, "cdp_url", None) if bp else None
    if not cdp_url:
        logger.warning("[FEIGE-WS-SHADOW] no cdp_url on session — observer not started")
        return None

    try:
        from cdp_use import CDPClient

        client = CDPClient(url=cdp_url)
        await client.start()

        # The Frontier WS lives on the real Feige SPA tab.  Attach to the monitor
        # tab plus any other jinritemai tabs (main + dedicated detection) so we
        # never miss the socket regardless of which tab holds it.
        try:
            tinfos = (await client.send_raw("Target.getTargets", {})).get("targetInfos", [])
        except Exception:
            tinfos = []
        targets = [target_id] + [
            t.get("targetId") for t in tinfos
            if t.get("type") == "page"
            and "jinritemai" in (t.get("url") or "")
            and t.get("targetId") and t.get("targetId") != target_id
        ]
        sids = []
        _sid_by_tid: dict = {}   # ws019: target_id -> session_id, to prefer the detection tab
        for tid in targets:
            if not tid:
                continue
            try:
                sid = (await client.send_raw(
                    "Target.attachToTarget", {"targetId": tid, "flatten": True})).get("sessionId")
                if sid:
                    await client.send_raw("Network.enable", {}, session_id=sid)
                    sids.append(sid)
                    _sid_by_tid[tid] = sid
            except Exception:
                pass
        if not sids:
            logger.warning("[FEIGE-WS-SHADOW] no sessions attached — observer not started")
            await client.stop()
            return None

        # Arm the page socket-capture hook now so window.__ecan_feige_ws is filled by
        # an early heartbeat — off-DOM sends then work on the first reply, not the 2nd.
        _diag_on = os.environ.get("ECAN_FEIGE_WS_RAW_DIAG", "") == "1"
        for sid in sids:
            try:
                await client.send_raw(
                    "Runtime.evaluate",
                    {"expression": ws_session.arm_socket_hook_js(), "returnByValue": True},
                    session_id=sid)
                # ws069: also arm the constructor + onclose/onopen reconnect tap (diag only)
                if _diag_on:
                    await client.send_raw(
                        "Runtime.evaluate",
                        {"expression": ws_session.arm_socket_ctor_diag_js(), "returnByValue": True},
                        session_id=sid)
            except Exception:
                pass

        seen: set = set()
        handover_seen: set = set()   # talk_ids already acked for a button 人工 handover
        stats = {"frames": 0, "msgs": 0}
        # ws059: arm WS-owns-dispatch (which pauses the DOM monitor scrape) only on the
        # FIRST actually-received frame — NOT at CDP-handler registration. A pre-existing
        # IM socket emits no frames until it reconnects, so registering the handler does
        # not mean frames are flowing. Suppressing the DOM monitor before the socket
        # delivers anything opens a cold-start blind window (live 2026-06-14: 49s gap,
        # 11:31:48 register -> 11:32:37 socket frames; '红黑款有货吗' at 11:32:30 lost by
        # both paths). Until the first frame proves the socket live, DOM stays the backup.
        _dispatch_armed = [False]
        _socket_sid = [None]   # ws009: remember the tab that actually holds the socket
        # ws075 Phase 0 + reconnect-follow state. Both gated; counters are best-effort.
        _cov_on = ws_coverage.enabled()
        _rcf_on = os.environ.get("ECAN_FEIGE_WS_RECONNECT_FOLLOW", "") == "1"
        _obs_start_ts = time.time()          # for the cold-start blind-window metric
        _last_frame_ts = [time.time()]       # updated on every received frame
        _last_socket_create_ts = [0.0]       # updated on Network.webSocketCreated
        _awaiting_frame_after_create = [False]

        # ws029: expose the detection-tab page-socket inject to other subsystems
        # (the placeholder sender) so they can ride the same idle-renderer lane the
        # read-ack uses. Returns True iff the inject reports 'SENT'.
        async def _inject_on_detection_tab(frame_bytes: bytes) -> bool:
            try:
                from .tab_pool import get_pool as _gp
                _dsid = _sid_by_tid.get(_gp().get_detection_tab())
            except Exception:
                _dsid = None
            if not _dsid or _dsid not in sids:
                return False
            try:
                res = await client.send_raw(
                    "Runtime.evaluate",
                    {"expression": ws_session.inject_js(frame_bytes),
                     "returnByValue": True},
                    session_id=_dsid)
                return (((res or {}).get("result") or {}).get("value")) == "SENT"
            except Exception:
                return False
        try:
            _DET_TAB_INJECTOR["fn"] = _inject_on_detection_tab
            _DET_TAB_INJECTOR["loop"] = asyncio.get_running_loop()
        except Exception:
            pass
        _det_ack_logged = [False]  # ws019: log once when read-ack first goes via detection tab

        async def _send_read_ack(frame_bytes: bytes) -> None:
            # ws018 (#1): route the read-ack OFF the renderer when enabled. Under
            # N-customer load the eval-inject (Runtime.evaluate) below queues behind
            # multi-second DOM send evals on the SAME CDP/renderer (a send holds the
            # op-lock for its whole runtime_evaluate — observed up to 29s on
            # 2026-06-07 一对六), so 已读 froze for minutes and only a later message's
            # cursor-based read-ack dragged it through. The raw socket bypasses the
            # renderer + CDP path entirely; read-acks are the safest frame to send raw
            # (idempotent read receipt, far lower anti-bot risk than a message). On ANY
            # failure raw_send() returns False and we fall through to the proven
            # eval-inject below. Gated: ECAN_FEIGE_WS_READ_ACK_RAW=1 (or the message
            # raw-send master ECAN_FEIGE_WS_SEND_RAW=1).
            if (os.environ.get("ECAN_FEIGE_WS_READ_ACK_RAW", "") == "1"
                    or os.environ.get("ECAN_FEIGE_WS_SEND_RAW", "") == "1"):
                try:
                    from . import ws_raw_sender as _wsr
                    if await _wsr.raw_send(frame_bytes):
                        return
                except Exception as _rawerr:
                    logger.debug(f"[FEIGE-WS-READ] raw read-ack failed -> eval ({_rawerr})")
            # tier0 已读: inject the read-ack on the page's authed socket (lock-free,
            # idempotent). ws009: inject on the KNOWN socket tab first and STOP on 'SENT'
            # — spraying every attached tab on every message piled Runtime.evaluate load
            # onto the very renderer that saturates under 1-vs-N (the 2026-06-06 freeze).
            js = ws_session.inject_js(frame_bytes)
            # ws019: prefer the dedicated DETECTION tab's socket for the read-ack.
            # Its renderer is idle (sidebar poll only — no per-customer bubble scrapes
            # or multi-second DOM send evals), so the eval-inject does NOT queue behind
            # the main tab's renderer (the 2026-06-07 一对六 已读 freeze). And it is a
            # REAL authed page socket, so the server HONORS the read receipt — unlike
            # ws018's separate raw socket, which Frontier accepted but did not apply.
            # Gated ECAN_FEIGE_WS_READ_ACK_DET_TAB=1; if the detection tab has no socket
            # the inject just isn't 'SENT' and we fall through to the other tabs
            # (== current behavior, no regression).
            _pref = []
            if os.environ.get("ECAN_FEIGE_WS_READ_ACK_DET_TAB", "") == "1":
                try:
                    from .tab_pool import get_pool as _gp
                    _dsid = _sid_by_tid.get(_gp().get_detection_tab())
                    if _dsid and _dsid in sids:
                        _pref = [_dsid]
                except Exception:
                    pass
            order = _pref + \
                    ([_socket_sid[0]] if (_socket_sid[0] in sids and _socket_sid[0] not in _pref) else []) + \
                    [s for s in sids if s not in _pref and s != _socket_sid[0]]
            for sid in order:
                try:
                    res = await client.send_raw(
                        "Runtime.evaluate",
                        {"expression": js, "returnByValue": True}, session_id=sid)
                    val = ((res or {}).get("result") or {}).get("value")
                    if val == "SENT":
                        _socket_sid[0] = sid     # found the socket tab; don't touch others
                        if _pref and sid == _pref[0] and not _det_ack_logged[0]:
                            _det_ack_logged[0] = True
                            logger.info(
                                "[FEIGE-WS-READ] read-ack now off-renderer via dedicated detection tab")
                        return
                except Exception:
                    pass
            # ws030 (Fix C): observability. We fell through the loop → NO attached
            # tab's page socket accepted the read-ack (none returned 'SENT'), so 已读
            # was silently NOT marked for this message. This is the only untraced
            # 已读-miss path (e.g. the detection tab momentarily lost its captured
            # socket). Log it so the customer's ~70% 已读 becomes diagnosable.
            logger.warning(
                f"[FEIGE-WS-READ] read-ack NOT accepted on any of {len(order)} tab(s) "
                f"— 已读 MISSED this message (pref_det_tab={bool(_pref)} "
                f"known_socket_sid={_socket_sid[0]!r})")

        def _on_frame(params, session_id=None):
            try:
                resp = params.get("response", {}) or {}
                if int(resp.get("opcode", -1)) != 2:   # binary protobuf only
                    return
                payload = resp.get("payloadData", "") or ""
                if not payload:
                    return
                raw = base64.b64decode(payload, validate=False)
                stats["frames"] += 1
                # ws075: frame-flow tracking for the reconnect-follow health check +
                # the reconnect coverage metric (did frames resume after a new socket?).
                _last_frame_ts[0] = time.time()
                if _awaiting_frame_after_create[0]:
                    _awaiting_frame_after_create[0] = False
                    if _cov_on:
                        ws_coverage.note("frames_after_create")
                ws_session.note_recv_frame(raw)   # feed routing + send-confirmation
                # ws059: first real frame -> NOW the WS path is actually delivering, so
                # arm WS-owns-dispatch (which pauses the DOM monitor). Before this point
                # the DOM monitor must keep scraping so a message arriving during the
                # socket cold-start/reconnect window is not lost by both paths.
                if do_dispatch and not _dispatch_armed[0]:
                    _dispatch_armed[0] = True
                    ws_session.set_dispatch_live(True)
                    if _cov_on:
                        ws_coverage.note_coldstart_gap((time.time() - _obs_start_ts) * 1000.0)
                    logger.info(
                        "[FEIGE-WS-SHADOW] first frame received -> WS now owns dispatch "
                        "(DOM monitor scrape paused from here)")
                # HumanMode: scan THIS frame for a competing bot answer (智能客服/
                # 机器人 — role=2, sender name matches a configured pattern, NOT our
                # own send). If one answered, suppress our own reply for that turn.
                # Done BEFORE the customer loop because that loop returns early on a
                # dedup hit and would skip this otherwise.
                if human_mode.enabled():
                    try:
                        for _bm in ws_reader.extract_messages(raw):
                            if _bm.sender_role == "2" and human_mode.is_competing_sender(_bm.customer_name):
                                _bc = ws_session.name_for_talk(_bm.conversation_id) or _bm.conversation_id
                                human_mode.note_competing_answer(
                                    _bc, _bm.customer_name, _bm.text, _bm.ts_ms)
                            elif _bm.sender_role == "2" and _bm.text:
                                # learn unknown server-side sender names (helps the
                                # store owner populate competing_answer_sender_patterns,
                                # e.g. the 机器人's real display name).
                                logger.debug(
                                    f"[HumanMode] role=2 sender seen name={_bm.customer_name!r} "
                                    f"conv={_bm.conversation_id} text={_bm.text[:40]!r}")
                    except Exception as _ce:
                        logger.debug(f"[HumanMode] competing-answer scan error: {_ce}")
                    # HumanMode: button 转人工/人工 handover. Unlike a TYPED '人工'
                    # (which arrives as a normal customer message and is caught by the
                    # keyword short-circuit in the customer loop below), the handover
                    # BUTTON emits a 'switch_human' frame with NO chat message — so it
                    # never reaches dispatch. Detect it here and ack it the same way.
                    # The frame retransmits in a sub-second burst; ack once per talk_id.
                    try:
                        _hv = ws_reader.detect_handover(raw)
                        if _hv:
                            # Record the human-mode ENTRY signal. switch_human is the
                            # first confirmed signal that a conversation switched to human
                            # service. NOT gated on yet — should_respond() stays always-True
                            # until we capture and confirm the silent 智能客服 auto-switch
                            # case (it may emit a different event). Idempotent.
                            human_mode.set_human_mode(_hv.talk_id, "human")
                        if _hv and _hv.talk_id not in handover_seen:
                            handover_seen.add(_hv.talk_id)
                            _hv_name = ws_session.name_for_talk(_hv.talk_id)
                            if _hv_name:
                                from . import placeholder_timer as _hv_ph
                                _hv_ph.note_handover_ack_needed(_hv_name)
                                logger.info(
                                    f"[HumanMode] button handover {_hv.triggered_word!r} "
                                    f"talk={_hv.talk_id} -> cust={_hv_name!r}; "
                                    f"ack {human_mode.human_ack_text()!r}, no LLM dispatch")
                            else:
                                logger.info(
                                    f"[HumanMode] button handover {_hv.triggered_word!r} "
                                    f"talk={_hv.talk_id} -> no known customer name "
                                    f"(no prior customer frame this session); cannot ack-route")
                    except Exception as _hve:
                        logger.debug(f"[HumanMode] handover detect error: {_hve}")
                for m in ws_reader.customer_messages(raw):   # sender_role == customer
                    # ws025: a product card the customer shares carries no
                    # nickname/uname, so the reader leaves customer_name empty →
                    # the item is dropped at the actionable
                    # required_field_missing:customer gate (live trace packet
                    # 10:32:50 + 瓦哒嘻哇 cards, all customer='' → never answered).
                    # Attribute it to the conversation's known customer (seeded by
                    # prior text frames) so the card — now carrying the product
                    # title from ws_reader._card_text — reaches the Q&A worker.
                    # Kill-switch: ECAN_FEIGE_WS_CARD_PARSE=0 reverts to dropping.
                    if (
                        not m.customer_name
                        and m.conversation_id
                        and os.environ.get("ECAN_FEIGE_WS_CARD_PARSE", "1") != "0"
                    ):
                        _nm = ws_session.name_for_talk(m.conversation_id)
                        if _nm:
                            m.customer_name = _nm
                            logger.info(
                                f"[FEIGE-WS-CARD] attributed name-less "
                                f"{m.msg_type or 'frame'} to cust={_nm!r} via "
                                f"conv={m.conversation_id} text={m.text[:60]!r}"
                            )
                    # ws033c: a product card shared ON ENTRY has no name yet, and for
                    # a card-ONLY conversation no named frame ever arrives. ws033
                    # dropped it forever (`continue`); ws033b tried a time-hold but it
                    # NEVER expired — card retransmits are a sub-second burst (live:
                    # 15 frames in 1.02s) and the expiry was only re-checked on frame
                    # arrival, so after the burst the card was held forever -> stuck.
                    # Just attribute it to a stable synthetic name and dispatch NOW;
                    # the conv|text dedup below prevents a duplicate if a named
                    # retransmit resolves the real name later (that card is deduped).
                    if m.msg_type == "template_card" and not m.customer_name:
                        m.customer_name = f"card:{m.conversation_id}"
                        if f"card|{m.conversation_id}|{m.text}" not in seen:
                            logger.info(
                                f"[FEIGE-WS-CARD] nameless card -> synthetic name "
                                f"{m.customer_name!r} conv={m.conversation_id} "
                                f"text={m.text[:60]!r}")
                    # ws070: collapse this talk_id onto ONE sticky dispatch identity so a
                    # name-less entry card and the customer's later named frames don't fork
                    # into two parallel QA pipelines (the 肽斯特 split → duplicate reply +
                    # fragmented context + doubled renderer load). First identity per talk_id
                    # wins; delivery is unaffected (frame_for de-synthesizes card:<talk>).
                    # Applied before the dedup key / read-ack / placeholder so every
                    # downstream key is canonical. Kill switch: STICKY_IDENTITY=0.
                    if (
                        m.conversation_id
                        and os.environ.get("ECAN_FEIGE_WS_STICKY_IDENTITY", "1") != "0"
                    ):
                        _canon = ws_session.sticky_identity(m.conversation_id, m.customer_name)
                        if _canon and _canon != m.customer_name:
                            logger.info(
                                f"[FEIGE-WS-IDENTITY] remap cust={m.customer_name!r} -> "
                                f"{_canon!r} (sticky for talk={m.conversation_id})")
                            m.customer_name = _canon
                    # ws027: product-card frames retransmit (5x in <1s) with
                    # UNSTABLE msg_ids — field-3 is sometimes the real id,
                    # sometimes a conv-like snowflake — so an msg_id-keyed dedup
                    # lets the SAME card dispatch 5x → PreDispatch mutual-exclusion
                    # collisions (live 肽斯特 13:40:37-41). Cards carry their
                    # goods_id inside the enriched text ([商品卡片] <title>
                    # 商品ID:<id>), so conv|text is a stable dedup key for them.
                    if m.msg_type == "template_card":
                        key = f"card|{m.conversation_id}|{m.text}"
                    else:
                        key = m.msg_id or f"{m.conversation_id}|{m.text}"
                    if key in seen:
                        return  # already handled this message (frames repeat)
                    seen.add(key)
                    stats["msgs"] += 1
                    # ws075 Phase 0: per-unique-message coverage — WS saw this message, and
                    # whether its identity resolved to a real name or fell to the card:<talk>
                    # synthetic (= a name DOM would have given). Ratio drives Phase 2.
                    if _cov_on:
                        ws_coverage.note("ws_first_seen")
                        ws_coverage.note(
                            "name_synthetic" if str(m.customer_name or "").startswith("card:")
                            else "name_resolved")
                    # ws004c (tier2): record arrival NOW (the socket sees it within ~3s
                    # of the customer typing) so the placeholder deadline anchors to true
                    # arrival, not the later PreDispatch arm-time — under WS dispatch
                    # nothing else records first-seen, so the deadline would otherwise
                    # slip and the 过渡句 land past Feige's 40s window.
                    try:
                        from . import placeholder_timer as _ph_fs
                        _ph_fs.mark_message_first_seen(m.customer_name, m.msg_id)
                    except Exception:
                        pass
                    # tier0 已读: mark this message read over WS FIRST (highest priority,
                    # before dispatch) so the customer sees 已读 ASAP — WS send otherwise
                    # bypasses the DOM open that used to mark-read as a side-effect.
                    if do_read_ack:
                        try:
                            _rf = ws_session.read_frame_for(m.conversation_id, m.read_cursor)
                            if _rf:
                                asyncio.get_running_loop().create_task(_send_read_ack(_rf))
                                logger.info(
                                    f"[FEIGE-WS-READ] read-ack talk={m.conversation_id} "
                                    f"cust={m.customer_name!r} cursor={m.read_cursor}")
                        except Exception as _re:
                            logger.debug(f"[FEIGE-WS-READ] read-ack failed: {_re}")
                    # HumanMode: record this customer turn (clears stale
                    # suppression), short-circuit a 人工 request with the configured
                    # ack smiley, then honour the human-mode gate. All no-ops unless
                    # ECAN_FEIGE_HUMAN_MODE=1.
                    if human_mode.enabled():
                        human_mode.note_customer_turn(m.customer_name, m.ts_ms)
                        if human_mode.is_human_trigger(m.text):
                            try:
                                from . import placeholder_timer as _hm_ph
                                _hm_ph.note_handover_ack_needed(m.customer_name)
                                logger.info(
                                    f"[HumanMode] 人工 trigger from cust={m.customer_name!r} "
                                    f"text={m.text[:40]!r} — ack {human_mode.human_ack_text()!r}, "
                                    f"skipping LLM dispatch")
                            except Exception as _he:
                                logger.debug(f"[HumanMode] handover-ack enqueue failed: {_he}")
                            continue
                        if not human_mode.should_respond(m.conversation_id):
                            logger.info(
                                f"[HumanMode] not in human mode for conv={m.conversation_id} "
                                f"cust={m.customer_name!r} — skipping dispatch")
                            continue
                    tag = "DISPATCH" if do_dispatch else "SHADOW"
                    logger.info(
                        f"[FEIGE-WS-SHADOW] mode={tag} customer={m.customer_name!r} "
                        f"conv={m.conversation_id} msg_id={m.msg_id} ts_ms={m.ts_ms} "
                        f"type={m.msg_type} text={m.text[:80]!r}"
                    )
                    if do_dispatch:
                        # generic detected-item shape the browser_event pipeline expects;
                        # identity_key mirrors the DOM monitor's dedup key.
                        # ws013: key session/customer fields on the customer NAME, the
                        # way the DOM monitor item does and the way the whole pipeline
                        # keys sessions (every send/ledger uses session_id="sc"). The
                        # earlier shape set customer_id=talk_id with NO session_id field,
                        # so _extract_actionable_items dropped it (session_keys resolved
                        # empty → actionable=0, total=1) and the turn died at PreDispatch
                        # with raw_items=0. Masked until ws010+single-tab made WS dispatch
                        # the SOLE path (no DOM dom_observed item to carry it). The real
                        # talk_id stays available under talk_id; WS send routing reads it
                        # from ws_session (fed by note_recv_frame), not from this item.
                        item = {
                            "customer_name": m.customer_name,
                            "name": m.customer_name,
                            "session_id": m.customer_name,
                            "customer_id": m.customer_name,
                            "talk_id": m.conversation_id,
                            "last_message": m.text,
                            "latest_message": m.text,
                            "msg_id": m.msg_id,
                            # ws015: parity with the DOM item, which carries
                            # latest_message_msg_id so the Q&A worker payload can
                            # set a source-msg-id for its stale-guard (frontdesk_dispatch
                            # reads `item.get("latest_message_msg_id") or source_customer_msg_id`
                            # and only forwards it when non-empty). The WS frame's msg_id IS
                            # the client_message_id, kept consistent with the DOM msg_id per
                            # ws008, so it's a safe source id. Front-desk-side dedup already
                            # uses enrich's authoritative scraped_msg_id; this only restores
                            # the worker-side guard that was silently absent on the WS path.
                            "latest_message_msg_id": m.msg_id,
                            "identity_key": f"{m.customer_name}|{m.text}",
                            # ws014: a WS frame fires precisely because a NEW unread
                            # customer message arrived, so mark it as a pending row.
                            # Without a pending marker (pending_timer / unread_badge /
                            # unread / needs_action) the actionable gate _mt042a_actionable
                            # (runner.py) drops the item — actionable=0, total=1 — and
                            # PreDispatch then sees "no visible sessions" → the front-desk
                            # LLM is told "actionable_items empty → call done()" → the
                            # customer gets dead silence. The DOM monitor's scraped item
                            # carries unread_badge='1' for the same row; WS must too.
                            "unread_badge": "1",
                            "source": "ws_frontier",
                        }
                        try:
                            dispatch_fn(item)
                        except Exception as _de:
                            logger.debug(f"[FEIGE-WS-SHADOW] dispatch_fn error: {_de}")
            except Exception:
                pass

        def _on_sent(params, session_id=None):
            # feed ws_session's per-conversation template cache (for off-DOM send)
            try:
                resp = params.get("response", {}) or {}
                if int(resp.get("opcode", -1)) != 2:
                    return
                payload = resp.get("payloadData", "") or ""
                if payload:
                    ws_session.note_sent_frame(base64.b64decode(payload, validate=False))
            except Exception:
                pass

        # ws075: socket-create tap — feeds the reconnect health check (did frames resume
        # after a new socket?) and the socket_created coverage metric.
        def _on_socket_created(params, session_id=None):
            try:
                _u = str(params.get("url") or "")
                if ("jinritemai" in _u) or ("frontier" in _u) or ("fxg" in _u):
                    _last_socket_create_ts[0] = time.time()
                    _awaiting_frame_after_create[0] = True
                    if _cov_on:
                        ws_coverage.note("socket_created")
            except Exception:
                pass

        # ws075 reconnect-follow: keep the observer attached to jinritemai tabs as they are
        # (re)created, so a socket cycling onto a new tab can't blind detection — the ws069
        # freeze was the fixed startup attach never following the ~60s reconnects -> 0 dispatch.
        _attached_tids = set(_sid_by_tid.keys())

        def _is_jinritemai_page(info) -> bool:
            return (info or {}).get("type") == "page" and "jinritemai" in ((info or {}).get("url") or "")

        async def _attach_jinritemai_tab(tid: str) -> bool:
            if not tid or tid in _attached_tids:
                return False
            try:
                _sid = (await client.send_raw(
                    "Target.attachToTarget", {"targetId": tid, "flatten": True})).get("sessionId")
                if not _sid:
                    return False
                await client.send_raw("Network.enable", {}, session_id=_sid)
                await client.send_raw(
                    "Runtime.evaluate",
                    {"expression": ws_session.arm_socket_hook_js(), "returnByValue": True},
                    session_id=_sid)
                sids.append(_sid)
                _sid_by_tid[tid] = _sid
                _attached_tids.add(tid)
                ws_session.set_observer_cdp(client, sids)   # refresh parked sids (read-ack/inject)
                logger.info(
                    f"[FEIGE-WS-RECONNECT] followed jinritemai tab ...{tid[-6:]} (now {len(sids)} attached)")
                if _cov_on:
                    ws_coverage.note("tab_attached")
                return True
            except Exception as _ae:
                logger.debug(f"[FEIGE-WS-RECONNECT] attach failed tid={tid}: {_ae}")
                return False

        def _on_target_created(params, session_id=None):
            try:
                _info = params.get("targetInfo", {}) or {}
                if _is_jinritemai_page(_info) and _info.get("targetId") not in _attached_tids:
                    asyncio.get_running_loop().create_task(_attach_jinritemai_tab(_info.get("targetId")))
            except Exception:
                pass

        def _on_target_destroyed(params, session_id=None):
            try:
                _tid = params.get("targetId")
                if _tid and _tid in _sid_by_tid:
                    _dead = _sid_by_tid.pop(_tid, None)
                    _attached_tids.discard(_tid)
                    if _dead in sids:
                        sids.remove(_dead)
                    ws_session.set_observer_cdp(client, sids)
                    logger.info(
                        f"[FEIGE-WS-RECONNECT] dropped dead tab ...{_tid[-6:]} (now {len(sids)} attached)")
            except Exception:
                pass

        async def _reconnect_health_loop():
            while True:
                try:
                    await asyncio.sleep(10.0)
                    # (1) attach any jinritemai tab we are not yet on (missed targetCreated)
                    try:
                        _tinfos = (await client.send_raw("Target.getTargets", {})).get("targetInfos", [])
                        for _t in _tinfos:
                            if _is_jinritemai_page(_t) and _t.get("targetId") not in _attached_tids:
                                await _attach_jinritemai_tab(_t.get("targetId"))
                    except Exception:
                        pass
                    # (2) frames-stale guard: a socket was created but no frame followed within the
                    # threshold -> the tracking has a gap -> re-enable Network on all sids.
                    _now = time.time()
                    _stale_after = float(os.environ.get("ECAN_FEIGE_WS_FRAMES_STALE_S", "30") or 30)
                    if (_last_socket_create_ts[0] > _last_frame_ts[0]
                            and (_now - _last_socket_create_ts[0]) > _stale_after):
                        logger.warning(
                            f"[FEIGE-WS-RECONNECT] frames stale {round(_now - _last_frame_ts[0], 1)}s "
                            f"after socket create — re-enabling Network on {len(sids)} tab(s)")
                        if _cov_on:
                            ws_coverage.note("frames_stale_repair")
                        for _s in list(sids):
                            try:
                                await client.send_raw("Network.enable", {}, session_id=_s)
                            except Exception:
                                pass
                        _last_socket_create_ts[0] = 0.0   # don't repeat until the next create
                except asyncio.CancelledError:
                    raise
                except Exception as _he:
                    logger.debug(f"[FEIGE-WS-RECONNECT] health loop: {_he}")

        async def _coverage_emit_loop():
            while True:
                try:
                    await asyncio.sleep(60.0)
                    logger.info(ws_coverage.format_line())
                    ws_coverage.reset_window()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    pass

        client._event_registry.register("Network.webSocketFrameReceived", _on_frame)
        client._event_registry.register("Network.webSocketFrameSent", _on_sent)
        client._event_registry.register("Network.webSocketCreated", _on_socket_created)
        # ws011: park the CDP handle so the raw sender (ws_raw_sender) can do its
        # one-time off-renderer connection-param capture (url/origin/UA/cookie).
        try:
            ws_session.set_observer_cdp(client, sids)
        except Exception:
            pass
        # ws075 reconnect-follow: discover + attach jinritemai tabs as they (re)appear, and run
        # the frames-stale health check. Gated ECAN_FEIGE_WS_RECONNECT_FOLLOW=1; best-effort.
        if _rcf_on:
            try:
                await client.send_raw("Target.setDiscoverTargets", {"discover": True})
                client._event_registry.register("Target.targetCreated", _on_target_created)
                client._event_registry.register("Target.targetDestroyed", _on_target_destroyed)
                asyncio.get_running_loop().create_task(_reconnect_health_loop())
                logger.info(
                    f"[FEIGE-WS-RECONNECT] reconnect-follow armed ({len(sids)} tabs, "
                    f"stale_guard={os.environ.get('ECAN_FEIGE_WS_FRAMES_STALE_S', '30')}s)")
            except Exception as _rcf_err:
                logger.debug(f"[FEIGE-WS-RECONNECT] arm failed: {_rcf_err}")
        # ws075 Phase 0: emit the coverage line every 60s when measuring.
        if _cov_on:
            try:
                asyncio.get_running_loop().create_task(_coverage_emit_loop())
                logger.info("[WS-COVERAGE] metrics armed (emit every 60s)")
            except Exception:
                pass
        # ws076A: passively capture the SPA's own history/conversation HTTP responses (off the
        # observer CDP, no replay/signing) and seed talk->name so name-less cards resolve from
        # turn 1. Gated ECAN_FEIGE_WS_PRIME_API=1.
        if os.environ.get("ECAN_FEIGE_WS_PRIME_API", "") == "1":
            try:
                from . import ws_prime_api
                ws_prime_api.register(client)
            except Exception as _pa_err:
                logger.debug(f"[WS-PRIME-API] arm failed: {_pa_err}")
        # ws068: warm-start the off-renderer raw socket now that the observer CDP handle is parked
        # (so ws_raw_sender can capture the token), so the FIRST reply doesn't eat the cold-start
        # connect latency/timeout (the "no response from start"). No-op unless ECAN_FEIGE_WS_SEND_RAW=1.
        if os.environ.get("ECAN_FEIGE_WS_SEND_RAW", "") == "1":
            try:
                from . import ws_raw_sender as _wsr_warm
                asyncio.get_running_loop().create_task(_wsr_warm.warmup())
            except Exception:
                pass
        # ws069: drain the constructor/onclose reconnect tap every 20s (diag only). Logs, per
        # (re)connect, whether the url-token and/or cookie actually changed vs the prior socket —
        # the event evidence the ws068 age theory was inferred without.
        if _diag_on:
            async def _ctor_diag_drain_loop():
                prev = {"url": None, "cookie": None}
                while True:
                    try:
                        await asyncio.sleep(20.0)
                        sid = _socket_sid[0] or (sids[0] if sids else None)
                        if not sid:
                            continue
                        res = await client.send_raw(
                            "Runtime.evaluate",
                            {"expression": ws_session.drain_ctor_diag_js(), "returnByValue": True},
                            session_id=sid)
                        val = ((res or {}).get("result") or {}).get("value") or "[]"
                        for ev in json.loads(val):
                            url = ev.get("url", "") or ""
                            cookie = ev.get("cookie", "") or ""
                            url_ch = prev["url"] is not None and url != prev["url"]
                            ck_ch = prev["cookie"] is not None and cookie != prev["cookie"]
                            logger.info(
                                f"[FEIGE-WS-DIAG] ctor/{ev.get('t')} url=...{url[-60:]} "
                                f"url_changed={url_ch} cookie_changed={ck_ch} "
                                f"cookie_len={len(cookie)} code={ev.get('code', '')} page_ts={ev.get('ts')}")
                            prev["url"] = url
                            prev["cookie"] = cookie
                    except asyncio.CancelledError:
                        raise
                    except Exception as _de:
                        logger.debug(f"[FEIGE-WS-DIAG] drain skipped: {_de}")
            try:
                asyncio.get_running_loop().create_task(_ctor_diag_drain_loop())
                logger.info("[FEIGE-WS-DIAG] ctor/onclose reconnect tap armed (drain every 20s)")
            except Exception:
                pass
        # ws059: do NOT arm WS-owns-dispatch here. Registering the CDP handler does NOT
        # mean frames are flowing — a pre-existing IM socket emits nothing until it
        # reconnects. Arming dispatch_live now would suppress the DOM monitor while the
        # socket is still silent (the cold-start blind window that dropped '红黑款有货吗'
        # on 2026-06-14). dispatch_live is instead armed on the FIRST received frame in
        # _on_frame, so the DOM monitor stays the backup until the socket proves live.
        logger.info(
            f"[FEIGE-WS-SHADOW] started (env {_ENV}=1) label={label!r} targets={len(sids)} "
            f"dispatch={do_dispatch} — {'WS will own dispatch on first frame' if do_dispatch else 'log-only shadow'}; "
            f"DOM monitor stays active until then; diff vs DOM dom_observed for detection-latency"
        )
        return client
    except Exception as exc:
        logger.warning(f"[FEIGE-WS-SHADOW] failed to start: {exc}")
        return None


async def stop_ws_shadow_observer(client: Any) -> None:
    """Best-effort teardown."""
    if ws_coverage.enabled():             # ws075: final coverage snapshot at teardown
        try:
            logger.info(ws_coverage.format_line())
        except Exception:
            pass
    ws_session.set_dispatch_live(False)   # DOM must resume dispatching once WS is down
    try:
        ws_session.set_observer_cdp(None, [])   # ws011: drop the parked CDP handle
    except Exception:
        pass
    if client is None:
        return
    try:
        await client.stop()
    except Exception:
        pass
