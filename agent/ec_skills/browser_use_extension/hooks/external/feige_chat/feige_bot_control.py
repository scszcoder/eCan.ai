"""Periodic suppression of Feige's OWN system customer-service bot (智能客服).

Feige auto-enables its built-in 智能客服 bot after ~10 minutes of dormancy. While
OUR agents are working we want Feige's bot OFF so it doesn't answer customers in
parallel (interference / double replies). Each tick reads the bot's state and,
if it's ON, closes it (ws121 — "ensure OFF"). Feige re-enables the bot after
~10 min dormant, so a ~5-min tick keeps it suppressed.

It runs PARALLEL to the DOM monitor: the same periodic tick driver in
``event_monitor``'s ``DOMMutationMonitor.check_now()`` fires
:func:`suppress_feige_bot_tick` on its own throttle (default every 5 min), the
same way the cold-start recovery scan is fired.

ws121: the on/off/state steps are the captured seller-config API (NOT a DOM
toggle) — ``intelligence_robot/{status,close,open}`` on pigeon.jinritemai.com,
fired as in-page XHRs so secsdk attaches the rotating csrf token (see
:func:`_bot_api_call`).

Gated ``ECAN_FEIGE_BOT_SUPPRESS=1`` (default OFF). Interval
``ECAN_FEIGE_BOT_SUPPRESS_INTERVAL_S`` (default 120s).

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
import json
import os

from utils.logger_helper import logger_helper as logger

# ws121 — the bot on/off is the seller-config API captured via ws119/ws120, NOT a
# DOM toggle. All three endpoints live under pigeon.jinritemai.com/backstage and
# need the rotating `x-secsdk-csrf-token` header — which ByteDance's secsdk
# interceptor attaches to in-page XHRs automatically, so we fire them via an
# in-page XMLHttpRequest (the same axios->XHR path the page itself uses) rather
# than reconstructing the token.  Each returns JSON with `code==0` on success.
_BOT_STATUS_URL = ("https://pigeon.jinritemai.com/backstage/intelligence_robot/"
                   "status?biz_type=4&PIGEON_BIZ_TYPE=2")
_BOT_CLOSE_URL = ("https://pigeon.jinritemai.com/backstage/intelligence_robot/"
                  "close?biz_type=4&PIGEON_BIZ_TYPE=2")
_BOT_OPEN_URL = ("https://pigeon.jinritemai.com/backstage/intelligence_robot/"
                 "open?biz_type=4&PIGEON_BIZ_TYPE=2&_pms=1&device_platform=web&FUSION=true")
# Captured payloads (close reason mirrors the UI's 人工客服充足，不需要 choice).
_BOT_CLOSE_BODY = {"reasons": [{"reason": "人工客服充足，不需要"}], "close_type": 1}
_BOT_OPEN_BODY = {"open_scenes": ["PreSale", "AfterSale"]}


async def _bot_api_call(browser_session, target_id, method, url, body):
    """Fire ONE intelligence_robot API call as an in-page XHR and return the
    parsed ``{ok, status, code, data}`` (or ``None`` on eval failure).

    Runs via ``_evaluate_js`` (awaitPromise) on the focused Feige tab so the
    page's secsdk attaches the csrf token + cookies. read_only=True: a timeout
    here must never nuke the shared BrowserSession the front-desk depends on.
    """
    try:
        from agent.ec_skills.browser_use_extension.extension_tools_service import (
            _evaluate_js,
        )
    except Exception:
        return None
    body_js = "null" if body is None else json.dumps(json.dumps(body, ensure_ascii=False))
    js = (
        "(function(){return new Promise(function(res){try{"
        "var x=new XMLHttpRequest();"
        f"x.open({json.dumps(method)},{json.dumps(url)},true);"
        "x.withCredentials=true;"
        "x.setRequestHeader('Content-Type','application/json;charset=UTF-8');"
        "x.setRequestHeader('Accept','application/json, text/plain, */*');"
        "x.onreadystatechange=function(){if(x.readyState===4){"
        "var c=null,d=null;try{var j=JSON.parse(x.responseText);c=j&&j.code;d=j&&j.data;}catch(e){}"
        "res(JSON.stringify({ok:true,status:x.status,code:c,data:d}));}};"
        "x.onerror=function(){res(JSON.stringify({ok:false,err:'xhr_error',status:x.status}));};"
        f"x.send({body_js});"
        "}catch(e){res(JSON.stringify({ok:false,err:String(e)}));}});})()"
    )
    try:
        kw = dict(focus=False, trace_label="feige_bot_toggle",
                  read_only=True, timeout_s=15.0)
        if target_id:
            kw["target_id"] = str(target_id)
        raw = await _evaluate_js(browser_session, js, **kw)
        # ws122: _evaluate_js ALREADY json.loads() a string result, so `raw` is
        # normally the parsed dict — do NOT parse again (the ws121 bug: a second
        # json.loads(dict) raised TypeError -> None -> the tick saw status=None
        # and never closed the bot). Only re-parse if it came back as a raw str.
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str) and raw:
            return json.loads(raw)
        return None
    except Exception as _e:
        logger.debug(f"[FEIGE-BOT-CTRL] api call failed ({method} {url[:60]}): {_e}")
        return None


async def get_bot_status(browser_session, target_id):
    """Read Feige's bot state. Returns 1 (ON) / 0 (OFF), or None if unknown."""
    r = await _bot_api_call(browser_session, target_id, "GET", _BOT_STATUS_URL, None)
    try:
        if r and r.get("ok") and isinstance(r.get("data"), dict):
            return int(r["data"].get("open_status"))
    except Exception:
        pass
    return None


async def turn_on_feige_bot(browser_session, target_id) -> bool:
    """Enable Feige's own 智能客服 bot (POST intelligence_robot/open). Returns True
    on success (``code==0``). Available but NOT used by the default suppression
    tick, which only ever closes the bot.
    """
    r = await _bot_api_call(browser_session, target_id, "POST", _BOT_OPEN_URL, _BOT_OPEN_BODY)
    ok = bool(r and r.get("ok") and r.get("code") == 0)
    logger.info(f"[FEIGE-BOT-CTRL] turn_on_feige_bot ok={ok} resp={r}")
    return ok


async def turn_off_feige_bot(browser_session, target_id) -> bool:
    """Disable Feige's own 智能客服 bot (POST intelligence_robot/close) so it does
    not answer customers in parallel with our agents. Returns True on success
    (``code==0``).
    """
    r = await _bot_api_call(browser_session, target_id, "POST", _BOT_CLOSE_URL, _BOT_CLOSE_BODY)
    ok = bool(r and r.get("ok") and r.get("code") == 0)
    logger.info(f"[FEIGE-BOT-CTRL] turn_off_feige_bot ok={ok} resp={r}")
    return ok


async def suppress_feige_bot_tick() -> None:
    """One suppression cycle: read the bot's state and, if it's ON, close it.

    ws121: now that ``intelligence_robot/status`` gives ``open_status`` we just
    ENSURE-OFF rather than blind-toggling on->off — no repeated ``/open`` (which
    would re-pop the scene-config wizard). Feige auto-enables the bot after
    ~10 min dormant, so a ~5-min ensure-off tick keeps it suppressed. Resolves
    the focused Feige tab the same way the cold-start recovery scan does.
    Best-effort; never raises. Gated ``ECAN_FEIGE_BOT_SUPPRESS=1``.
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
        status = await get_bot_status(browser_session, target_id)
        if status == 1:
            ok = await turn_off_feige_bot(browser_session, target_id)
            logger.info(f"[FEIGE-BOT-CTRL] suppression tick: bot was ON -> close ok={ok}")
        else:
            logger.info(
                f"[FEIGE-BOT-CTRL] suppression tick: bot not open (status={status}) — no action")
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

    ws179: ``ECAN_FEIGE_OPEN_CLAIM_CAPTURE=1`` widens the same sniffer to EVERY
    jinritemai XHR/Fetch (GET included), marker ``[FEIGE-OPEN-CLAIM-CAP]`` — for
    the manual cold-row click test that hunts the conversation open/claim call
    (the 2026-07-16 verdict: the server accept-but-ignores sends into a
    conversation this seat hasn't opened; ws137's 0/27 first-contact result).
    Protocol: idle the page ~10s, click ONE cold conversation row, idle ~10s;
    diff the [FEIGE-OPEN-CLAIM-CAP] window around the click.
    """
    _claim_wide = os.environ.get("ECAN_FEIGE_OPEN_CLAIM_CAPTURE", "") == "1"
    if not _claim_wide and os.environ.get("ECAN_FEIGE_BOT_TOGGLE_CAPTURE", "") != "1":
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
        # ws179 wide mode: the claim call may be ANY request the SPA fires on a row
        # click, so keep every jinritemai XHR/Fetch (GET included) and raise the cap.
        _marker = "[FEIGE-OPEN-CLAIM-CAP]" if _claim_wide else "[FEIGE-BOT-TOGGLE-CAP]"
        _cap_max = 600 if _claim_wide else 120
        # URL/payload hints for the bot on/off mutation (don't over-filter — also
        # keep every non-GET XHR to jinritemai during the manual click test).
        _keys = ("intelligent", "robot", "smart", "reception", "auto_reply",
                 "customer_service", "switch", "enable", "disable", "open", "close",
                 "status", "接待", "智能", "机器人")

        def _interesting(method: str, url: str, post: str, typ: str) -> bool:
            if "jinritemai" not in url:
                return False
            if _claim_wide:
                return typ in ("XHR", "Fetch")
            if typ in ("XHR", "Fetch") and method != "GET":
                return True
            blob = (url + " " + (post or "")).lower()
            return any(k in blob for k in _keys)

        def _on_req(params, session_id=None):
            try:
                if counter["n"] >= _cap_max:
                    return
                req = params.get("request", {}) or {}
                url = req.get("url", "") or ""
                method = req.get("method", "") or ""
                post = str(req.get("postData", "") or "")
                if not _interesting(method, url, post, str(params.get("type", ""))):
                    return
                counter["n"] += 1
                logger.info(
                    f"{_marker} REQ " + _json.dumps(
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
                f"{_marker} RESP status={meta.get('status')} "
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
            f"{_marker} capture armed on {len(sids)} Feige tab(s) — "
            + ("click ONE cold conversation row to record the open/claim calls"
               if _claim_wide else
               "click 关闭/开启智能客服 once to record the toggle request"))
    except Exception as _e:
        logger.debug(f"[FEIGE-BOT-TOGGLE-CAP] capture start failed (non-fatal): {_e}")
