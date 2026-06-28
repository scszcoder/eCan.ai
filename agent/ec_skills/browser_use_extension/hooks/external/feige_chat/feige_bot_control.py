"""Periodic suppression of Feige's OWN system customer-service bot (智能客服).

Feige auto-enables its built-in 智能客服 bot after ~10 minutes of dormancy. While
OUR agents are working we want Feige's bot OFF so it doesn't answer customers in
parallel (interference / double replies). This module periodically toggles it —
turn ON then quickly OFF — which keeps it suppressed and resets Feige's ~10-min
dormant auto-enable timer, leaving the bot in the OFF state.

It runs PARALLEL to the DOM monitor: the same periodic tick driver in
``event_monitor``'s ``DOMMutationMonitor.check_now()`` fires
:func:`suppress_feige_bot_tick` on its own throttle (default every 5 min), the
same way the cold-start recovery scan is fired.

The actual CDP + DOM toggle steps are PLACEHOLDERS for now — to be filled in when
we have the concrete Feige sidebar/settings DOM for the bot on/off control.

Gated ``ECAN_FEIGE_BOT_SUPPRESS=1`` (default OFF until the placeholders are
implemented). Interval ``ECAN_FEIGE_BOT_SUPPRESS_INTERVAL_S`` (default 300s).

Investigation aid (preferred toggle transport):
:func:`start_bot_toggle_capture` is a passive network sniffer that records the
authenticated XHR the settings SPA fires when you click 关闭/开启智能客服 — its
method + URL + payload + headers, plus the response body. Once captured, the
on/off steps can be a single in-page ``fetch()`` instead of the fragile
multi-dialog DOM clicker (no dedicated tab, no retention/欢迎回来 modals, immune
to class-name redesigns). Gated ``ECAN_FEIGE_BOT_TOGGLE_CAPTURE=1`` (default
OFF), marker ``[FEIGE-BOT-TOGGLE-CAP]``. NOTE: the 智能客服 toggle is an HTTP
config mutation, NOT a chat-WS frame — the Frontier socket only carries chat, so
there is no WS read/send path for it.
"""
import asyncio
import os

from utils.logger_helper import logger_helper as logger


async def turn_on_feige_bot(browser_session, target_id) -> bool:
    """PLACEHOLDER — enable Feige's own 智能客服 bot via CDP + DOM.

    TODO: locate the bot on/off control in the Feige sidebar/settings and click
    it ON (e.g. ``_evaluate_js`` with a selector, like the recovery scan). Toggling
    counts as activity, which resets Feige's ~10-min dormant auto-enable timer.

    Returns True on success; currently a no-op stub.
    """
    logger.info(
        "[FEIGE-BOT-CTRL] turn_on_feige_bot() — PLACEHOLDER (no-op; "
        f"fill with the DOM toggle) target_id={target_id}")
    return False


async def turn_off_feige_bot(browser_session, target_id) -> bool:
    """PLACEHOLDER — disable Feige's own 智能客服 bot via CDP + DOM.

    TODO: locate the bot on/off control and click it OFF so Feige's bot does not
    answer customers while our agents are handling them.

    Returns True on success; currently a no-op stub.
    """
    logger.info(
        "[FEIGE-BOT-CTRL] turn_off_feige_bot() — PLACEHOLDER (no-op; "
        f"fill with the DOM toggle) target_id={target_id}")
    return False


async def suppress_feige_bot_tick() -> None:
    """One suppression cycle: toggle Feige's bot ON then quickly OFF so it stays
    suppressed (and the ~10-min dormant auto-enable timer is reset).

    Resolves the focused Feige tab/session the same way the cold-start recovery
    scan does, then calls the (placeholder) on/off steps. Best-effort; never
    raises. Gated ``ECAN_FEIGE_BOT_SUPPRESS=1``.
    """
    if os.environ.get("ECAN_FEIGE_BOT_SUPPRESS", "") != "1":
        return
    try:
        from agent.ec_skills.browser_node.build_helpers import cached_browser_sessions
        from .dom_assets import (
            ensure_feige_tab_reachable,
            _SESSION_FOCUSED_FEIGE_TID_ATTR,
        )
    except Exception:
        return
    browser_session = None
    for sess in list((cached_browser_sessions or {}).values()):
        if sess is not None:
            browser_session = sess
            break
    if browser_session is None:
        return
    target_id = None
    try:
        if await ensure_feige_tab_reachable(browser_session):
            target_id = getattr(browser_session, _SESSION_FOCUSED_FEIGE_TID_ATTR, None)
    except Exception:
        target_id = None
    try:
        await turn_on_feige_bot(browser_session, target_id)
        await turn_off_feige_bot(browser_session, target_id)
        logger.info("[FEIGE-BOT-CTRL] suppression tick complete (placeholder on->off)")
    except Exception as _e:
        logger.debug(f"[FEIGE-BOT-CTRL] suppression tick failed (non-fatal): {_e}")


# ── Toggle-API capture (ws119, investigation) ───────────────────────────────
# Attach a dedicated CDP client to the live Feige tab(s), enable Network, and log
# the authenticated XHR the settings page fires when 智能客服 is toggled, so the
# on/off steps can become a single fetch(). Idempotent + bounded; mirrors the
# event_monitor WS-frame capture pattern. Marker [FEIGE-BOT-TOGGLE-CAP].
_TOGGLE_CAP_CLIENT = [None]   # keep a strong ref so the client/loop isn't GC'd
_TOGGLE_CAP_STARTED = [False]
_TOGGLE_CAP_TASKS: set = set()   # ws120: strong refs to detached body-fetch tasks


async def start_bot_toggle_capture() -> None:
    """ws119: passively record the bot enable/disable HTTP request (and its response
    body) so :func:`turn_on_feige_bot`/:func:`turn_off_feige_bot` can be rewritten
    as a single authenticated ``fetch()``. Best-effort, idempotent, never raises.
    Gated ``ECAN_FEIGE_BOT_TOGGLE_CAPTURE=1``.
    """
    if os.environ.get("ECAN_FEIGE_BOT_TOGGLE_CAPTURE", "") != "1":
        return
    if _TOGGLE_CAP_STARTED[0]:
        return
    try:
        from agent.ec_skills.browser_node.build_helpers import cached_browser_sessions
    except Exception:
        return
    session = None
    for sess in list((cached_browser_sessions or {}).values()):
        if sess is not None:
            session = sess
            break
    if session is None:
        return
    cdp_url = getattr(session, "cdp_url", None)
    if not cdp_url:
        bp = getattr(session, "browser_profile", None)
        cdp_url = getattr(bp, "cdp_url", None) if bp else None
    if not cdp_url:
        return
    try:
        import json as _json
        from cdp_use import CDPClient as _CapCDPClient

        client = _CapCDPClient(url=cdp_url)
        await client.start()
        # Attach to every real Feige page tab so whichever one holds the settings
        # SPA is covered (the user opens it in the normal tab).
        sids = []
        try:
            _tinfos = (await client.send_raw("Target.getTargets", {})).get("targetInfos", [])
        except Exception:
            _tinfos = []
        for _t in _tinfos:
            if _t.get("type") != "page" or "jinritemai" not in (_t.get("url") or ""):
                continue
            try:
                _sid = (await client.send_raw(
                    "Target.attachToTarget",
                    {"targetId": _t.get("targetId"), "flatten": True})).get("sessionId")
                if _sid:
                    await client.send_raw("Network.enable", {}, session_id=_sid)
                    sids.append(_sid)
            except Exception:
                pass
        if not sids:
            await client.stop()
            return

        counter = {"n": 0}
        pending = {}   # requestId -> {url, status, sid}
        # URL/payload hints for the bot on/off mutation (don't over-filter — also
        # keep every non-GET XHR to jinritemai during the manual click test).
        _keys = ("intelligent", "robot", "smart", "reception", "auto_reply",
                 "customer_service", "switch", "enable", "disable", "open", "close",
                 "status", "接待", "智能", "机器人")

        def _interesting(method: str, url: str, post: str, typ: str) -> bool:
            if "jinritemai" not in url:
                return False
            if typ in ("XHR", "Fetch") and method != "GET":
                return True
            blob = (url + " " + (post or "")).lower()
            return any(k in blob for k in _keys)

        def _on_req(params, session_id=None):
            try:
                if counter["n"] >= 120:
                    return
                req = params.get("request", {}) or {}
                url = req.get("url", "") or ""
                method = req.get("method", "") or ""
                post = str(req.get("postData", "") or "")
                if not _interesting(method, url, post, str(params.get("type", ""))):
                    return
                counter["n"] += 1
                logger.info(
                    "[FEIGE-BOT-TOGGLE-CAP] REQ " + _json.dumps(
                        {"method": method, "url": url[:400], "postData": post[:1500],
                         "headers": req.get("headers", {})}, ensure_ascii=False))
                pending[params.get("requestId", "")] = {"url": url, "sid": session_id}
            except Exception:
                pass

        def _on_resp(params, session_id=None):
            try:
                rid = params.get("requestId", "")
                if rid in pending:
                    pending[rid]["status"] = (params.get("response", {}) or {}).get("status")
            except Exception:
                pass

        async def _fetch_body(rid, meta):
            body = ""
            try:
                body = (await client.send_raw(
                    "Network.getResponseBody", {"requestId": rid},
                    session_id=meta.get("sid"))).get("body", "") or ""
            except Exception:
                pass
            logger.info(
                f"[FEIGE-BOT-TOGGLE-CAP] RESP status={meta.get('status')} "
                f"url={meta['url'][:200]} body={body[:1500]!r}")

        def _on_done(params, session_id=None):
            # ws120: must NOT await client.send_raw() here — cdp_use runs event
            # handlers inline on its single read loop, so awaiting a CDP response
            # from inside the handler deadlocks the loop (it's the same loop that
            # has to read that response). ws119 logged 0 RESP lines for exactly
            # this reason. Schedule the body fetch as a detached task so the
            # handler returns immediately and the pump stays free.
            try:
                rid = params.get("requestId", "")
                meta = pending.pop(rid, None)
                if meta is None:
                    return
                _t = asyncio.create_task(_fetch_body(rid, meta))
                _TOGGLE_CAP_TASKS.add(_t)
                _t.add_done_callback(_TOGGLE_CAP_TASKS.discard)
            except Exception:
                pass

        reg = client._event_registry
        reg.register("Network.requestWillBeSent", _on_req)
        reg.register("Network.responseReceived", _on_resp)
        reg.register("Network.loadingFinished", _on_done)
        _TOGGLE_CAP_CLIENT[0] = client
        _TOGGLE_CAP_STARTED[0] = True
        logger.info(
            f"[FEIGE-BOT-TOGGLE-CAP] capture armed on {len(sids)} Feige tab(s) — "
            "click 关闭/开启智能客服 once to record the toggle request")
    except Exception as _e:
        logger.debug(f"[FEIGE-BOT-TOGGLE-CAP] capture start failed (non-fatal): {_e}")
