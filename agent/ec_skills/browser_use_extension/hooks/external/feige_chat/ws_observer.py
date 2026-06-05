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
        for tid in targets:
            if not tid:
                continue
            try:
                sid = (await client.send_raw(
                    "Target.attachToTarget", {"targetId": tid, "flatten": True})).get("sessionId")
                if sid:
                    await client.send_raw("Network.enable", {}, session_id=sid)
                    sids.append(sid)
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
                    key = m.msg_id or f"{m.conversation_id}|{m.text}"
                    if key in seen:
                        return  # already handled this message (frames repeat)
                    seen.add(key)
                    stats["msgs"] += 1
                    tag = "DISPATCH" if do_dispatch else "SHADOW"
                    logger.info(
                        f"[FEIGE-WS-SHADOW] mode={tag} customer={m.customer_name!r} "
                        f"conv={m.conversation_id} msg_id={m.msg_id} ts_ms={m.ts_ms} "
                        f"type={m.msg_type} text={m.text[:80]!r}"
                    )
                    if do_dispatch:
                        # generic detected-item shape the browser_event pipeline expects;
                        # identity_key mirrors the DOM monitor's dedup key.
                        item = {
                            "customer_name": m.customer_name,
                            "name": m.customer_name,
                            "customer_id": m.conversation_id,
                            "last_message": m.text,
                            "latest_message": m.text,
                            "msg_id": m.msg_id,
                            "identity_key": f"{m.customer_name}|{m.text}",
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
    if client is None:
        return
    try:
        await client.stop()
    except Exception:
        pass
