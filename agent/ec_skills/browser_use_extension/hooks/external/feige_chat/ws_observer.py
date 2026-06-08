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
import logging
import os
from typing import Any

from . import ws_reader, ws_session

logger = logging.getLogger("eCan")

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
        for sid in sids:
            try:
                await client.send_raw(
                    "Runtime.evaluate",
                    {"expression": ws_session.arm_socket_hook_js(), "returnByValue": True},
                    session_id=sid)
            except Exception:
                pass

        seen: set = set()
        stats = {"frames": 0, "msgs": 0}
        _socket_sid = [None]   # ws009: remember the tab that actually holds the socket
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
                ws_session.note_recv_frame(raw)   # feed routing + send-confirmation
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
                    key = m.msg_id or f"{m.conversation_id}|{m.text}"
                    if key in seen:
                        return  # already handled this message (frames repeat)
                    seen.add(key)
                    stats["msgs"] += 1
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

        client._event_registry.register("Network.webSocketFrameReceived", _on_frame)
        client._event_registry.register("Network.webSocketFrameSent", _on_sent)
        # ws011: park the CDP handle so the raw sender (ws_raw_sender) can do its
        # one-time off-renderer connection-param capture (url/origin/UA/cookie).
        try:
            ws_session.set_observer_cdp(client, sids)
        except Exception:
            pass
        # Only now is the WS path confirmed live. Tell ws_session so the DOM monitor
        # suppresses its own dispatch ONLY while we are actually dispatching — never
        # leave DOM suppressed with no live WS dispatcher behind it (total-stall bug).
        if do_dispatch:
            ws_session.set_dispatch_live(True)
        logger.info(
            f"[FEIGE-WS-SHADOW] started (env {_ENV}=1) label={label!r} targets={len(sids)} "
            f"dispatch={do_dispatch} — {'WS owns dispatch' if do_dispatch else 'log-only shadow'}; "
            f"diff vs DOM dom_observed for detection-latency"
        )
        return client
    except Exception as exc:
        logger.warning(f"[FEIGE-WS-SHADOW] failed to start: {exc}")
        return None


async def stop_ws_shadow_observer(client: Any) -> None:
    """Best-effort teardown."""
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
