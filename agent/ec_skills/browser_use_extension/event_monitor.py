"""
Browser Event Monitor — auto-starts CDP-based event capture sidecars
from browser_automation node editor config.

Each monitor config in ``inputsValues.eventMonitors.content`` describes a
capture rule (HTTP polling, WebSocket, SSE, DOM mutation, or raw CDP).
When a match fires, the monitor bridges the event into the same
``sync_task_wait_in_line("browser_event", ...)`` dispatch path used by
``BrowserEventService``, so downstream ``pend_event`` nodes configured
with a matching ``browserEventLabel`` resume automatically.

Lifecycle:
    1. ``parse_monitor_configs(inputs)`` extracts and validates configs.
    2. ``start_monitors(session, configs)`` creates capture instances.
    3. ``stop_monitors(monitor_set)`` tears them down.

Only HTTP-polling, DOM mutation, WebSocket, and SSE are implemented in Phase 1.  CDP raw monitors will follow the same bridge pattern in Phase 6.
"""
from __future__ import annotations

import json
import asyncio
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from utils.logger_helper import logger_helper as logger
from utils import agent_status as _agent_status
from agent.ec_skills.browser_use_extension.event_monitor_capability import (
    clear_attached_monitor_set,
    get_attached_monitor_set,
    get_event_monitor_capability,
    set_attached_monitor_set,
)
from agent.ec_skills.browser_use_extension.event_models import NormalizedBrowserEvent

# ── Top-level import for websocket health-check (avoids import overhead on every poll) ──
try:
    from websockets.protocol import State as _WsState
except ImportError:
    _WsState = None


# Global registry of active monitor sets keyed by monitor_set_id
# Used for cleanup when sessions close or runners shut down
_active_monitor_sets: Dict[str, ActiveMonitorSet] = {}
_session_start_locks: Dict[int, asyncio.Lock] = {}

# 2026-05-27 mt050H — set of customer_name prefixes that the next DOM
# diff calc should treat as freshly-added.  Used after
# ``direct_stale_dropped`` to force EventMonitor to re-emit the
# customer's row even though its sidebar text hasn't changed (which
# would normally suppress the re-emit because diff sees added=0).
# Live customer trace 2026-05-27 J14N9 was stuck 5+ minutes after a
# stale-drop because mt046A cleared the dedup ledgers but no new
# dom_observed ever fired (sidebar row text was unchanged).
#
# Format: just the customer_name (e.g. "J14N9").  The diff calc
# walks current_keys (format "{customer_name}|{last_message}") and
# treats any key whose prefix matches as freshly added.  The matched
# entry is popped from the set after one tick so we never force
# more than one re-emit per stale-drop event.
_FORCED_REEMIT_CUSTOMER_NAMES: set = set()
# ws048: hold strong references to fire-and-forget WS-DIRECT-QA dispatch tasks.
# asyncio only keeps a WEAK reference to a bare create_task() result, so under GC
# pressure (exactly the saturation spike that drops turns) an unreferenced task can
# be collected mid-execution and vanish — no dispatch, no exception, no fallback.
# This was the silent-drop root cause (童趣科普 2026-06-11 13:06:49). Tasks discard
# themselves on completion via add_done_callback.
_WS_DIRECT_DISPATCH_TASKS: set = set()


def force_reemit_for_customer(customer_name: str) -> None:
    """Mark *customer_name* for one-shot re-emit on the next EventMonitor
    tick.  See ``_FORCED_REEMIT_CUSTOMER_NAMES`` docstring above.

    Thread-safe — set ops are atomic in CPython for builtin sets.
    Idempotent — adding the same name twice is a no-op.
    """
    if not customer_name:
        return
    _FORCED_REEMIT_CUSTOMER_NAMES.add(str(customer_name))


def _live_chat_bridge():
    """Return the active live-chat bundle's runner bridge, or None.

    2026-08-01: this module used to lazy-import the site bundle's
    modules directly at each call site.  Those sites now resolve every
    site-specific capability (tab pool, ws observer, dispatch state,
    tunables, ...) through the ONE bridge object the active bundle
    registers at package import (see
    ``live_chat_dispatch.register_runner_bridge`` and the active
    bundle's ``runner_bridge.py``).  A None bridge (no live-chat bundle
    loaded in this process) must degrade each call site to the same
    fallback its old failed-import path took.
    """
    try:
        from agent.ec_skills import live_chat_dispatch
        return live_chat_dispatch.runner_bridge()
    except Exception:
        return None


def _live_chat_env(name: str) -> "str | None":
    """Read a live-chat tunable env var by its platform-neutral name.

    Falls back to any legacy site-branded alias of the same knob so
    existing ops run-scripts keep working while platform code stays
    site-agnostic (see ``live_chat_dispatch.live_chat_env``).
    """
    try:
        from agent.ec_skills.live_chat_dispatch import live_chat_env
        return live_chat_env(name)
    except Exception:
        return None


_MONITOR_RUNTIME_EVALUATE_TIMEOUT_S = float(
    os.getenv("ECAN_MONITOR_CDP_EVALUATE_TIMEOUT_S", "3.0")
)


# ---------------------------------------------------------------------------
# Independent CDP connection for monitor DOM polling
# ---------------------------------------------------------------------------
# Monitors must NOT use the agent's BrowserSession CDP client because browser-use
# operations (screenshot, navigation, etc.) monopolise it and cause the monitor's
# Runtime.evaluate calls to hang/time out.
#
# Instead each monitor gets its own lightweight CDPClient that connects directly
# to Chrome's debugging WebSocket and attaches to the specific target tab.
# ---------------------------------------------------------------------------

async def _get_monitor_cdp(mutation_state: Dict[str, Any], session: Any, target_id: str):
    """Return (cdp_client, session_id) using an independent CDP connection.

    The client and session_id are cached in *mutation_state* so they persist
    across polling cycles.  If the connection drops they are recreated.
    The WebSocket state is checked before each use — no keep-alive ping is sent
    to avoid adding per-cycle CDP round-trips.
    """
    cached_client = mutation_state.get("_mon_cdp_client")
    cached_sid = mutation_state.get("_mon_cdp_session_id")

    # Quick health check — is the cached client still alive?
    if cached_client and cached_sid:
        ws = getattr(cached_client, "ws", None)
        if ws is not None and _WsState is not None:
            try:
                if ws.state is _WsState.OPEN:
                    return cached_client, cached_sid
            except Exception:
                pass
        # Dead — clean up and recreate
        try:
            await cached_client.stop()
        except Exception:
            pass
        mutation_state.pop("_mon_cdp_client", None)
        mutation_state.pop("_mon_cdp_session_id", None)

    # Resolve Chrome's debugging WebSocket URL from the BrowserSession.
    cdp_url = getattr(session, "cdp_url", None)
    if not cdp_url:
        bp = getattr(session, "browser_profile", None)
        cdp_port = getattr(bp, "cdp_url", None) if bp else None
        if not cdp_port:
            return None, None
        cdp_url = cdp_port

    try:
        from cdp_use import CDPClient as _MonCDPClient

        client = _MonCDPClient(url=cdp_url)
        await client.start()

        attach_result = await client.send_raw(
            "Target.attachToTarget",
            {"targetId": target_id, "flatten": True},
        )
        sid = attach_result.get("sessionId")
        if not sid:
            logger.warning(
                f"[EventMonitor] Independent CDP: attachToTarget returned no sessionId "
                f"for target={target_id[-6:]}"
            )
            await client.stop()
            return None, None

        await client.send_raw("Runtime.enable", {}, session_id=sid)

        mutation_state["_mon_cdp_client"] = client
        mutation_state["_mon_cdp_session_id"] = sid
        mutation_state.pop("_mon_cdp_attach_failed_target_id", None)
        mutation_state.pop("_mon_cdp_last_error", None)
        logger.info(
            f"[EventMonitor] Independent CDP connection established: "
            f"target=...{target_id[-6:]}, sessionId=...{sid[-6:] if sid else 'None'}"
        )
        return client, sid
    except Exception as exc:
        mutation_state["_mon_cdp_attach_failed_target_id"] = str(target_id or "")
        mutation_state["_mon_cdp_last_error"] = str(exc)
        logger.warning(f"[EventMonitor] Failed to create independent CDP connection: {exc}")
        return None, None


async def _cleanup_monitor_cdp(mutation_state: Dict[str, Any]):
    """Tear down the independent CDP client cached in mutation_state."""
    client = mutation_state.pop("_mon_cdp_client", None)
    mutation_state.pop("_mon_cdp_session_id", None)
    if client:
        try:
            await client.stop()
        except Exception:
            pass


async def _open_detection_tab(session: Any, monitor_url: str) -> str:
    """Open a dedicated tab at *monitor_url* for the 新消息 sidebar poll, ISOLATED
    from the main tab's per-customer bubble scrapes (gated by env
    ``ECAN_LIVE_CHAT_DEDICATED_DETECTION_TAB``).  Returns the new target_id, or ''
    on failure (caller falls back to the shared tab).

    Why: the detection poll and the bubble/thread scrapes share ONE Chrome
    renderer when they run on the same tab.  Two ``Runtime.evaluate`` calls on
    the same page serialize on V8's single main thread, so a 5-28s bubble scrape
    blocks the poll → it times out (6 s) → consecutive-recycle spiral → 100-184s
    detection blackout (customer mt070 1-to-6; reproduced + measured locally via
    the emulation A/B, blackout detection-lag max 162.8s vs 35.2s clean).  A
    SEPARATE tab = a separate renderer/main-thread, so the long bubble scrape on
    the main tab can no longer block the detection poll.

    The tab persists after this returns (``Target.createTarget`` makes a real
    tab); the temporary client used to create it is closed.  The EventMonitor's
    own independent CDP client (``_get_monitor_cdp``) then attaches to it.  The
    sidebar still updates in this tab via the site's WS push / the emulation's
    BroadcastChannel (neither is background-throttled); CDP ``Runtime.evaluate``
    reads the DOM regardless of tab visibility.
    """
    cdp_url = getattr(session, "cdp_url", None)
    if not cdp_url:
        bp = getattr(session, "browser_profile", None)
        cdp_url = getattr(bp, "cdp_url", None) if bp else None
    if not cdp_url:
        return ""
    client = None
    try:
        from cdp_use import CDPClient as _DetCDPClient

        client = _DetCDPClient(url=cdp_url)
        await client.start()
        # Close stale detection tabs left over from previous app sessions (the
        # browser can outlive the app). Recognized by _DETECTION_TAB_MARKER;
        # without this they accumulate one per restart AND a reattaching
        # browser session can adopt one as its main tab (rows=0 blindness).
        try:
            stale = await client.send_raw("Target.getTargets", {})
            for info in (stale or {}).get("targetInfos", []) if isinstance(stale, dict) else []:
                if str(info.get("type") or "") != "page":
                    continue
                if _is_detection_tab_url(info.get("url")):
                    tid_stale = str(info.get("targetId") or "")
                    if tid_stale:
                        await client.send_raw("Target.closeTarget", {"targetId": tid_stale})
                        logger.info(
                            f"[EventMonitor] closed stale detection tab ...{tid_stale[-6:]} "
                            f"from a previous session"
                        )
        except Exception as _stale_err:
            logger.debug(f"[EventMonitor] stale detection-tab sweep skipped: {_stale_err}")
        # Stamp the new tab with the marker fragment (path routing on the
        # monitored sites; the fragment does not affect page load).
        marked_url = monitor_url.split("#", 1)[0] + _DETECTION_TAB_MARKER
        res = await client.send_raw(
            "Target.createTarget",
            {"url": marked_url, "newWindow": False, "background": True},
        )
        tid = str((res or {}).get("targetId") or "") if isinstance(res, dict) else ""
        return tid
    except Exception as exc:
        logger.warning(f"[EventMonitor] dedicated detection tab open failed: {exc}")
        return ""
    finally:
        if client is not None:
            try:
                await client.stop()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# mt059 Phase 1: live-chat WebSocket-frame CAPTURE diagnostic
# ---------------------------------------------------------------------------
# Goal (2C): detect new customer messages from CDP Network.webSocketFrameReceived
# events instead of polling Runtime.evaluate on the saturated front-desk
# renderer.  WS frames are delivered by Chrome's BROWSER process, not the
# renderer JS thread, so they are immune to scrape/focus contention.
#
# BLOCKER this capture removes: we have ZERO samples of the site's WS frames, so
# we cannot know which frame == "new incoming customer message" nor how to
# extract (customer, text) from it.  The live-chat site very likely uses BINARY
# protobuf frames, in which case payloadData is base64 and unparseable without
# the schema.  This diagnostic records real frames so Phase 2 (the parser +
# 新消息 dispatch integration) can be written against actual data instead of
# guesswork.
#
# Entirely env-gated (ECAN_LIVE_CHAT_WS_CAPTURE=1) and runs on its OWN dedicated
# independent CDP client (never the renderer-polling client, never the agent's
# shared client), so a normal run is completely unaffected.
# ws179: env-tunable — the default 600 capped out ~60s into the 2026-07-16 run,
# leaving the open/claim click test blind to WS frames; raise for capture runs.
try:
    _LIVE_CHAT_WS_CAPTURE_MAX_FRAMES = int(
        (_live_chat_env("ECAN_LIVE_CHAT_WS_CAPTURE_MAX_FRAMES") or "600") or 600)
except (TypeError, ValueError):
    _LIVE_CHAT_WS_CAPTURE_MAX_FRAMES = 600  # stop logging after this many to bound log size


async def _start_live_chat_ws_frame_capture(session: Any, target_id: str, label: str):
    """Attach a dedicated CDP client to *target_id*, enable Network, and log the
    site's WebSocket frames so the frame format can be reverse-engineered.

    Returns the CDP client (so the caller can stop it on monitor teardown) or
    None if it could not be established.  Best-effort and fully isolated: any
    failure is swallowed — this must never break the live DOM monitor.
    """
    if (_live_chat_env("ECAN_LIVE_CHAT_WS_CAPTURE") or "") != "1":
        return None
    if not target_id:
        logger.warning("[LIVE-CHAT-WS-CAPTURE] no target_id — capture not started")
        return None

    cdp_url = getattr(session, "cdp_url", None)
    if not cdp_url:
        bp = getattr(session, "browser_profile", None)
        cdp_url = getattr(bp, "cdp_url", None) if bp else None
    if not cdp_url:
        logger.warning("[LIVE-CHAT-WS-CAPTURE] no cdp_url on session — capture not started")
        return None

    try:
        from cdp_use import CDPClient as _CapCDPClient

        client = _CapCDPClient(url=cdp_url)
        await client.start()
        attach = await client.send_raw(
            "Target.attachToTarget", {"targetId": target_id, "flatten": True}
        )
        sid = attach.get("sessionId")
        if not sid:
            logger.warning("[LIVE-CHAT-WS-CAPTURE] attachToTarget returned no sessionId")
            await client.stop()
            return None
        await client.send_raw("Network.enable", {}, session_id=sid)

        # mt059+ (2026-06-04, spike b): also attach to any OTHER real site tabs
        # (the MAIN tab where sends/HTTP happen, not just the monitor's tab) so the
        # one isolated capture session sees BOTH incoming WS frames AND outgoing
        # HTTP sends + their auth headers.
        sids = [sid]
        try:
            _tinfos = (await client.send_raw("Target.getTargets", {})).get("targetInfos", [])
            for _t in _tinfos:
                if _t.get("type") != "page" or "jinritemai" not in (_t.get("url") or ""):
                    continue
                _tid = _t.get("targetId")
                if not _tid or _tid == target_id:
                    continue
                try:
                    _s2 = (await client.send_raw(
                        "Target.attachToTarget", {"targetId": _tid, "flatten": True})).get("sessionId")
                    if _s2:
                        await client.send_raw("Network.enable", {}, session_id=_s2)
                        sids.append(_s2)
                except Exception:
                    pass
        except Exception:
            pass
        for _s in sids:
            try:
                await client.send_raw("Runtime.enable", {}, session_id=_s)
            except Exception:
                pass

        import json as _json
        # ws035: route the high-volume per-frame capture to its own async sink
        # (eCan.wscap.log) so it stops drowning the operational log. Configured in
        # logger_helper; an inline kill-switch env there routes it back to the main log.
        _cap_log = logging.getLogger("eCan.wscap")
        ws_urls: Dict[str, str] = {}        # requestId -> url
        counter = {"frames": 0, "http": 0, "capped": False}

        def _preview(opcode: int, payload: str) -> str:
            # opcode 1 = text (UTF-8), 2 = binary (base64), 8/9/10 = control.
            if opcode == 1:
                return f"text[{len(payload)}]: {payload[:240]!r}"
            try:
                import base64
                raw = base64.b64decode(payload, validate=False)
                return f"binary[b64={len(payload)} bytes={len(raw)}] head_hex={raw[:24].hex()}"
            except Exception:
                return f"binary[b64={len(payload)}] (decode failed)"

        def _capjson(rec: dict) -> None:
            # FULL record on ONE line so it can be parsed out of eCan.log offline
            # (the customer already ships eCan.log — no extra file to collect).
            try:
                _cap_log.info("[LIVE-CHAT-WS-CAP-JSON] " + _json.dumps(rec, ensure_ascii=False))
            except Exception:
                pass

        def _on_created(params, session_id=None):
            try:
                rid = params.get("requestId", "")
                url = params.get("url", "")
                ws_urls[rid] = url
                logger.info(f"[LIVE-CHAT-WS-CAPTURE] created rid=...{rid[-6:]} url={url}")
                _capjson({"k": "ws_created", "url": url})
            except Exception:
                pass

        def _on_frame(direction):
            def _handler(params, session_id=None):
                try:
                    if counter["capped"]:
                        return
                    rid = params.get("requestId", "")
                    resp = params.get("response", {}) or {}
                    opcode = int(resp.get("opcode", -1))
                    if opcode in (8, 9, 10):  # close/ping/pong — skip noise
                        return
                    payload = resp.get("payloadData", "") or ""
                    counter["frames"] += 1
                    _cap_log.info(
                        f"[LIVE-CHAT-WS-CAPTURE] {direction} rid=...{rid[-6:]} "
                        f"url={ws_urls.get(rid, '?')} opcode={opcode} {_preview(opcode, payload)}"
                    )
                    _capjson({"k": "ws", "dir": direction, "opcode": opcode,
                              "url": ws_urls.get(rid, "?"), "payload_b64": payload})  # FULL payload
                    if counter["frames"] >= _LIVE_CHAT_WS_CAPTURE_MAX_FRAMES:
                        counter["capped"] = True
                        logger.info(
                            f"[LIVE-CHAT-WS-CAPTURE] frame cap "
                            f"({_LIVE_CHAT_WS_CAPTURE_MAX_FRAMES}) reached — further frames suppressed"
                        )
                except Exception:
                    pass
            return _handler

        def _on_http(params, session_id=None):
            # Data-bearing requests to ByteDance hosts: the send endpoint + the
            # anti-bot/auth header shape (X-Bogus/a_bogus/msToken/...).
            try:
                if counter["http"] >= 300:
                    return
                req = params.get("request", {}) or {}
                url = req.get("url", "")
                if not any(h in url for h in ("jinritemai", "byted", "douyin", "snssdk")):
                    return
                if req.get("method") == "GET" and not req.get("postData"):
                    return
                counter["http"] += 1
                _capjson({"k": "http", "method": req.get("method"), "url": url[:400],
                          "headers": req.get("headers", {}), "postData": str(req.get("postData", ""))[:2000]})
            except Exception:
                pass

        # ── Product-detail response-body capture (Step 0, gated) ──────────────
        # The PC product card is slim (title/price + a few badges); the rich
        # attributes the customer asks about (材质/成分/运费险/包邮/优惠券) live in
        # the product-detail responses the seller backend already serves. The
        # request handler above logs only the request side. With this flag on we
        # also pull the RESPONSE body for the conversation/product endpoints so we
        # can map which one carries those fields (one card send is enough). Bodies
        # are large, so this is OFF by default and capped.
        _capture_detail = (_live_chat_env("ECAN_LIVE_CHAT_PRODUCT_DETAIL_CAPTURE") or "0") == "1"
        # ws186: parse the same response bodies into the site product-detail
        # store (authoritative 价格/券/发货 for Q&A card context) — production
        # path, independent of the diagnostic log capture above. The parse is a
        # json.loads per matched response (rare: card arrivals / workstation
        # refreshes), all site-specific logic lives in the hook module.
        # Kill: ECAN_LIVE_CHAT_CARD_JSON=0.
        _parse_detail = (_live_chat_env("ECAN_LIVE_CHAT_CARD_JSON") or "1") != "0"
        _detail_url_keys = ("get_consulting_products", "get_user_card",
                            "get_product_list", "get_consulting_product",
                            "product/detail", "goods/detail",
                            "getTemplateCardDataV2")
        _detail_counter = {"n": 0, "parsed": 0}
        _detail_pending: Dict[str, dict] = {}   # requestId -> {url, status, sid}

        def _on_response(params, session_id=None):
            # Match product-detail responses; defer the body fetch to
            # loadingFinished (the body isn't buffered yet at responseReceived).
            try:
                resp = params.get("response", {}) or {}
                url = resp.get("url", "") or ""
                if not any(k in url for k in _detail_url_keys):
                    return
                _detail_pending[params.get("requestId", "")] = {
                    "url": url, "status": resp.get("status"), "sid": session_id}
            except Exception:
                pass

        _detail_cap_tasks: set = set()   # strong refs to detached body-fetch tasks

        async def _fetch_detail_body(rid, meta):
            try:
                try:
                    body_res = await client.send_raw(
                        "Network.getResponseBody", {"requestId": rid},
                        session_id=meta.get("sid"))
                except Exception as _be:
                    logger.info(f"[LIVE-CHAT-PRODUCT-DETAIL-CAP] body fetch failed url={meta['url'][:120]} err={_be}")
                    return
                body = body_res.get("body", "") or ""
                # ws186: feed the site's product-detail store (parse only — no body logging).
                if _parse_detail and _detail_counter["parsed"] < 500:
                    try:
                        _pds186 = _live_chat_bridge().product_detail_store
                        if _pds186.note_detail_body(meta.get("url", ""), body):
                            _detail_counter["parsed"] += 1
                    except Exception:
                        pass
                if _capture_detail and _detail_counter["n"] < 40:
                    _detail_counter["n"] += 1
                    # Log to main eCan.log (ships with the run) — full body on one line.
                    logger.info(
                        f"[LIVE-CHAT-PRODUCT-DETAIL-CAP] #{_detail_counter['n']} "
                        f"status={meta.get('status')} url={meta['url'][:200]} body={body!r}"
                    )
                    _capjson({"k": "product_detail", "url": meta["url"],
                              "status": meta.get("status"), "body": body})
            except Exception:
                pass

        def _on_loading_finished(params, session_id=None):
            # ws181: must NOT await inside the handler — cdp_use runs event
            # handlers inline on its single read loop, so awaiting send_raw here
            # deadlocks the pump (the same loop has to read that response) —
            # the ws120 lesson, re-introduced by this capture. This exact
            # deadlock froze the WHOLE capture client at FIRST-CARD arrival in
            # 3/3 runs (wscap last write 10:13:00 / 21:48:23 / 14:15:54, each
            # ending on the card's getTemplateCardDataV2): the card makes the
            # page fetch get_consulting_products, which matches
            # _detail_url_keys. Schedule the body fetch detached instead.
            try:
                rid = params.get("requestId", "")
                meta = _detail_pending.pop(rid, None)
                if meta is None:
                    return
                # ws186: keep fetching while either consumer still wants bodies.
                if not ((_capture_detail and _detail_counter["n"] < 40)
                        or (_parse_detail and _detail_counter["parsed"] < 500)):
                    return
                _t = asyncio.create_task(_fetch_detail_body(rid, meta))
                _detail_cap_tasks.add(_t)
                _t.add_done_callback(_detail_cap_tasks.discard)
            except Exception:
                pass

        reg = client._event_registry
        reg.register("Network.webSocketCreated", _on_created)
        reg.register("Network.webSocketFrameReceived", _on_frame("recv"))
        reg.register("Network.webSocketFrameSent", _on_frame("sent"))
        reg.register("Network.requestWillBeSent", _on_http)
        if _capture_detail or _parse_detail:
            reg.register("Network.responseReceived", _on_response)
            reg.register("Network.loadingFinished", _on_loading_finished)
            logger.info(
                f"[LIVE-CHAT-PRODUCT-DETAIL-CAP] enabled — capture={_capture_detail} "
                f"parse={_parse_detail} (ws186 card-JSON store)")

        # In-page send-handle probe — READ-ONLY (only inspects `window`; never
        # calls a send fn).  Runs twice so a late-initialising IM SDK is caught.
        # Deep send-handle probe: recurse one level into chatd / pigeon event bus,
        # AND install a DEFENSIVE send-tracer (wraps send-like methods; ALWAYS calls
        # through to the original, logging in a swallowed try/catch so it can never
        # block a real send) onto window.__ecan_send_trace.  The +25s round installs
        # it; the +70s round returns what fired when the bot/human sent a reply.
        _JS_SEND_PROBE = r"""
(function(){var o={sendCandidates:[],deep:[],sendTrace:[],reactRoot:false,error:null};try{
 var roots=['chatd','__mona_pigeon_event','__WORKBENCH_EVENT_SDK_IN_WINDOW__','pigeon','__pigeon','imSdk','im','PigeonIM'];
 function mem(v){var m=[];try{for(var p in v){try{if(/send|message|emit|dispatch|sdk|conn|socket|reply|post/i.test(p))m.push(p+':'+(typeof v[p]));}catch(e){}}}catch(e){}return m.slice(0,40);}
 for(var i=0;i<roots.length;i++){var k=roots[i];var v;try{v=window[k];}catch(e){continue;}if(!v)continue;
  o.deep.push({root:k,type:(typeof v),members:mem(v)});
  try{for(var p in v){try{var sv=v[p];if(sv&&(typeof sv==='object'||typeof sv==='function')){var mm=mem(sv);if(mm.length)o.sendCandidates.push({path:k+'.'+p,members:mm});}}catch(e){}}}catch(e){}}
 o.reactRoot=!!document.querySelector('#root,[data-reactroot]');
 if(!window.__ecan_send_trace)window.__ecan_send_trace=[];
 function wrap(obj,name,label){try{var orig=obj[name];if(typeof orig!=='function'||orig.__ecanw)return;var w=function(){try{var a=[];for(var i=0;i<Math.min(arguments.length,3);i++){var x=arguments[i];try{a.push(typeof x==='object'?JSON.stringify(x).slice(0,300):String(x).slice(0,200));}catch(e){a.push('['+(typeof x)+']');}}window.__ecan_send_trace.push({fn:label,args:a});}catch(e){}return orig.apply(this,arguments);};w.__ecanw=true;obj[name]=w;}catch(e){}}
 for(var i=0;i<roots.length;i++){var k=roots[i];var v;try{v=window[k];}catch(e){continue;}if(!v)continue;try{for(var p in v){try{if(/^(send|sendMessage|sendMsg|sendText|emit|emitByApp|emitByPlugin|reply|postMessage)$/i.test(p)&&typeof v[p]==='function')wrap(v,p,k+'.'+p);}catch(e){}}}catch(e){}}
 o.sendTrace=(window.__ecan_send_trace||[]).slice(-20);
}catch(e){o.error=String(e);}return JSON.stringify(o);})()
"""

        # Probe JS is overridable from a file (env ECAN_LIVE_CHAT_PROBE_JS_FILE) so the
        # send-handle hunt can iterate WITHOUT an app rebuild — drop in a new .js,
        # restart, capture again.  Falls back to the built-in static probe above.
        _probe_js = _JS_SEND_PROBE
        try:
            _pjf = (_live_chat_env("ECAN_LIVE_CHAT_PROBE_JS_FILE") or "").strip()
            if _pjf and os.path.isfile(_pjf):
                _txt = open(_pjf, encoding="utf-8").read().strip()
                if _txt:
                    _probe_js = _txt
                    logger.info(f"[LIVE-CHAT-WS-CAPTURE] probe JS overridden from file {_pjf} ({len(_txt)} chars)")
        except Exception as _pjf_err:
            logger.debug(f"[LIVE-CHAT-WS-CAPTURE] probe-js-file read failed (using default): {_pjf_err}")

        async def _run_js_probe():
            for _delay in (25, 70):
                try:
                    await asyncio.sleep(_delay)
                except Exception:
                    return
                for _s in list(sids):
                    try:
                        _r = await client.send_raw(
                            "Runtime.evaluate",
                            {"expression": _probe_js, "returnByValue": True},
                            session_id=_s,
                        )
                        _v = (_r.get("result") or {}).get("value")
                        if _v:
                            _capjson({"k": "js_probe", "sid": str(_s)[-6:], "probe": _json.loads(_v)})
                    except Exception:
                        pass

        try:
            setattr(client, "_ecan_ws_probe_task", asyncio.create_task(_run_js_probe()))
        except Exception:
            pass

        logger.info(
            f"[LIVE-CHAT-WS-CAPTURE] started for label={label!r} targets={len(sids)} "
            f"(env ECAN_LIVE_CHAT_WS_CAPTURE=1); FULL frames+http+probe -> [LIVE-CHAT-WS-CAP-JSON] in eCan.log"
        )
        return client
    except Exception as exc:
        logger.warning(f"[LIVE-CHAT-WS-CAPTURE] failed to start: {exc}")
        return None


async def _monitor_runtime_evaluate(
    session: Any,
    mon_client: Any,
    params: Dict[str, Any],
    *,
    session_id: str,
) -> Dict[str, Any]:
    """Run monitor Runtime.evaluate without racing the site's send/scrape evals."""

    async def _send_eval() -> Dict[str, Any]:
        return await mon_client.send_raw(
            "Runtime.evaluate",
            params,
            session_id=session_id,
        )

    try:
        operation_lock = _live_chat_bridge().dom.session_cdp_operation_lock(session)
    except Exception:
        operation_lock = None

    async def _send_with_optional_operation_lock() -> Dict[str, Any]:
        if operation_lock is not None:
            async with operation_lock:
                return await _send_eval()
        return await _send_eval()

    return await asyncio.wait_for(
        _send_with_optional_operation_lock(),
        timeout=_MONITOR_RUNTIME_EVALUATE_TIMEOUT_S,
    )


def register_monitor_set(monitor_set: ActiveMonitorSet) -> None:
    """Register an active monitor set in the global registry."""
    global _active_monitor_sets
    _active_monitor_sets[monitor_set.monitor_set_id] = monitor_set
    logger.debug(f"[EventMonitor] Registered monitor set {monitor_set.monitor_set_id} in global registry")


def unregister_monitor_set(monitor_set_id: str) -> None:
    """Unregister a monitor set from the global registry."""
    global _active_monitor_sets
    if monitor_set_id in _active_monitor_sets:
        del _active_monitor_sets[monitor_set_id]
        logger.debug(f"[EventMonitor] Unregistered monitor set {monitor_set_id} from global registry")


async def cleanup_all_monitors() -> None:
    """Stop all active monitors in the global registry.
    
    Called when the runner shuts down or when explicitly cleaning up resources.
    """
    global _active_monitor_sets
    monitor_sets = list(_active_monitor_sets.values())
    if not monitor_sets:
        return
    
    logger.info(f"[EventMonitor] Cleaning up {len(monitor_sets)} active monitor set(s)")
    for monitor_set in monitor_sets:
        try:
            await stop_monitors(monitor_set, session=None)
        except Exception as e:
            logger.debug(f"[EventMonitor] Error during cleanup of monitor set {monitor_set.monitor_set_id}: {e}")
    
    _active_monitor_sets.clear()
    logger.info("[EventMonitor] All monitor sets cleaned up")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class EventMonitorConfig:
    """One event-capture rule from the node editor."""

    id: str = ""
    label: str = ""
    enabled: bool = True
    source_type: str = "http_polling"  # http_polling | websocket | sse | dom_mutation | cdp_raw

    def __setattr__(self, name, value):
        if name == "label" and hasattr(self, "label") and self.label and value != self.label:
            import traceback
            logger.warning(
                f"[EventMonitorConfig] LABEL MUTATION DETECTED: "
                f"'{self.label}' -> '{value}'\n"
                f"{''.join(traceback.format_stack()[-5:])}"
            )
        super().__setattr__(name, value)

    # Common
    url_patterns: List[str] = field(default_factory=list)

    # HTTP Polling
    methods: List[str] = field(default_factory=lambda: ["GET", "POST"])
    content_filters: List[str] = field(default_factory=list)  # substring matches
    min_body_length: int = 10

    # WebSocket
    frame_direction: str = "incoming"  # incoming | outgoing | both

    # SSE
    sse_event_types: List[str] = field(default_factory=list)

    # DOM Mutation
    dom_selector: str = ""
    dom_attributes: bool = False
    dom_child_list: bool = True
    dom_subtree: bool = True
    dom_check_interval_ms: int = 750  # mt058A: saner default for the shared front-desk renderer (see form-meta.tsx)

    # CDP Raw
    cdp_domain: str = ""
    cdp_event_method: str = ""
    cdp_filter_expr: str = ""


def _safe_json_loads(raw: Any) -> Any:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


_LIVE_CHAT_BEFORE_EXTRACT_CURRENT_TAB_JS = r"""
(async function() {
  try {
    var current = document.querySelector('[data-qa-id="qa-active-chat-tab"]');
    if (!current) return;
    var tabBtn = current.closest('[role="tab"]');
    var tabWrap = current.closest('.auxo-tabs-tab, .tab');
    var selected =
      (tabBtn && tabBtn.getAttribute('aria-selected') === 'true') ||
      (tabWrap && /\b(auxo-tabs-tab-active|active)\b/.test(String(tabWrap.className || '')));
    if (!selected) {
      current.click();
      await new Promise(function(resolve) { setTimeout(resolve, 160); });
    }
  } catch (e) {}
})()
"""


def _default_dom_extractor_config(cfg: EventMonitorConfig) -> Dict[str, Any]:
    selectors = [s.strip() for s in (cfg.dom_selector or "").split(",") if s and s.strip()]
    for fallback_selector in (
        "#stat-sessions",
        "#customer-list",
        ".customer-item",
        ".session-row",
        '#chantListScrollArea',
        'a[href*="/chat?session="]',
        'a[href*="chat?session="]',
    ):
        if fallback_selector not in selectors:
            selectors.append(fallback_selector)

    page_patterns = [p for p in cfg.url_patterns if isinstance(p, str) and p.strip()]
    # Do NOT default to ["/control"] — that is test-rig specific.
    # Monitors without explicit URL patterns should run on whatever page
    # the browser agent is currently viewing (e.g. a live-chat workstation,
    # Shopify, etc.).

    return {
        "version": 1,
        "page_url_patterns": page_patterns,  # empty = match any page
        "before_extract_js": _LIVE_CHAT_BEFORE_EXTRACT_CURRENT_TAB_JS,
        "roots": selectors or ["body"],
        "items": [
            # ── Live-chat workstation sessions ────────────────────────────────
            # Matches ALL session items (not filtered by badge class).
            # Detection strategy: use data-btm (last-message ID) as part of
            # the composite identity key ["name", "last_msg_id"].
            # When a new message arrives, data-btm changes → old key is removed,
            # new key is added → emit_on:"added" fires.
            # Avoids:
            #   - :has() which silently fails in CDP querySelectorAll context
            #   - obfuscated badge class names that change on each deploy
            {
                "selector": '[data-qa-id="qa-conversation-chat-item"]',
                "fields": {
                    "name": {
                        "source": "attr",
                        "selector": ".MP1bk3ccfHC9V2SnPCGD",
                        "attr": "title",
                        "fallback": [
                            {"source": "text", "selector": ".MP1bk3ccfHC9V2SnPCGD"},
                            {"source": "text", "selector": ".Jv6FtqUv5VoYARd2pp4y"},
                        ],
                    },
                    "last_msg_id": {
                        # data-btm is the last-message ID tag; changes with each new message
                        "source": "attr",
                        "selector": "[data-btm]",
                        "attr": "data-btm",
                    },
                    "last_message": {
                        "source": "text",
                        "selector": ".lF_M7QiFB0ukHWpMfQde span",
                    },
                    "timestamp": {
                        "source": "text",
                        "selector": ".CEnLM8MEGksTdgi_8Lqf",
                    },
                    "sidebar_scope": {
                        "source": "attr",
                        "attr": "data-btm-id",
                        "regex": r"\.([A-Za-z]+)$",
                        "group": 1,
                    },
                },
            },
            # ── Generic test-rig / chat-session links ─────────────────────────
            {
                "selector": 'a[href*="/chat?session="], a[href*="chat?session="]',
                "fields": {
                    "session": {
                        "source": "attr",
                        "attr": "href",
                        "regex": r"[?&]session=([^&]+)",
                        "group": 1,
                    },
                    "chatUrl": {"source": "attr", "attr": "href"},
                    "name": {
                        "source": "closest_text",
                        "closest": ".customer-card, .customer-item, .session-row, li, tr, div",
                        "regex": r"Customer\s*:?\s*([A-Za-z0-9_\-]+)",
                        "group": 1,
                        "fallback": [
                            {
                                "source": "closest_text",
                                "closest": ".customer-card, .customer-item, .session-row, li, tr, div",
                                "split_before": " Session",
                            },
                            {"source": "text"},
                        ],
                    },
                },
            },
        ],
        "key_field": "name",
        "identity": {
            # Composite key: session name + last-message ID.
            # Each new message changes last_msg_id → triggers "added".
            "key_fields": ["name", "last_msg_id"],
        },
        "empty_text_patterns": ["no customers", "no active customers", "no customers yet"],
        "emit_on": "added",
    }


def _resolve_dom_extractor_config(cfg: EventMonitorConfig) -> Dict[str, Any]:
    advanced = _safe_json_loads(cfg.cdp_filter_expr)
    if isinstance(advanced, dict):
        merged = _default_dom_extractor_config(cfg)
        merged.update({k: v for k, v in advanced.items() if v is not None})

        # If the ADVANCED config explicitly provides a key_field, override identity —
        # BUT only if the advanced config does NOT already provide a composite identity
        # with multiple key_fields (e.g. ["customer_name", "last_message"]).
        explicit_key_field = str(advanced.get("key_field") or "").strip()
        if explicit_key_field:
            merged["key_field"] = explicit_key_field
            adv_identity = advanced.get("identity")
            adv_key_fields = (
                adv_identity.get("key_fields")
                if isinstance(adv_identity, dict) and isinstance(adv_identity.get("key_fields"), list)
                else []
            )
            if len(adv_key_fields) > 1:
                # Preserve the composite identity from the advanced config
                merged["identity"] = adv_identity
            else:
                merged["identity"] = {"key_fields": [explicit_key_field]}

        # Support shorthand extractor configs saved by the skill editor, e.g.
        # {page_url_patterns, roots, item_selector, fields, key_field, filters}.
        item_selector = str(advanced.get("item_selector") or merged.get("item_selector") or "").strip()
        raw_fields = advanced.get("fields") if isinstance(advanced.get("fields"), dict) else (
            merged.get("fields") if isinstance(merged.get("fields"), dict) else {}
        )
        _DOM_PROPS = {"textContent", "innerText", "innerHTML", "value", "checked"}
        if item_selector and raw_fields:
            normalized_fields = {}
            for field_name, spec in raw_fields.items():
                if not isinstance(spec, dict):
                    continue
                normalized = dict(spec)
                if normalized.get("text") is True:
                    normalized.pop("text", None)
                    normalized.setdefault("source", "text")
                elif normalized.get("attr") and not normalized.get("source"):
                    if normalized["attr"] in _DOM_PROPS:
                        normalized.pop("attr")
                        normalized.setdefault("source", "text")
                    else:
                        normalized.setdefault("source", "attr")
                elif not normalized.get("source"):
                    normalized.setdefault("source", "text")
                normalized_fields[str(field_name)] = normalized
            if normalized_fields:
                merged["items"] = [{
                    "selector": item_selector,
                    "fields": normalized_fields,
                }]

        # Defensively normalize any merged item field specs as well.
        normalized_items = []
        for item in (merged.get("items") or []):
            if not isinstance(item, dict):
                continue
            normalized_item = dict(item)
            fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
            normalized_fields = {}
            for field_name, spec in fields.items():
                if not isinstance(spec, dict):
                    continue
                normalized = dict(spec)
                if normalized.get("text") is True:
                    normalized.pop("text", None)
                    normalized.setdefault("source", "text")
                elif normalized.get("attr") and not normalized.get("source"):
                    if normalized["attr"] in _DOM_PROPS:
                        normalized.pop("attr")
                        normalized.setdefault("source", "text")
                    else:
                        normalized.setdefault("source", "attr")
                elif not normalized.get("source"):
                    normalized.setdefault("source", "text")
                normalized_fields[str(field_name)] = normalized
            if normalized_fields:
                normalized_item["fields"] = normalized_fields
            normalized_items.append(normalized_item)
        if normalized_items:
            merged["items"] = normalized_items

        # Some older saved monitor payloads omitted identity overrides even though
        # they set key_field=msg_id. Reassert the effective identity after item merge
        # — BUT only if the identity wasn't already explicitly set with multiple fields
        # (e.g. composite key ["name", "last_msg_id"] for change detection).
        effective_key_field = str(merged.get("key_field") or "").strip()
        if effective_key_field:
            identity_cfg = merged.get("identity")
            if not isinstance(identity_cfg, dict):
                identity_cfg = {}
            existing_key_fields = identity_cfg.get("key_fields") if isinstance(identity_cfg.get("key_fields"), list) else []
            if len(existing_key_fields) <= 1:
                # Only override if identity has 0 or 1 key field (not composite)
                identity_cfg["key_fields"] = [effective_key_field]
            merged["identity"] = identity_cfg

        return merged


def _normalize_url_for_monitor(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    normalized = raw.lower()
    if normalized.startswith("http://"):
        normalized = normalized[7:]
    elif normalized.startswith("https://"):
        normalized = normalized[8:]
    return normalized.rstrip("/")


# Dedicated detection tabs are stamped with this URL fragment at creation so a
# LATER app session (reusing the same browser) can recognize them: without the
# marker, browser-use reattaching to a surviving browser can adopt a leftover
# detection tab as the agent's MAIN tab (2026-08-28 customer incident: focus
# landed on the prior session's detection tab, whose workspace instance never
# renders the conversation list -> every DOM path saw rows=0 for the whole
# session while the real logged-in tab sat unused). Marked tabs are excluded
# from monitor-target resolution and stale ones are closed at setup.
_DETECTION_TAB_MARKER = "#ecan_det"


def _is_detection_tab_url(url: Any) -> bool:
    return str(url or "").endswith(_DETECTION_TAB_MARKER)


def _monitor_url_matches(actual_url: str, pattern: str) -> bool:
    actual = _normalize_url_for_monitor(actual_url)
    wanted = _normalize_url_for_monitor(pattern)
    if not actual or not wanted:
        return False
    return wanted in actual


def _target_info_get(target_info: Any, key: str, default: Any = "") -> Any:
    if isinstance(target_info, dict):
        return target_info.get(key, default)
    return getattr(target_info, key, default)


def _target_info_matches_patterns(target_info: Any, patterns: List[str]) -> bool:
    target_type = str(_target_info_get(target_info, "type") or _target_info_get(target_info, "target_type") or "")
    if target_type not in ("page", "tab"):
        return False
    target_url = str(_target_info_get(target_info, "url") or "")
    if _is_detection_tab_url(target_url):
        # Never re-target a monitor onto a dedicated detection tab (its own
        # binding is by explicit target id, not by URL match).
        return False
    if not patterns:
        return True
    return any(_monitor_url_matches(target_url, pat) for pat in patterns)


async def _resolve_monitor_target_id_live(
    session: Any,
    cfg: EventMonitorConfig,
    extractor_cfg: Dict[str, Any],
    *,
    avoid_target_id: str = "",
) -> str:
    """Resolve target from BrowserSession state, then Chrome's live target list.

    SessionManager is normally enough, but a tab can be replaced or detached
    without the monitor's cached target_id being refreshed yet.  On attach
    failures, query Target.getTargets directly so a DOM monitor can recover
    from a dead target instead of polling the missing id forever.
    """
    avoid_target_id = str(avoid_target_id or "")
    try:
        candidate = _resolve_monitor_target_id(session, cfg, extractor_cfg)
    except Exception:
        candidate = ""
    candidate = str(candidate or "")
    if candidate and candidate != avoid_target_id:
        return candidate

    root = getattr(session, "_cdp_client_root", None)
    if root is None:
        return ""

    patterns = [p for p in (extractor_cfg.get("page_url_patterns") or []) if isinstance(p, str) and p.strip()]
    try:
        targets_result = await root.send.Target.getTargets()
    except Exception as exc:
        logger.debug(f"[EventMonitor] Live target refresh failed for '{cfg.label}': {exc}")
        return ""

    target_infos = []
    if isinstance(targets_result, dict):
        target_infos = list(targets_result.get("targetInfos") or [])
    else:
        target_infos = list(getattr(targets_result, "targetInfos", None) or [])

    focus_target_id = str(getattr(session, "agent_focus_target_id", "") or "")
    for target_info in target_infos:
        tid = str(_target_info_get(target_info, "targetId") or _target_info_get(target_info, "target_id") or "")
        if tid and tid == focus_target_id and tid != avoid_target_id and _target_info_matches_patterns(target_info, patterns):
            return tid

    for target_info in target_infos:
        tid = str(_target_info_get(target_info, "targetId") or _target_info_get(target_info, "target_id") or "")
        if tid and tid != avoid_target_id and _target_info_matches_patterns(target_info, patterns):
            return tid
    return ""


async def _retarget_monitor_target(
    mutation_state: Dict[str, Any],
    session: Any,
    cfg: EventMonitorConfig,
    extractor_cfg: Dict[str, Any],
    target_id: str,
    *,
    reason: str,
    avoid_target_id: str = "",
) -> str:
    fresh_target = await _resolve_monitor_target_id_live(
        session,
        cfg,
        extractor_cfg,
        avoid_target_id=avoid_target_id,
    )
    if fresh_target and fresh_target != target_id:
        logger.info(
            f"[EventMonitor] Re-targeted '{cfg.label}' monitor after {reason}: "
            f"old=...{target_id[-6:] if target_id else 'None'}, "
            f"new=...{fresh_target[-6:]}"
        )
        await _cleanup_monitor_cdp(mutation_state)
        mutation_state["target_id"] = fresh_target
        mutation_state.pop("_mon_cdp_attach_failed_target_id", None)
        mutation_state.pop("_mon_cdp_last_error", None)
        return fresh_target
    return target_id


async def _ensure_monitor_cdp_ready(session: Any, mutation_state: Dict[str, Any], label: str) -> bool:
    """Best-effort ensure the BrowserSession has an initialized root CDP client.

    Back-off and surface-once guard: after _CDP_UNREACHABLE_THRESHOLD consecutive
    failures we emit a single ERROR with a clear operator hint, then retry at
    _CDP_UNREACHABLE_BACKOFF_S intervals and stay quiet (DEBUG) until CDP
    recovers — at which point we log a matching INFO recovery line.
    """
    _CDP_UNREACHABLE_THRESHOLD = 3
    _CDP_UNREACHABLE_BACKOFF_S = 10.0
    _CDP_HEALTHY_INTERVAL_S = 1.0

    cdp_root = getattr(session, "_cdp_client_root", None)
    session_manager = getattr(session, "session_manager", None)
    if cdp_root is not None and session_manager is not None:
        if mutation_state.get("_cdp_unreachable_surfaced"):
            logger.info(
                f"[EventMonitor] CDP recovered for monitor '{label}' after "
                f"{mutation_state.get('_cdp_ready_fail_count', 0)} failed attempts"
            )
        mutation_state["_cdp_ready_fail_count"] = 0
        mutation_state["_cdp_unreachable_surfaced"] = False
        return True

    now = time.time()
    last_attempt = float(mutation_state.get("_cdp_ready_last_attempt", 0.0) or 0.0)
    surfaced = bool(mutation_state.get("_cdp_unreachable_surfaced"))
    min_interval = _CDP_UNREACHABLE_BACKOFF_S if surfaced else _CDP_HEALTHY_INTERVAL_S
    if now - last_attempt < min_interval:
        return False
    mutation_state["_cdp_ready_last_attempt"] = now

    fail_count = int(mutation_state.get("_cdp_ready_fail_count", 0) or 0)
    start_exc: Optional[BaseException] = None
    try:
        if not surfaced:
            logger.info(
                f"[EventMonitor] CDP not ready for monitor '{label}', attempting BrowserSession.start() "
                f"(root={cdp_root is not None}, session_manager={session_manager is not None})"
            )
        if hasattr(session, "start"):
            await session.start()
    except Exception as exc:
        start_exc = exc

    cdp_root = getattr(session, "_cdp_client_root", None)
    session_manager = getattr(session, "session_manager", None)
    ready = cdp_root is not None and session_manager is not None
    if ready:
        if surfaced:
            logger.info(
                f"[EventMonitor] CDP recovered for monitor '{label}' after "
                f"{fail_count} failed attempts"
            )
        mutation_state["_cdp_ready_fail_count"] = 0
        mutation_state["_cdp_unreachable_surfaced"] = False
        return True

    fail_count += 1
    mutation_state["_cdp_ready_fail_count"] = fail_count

    if fail_count >= _CDP_UNREACHABLE_THRESHOLD and not surfaced:
        mutation_state["_cdp_unreachable_surfaced"] = True
        exc_hint = f" (last error: {start_exc!r})" if start_exc is not None else ""
        logger.error(
            f"[EventMonitor] CDP unreachable for monitor '{label}' after "
            f"{fail_count} attempts — Chrome remote-debugging port appears to be "
            f"down. Check that Chrome is running and was launched with "
            f"--remote-debugging-port. Retrying every "
            f"{_CDP_UNREACHABLE_BACKOFF_S:.0f}s; further failures will be silent "
            f"until recovery.{exc_hint}"
        )
    elif start_exc is not None:
        logger.debug(
            f"[EventMonitor] ensure_monitor_cdp_ready failed for '{label}' "
            f"(attempt {fail_count}): {start_exc!r}"
        )
    return False


def _resolve_monitor_target_id(session: Any, cfg: EventMonitorConfig, extractor_cfg: Dict[str, Any]) -> str:
    """Resolve a stable target_id for a monitor.

    Prefer the session's current focused page target. If it does not match the
    monitor's page patterns, search all known page/tab targets for a matching URL.
    """
    try:
        sm = getattr(session, "session_manager", None)
        if sm is None:
            return str(getattr(session, "agent_focus_target_id", "") or "")

        patterns = [p for p in (extractor_cfg.get("page_url_patterns") or []) if isinstance(p, str) and p.strip()]
        focus_target_id = str(getattr(session, "agent_focus_target_id", "") or "")
        all_targets = sm.get_all_targets() or {}

        def _matches_target_url(target: Any) -> bool:
            target_url = str(getattr(target, "url", "") or "")
            # A leftover dedicated detection tab must never be adopted as the
            # monitor/scrape tab — its workspace instance doesn't render the
            # conversation list (2026-08-28 rows=0 incident).
            if _is_detection_tab_url(target_url):
                return False
            if not patterns:
                return True
            return any(_monitor_url_matches(target_url, pat) for pat in patterns)

        # For chat_message_added, always prefer the agent's focused target
        # (each service agent focuses its own chat tab).  Only fall through to
        # pattern search if agent_focus_target_id is empty/unset.
        if cfg.label == "chat_message_added" and focus_target_id:
            focus_target = sm.get_target(focus_target_id) if sm else None
            if focus_target and getattr(focus_target, "target_type", "") in ("page", "tab"):
                target_url = str(getattr(focus_target, "url", "") or "")
                # Sanity: make sure it's a chat page, not the control page —
                # and never a leftover dedicated detection tab.
                if not _is_detection_tab_url(target_url) and (
                    "/chat" in target_url or not target_url or "/control" not in target_url
                ):
                    return focus_target_id

        if focus_target_id:
            focus_target = sm.get_target(focus_target_id)
            if focus_target and getattr(focus_target, "target_type", "") in ("page", "tab") and _matches_target_url(focus_target):
                return focus_target_id

        for tid, target in all_targets.items():
            if getattr(target, "target_type", "") not in ("page", "tab"):
                continue
            if _matches_target_url(target):
                return str(tid)

        return focus_target_id
    except Exception:
        return str(getattr(session, "agent_focus_target_id", "") or "")
    return _default_dom_extractor_config(cfg)


def _build_dom_runtime_expression(extractor_cfg: Dict[str, Any]) -> str:
    cfg_json = json.dumps(extractor_cfg)
    return f"""
        (async function() {{
            const cfg = {cfg_json};
            const currentUrl = String((window && window.location && window.location.href) || '');

            function normalizeText(value) {{
                return String(value || '').replace(/\\s+/g, ' ').trim();
            }}

            function normalizePattern(value) {{
                const raw = String(value || '').trim();
                if (!raw) return '';
                try {{
                    const parsed = new URL(raw, currentUrl || window.location.origin);
                    return `${{parsed.pathname || ''}}${{parsed.search || ''}}${{parsed.hash || ''}}` || raw;
                }} catch (e) {{
                    return raw;
                }}
            }}

            function queryAllWithin(root, selector) {{
                if (!selector) return [];
                try {{
                    return Array.from((root || document).querySelectorAll(selector));
                }} catch (e) {{
                    return [];
                }}
            }}

            function readField(spec, el, root) {{
                if (!spec || typeof spec !== 'object') return '';
                const source = spec.source || 'text';
                const selector = spec.selector || '';
                const target = selector ? ((el && el.querySelector) ? el.querySelector(selector) : null) : el;
                let raw = '';

                if (source === 'literal') {{
                    raw = spec.value || '';
                }} else if (source === 'attr') {{
                    const attrTarget = target || el;
                    const attrName = spec.attr || 'href';
                    const domProps = ['textContent','innerText','innerHTML','value','checked','src','href'];
                    if (domProps.includes(attrName) && attrTarget) {{
                        raw = normalizeText(String(attrTarget[attrName] || ''));
                    }} else {{
                        raw = attrTarget && attrTarget.getAttribute ? (attrTarget.getAttribute(attrName) || '') : '';
                    }}
                }} else if (source === 'closest_text') {{
                    const closestBase = el && el.closest && spec.closest ? el.closest(spec.closest) : null;
                    raw = normalizeText((closestBase && closestBase.textContent) || (el && el.textContent) || '');
                }} else if (source === 'root_text') {{
                    raw = normalizeText((root && root.textContent) || '');
                }} else {{
                    raw = normalizeText((target && target.textContent) || '');
                }}

                if (spec.regex) {{
                    try {{
                        const match = String(raw || '').match(new RegExp(spec.regex, spec.flags || 'i'));
                        raw = match ? (match[spec.group || 1] || match[0] || '') : '';
                    }} catch (e) {{}}
                }}
                if (!raw && Array.isArray(spec.fallback)) {{
                    for (const fb of spec.fallback) {{
                        raw = readField(fb, el, root);
                        if (raw) break;
                    }}
                }}
                if (spec.split_before && raw) {{
                    raw = String(raw).split(spec.split_before)[0] || raw;
                }}
                return normalizeText(raw);
            }}

            const pagePatterns = Array.isArray(cfg.page_url_patterns) ? cfg.page_url_patterns : [];
            if (pagePatterns.length > 0) {{
                let currentPath = currentUrl;
                try {{
                    const parsedCurrent = new URL(currentUrl);
                    currentPath = `${{parsedCurrent.pathname || ''}}${{parsedCurrent.search || ''}}${{parsedCurrent.hash || ''}}` || currentUrl;
                }} catch (e) {{}}
                const pageOk = pagePatterns.some(p => {{
                    const rawPattern = String(p || '').trim();
                    const normalizedPattern = normalizePattern(rawPattern);
                    if (!rawPattern && !normalizedPattern) return false;
                    return (
                        (rawPattern && currentUrl.includes(rawPattern)) ||
                        (normalizedPattern && currentUrl.includes(normalizedPattern)) ||
                        (rawPattern && currentPath.includes(rawPattern)) ||
                        (normalizedPattern && currentPath.includes(normalizedPattern)) ||
                        (rawPattern && rawPattern.includes(currentPath)) ||
                        (normalizedPattern && normalizedPattern.includes(currentPath))
                    );
                }});
                if (!pageOk) {{
                    return JSON.stringify({{status: 'page_mismatch', currentUrl}});
                }}
            }}

            if (cfg.state_fetch && typeof cfg.state_fetch === 'object') {{
                try {{
                    const stateUrl = String(cfg.state_fetch.url || '').trim();
                    const adapter = String(cfg.state_fetch.adapter || '').trim();
                    if (stateUrl && adapter) {{
                        const resp = await fetch(stateUrl, {{ credentials: 'include' }});
                        const data = await resp.json();
                        if (adapter === 'test_rig_control_customers_v1') {{
                            const customersMap = (data && typeof data === 'object' && data.customers && typeof data.customers === 'object')
                                ? data.customers
                                : {{}};
                            const items = Object.values(customersMap).map(c => {{
                                const session = normalizeText((c && c.session_id) || '');
                                const name = normalizeText((c && c.name) || '');
                                return {{
                                    session,
                                    name,
                                    chatUrl: session ? `/chat?session=${{session}}` : '',
                                    identity_key: session,
                                }};
                            }}).filter(item => item.session);
                            if (items.length === 0) {{
                                return JSON.stringify({{
                                    status: 'empty',
                                    currentUrl,
                                    count: 0,
                                    items: [],
                                    key_field: 'session',
                                    key_fields: ['session'],
                                }});
                            }}
                            return JSON.stringify({{
                                status: 'ok',
                                currentUrl,
                                count: items.length,
                                items,
                                key_field: 'session',
                                key_fields: ['session'],
                            }});
                        }}
                    }}
                }} catch (e) {{}}
            }}

            if (cfg.before_extract_js) {{
                try {{
                    const maybePromise = (0, eval)(String(cfg.before_extract_js));
                    if (maybePromise && typeof maybePromise.then === 'function') {{
                        await maybePromise;
                    }}
                }} catch (e) {{}}
            }}

            const roots = [];
            const rootSelectors = Array.isArray(cfg.roots) ? cfg.roots : [];
            rootSelectors.forEach(s => queryAllWithin(document, s).forEach(el => roots.push(el)));
            if (roots.length === 0) roots.push(document.body);
            const rootDebug = roots.slice(0, 3).map((root, idx) => {{
                if (!root) return {{ index: idx, exists: false }};
                let html = '';
                let text = '';
                try {{
                    html = String(root.innerHTML || '').slice(0, 400);
                }} catch (e) {{}}
                try {{
                    text = normalizeText(root.textContent || '').slice(0, 200);
                }} catch (e) {{}}
                return {{
                    index: idx,
                    exists: true,
                    tag: String(root.tagName || '').toLowerCase(),
                    id: String(root.id || ''),
                    className: String(root.className || ''),
                    childCount: Number(root.childElementCount || 0),
                    html,
                    text,
                }};
            }});

            const keyField = cfg.key_field || '';
            const identityCfg = (cfg.identity && typeof cfg.identity === 'object') ? cfg.identity : {{}};
            const keyFields = Array.isArray(identityCfg.key_fields) ? identityCfg.key_fields.map(v => normalizeText(v)) : (keyField ? [keyField] : []);
            const itemSpecs = Array.isArray(cfg.items) ? cfg.items : [];
            const itemFilters = (cfg.filters && typeof cfg.filters === 'object') ? cfg.filters : {{}};
            const selectorDebug = itemSpecs.map((spec, idx) => {{
                const selector = String((spec && spec.selector) || '');
                let total = 0;
                const perRoot = [];
                for (const root of roots.slice(0, 3)) {{
                    const nodes = queryAllWithin(root, selector);
                    const count = Array.isArray(nodes) ? nodes.length : 0;
                    total += count;
                    perRoot.push(count);
                }}
                return {{ index: idx, selector, total, perRoot }};
            }});
            const pageDebug = {{
                bodyMsgCount: queryAllWithin(document, '.msg').length,
                rootMsgCount: queryAllWithin(document, '#messages .msg').length,
                bodyText: normalizeText((document.body && document.body.textContent) || '').slice(0, 400),
            }};
            const extractionDebug = [];
            const items = [];
            const seenKeys = new Set();

            for (const root of roots) {{
                if (!root) continue;
                for (const spec of itemSpecs) {{
                    const nodes = queryAllWithin(root, spec.selector || '');
                    for (const node of nodes) {{
                        const fields = (spec && spec.fields && typeof spec.fields === 'object') ? spec.fields : {{}};
                        const item = {{}};
                        for (const [fieldName, fieldSpec] of Object.entries(fields)) {{
                            item[fieldName] = readField(fieldSpec, node, root);
                        }}
                        let skipReason = '';
                        if (itemFilters.from_equals && normalizeText(item.from) !== normalizeText(itemFilters.from_equals)) {{
                            skipReason = `from_mismatch:${{normalizeText(item.from)}}!=${{normalizeText(itemFilters.from_equals)}}`;
                        }}
                        if (!skipReason && String((spec && spec.selector) || '') === '[data-qa-id="qa-conversation-chat-item"]') {{
                            const btmId = node && node.getAttribute ? String(node.getAttribute('data-btm-id') || '') : '';
                            const inCurrentList = !!(
                                (node && node.closest && node.closest('.pigeonChatNotScrollBox')) ||
                                btmId.endsWith('.current')
                            );
                            const inRecentList = !!(
                                (node && node.closest && node.closest('.pigeonChatScrollBox')) ||
                                btmId.endsWith('.recent') ||
                                btmId.endsWith('.systemConv')
                            );
                            item._section = inCurrentList ? 'current' : (inRecentList ? 'recent' : 'neither');  // ws156 diag
                            if (inRecentList && !inCurrentList) {{
                                skipReason = 'non_current_sidebar';
                            }}
                        }}
                        let itemKey = '';
                        if (keyFields.length > 0) {{
                            itemKey = normalizeText(
                                keyFields.map(fieldName => normalizeText(item[fieldName] || '')).join('|')
                            );
                        }} else if (keyField) {{
                            itemKey = normalizeText(item[keyField] || '');
                        }} else {{
                            itemKey = normalizeText(JSON.stringify(item));
                        }}
                        if (!itemKey) {{
                            // Be defensive for chat-message monitors: older saved configs can
                            // leak the wrong identity key fields, but msg_id is still the real
                            // stable identity for rendered chat messages.
                            for (const fallbackField of ['msg_id', 'message_id', 'session', 'chatUrl', 'timestamp', 'text']) {{
                                const fallbackValue = normalizeText(item[fallbackField] || '');
                                if (fallbackValue) {{
                                    itemKey = fallbackValue;
                                    break;
                                }}
                            }}
                        }}
                        if (!itemKey) {{
                            if (!skipReason) skipReason = 'empty_item_key';
                        }} else if (seenKeys.has(itemKey)) {{
                            if (!skipReason) skipReason = 'duplicate_item_key';
                        }}
                        extractionDebug.push({{
                            selector: String((spec && spec.selector) || ''),
                            item,
                            itemKey,
                            skipReason,
                        }});
                        if (skipReason) continue;
                        seenKeys.add(itemKey);
                        item.identity_key = itemKey;
                        items.push(item);
                    }}
                }}
            }}

            if (items.length === 0) {{
                const pageText = normalizeText((document.body && document.body.textContent) || '').toLowerCase();
                const empties = Array.isArray(cfg.empty_text_patterns) ? cfg.empty_text_patterns : [];
                if (empties.some(p => p && pageText.includes(String(p).toLowerCase()))) {{
                    return JSON.stringify({{
                        status: 'empty',
                        currentUrl,
                        count: 0,
                        items: [],
                        key_field: keyField,
                        debug: {{
                            rootSelectors,
                            rootCount: roots.length,
                            rootDebug,
                            selectorDebug,
                            pageDebug,
                            extractionDebug,
                        }}
                    }});
                }}
                return JSON.stringify({{
                    status: 'no_match',
                    currentUrl,
                    count: 0,
                    items: [],
                    key_field: keyField,
                    debug: {{
                        rootSelectors,
                        rootCount: roots.length,
                        rootDebug,
                        selectorDebug,
                        pageDebug,
                        extractionDebug,
                    }}
                }});
            }}

            // ws156 diag: surface SKIPPED chat-item rows (with reason + section + name) even on a
            // successful extraction, so we can see WHY a reopened/closed row is dropped (e.g.
            // non_current_sidebar = the closed/recent sidebar section, or empty_item_key =
            // nameless). extractionDebug is already built above; compact it to keep the payload small.
            var _skippedDiag = [];
            try {{
                for (var _sd = 0; _sd < extractionDebug.length; _sd++) {{
                    var _sde = extractionDebug[_sd];
                    if (!_sde || !_sde.skipReason) continue;
                    var _sdi = _sde.item || {{}};
                    _skippedDiag.push({{
                        skip: String(_sde.skipReason || ''),
                        section: String(_sdi._section || ''),
                        name: String(_sdi.name || _sdi.customer_name || _sdi.nickname || ''),
                        preview: String(_sdi.preview || _sdi.text || _sdi.last_message || '').slice(0, 40),
                        key: String(_sde.itemKey || '')
                    }});
                }}
            }} catch (_sderr) {{}}
            return JSON.stringify({{
                status: 'ok',
                currentUrl,
                count: items.length,
                items,
                skipped: _skippedDiag,
                key_field: keyField,
                key_fields: keyFields
            }});
        }})()
    """


def _parse_event_body_value(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return {}
        try:
            parsed = json.loads(s)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _build_normalized_browser_event(
    *,
    session: Any = None,
    monitor_id: str,
    label: str,
    source_type: str,
    params_obj: Dict[str, Any],
    sub_id: str = "",
    scope: str = "session",
    change_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = _parse_event_body_value(params_obj.get("body"))
    event = NormalizedBrowserEvent(
        event_id=sub_id or f"evt_{uuid.uuid4().hex[:12]}",
        session_id=str(id(session)) if session is not None else "",
        monitor_id=monitor_id,
        label=label,
        source_type=source_type,
        scope=scope,
        url=str(params_obj.get("url") or ""),
        detected_at=str(int(time.time() * 1000)),
        change_summary=change_summary or {},
        payload=payload,
    )
    return event.to_dict()


@dataclass
class ActiveMonitorSet:
    """Tracks all running monitors for a browser_automation node."""

    monitors: List[Any] = field(default_factory=list)  # PollingCapture instances etc.
    configs: List[EventMonitorConfig] = field(default_factory=list)
    agent_id: str = ""
    monitor_set_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------

def parse_monitor_configs(inputs: dict) -> List[EventMonitorConfig]:
    """Extract EventMonitorConfig list from node inputsValues.

    ``inputs`` is the ``config_metadata.get("inputsValues", {})`` dict.
    Returns only enabled configs with a non-empty label.
    """
    raw = (inputs.get("eventMonitors") or {}).get("content", [])
    if not isinstance(raw, list):
        return []

    configs: List[EventMonitorConfig] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        def _pick(*keys: str, default: Any = None) -> Any:
            for key in keys:
                if key in item and item.get(key) is not None:
                    return item.get(key)
            return default

        enabled = item.get("enabled", True)
        if isinstance(enabled, str):
            enabled = enabled.lower() in ("true", "1", "yes", "on")
        if not enabled:
            continue

        label = (item.get("label") or "").strip()
        if not label:
            logger.warning("[EventMonitor] Skipping monitor with empty label")
            continue

        source_type = str(_pick("sourceType", "source_type", default="http_polling") or "http_polling").strip()

        # Parse comma-separated strings into lists
        def _csv(val: Any) -> List[str]:
            if isinstance(val, list):
                return [s.strip() for s in val if isinstance(s, str) and s.strip()]
            if isinstance(val, str) and val.strip():
                return [s.strip() for s in val.split(",") if s.strip()]
            return []

        cfg = EventMonitorConfig(
            id=str(_pick("id", default=f"monitor_{len(configs) + 1}") or f"monitor_{len(configs) + 1}").strip(),
            label=label,
            enabled=True,
            source_type=source_type,
            url_patterns=_csv(_pick("urlPatterns", "url_patterns")),
            methods=_csv(_pick("methods")) or ["GET", "POST"],
            content_filters=_csv(_pick("contentFilters", "content_filters")),
            min_body_length=int(_pick("minBodyLength", "min_body_length", default=10) or 10),
            frame_direction=str(_pick("frameDirection", "frame_direction", default="incoming") or "incoming").strip(),
            sse_event_types=_csv(_pick("sseEventTypes", "sse_event_types")),
            dom_selector=str(_pick("domSelector", "dom_selector", default="") or "").strip(),
            dom_attributes=bool(_pick("domAttributes", "dom_attributes", default=False)),
            dom_child_list=bool(_pick("domChildList", "dom_child_list", default=True)),
            dom_subtree=bool(_pick("domSubtree", "dom_subtree", default=True)),
            dom_check_interval_ms=max(50, int(_pick("domCheckIntervalMs", "dom_check_interval_ms", default=750) or 750)),
            cdp_domain=str(_pick("cdpDomain", "cdp_domain", default="") or "").strip(),
            cdp_event_method=str(_pick("cdpEventMethod", "cdp_event_method", default="") or "").strip(),
            cdp_filter_expr=str(_pick("cdpFilterExpr", "cdp_filter_expr", default="") or "").strip(),
        )
        configs.append(cfg)
        logger.info(
            f"[EventMonitor] Parsed config: label='{cfg.label}', "
            f"source={cfg.source_type}, urls={cfg.url_patterns}"
        )

    return configs


# ---------------------------------------------------------------------------
# ws095: cold-start OVERDUE-recovery window. Messages already sitting overdue in a
# conversation BEFORE the WS reader connected emit NO new frame, so WS never detects them;
# and the DOM monitor goes quiet once WS owns dispatch (is_dispatch_live). So at cold start
# the overdue rows fall in a gap (2026-06-19 "已经出现的超时回复没有立刻回复处理"). For a short
# window after the DOM monitor first runs, keep it scraping AND stamp the overdue (unread)
# rows as _ecan_coldstart_recovery so the ws086 suppress-bypass dispatches them despite WS
# live — safe by the same reasoning (WS provably can't carry a message that predates the
# socket). Gated ECAN_LIVE_CHAT_COLDSTART_RECOVERY_SCRAPE=1 (default OFF); window
# ECAN_LIVE_CHAT_COLDSTART_RECOVERY_WINDOW_S (default 30s).
_COLDSTART_RECOVERY_T0 = [0.0]
_COLDSTART_SCAN_LAST = [0.0]   # ws103: throttle the main-tab recovery scan
_COLDSTART_SCAN_TASKS: set = set()   # ws103: strong refs (ws048: bare create_task GC'd)
_LIVE_CHAT_BOT_TOGGLE_LAST = [0.0]   # throttle the site-own-bot suppression tick
_LIVE_CHAT_BOT_TOGGLE_TASKS: set = set()   # strong refs so the tick task isn't GC'd


def _live_chat_lean_baseline() -> bool:
    """ws125: master kill for the post-ws095 MAIN-TAB recovery/backstop machinery
    (ws103/104/107/108/110 cold-start recovery + missed-msg backstop + residue +
    stuck recovery). ws095 — the fastest, no-stall build — had none of it. Setting
    ECAN_LIVE_CHAT_LEAN_BASELINE=1 makes a later build run the lean ws095 hot path so
    we can A/B-confirm that this machinery is the 1-vs-N stall source. Default OFF."""
    return (_live_chat_env("ECAN_LIVE_CHAT_LEAN_BASELINE") or "") == "1"


def _coldstart_recovery_active() -> bool:
    if _live_chat_lean_baseline():
        return False
    if (_live_chat_env("ECAN_LIVE_CHAT_COLDSTART_RECOVERY_SCRAPE") or "") != "1":
        return False
    if _COLDSTART_RECOVERY_T0[0] <= 0.0:
        _COLDSTART_RECOVERY_T0[0] = time.monotonic()
        return True
    try:
        _win = float((_live_chat_env("ECAN_LIVE_CHAT_COLDSTART_RECOVERY_WINDOW_S") or "30") or 30)
    except (TypeError, ValueError):
        _win = 30.0
    return (time.monotonic() - _COLDSTART_RECOVERY_T0[0]) < _win


# Runner bridge (same dispatch path as BrowserEventService)
# ---------------------------------------------------------------------------

def _dispatch_to_runners(
    label_or_event: Any,
    event_data: Optional[dict] = None,
    target_agent_id: str = "",
) -> int:
    """Broadcast an event to all agent runners.

    Returns the number of runners that received the dispatch.
    Uses the exact same ``sync_task_wait_in_line("browser_event", ...)``
    pattern as ``BrowserEventService._dispatch_to_runners``.
    """
    # Backward-compatible call styles:
    #   _dispatch_to_runners(label, event_data)
    #   _dispatch_to_runners(event_data)
    if event_data is None and isinstance(label_or_event, dict):
        event_data = label_or_event
        label = str(event_data.get("sub_type") or event_data.get("type") or "browser_event")
    else:
        label = str(label_or_event)
        event_data = event_data or {}

    from app_context import AppContext

    runners = []
    try:
        mw = AppContext.get_main_window()
        if mw and hasattr(mw, "agents"):
            for ag in (mw.agents or []):
                r = getattr(ag, "runner", None)
                if r:
                    runners.append(r)
    except Exception:
        pass

    if not runners:
        logger.warning(f"[EventMonitor] No runners available for label='{label}'")
        return 0

    # Route to owner agent only when available; otherwise keep legacy broadcast.
    if target_agent_id:
        target_runners = []
        for runner in runners:
            try:
                runner_agent = getattr(runner, "agent", None)
                rid = (
                    getattr(getattr(runner_agent, "card", None), "id", "")
                    or getattr(runner_agent, "id", "")
                    or ""
                )
                if rid == target_agent_id:
                    target_runners.append(runner)
            except Exception:
                continue
        if target_runners:
            runners = target_runners
        else:
            logger.warning(
                f"[EventMonitor] target_agent_id='{target_agent_id}' not found; "
                f"falling back to broadcast for label='{label}'"
            )

    dispatched = 0
    for runner in runners:
        try:
            runner_agent = getattr(runner, "agent", None)
            runner_agent_id = (
                getattr(getattr(runner_agent, "card", None), "id", "")
                or getattr(runner_agent, "id", "")
                or ""
            )
            logger.info(
                f"[EventMonitor] Dispatching browser_event label='{label}' "
                f"to runner_agent_id='{runner_agent_id}' target_agent_id='{target_agent_id or ''}'"
            )
            runner.sync_task_wait_in_line("browser_event", event_data, source="event_monitor")
            dispatched += 1
        except Exception as e:
            logger.debug(f"[EventMonitor] Runner dispatch failed: {e}")

    logger.info(
        f"[EventMonitor] Dispatched '{label}' to {dispatched}/{len(runners)} runner(s)"
    )
    return dispatched


def _build_bridge_callback(label: str, monitor_set_id: str, target_agent_id: str = "", session: Any = None):
    """Build an on_message callback that bridges PollingCapture matches to runners.

    The callback signature matches PollingCapture's on_message:
        (url: str, method: str, status: int, body: str, rule: str) -> None
    """
    _fire_count = 0
    _bridge_started_ms = int(time.time() * 1000)
    _seen_msg_ids: set[str] = set()
    _seen_session_ids: set[str] = set()

    def _trim_set(s: set[str], keep_last: int = 2000) -> None:
        if len(s) <= keep_last:
            return
        # Drop an arbitrary chunk to cap growth.
        for i, k in enumerate(list(s)):
            s.discard(k)
            if i >= len(s) - keep_last:
                break

    def _dispatch_event(sub_type: str, params_obj: dict, fire_count: int) -> None:
        sub_id = f"monitor:{monitor_set_id}:{sub_type}"
        normalized_event = _build_normalized_browser_event(
            session=session,
            monitor_id=monitor_set_id,
            label=sub_type,
            source_type="http_polling",
            params_obj=params_obj,
            sub_id=sub_id,
        )
        event = {
            "type": "browser_event",
            "sub_type": sub_type,
            "sub_id": sub_id,
            "event_method": "EventMonitor.http_polling",
            "domain": "EventMonitor",
            "fire_count": fire_count,
            "agent_id": target_agent_id or "",
            "event": normalized_event,
            "params": params_obj,
            "timestamp": int(time.time() * 1000),
        }
        _dispatch_to_runners(sub_type, event, target_agent_id=target_agent_id)

    def _bridge(url: str, method: str, status: int, body: str, rule: str):
        nonlocal _fire_count
        _fire_count += 1

        # Truncate body for dispatch (avoid bloating event queue)
        truncated_body = body
        if len(body) > 2000:
            truncated_body = body[:2000] + f"...(+{len(body) - 2000})"

        params_obj = {
            "url": url,
            "method": method,
            "status": status,
            "body": truncated_body,
            "rule": rule,
        }

        # Best-effort parse to suppress duplicate/no-op polling and emit synthetic new_customer.
        parsed = None
        try:
            parsed = json.loads(body) if isinstance(body, str) and body.strip().startswith("{") else None
        except Exception:
            parsed = None

        # For chat polling, only dispatch when has_new is true and at least one new msg_id appears.
        if isinstance(parsed, dict):
            session_id = str(parsed.get("session_id") or "").strip()
            has_new = bool(parsed.get("has_new"))
            messages = parsed.get("messages") if isinstance(parsed.get("messages"), list) else []

            if label == "new_chat_msg":
                if not has_new:
                    logger.debug(f"[EventMonitor] Skip polling event (has_new=false): {url}")
                    return

                new_msg_found = False
                for m in messages:
                    if not isinstance(m, dict):
                        continue
                    if str(m.get("from") or "").lower() != "customer":
                        continue
                    msg_id = str(m.get("msg_id") or "").strip()
                    if not msg_id:
                        continue
                    if msg_id not in _seen_msg_ids:
                        _seen_msg_ids.add(msg_id)
                        new_msg_found = True
                _trim_set(_seen_msg_ids, keep_last=4000)
                if not new_msg_found:
                    logger.debug(f"[EventMonitor] Skip polling event (duplicate msg_ids): {url}")
                    return

            # After warmup, first time a session_id is observed => emit synthetic new_customer.
            warmup_ms = 8000
            now_ms = int(time.time() * 1000)
            if session_id and session_id not in _seen_session_ids:
                _seen_session_ids.add(session_id)
                _trim_set(_seen_session_ids, keep_last=2000)
                if now_ms - _bridge_started_ms > warmup_ms:
                    synth_params = dict(params_obj)
                    synth_params["rule"] = "session_first_seen"
                    synth_params["session_id"] = session_id
                    _dispatch_event("new_customer", synth_params, _fire_count)
                    logger.info(
                        f"[EventMonitor] Synthetic new_customer from polling: "
                        f"session_id={session_id}, url={url}"
                    )

        _dispatch_event(label, params_obj, _fire_count)
        logger.info(
            f"[EventMonitor] HTTP polling match #{_fire_count}: "
            f"label='{label}', rule='{rule}', url={url}, "
            f"dispatched via event bridge"
        )

    return _bridge


# ---------------------------------------------------------------------------
# Monitor lifecycle
# ---------------------------------------------------------------------------

async def start_monitors(
    session,  # BrowserSession
    configs: List[EventMonitorConfig],
    agent_id: str = "",
) -> Optional[ActiveMonitorSet]:
    """Start all configured event monitors on the given BrowserSession.

    Returns an ActiveMonitorSet (or None if no monitors to start).
    Only HTTP polling is supported in Phase 1.

    Idempotent: if monitors already exist on this session, returns existing set.
    """
    if not configs:
        return None

    logger.info(
        f"[EventMonitor] start_monitors called: "
        f"labels={[c.label for c in configs]}, session_id={id(session)}"
    )

    session_key = id(session)
    lock = _session_start_locks.get(session_key)
    if lock is None:
        lock = asyncio.Lock()
        _session_start_locks[session_key] = lock

    async with lock:
        # Check for existing monitors on this session (idempotency)
        existing_set = get_attached_monitor_set(session)
        if existing_set and existing_set.monitors:
            logger.info(
                f"[EventMonitor] Monitors already active on session "
                f"(set_id={existing_set.monitor_set_id}, {len(existing_set.monitors)} monitors). Skipping start."
            )
            return existing_set

        monitor_set = ActiveMonitorSet(configs=configs, agent_id=agent_id or "")

        for cfg in configs:
            logger.info(
                f"[EventMonitor] Processing monitor config: label='{cfg.label}', "
                f"source_type='{cfg.source_type}', enabled={cfg.enabled}"
            )

            if not cfg.enabled:
                logger.debug(f"[EventMonitor] Skipping disabled monitor: label='{cfg.label}'")
                continue
            if cfg.source_type == "http_polling":
                monitor = await _start_http_polling_monitor(
                    session, cfg, monitor_set.monitor_set_id, monitor_set.agent_id
                )
                if monitor:
                    monitor_set.monitors.append(monitor)
            elif cfg.source_type == "websocket":
                monitor = await _start_websocket_monitor(
                    session, cfg, monitor_set.monitor_set_id, monitor_set.agent_id
                )
                if monitor:
                    monitor_set.monitors.append(monitor)
            elif cfg.source_type == "sse":
                monitor = await _start_sse_monitor(
                    session, cfg, monitor_set.monitor_set_id, monitor_set.agent_id
                )
                if monitor:
                    monitor_set.monitors.append(monitor)
            elif cfg.source_type == "dom_mutation":
                monitor = await _start_dom_mutation_monitor(
                    session, cfg, monitor_set.monitor_set_id, monitor_set.agent_id
                )
                if monitor:
                    monitor_set.monitors.append(monitor)
            elif cfg.source_type == "cdp_raw":
                logger.info(
                    f"[EventMonitor] CDP raw monitor '{cfg.label}' - not yet implemented (Phase 6)"
                )
            else:
                logger.warning(
                    f"[EventMonitor] Unknown source_type '{cfg.source_type}' for label '{cfg.label}'"
                )

        started = len(monitor_set.monitors)
        if started > 0:
            # Store on session capability for persistence across loop iterations.
            set_attached_monitor_set(session, monitor_set)
            capability = get_event_monitor_capability(session, create=True)
            if capability:
                capability.configure(configs)
            # Register in global registry for cleanup tracking
            register_monitor_set(monitor_set)
            logger.info(
                f"[EventMonitor] Started {started} monitor(s) "
                f"(set_id={monitor_set.monitor_set_id})"
            )
            return monitor_set
        return None

async def _start_http_polling_monitor(
    session, cfg: EventMonitorConfig, monitor_set_id: str, target_agent_id: str = ""
):
    """Start a PollingCapture instance for an HTTP polling monitor config."""
    try:
        from agent.ec_skills.browser_use_extension.polling_capture import PollingCapture, PollingCaptureConfig

        # Build content filter callables from substring strings
        content_filter_fns: List[Callable[[str], Optional[str]]] = []
        for substr in cfg.content_filters:
            # Each content filter checks if the substring is present in body
            # and returns the substring as the rule name on match
            def _make_filter(s: str):
                def _filter(body: str) -> Optional[str]:
                    return s if s in body else None
                return _filter
            content_filter_fns.append(_make_filter(substr))

        capture_config = PollingCaptureConfig(
            url_patterns=cfg.url_patterns,
            methods=cfg.methods,
            content_filters=content_filter_fns,
            min_body_length=cfg.min_body_length,
        )

        bridge_callback = _build_bridge_callback(cfg.label, monitor_set_id, target_agent_id, session=session)

        capture = PollingCapture(
            session=session,
            config=capture_config,
            on_message=bridge_callback,
        )
        await capture.start()

        logger.info(
            f"[EventMonitor] HTTP polling monitor started: "
            f"label='{cfg.label}', urls={cfg.url_patterns}, "
            f"filters={cfg.content_filters}"
        )
        return capture

    except Exception as e:
        logger.error(f"[EventMonitor] Failed to start HTTP polling monitor '{cfg.label}': {e}")
        return None


async def stop_monitors(monitor_set: Optional[ActiveMonitorSet], session=None) -> None:
    """Stop all monitors in a set (cleanup).
    
    Args:
        monitor_set: The ActiveMonitorSet to stop
        session: Optional BrowserSession to clear the stored monitor reference from
    """
    if not monitor_set:
        return
    for monitor in monitor_set.monitors:
        try:
            if hasattr(monitor, "stop"):
                await monitor.stop()
        except Exception as e:
            logger.debug(f"[EventMonitor] Error stopping monitor: {e}")
    monitor_set.monitors.clear()
    _agent_status.report(monitor="stopped")
    
    # Clear session reference if provided
    if session:
        clear_attached_monitor_set(session)
    
    # Unregister from global registry
    unregister_monitor_set(monitor_set.monitor_set_id)


async def _start_dom_mutation_monitor(
    session, cfg: EventMonitorConfig, monitor_set_id: str, target_agent_id: str = ""
):
    """Start a DOM mutation monitor using CDP's DOM events."""
    try:
        logger.info(f"[EventMonitor] Starting DOM mutation monitor '{cfg.label}'...")
        
        bridge_callback = _build_bridge_callback(cfg.label, monitor_set_id, target_agent_id)
        
        # Get CDP client from session
        cdp_client = session.cdp_client if hasattr(session, 'cdp_client') else None
        if not cdp_client:
            logger.error(f"[EventMonitor] No CDP client available for DOM mutation monitor '{cfg.label}'")
            return None
        
        logger.debug(f"[EventMonitor] CDP client found for DOM monitor '{cfg.label}'")
        
        # Pre-cache the extractor config once at startup (avoids json.loads on every 250ms poll)
        extractor_cfg = None
        try:
            extractor_cfg = _resolve_dom_extractor_config(cfg)
        except Exception as _ec_err:
            logger.warning(f"[EventMonitor] Failed to pre-resolve extractor for '{cfg.label}': {_ec_err}")
        if extractor_cfg is None:
            extractor_cfg = _default_dom_extractor_config(cfg)

        # Pre-build the JS expression once — the config never changes at runtime
        try:
            runtime_expr = _build_dom_runtime_expression(extractor_cfg)
        except Exception as _expr_err:
            logger.warning(f"[EventMonitor] Failed to pre-build JS expr for '{cfg.label}': {_expr_err}")
            runtime_expr = None

        mutation_state = {}
        mutation_state.update({
            "enabled": True,
            "callback": bridge_callback,
            "config": cfg,
            "monitor_set_id": monitor_set_id,
            "agent_id": target_agent_id or "",
            "last_check": time.time(),
            "last_customer_count": 0,
            "last_keys": [],
            "last_status": "starting",
            "last_current_url": "",
            "last_removed_keys": [],
            "last_reordered_keys": [],
            "last_top_changed": False,
            "last_items": [],
            "last_added_items": [],
            "check_interval_ms": max(50, int(getattr(cfg, "dom_check_interval_ms", 750) or 750)),
            "_dom_debug": os.environ.get("ECAN_DOM_DEBUG", "") == "1",
            "_dom_debug_dump_expr": None,  # lazy-built JS for text skeleton
            "page_mismatch_count": 0,
            # ── Perf caches: avoid re-parsing/re-building every 250ms ──────────
            "_cached_extractor_cfg": extractor_cfg,
            "_cached_runtime_expr": runtime_expr,
            "_cached_extractor_cfg_str": str(id(extractor_cfg)),  # invalidation sentinel
        })
        # Resolve target_id from the pre-cached config
        try:
            _resolved_tid = _resolve_monitor_target_id(session, cfg, extractor_cfg)
            # 2026-06-03 dedicated detection tab (mt071: default ON; kill-switch
            # ECAN_LIVE_CHAT_DEDICATED_DETECTION_TAB=0): bind the 新消息 poll to its OWN
            # tab so the per-customer bubble scrapes (which stay on _resolved_tid)
            # can't blind it. See _open_detection_tab.
            _det_tid = ""
            if (
                (_live_chat_env("ECAN_LIVE_CHAT_DEDICATED_DETECTION_TAB") or "1") != "0"
                and _resolved_tid
            ):
                try:
                    _sm = getattr(session, "session_manager", None)
                    _all = _sm.get_all_targets() if _sm else {}
                    _t = (_all or {}).get(_resolved_tid)
                    _murl = str(getattr(_t, "url", "") or "")
                    if _murl:
                        _det_tid = await _open_detection_tab(session, _murl)
                    if _det_tid:
                        _tp_det = _live_chat_bridge().tab_pool
                        _pool_det = _tp_det.get_pool()
                        _pool_det.designate_detection_tab(_det_tid)
                        # bubble scrapes use the original tab; pin it as the monitor/scrape tab
                        _pool_det.designate_monitor(_resolved_tid)
                        # let the new tab load its sidebar before the first poll
                        await asyncio.sleep(2.5)
                        logger.info(
                            f"[EventMonitor] DEDICATED detection tab ...{_det_tid[-6:]} "
                            f"(bubble scrapes stay on ...{_resolved_tid[-6:]})"
                        )
                except Exception as _det_err:
                    logger.warning(
                        f"[EventMonitor] dedicated detection tab setup failed "
                        f"(falling back to shared tab): {_det_err}"
                    )
                    _det_tid = ""
            mutation_state["target_id"] = _det_tid or _resolved_tid
            logger.info(
                f"[EventMonitor] Bound DOM monitor '{cfg.label}' to target_id="
                f"{str(mutation_state.get('target_id') or '')[-4:] or 'None'}"
                f"{' (dedicated)' if _det_tid else ''}"
            )
        except Exception as _bind_err:
            logger.warning(f"[EventMonitor] Failed to bind DOM monitor target for '{cfg.label}': {_bind_err}")
            mutation_state["target_id"] = str(getattr(session, "agent_focus_target_id", "") or "")

        if mutation_state["_dom_debug"]:
            mutation_state["check_interval_ms"] = max(mutation_state["check_interval_ms"], 5000)
            logger.info(
                f"[EventMonitor] DOM_DEBUG enabled for '{cfg.label}' — "
                f"poll interval raised to {mutation_state['check_interval_ms']}ms, "
                f"text skeleton dump on every heartbeat"
            )
            # Log full config so we can verify what the extractor will use
            _cfg_items = [(s.get("selector", "?"), list(s.get("fields", {}).keys())) for s in (extractor_cfg or {}).get("items", [])]
            _cfg_roots = (extractor_cfg or {}).get("roots", [])
            _cfg_identity = (extractor_cfg or {}).get("identity", {})
            _cfg_emit = (extractor_cfg or {}).get("emit_on", "?")
            _cfg_key_field = (extractor_cfg or {}).get("key_field", "?")
            _cdp_filter = str(cfg.cdp_filter_expr or "")[:200]
            logger.info(
                f"[EventMonitor][DOM_DEBUG] CONFIG for '{cfg.label}':\n"
                f"  cdp_filter_expr={_cdp_filter or '(empty)'}\n"
                f"  resolved_from={'_resolve' if _cdp_filter else '_default'}\n"
                f"  roots={_cfg_roots}\n"
                f"  items={_cfg_items}\n"
                f"  key_field={_cfg_key_field}\n"
                f"  identity={_cfg_identity}\n"
                f"  emit_on={_cfg_emit}\n"
                f"  runtime_expr_len={len(runtime_expr or '')}"
            )
        logger.info(f"[EventMonitor] DOM polling state initialized for '{cfg.label}'")
        
        # Create monitor object that can be checked periodically
        class DOMMutationMonitor:
            def __init__(self, state):
                self.state = state
                self._task: Optional[asyncio.Task] = None
            
            async def check_now(self):
                """Check method that can be called periodically."""
                if not self.state["enabled"]:
                    return
                # ws108: run the MAIN-tab missed-message backstop CONTINUOUSLY (not just the
                # startup window), independent of WS-live / PAUSE_DOM_MONITOR. It catches a
                # new conversation's first message that the WS/detection path jams on (the
                # cold-start "小店为你服务" case ws086 can't recover because its DOM path is
                # paused), plus startup residue. The scan is a LIGHT sidebar read (~3ms) so a
                # tight throttle is cheap, and its own per-(name,preview) staleness gate means
                # it never races the WS path. ws145: default 12s->5s — at cold-start the WS
                # socket often doesn't receive a conversation's frames for 60-90s (live 陆地飞鱼
                # talk ...063578: first WS frame 87s late), so this backstop IS the timely
                # detection path; a 12s scan added ~12s of pure blindness before the banner was
                # even seen. Throttle interval ECAN_LIVE_CHAT_BACKSTOP_INTERVAL_S (default 5s).
                try:
                    _now_cs = time.monotonic()
                    try:
                        _bs_iv = float((_live_chat_env("ECAN_LIVE_CHAT_BACKSTOP_INTERVAL_S") or "5") or 5)
                    except (TypeError, ValueError):
                        _bs_iv = 5.0
                    if _live_chat_lean_baseline():
                        _bs_iv = float("inf")   # ws125: lean ws095 path — no main-tab backstop
                    if _now_cs - _COLDSTART_SCAN_LAST[0] >= _bs_iv:
                        _COLDSTART_SCAN_LAST[0] = _now_cs
                        _cs_recover = _live_chat_bridge().front_desk.coldstart_overdue_recovery_scan
                        # ws166: hand the scan the WS/legacy dispatcher so it can run
                        # (and bootstrap the dispatch slot via a legacy browser_event)
                        # even when NO event has fired yet this process — a quiet-
                        # sidebar startup previously left the slot unregistered and
                        # the backstop silently dead (live 2026-07-10 21:38 'sc'
                        # 转人工: WS dropped it, DOM paused, backstop returned 0
                        # every 5s → total cold-start blindness).
                        try:
                            _cs_dispatcher = _ws_dispatch_fn
                        except NameError:
                            _cs_dispatcher = None
                        _cs_task = asyncio.create_task(
                            _cs_recover(legacy_dispatcher=_cs_dispatcher)
                        )
                        _COLDSTART_SCAN_TASKS.add(_cs_task)
                        _cs_task.add_done_callback(_COLDSTART_SCAN_TASKS.discard)
                except Exception:
                    pass
                # Site-own-bot suppressor: PARALLEL to the DOM monitor, on its own
                # throttle (default 5 min). Toggles the site's built-in 智能客服 bot
                # ON->OFF to keep it suppressed (the site auto-enables it after ~10 min
                # dormant; we want it off so it doesn't answer in parallel). Fired as
                # a detached task so it never blocks the monitor tick. The toggle
                # steps are placeholders for now; gated ECAN_LIVE_CHAT_BOT_SUPPRESS=1.
                try:
                    if (_live_chat_env("ECAN_LIVE_CHAT_BOT_SUPPRESS") or "") == "1":
                        try:
                            _bot_iv = float(
                                (_live_chat_env("ECAN_LIVE_CHAT_BOT_SUPPRESS_INTERVAL_S") or "120") or 120)
                        except (TypeError, ValueError):
                            _bot_iv = 120.0
                        if time.monotonic() - _LIVE_CHAT_BOT_TOGGLE_LAST[0] >= _bot_iv:
                            _LIVE_CHAT_BOT_TOGGLE_LAST[0] = time.monotonic()
                            _suppress_bot = _live_chat_bridge().bot_control.suppress_bot_tick
                            _bot_task = asyncio.create_task(_suppress_bot())
                            _LIVE_CHAT_BOT_TOGGLE_TASKS.add(_bot_task)
                            _bot_task.add_done_callback(_LIVE_CHAT_BOT_TOGGLE_TASKS.discard)
                except Exception:
                    pass
                # ws119 toggle-API capture (investigation): one-shot arm of a passive
                # network sniffer that records the XHR fired when 智能客服 is toggled,
                # so the on/off steps can become a single fetch(). Idempotent (starts
                # once, keeps its own CDP client); gated ECAN_LIVE_CHAT_BOT_TOGGLE_CAPTURE=1.
                try:
                    if ((_live_chat_env("ECAN_LIVE_CHAT_BOT_TOGGLE_CAPTURE") or "") == "1"
                            or (_live_chat_env("ECAN_LIVE_CHAT_OPEN_CLAIM_CAPTURE") or "") == "1"):
                        _start_bot_cap = _live_chat_bridge().bot_control.start_bot_toggle_capture
                        _cap_task = asyncio.create_task(_start_bot_cap())
                        _LIVE_CHAT_BOT_TOGGLE_TASKS.add(_cap_task)
                        _cap_task.add_done_callback(_LIVE_CHAT_BOT_TOGGLE_TASKS.discard)
                except Exception:
                    pass
                # ws010: while WS dispatch is LIVE, this DOM scrape is redundant — the
                # observer already detects off the socket — and it's heavy renderer load
                # (the `DOM check timed out 6s` evals that helped wedge the event loop in
                # the 2026-06-06 stall). Pause it while WS owns dispatch. Self-healing: if
                # WS dispatch dies (is_dispatch_live False) the check resumes immediately,
                # so detection is never silently lost. Reversible: ECAN_LIVE_CHAT_WS_PAUSE_DOM_MONITOR=0.
                try:
                    if (_live_chat_env("ECAN_LIVE_CHAT_WS_PAUSE_DOM_MONITOR") or "") != "0":
                        _ws_sess_pause = _live_chat_bridge().ws_session
                        if _ws_sess_pause.is_dispatch_live():
                            # ws095: during the cold-start recovery window, KEEP scraping so
                            # pre-existing overdue rows (which WS can't carry) get recovered
                            # before the DOM monitor goes quiet under WS-owns-dispatch. The
                            # MAIN-tab recovery scan itself now fires from the top of check_now
                            # (ws104), independent of this branch.
                            if not _coldstart_recovery_active():
                                return
                except Exception:
                    pass
                try:
                    await _check_for_customer_changes(self.state, cfg, bridge_callback, session)
                except Exception as e:
                    logger.error(f"[EventMonitor] Error in DOM check: {e}")

            def start_loop(self):
                if self._task and not self._task.done():
                    return

                async def _run_loop():
                    interval_s = max(0.05, float(self.state.get("check_interval_ms", 250)) / 1000.0)
                    # 2026-05-24 mt037B: timeout floor was 8.0s, lowered to
                    # 5.0s.  Default check_interval_ms is 250 → interval_s*20
                    # = 5.0, so this gives an effective 5 s ceiling.
                    # Combined with mt037A (force-recycle CDP on timeout)
                    # this caps the worst-case detection lag at one
                    # 5 s timeout instead of 5×8 s = 40 s clusters seen
                    # in the customer's 2026-05-24 13:31:36-13:32:28 trace.
                    #
                    # mt066 (2026-06-02): the per-poll timeout MUST NOT scale
                    # with the poll interval — they are independent concerns.
                    # The interval_s*20 formula silently assumed the 250 ms
                    # default; when the skill raised the interval to 750 ms it
                    # ballooned the timeout to 15 s, so every poll that got
                    # contended by the heavy bubble-scrape load on the shared
                    # renderer burned 15 s before recycling instead of 5 s —
                    # tripling the detection blindness (customer 1-to-5 trace
                    # 2026-06-02 17:17-17:20: 3× consecutive 15 s timeouts →
                    # 77 s detection lag → 88 s placeholder).  A healthy poll
                    # completes in <1 s; cap the timeout at a fixed 6 s ceiling
                    # regardless of interval so a contended poll recycles fast
                    # and keeps retrying to catch a free renderer window.
                    check_timeout_s = min(max(interval_s * 20, 5.0), 6.0)
                    logger.info(
                        f"[EventMonitor] DOM monitor loop started: "
                        f"label='{self.state['config'].label}', interval_ms={self.state.get('check_interval_ms', 250)}"
                    )
                    _agent_status.report(monitor="running", monitor_label=self.state['config'].label)
                    # ws074: pre-start the placeholder sweeper HERE — at monitor-loop start,
                    # before the first message — instead of lazily on the first reply-delivery
                    # (HOT-PATH-B), which on a cold conversation does not run until ~40s in. The
                    # first turn's placeholder deadline (20s) elapsed before the sweeper existed,
                    # so turn #1 never got a 过渡句 (live 21:30: sweeper started 21:30:53 for a
                    # 21:30:12 message). Idempotent (task-liveness gated); a no-op if running.
                    try:
                        _ws074_start_sweeper = _live_chat_bridge().dom._start_placeholder_sweeper
                        _ws074_start_sweeper(session)
                        logger.info(
                            "[placeholder_timer] ws074: sweeper pre-started at monitor-loop start"
                        )
                    except Exception as _ws074_sw_err:
                        logger.debug(
                            f"[placeholder_timer] ws074 sweeper pre-start skipped: {_ws074_sw_err}"
                        )
                    consecutive_errors = 0
                    try:
                        while self.state.get("enabled", False):
                            try:
                                await asyncio.wait_for(self.check_now(), timeout=check_timeout_s)
                                consecutive_errors = 0
                            except asyncio.TimeoutError:
                                consecutive_errors += 1
                                logger.warning(
                                    f"[EventMonitor] DOM check timed out after {check_timeout_s:.1f}s "
                                    f"(label='{self.state['config'].label}', consecutive={consecutive_errors}); "
                                    "recycling CDP client"
                                )
                                # 2026-05-24 mt037A: a timeout on
                                # ``check_now`` means the underlying CDP
                                # eval (typically via the independent
                                # monitor CDP client established in
                                # ``_get_monitor_cdp``) is stuck on a
                                # client that has either lost its socket
                                # or is queued behind a hung Runtime.evaluate.
                                # Pre-mt037A the next iteration REUSED the
                                # same stuck client, producing the 5×8 s
                                # consecutive-timeout clusters observed in
                                # the customer's 2026-05-24 13:31:36 →
                                # 13:32:28 trace (40 s of "customer message
                                # not detected").  Forcing teardown here
                                # makes the next iteration's
                                # ``_get_monitor_cdp`` call open a FRESH
                                # WebSocket + reattach to the target.  The
                                # customer's message gets seen on the next
                                # poll (~250 ms later) instead of the next
                                # 5 s timeout.
                                try:
                                    await _cleanup_monitor_cdp(self.state)
                                except Exception as _cleanup_err:
                                    logger.debug(
                                        f"[EventMonitor] CDP recycle failed "
                                        f"(non-fatal): {_cleanup_err}"
                                    )
                            except Exception as check_err:
                                consecutive_errors += 1
                                logger.error(
                                    f"[EventMonitor] DOM check error "
                                    f"(label='{self.state['config'].label}', consecutive={consecutive_errors}): {check_err}"
                                )
                            # mt058: adaptive backoff under renderer saturation.
                            # The front-desk monitor shares ONE Chrome renderer
                            # JS thread with the bubble-scrape / focus evals.
                            # When those saturate the thread the check keeps
                            # timing out, and re-polling every interval_s
                            # (250 ms) just piles another Runtime.evaluate onto
                            # the contended renderer — the monitor adds to the
                            # very congestion that's blinding it (2026-06-01
                            # 1-to-6 trace: up to 17 consecutive 5 s timeouts).
                            # Healthy path (consecutive_errors == 0) keeps the
                            # configured fast cadence for low detection latency;
                            # on sustained timeouts back off (cap 2 s) so the
                            # concurrent scrapes can drain instead of competing
                            # with a fresh poll, then snap back to fast polling
                            # the moment a check succeeds.
                            if consecutive_errors > 0:
                                backoff_s = min(
                                    interval_s * (2 ** min(consecutive_errors, 4)),
                                    2.0,
                                )
                            else:
                                backoff_s = interval_s
                            await asyncio.sleep(backoff_s)
                    except asyncio.CancelledError:
                        logger.debug(f"[EventMonitor] DOM monitor loop cancelled: label='{self.state['config'].label}'")
                        raise
                    except Exception as loop_err:
                        logger.error(f"[EventMonitor] DOM monitor loop error: {loop_err}")
                    # Auto-restart if the task exits unexpectedly while still enabled.
                    if self.state.get("enabled", False):
                        logger.warning(
                            f"[EventMonitor] DOM monitor loop exited unexpectedly for "
                            f"label='{self.state['config'].label}'; restarting in 2s"
                        )
                        _agent_status.report(monitor="stopped", monitor_label=self.state['config'].label)
                        await asyncio.sleep(2.0)
                        if self.state.get("enabled", False):
                            self._task = asyncio.create_task(_run_loop())

                self._task = asyncio.create_task(_run_loop())
            
            async def stop(self):
                self.state["enabled"] = False
                if self._task and not self._task.done():
                    self._task.cancel()
                    try:
                        await self._task
                    except asyncio.CancelledError:
                        pass
                # mt059: tear down the WS-frame capture client if one was started.
                _wsc = self.state.pop("_ws_capture_client", None)
                if _wsc is not None:
                    try:
                        await _wsc.stop()
                    except Exception:
                        pass
                # live-chat ws: tear down the shadow WS observer if one was started.
                _wss = self.state.pop("_ws_shadow_client", None)
                if _wss is not None:
                    try:
                        _stop_ws_shadow = _live_chat_bridge().ws_observer.stop_ws_shadow_observer
                        await _stop_ws_shadow(_wss)
                    except Exception:
                        pass
                logger.info(f"[EventMonitor] DOM mutation monitor stopped: label='{self.state['config'].label}'")
        
        monitor = DOMMutationMonitor(mutation_state)
        monitor.start_loop()

        # mt059 Phase 1: optional WS-frame capture on a dedicated isolated CDP
        # client (env ECAN_LIVE_CHAT_WS_CAPTURE=1).  No-op otherwise; never touches
        # the renderer-polling client.
        try:
            _ws_cap = await _start_live_chat_ws_frame_capture(
                session, mutation_state.get("target_id", ""), cfg.label
            )
            if _ws_cap is not None:
                mutation_state["_ws_capture_client"] = _ws_cap
        except Exception as _wscap_err:
            logger.debug(f"[LIVE-CHAT-WS-CAPTURE] launch error (non-fatal): {_wscap_err}")

        # live-chat ws: live SHADOW-mode WS reader (bundle env-gated).  Site-
        # specific hook — decodes customer messages straight off the site socket
        # and logs them alongside the DOM monitor for head-to-head detection latency.
        # Log-only, no dispatch.  All logic lives in the bundle's ws_observer; thin call.
        # WS dispatch closure: builds the SAME browser_event the DOM monitor emits
        # (so PreDispatch/dedup/Q&A downstream are identical — WS only triggers
        # earlier).  Invoked by the observer ONLY when the bundle's WS-dispatch flag
        # is on; the DOM monitor suppresses its own dispatch in that mode
        # (_check_for_customer_changes).
        def _ws_dispatch_fn(_item: dict) -> None:
            try:
                _payload = {"items": [_item], "key_field": "identity_key"}
                _sub_id = f"ws:{monitor_set_id}:{cfg.label}"
                _params = {
                    "url": mutation_state.get("monitor_url") or "",
                    "method": "WS_FRAME", "status": 200,
                    "body": json.dumps(_payload), "rule": cfg.label,
                    "detection": "ws_frontier", "customer_count": 1,
                }
                _norm = _build_normalized_browser_event(
                    session=session, monitor_id=monitor_set_id, label=cfg.label,
                    source_type="ws_frontier", params_obj=_params, sub_id=_sub_id, scope="tab",
                )
                _evt = {
                    "type": "browser_event", "sub_type": cfg.label, "sub_id": _sub_id,
                    "event_method": "WS.frontier", "domain": "WS",
                    "event": _norm, "params": _params,
                }
                def _legacy_dispatch() -> None:
                    _dispatch_to_runners(
                        cfg.label, _evt,
                        target_agent_id=(mutation_state.get("agent_id") or target_agent_id or ""),
                    )
                # ws023: direct-to-QA hot path — route the WS item straight through
                # run()'s coordination per-frame on the observer loop, bypassing the
                # SERIAL front-desk task (the 1-to-6 throughput cliff that lost turns /
                # contaminated state). route_inbound_customer_ws falls back to
                # _legacy_dispatch on any error / registry-miss, so a message is never
                # lost. Default OFF; enable with ECAN_LIVE_CHAT_WS_DIRECT_QA=1.
                # ws048: register the inbound with the watchdog backstop (gated;
                # no-op unless the bundle's WS-watchdog flag is on) so a silently-
                # dropped turn is re-dispatched by us instead of waiting on the
                # site's re-push.
                try:
                    _ws_wd = _live_chat_bridge().ws_inbound_watchdog
                    _ws_wd.note_inbound(_item)
                except Exception:
                    pass
                if (_live_chat_env("ECAN_LIVE_CHAT_WS_DIRECT_QA") or "") == "1":
                    try:
                        import asyncio as _aio
                        _route_direct = _live_chat_bridge().front_desk.route_inbound_customer_ws
                        # ws048: keep a STRONG reference to the task — a bare
                        # create_task() is only weakly held and can be GC'd mid-run
                        # under load, silently losing the turn. Discard on completion;
                        # surface any exception (was invisible before).
                        _wd_task = _aio.get_running_loop().create_task(
                            _route_direct(_item, _legacy_dispatch))
                        _WS_DIRECT_DISPATCH_TASKS.add(_wd_task)

                        def _wd_done(_t, _cust=_item.get("customer_name")):
                            _WS_DIRECT_DISPATCH_TASKS.discard(_t)
                            try:
                                _exc = _t.exception()
                            except Exception:
                                _exc = None
                            if _exc is not None:
                                logger.warning(
                                    f"[WS-DIRECT-QA] dispatch task FAILED cust={_cust!r}: {_exc!r}")
                        _wd_task.add_done_callback(_wd_done)
                        logger.info(
                            f"[WS-DIRECT-QA] routed cust={_item.get('customer_name')!r} "
                            f"direct to QA (bypass front-desk task)")
                    except Exception as _dq_err:
                        logger.debug(f"[WS-DIRECT-QA] schedule failed -> legacy: {_dq_err}")
                        _legacy_dispatch()
                else:
                    _legacy_dispatch()
                    logger.info(f"[LIVE-CHAT-WS-SHADOW] dispatched WS detection: cust={_item.get('customer_name')!r}")
            except Exception as _wdf_err:
                logger.debug(f"[LIVE-CHAT-WS-SHADOW] dispatch build error: {_wdf_err}")

        try:
            _start_ws_shadow = _live_chat_bridge().ws_observer.start_ws_shadow_observer
            _ws_shadow = await _start_ws_shadow(
                session, mutation_state.get("target_id", ""), cfg.label,
                dispatch_fn=_ws_dispatch_fn,
            )
            if _ws_shadow is None:
                logger.warning(
                    "[LIVE-CHAT-WS-SHADOW] observer NOT started (env gate off or "
                    "startup failure — see lines above); detection rides the DOM "
                    "monitor + backstop scans only"
                )
            if _ws_shadow is not None:
                mutation_state["_ws_shadow_client"] = _ws_shadow
                # ws048: start the inbound-watchdog sweeper (gated; no-op unless
                # the bundle's WS-watchdog flag is on). Re-dispatches via the SAME
                # WS path.
                try:
                    import asyncio as _aio_wd
                    _ws_wd = _live_chat_bridge().ws_inbound_watchdog
                    _ws_wd.start(_aio_wd.get_running_loop(), _ws_dispatch_fn)
                except Exception as _wd_start_err:
                    logger.debug(f"[WS-WATCHDOG] start error (non-fatal): {_wd_start_err}")
                # ws051: start the GIL canary (process-wide) + a loop heartbeat on
                # this observer loop (gated ECAN_STALL_DIAG=1). Pins whether the
                # CDP send-stall is GIL starvation vs a blocked loop, and dumps all
                # thread stacks the instant a stall is detected.
                try:
                    import asyncio as _aio_sd
                    from utils import stall_diagnostics as _sd
                    _sd.start_canary()
                    _sd.ensure_loop_heartbeat(_aio_sd.get_running_loop())
                except Exception as _sd_err:
                    logger.debug(f"[STALL-DIAG] start error (non-fatal): {_sd_err}")
        except Exception as _wsshadow_err:
            logger.warning(f"[LIVE-CHAT-WS-SHADOW] launch error (non-fatal): {_wsshadow_err}")

        logger.info(
            f"[EventMonitor] DOM mutation monitor started: "
            f"label='{cfg.label}', filters={cfg.content_filters}, selector={cfg.dom_selector}, "
            f"interval_ms={mutation_state['check_interval_ms']}"
        )
        return monitor
        
    except Exception as e:
        logger.error(f"[EventMonitor] Failed to start DOM mutation monitor '{cfg.label}': {e}")
        import traceback
        logger.debug(f"[EventMonitor] DOM mutation startup error traceback: {traceback.format_exc()}")
        return None


async def check_dom_monitors_periodically():
    """Legacy no-op.

    DOM mutation monitors now own their own per-session asyncio loops. Keeping a
    process-global monitor list causes monitor ownership leakage across skills
    and browser sessions.
    """
    return


async def _check_for_customer_changes(mutation_state, cfg, bridge_callback, session):
    """Check for real customer changes in the control panel DOM."""
    try:
        logger.debug(f"[EventMonitor] _check_for_customer_changes called")

        # ── Skip if poll interval hasn't elapsed yet ──────────────────────────
        current_time = time.time()
        time_since_last = current_time - mutation_state["last_check"]
        interval_s = max(0.05, float(mutation_state.get("check_interval_ms", 250)) / 1000.0)
        if time_since_last < interval_s:
            return
        mutation_state["last_check"] = current_time

        # ── Periodic heartbeat (INFO, every 30 s) ─────────────────────────────
        # Visible in production logs so you can confirm the monitor is alive,
        # what page it's polling, and how many items the extractor currently sees
        # — without spamming a line every 250 ms.
        # Also fires on the very first cycle (last_ts=0) so startup state is visible.
        _hb_interval = 30.0
        _last_hb = float(mutation_state.get("_last_heartbeat_ts") or 0.0)
        _emit_heartbeat = (current_time - _last_hb) >= _hb_interval
        if _emit_heartbeat:
            mutation_state["_last_heartbeat_ts"] = current_time
            # NOTE: the actual log line is emitted further down after we have
            # status/url/items from the DOM query — do NOT log here.

        # ── Use pre-cached extractor config (built once at startup) ───────────
        extractor_cfg = mutation_state.get("_cached_extractor_cfg")
        if extractor_cfg is None:
            # Defensive: rebuild if somehow missing (shouldn't happen in normal flow)
            extractor_cfg = _resolve_dom_extractor_config(cfg)
            mutation_state["_cached_extractor_cfg"] = extractor_cfg

        # ── Use pre-built JS expression (avoids _build_dom_runtime_expression on every cycle) ──
        runtime_expr = mutation_state.get("_cached_runtime_expr")
        if runtime_expr is None:
            runtime_expr = _build_dom_runtime_expression(extractor_cfg)
            mutation_state["_cached_runtime_expr"] = runtime_expr

        target_id = str(mutation_state.get("target_id") or "")
        if not target_id:
            target_id = _resolve_monitor_target_id(session, cfg, extractor_cfg)
            mutation_state["target_id"] = target_id

        # For chat monitors, periodically re-resolve target if the cached one
        # doesn't match (the agent may not have navigated to the chat tab when
        # the monitor started).  Other monitors recover on attach failure below.
        if cfg.label == "chat_message_added" and target_id:
            _retarget_interval = 5.0  # seconds between re-resolve attempts
            _last_retarget = float(mutation_state.get("_last_retarget_check") or 0)
            if time.time() - _last_retarget > _retarget_interval:
                mutation_state["_last_retarget_check"] = time.time()
                target_id = await _retarget_monitor_target(
                    mutation_state,
                    session,
                    cfg,
                    extractor_cfg,
                    target_id,
                    reason="periodic_check",
                )

        if not await _ensure_monitor_cdp_ready(session, mutation_state, cfg.label):
            logger.debug(f"[EventMonitor] CDP still not ready for monitor '{cfg.label}', deferring check")
            return

        # --- Independent CDP connection (does NOT share the agent's CDP client) ---
        mon_client, mon_sid = await _get_monitor_cdp(mutation_state, session, target_id)
        if not mon_client or not mon_sid:
            failed_target = str(mutation_state.get("_mon_cdp_attach_failed_target_id") or "")
            if failed_target and failed_target == target_id:
                new_target = await _retarget_monitor_target(
                    mutation_state,
                    session,
                    cfg,
                    extractor_cfg,
                    target_id,
                    reason="attach_failed",
                    avoid_target_id=target_id,
                )
                if new_target != target_id:
                    return
            logger.debug(f"[EventMonitor] Independent CDP not available for '{cfg.label}', deferring")
            return

        # ── Only fetch URL if actually going to poll (moved after interval check) ──
        current_url = "unknown"
        try:
            url_result = await _monitor_runtime_evaluate(
                session,
                mon_client,
                {"expression": "window.location.href"},
                session_id=mon_sid,
            )
            current_url = (url_result.get("result") or {}).get("value", "unknown")
        except Exception as _url_err:
            logger.debug(f"[EventMonitor] URL fetch via independent CDP failed: {_url_err}")
            # Connection may be stale — force reconnect on next cycle
            await _cleanup_monitor_cdp(mutation_state)

        current_count = mutation_state["last_customer_count"]

        # --- DOM extractor query via independent CDP (use pre-built expression) ---
        try:
            if not runtime_expr:
                runtime_expr = _build_dom_runtime_expression(extractor_cfg)
            result = await _monitor_runtime_evaluate(
                session,
                mon_client,
                {"expression": runtime_expr, "awaitPromise": True},
                session_id=mon_sid,
            )
            dom_content = result.get("result", {}).get("value", "")
            logger.debug(f"[EventMonitor] DOM query result via Runtime: {dom_content[:100]}...")
        except Exception as runtime_err:
            if _emit_heartbeat:
                logger.info(
                    f"[EventMonitor][HB] label='{cfg.label}' CDP_ERROR={runtime_err} "
                    f"target=...{str(mutation_state.get('target_id') or '')[-6:]}"
                )
                _agent_status.report(monitor="running", monitor_label=cfg.label, monitor_hb="cdp_error")
            logger.debug(f"[EventMonitor] Runtime domain query failed: {runtime_err}")
            # Connection may be stale — force reconnect on next cycle
            await _cleanup_monitor_cdp(mutation_state)
            return

        try:
            data = json.loads(dom_content) if isinstance(dom_content, str) and dom_content.strip() else {}
        except Exception:
            logger.debug(f"[EventMonitor] DOM query result was not valid JSON")
            return
        # ws156 diag: surface which sidebar rows the extractor SKIPPED and why (reason + section +
        # name), so a reopened/closed row that never dispatches is explained precisely —
        # non_current_sidebar (closed/recent sidebar section) vs empty_item_key (nameless) vs
        # a non-current row. Read-only; gated ECAN_LIVE_CHAT_MONITOR_SKIP_DIAG (default on).
        try:
            if isinstance(data, dict) and (_live_chat_env("ECAN_LIVE_CHAT_MONITOR_SKIP_DIAG") or "1") != "0":
                _skip_diag = list(data.get("skipped") or [])   # present on status='ok' (count>0)
                if not _skip_diag:
                    # ws157: on status='no_match'/'empty' (count=0 — the reopened row was the ONLY
                    # row and got skipped) the skip info lives under debug.extractionDebug (full
                    # items, already carrying item._section from ws156). Compact it the same way.
                    _ed = data.get("debug") if isinstance(data.get("debug"), dict) else {}
                    for _e in (_ed.get("extractionDebug") or []):
                        if not (isinstance(_e, dict) and _e.get("skipReason")):
                            continue
                        _it = _e.get("item") if isinstance(_e.get("item"), dict) else {}
                        _skip_diag.append({
                            "skip": _e.get("skipReason"),
                            "section": _it.get("_section") or "",
                            "name": _it.get("name") or _it.get("customer_name") or _it.get("nickname") or "",
                            "preview": str(_it.get("preview") or _it.get("text") or _it.get("last_message") or "")[:40],
                            "key": _e.get("itemKey") or "",
                        })
                if _skip_diag:
                    logger.info(
                        f"[EventMonitor] ws156 skip-diag label='{cfg.label}' "
                        f"status={data.get('status')} found={data.get('count')} "
                        f"skipped={_skip_diag[:8]}"
                    )
        except Exception:
            pass
        if not isinstance(data, dict):
            logger.debug(
                f"[EventMonitor] DOM query returned non-object payload "
                f"(type={type(data).__name__}), coercing to empty snapshot"
            )
            data = {}

        status = str(data.get("status") or "")
        current_url = str(data.get("currentUrl") or current_url)
        mutation_state["last_status"] = status or "ok"
        mutation_state["last_current_url"] = current_url

        # In DOM_DEBUG mode, log the raw extractor result (truncated)
        if mutation_state.get("_dom_debug") and _emit_heartbeat:
            _raw_preview = str(dom_content or "")[:3000]
            logger.info(f"[EventMonitor][DOM_DEBUG] raw_result ({len(dom_content or '')} chars): {_raw_preview}")
            # On first heartbeat, also show the runtime expression head (config embedded in JS)
            if not mutation_state.get("_dom_debug_expr_logged"):
                mutation_state["_dom_debug_expr_logged"] = True
                _expr_head = str(runtime_expr or "")[:600]
                logger.info(f"[EventMonitor][DOM_DEBUG] runtime_expr head ({len(runtime_expr or '')} total chars): {_expr_head}")

        if status in ("no_match", "empty"):
            debug_info = data.get("debug") if isinstance(data.get("debug"), dict) else {}
            if debug_info:
                try:
                    _dbg_level = logger.info if mutation_state.get("_dom_debug") else logger.debug
                    _dbg_level(
                        "[EventMonitor] DOM debug "
                        f"status={status} "
                        f"rootCount={debug_info.get('rootCount')} "
                        f"rootSelectors={debug_info.get('rootSelectors')} "
                        f"selectorDebug={debug_info.get('selectorDebug')} "
                        f"pageDebug={debug_info.get('pageDebug')} "
                        f"rootDebug={debug_info.get('rootDebug')} "
                        f"extractionDebug={debug_info.get('extractionDebug')}"
                    )
                except Exception:
                    pass
            # Promote to INFO on heartbeat so no_match is visible in production logs
            if _emit_heartbeat:
                root_count = (debug_info or {}).get("rootCount", "?")
                logger.info(
                    f"[EventMonitor][HB] label='{cfg.label}' status={status} "
                    f"url={current_url[:80]} roots_found={root_count} items=0 "
                    f"target=...{str(mutation_state.get('target_id') or '')[-6:]}"
                )
                _agent_status.report(
                    monitor="running", monitor_label=cfg.label, monitor_hb=str(status),
                    site_tab="found", site_tab_url=current_url[:120],
                    dom_roots=root_count, dom_items=0,
                )
        if status == "page_mismatch":
            mutation_state["page_mismatch_count"] = int(mutation_state.get("page_mismatch_count") or 0) + 1
            mismatch_count = mutation_state["page_mismatch_count"]
            if (
                cfg.label == "chat_message_added"
                and mismatch_count >= 5
                and current_url
                and "127.0.0.1:9877/chat?session=" not in current_url
            ):
                logger.warning(
                    f"[EventMonitor] Retiring stale chat monitor '{cfg.label}' after "
                    f"{mismatch_count} page mismatches; current_url={current_url}"
                )
                mutation_state["enabled"] = False
            # Promote to INFO on heartbeat — page_mismatch was completely silent before
            if _emit_heartbeat:
                _cfg_patterns = (mutation_state.get("_cached_extractor_cfg") or {}).get("page_url_patterns") or []
                logger.info(
                    f"[EventMonitor][HB] label='{cfg.label}' status=page_mismatch "
                    f"url={current_url[:80]} expected_patterns={_cfg_patterns} "
                    f"target=...{str(mutation_state.get('target_id') or '')[-6:]}"
                )
                _agent_status.report(
                    monitor="running", monitor_label=cfg.label, monitor_hb="page_mismatch",
                    site_tab="missing", site_tab_url=current_url[:120], dom_items=0,
                )
            else:
                logger.debug(f"[EventMonitor] DOM page mismatch, skipping: {current_url}")
            return
        mutation_state["page_mismatch_count"] = 0

        # ── DOM Debug: text skeleton dump on heartbeat cycles ─────────────────
        # Set ECAN_DOM_DEBUG=1 to enable. Slows poll to 5s, dumps compact text
        # tree of each root so you can see exactly what selectors would match.
        if mutation_state.get("_dom_debug") and _emit_heartbeat and mon_client and mon_sid:
            try:
                _dump_expr = mutation_state.get("_dom_debug_dump_expr")
                if not _dump_expr:
                    _roots_json = json.dumps(
                        (extractor_cfg or {}).get("roots") or ["body"]
                    )
                    _item_selectors_json = json.dumps(
                        [s.get("selector", "") for s in (extractor_cfg or {}).get("items", [])]
                    )
                    _dump_expr = f"""
(function() {{
  var roots = {_roots_json};
  var itemSelectors = {_item_selectors_json};
  var foundRoots = [];
  for (var i = 0; i < roots.length; i++) {{
    try {{
      var els = document.querySelectorAll(roots[i]);
      for (var j = 0; j < els.length; j++) foundRoots.push({{ el: els[j], selector: roots[i] }});
    }} catch(e) {{}}
  }}
  var lines = [];

  // === SELECTOR VERIFICATION ===
  lines.push('=== SELECTOR VERIFICATION ===');
  lines.push('root_selectors_tried=' + roots.length + ' roots_found=' + foundRoots.length);
  for (var ri = 0; ri < foundRoots.length; ri++) {{
    lines.push('ROOT[' + ri + '] selector="' + foundRoots[ri].selector + '" tag=' + foundRoots[ri].el.tagName + '#' + (foundRoots[ri].el.id || ''));
  }}
  // Test each item selector directly on document (bypassing roots)
  for (var si = 0; si < itemSelectors.length; si++) {{
    var sel = itemSelectors[si];
    try {{
      var docCount = document.querySelectorAll(sel).length;
      lines.push('ITEM_SEL[' + si + '] "' + sel.slice(0, 80) + '" doc_match=' + docCount);
    }} catch(e) {{
      lines.push('ITEM_SEL[' + si + '] "' + sel.slice(0, 80) + '" ERROR=' + e.message);
    }}
    // Also test within each root
    for (var ri2 = 0; ri2 < foundRoots.length; ri2++) {{
      try {{
        var rootCount = foundRoots[ri2].el.querySelectorAll(sel).length;
        lines.push('  within_root[' + ri2 + '] match=' + rootCount);
      }} catch(e2) {{
        lines.push('  within_root[' + ri2 + '] ERROR=' + e2.message);
      }}
    }}
  }}
  // Also try the raw [data-qa-id] selector as an independent sanity check
  try {{
    var qaAll = document.querySelectorAll('[data-qa-id]');
    var qaIds = {{}};
    for (var q = 0; q < qaAll.length; q++) {{
      var qid = qaAll[q].getAttribute('data-qa-id');
      qaIds[qid] = (qaIds[qid] || 0) + 1;
    }}
    lines.push('ALL_QA_IDS=' + JSON.stringify(qaIds));
  }} catch(e) {{}}

  // === TEXT SKELETON ===
  if (foundRoots.length === 0) foundRoots = [{{ el: document.body, selector: 'body' }}];
  function walk(el, depth) {{
    if (depth > 12 || lines.length > 300) return;
    var tag = (el.tagName || '').toLowerCase();
    if (tag === 'script' || tag === 'style' || tag === 'svg' || tag === 'noscript') return;
    var ownText = '';
    for (var c = 0; c < el.childNodes.length; c++) {{
      if (el.childNodes[c].nodeType === 3) ownText += el.childNodes[c].textContent.trim();
    }}
    var attrs = '';
    var qa = el.getAttribute && el.getAttribute('data-qa-id');
    if (qa) attrs += ' qa="' + qa + '"';
    var btm = el.getAttribute && el.getAttribute('data-btm');
    if (btm) attrs += ' btm="' + btm + '"';
    var title = el.getAttribute && el.getAttribute('title');
    if (title) attrs += ' title="' + title.slice(0, 30) + '"';
    var cls = (typeof el.className === 'string') ? el.className : '';
    if (cls) attrs += ' c="' + cls.slice(0, 45) + '"';
    var indent = '';
    for (var d = 0; d < depth; d++) indent += '  ';
    if (ownText || el.children.length > 0 || attrs) {{
      lines.push(indent + '<' + tag + attrs + '>' + (ownText ? ' "' + ownText.slice(0, 60) + '"' : ''));
    }}
    for (var k = 0; k < el.children.length; k++) walk(el.children[k], depth + 1);
  }}
  lines.push('=== TEXT SKELETON ===');
  for (var r = 0; r < foundRoots.length; r++) {{
    lines.push('--- ROOT ' + r + ': ' + foundRoots[r].el.tagName + '#' + (foundRoots[r].el.id || '') + ' ---');
    walk(foundRoots[r].el, 0);
  }}
  return lines.join('\\n');
}})()
"""
                    mutation_state["_dom_debug_dump_expr"] = _dump_expr
                _dump_result = await _monitor_runtime_evaluate(
                    session,
                    mon_client,
                    {"expression": _dump_expr},
                    session_id=mon_sid,
                )
                _skeleton = str((_dump_result.get("result") or {}).get("value") or "")
                if _skeleton:
                    _max_dump = 6000
                    _skeleton = _skeleton[:_max_dump]
                    logger.info(
                        f"[EventMonitor][DOM_DEBUG] label='{cfg.label}' "
                        f"selector_verify + text_skeleton ({len(_skeleton)} chars):\n{_skeleton}"
                    )
            except Exception as _dump_err:
                logger.info(f"[EventMonitor][DOM_DEBUG] dump failed: {_dump_err}")

        items = data.get("items") if isinstance(data.get("items"), list) else []
        key_field = str(data.get("key_field") or "")
        key_fields = data.get("key_fields") if isinstance(data.get("key_fields"), list) else []
        current_keys: List[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if key_fields:
                key = str(item.get("identity_key") or "").strip()
            elif key_field:
                key = str(item.get(key_field) or "").strip()
            else:
                try:
                    key = json.dumps(item, sort_keys=True)
                except Exception:
                    key = ""
            if key:
                current_keys.append(key)

        # ── Heartbeat for ok/empty status + item detail log ─────────────────
        if _emit_heartbeat or not mutation_state.get("keys_initialized"):
            _item_keys_preview = [
                str(item.get("identity_key") or item.get(key_field) or "?")[:40]
                for item in items[:5]
            ]
            _items_detail = ""
            if items:
                # Show brief field summary on every heartbeat (not just first)
                _items_detail = " | sample=" + str([
                    {k: str(v)[:30] for k, v in item.items() if k != "identity_key"}
                    for item in items[:3]
                ])
            if _emit_heartbeat or _items_detail:
                logger.info(
                    f"[EventMonitor][HB] label='{cfg.label}' status={status or 'ok'} "
                    f"url={current_url[:80]} items={len(items)} keys={_item_keys_preview}"
                    + _items_detail
                )
                _agent_status.report(
                    monitor="running", monitor_label=cfg.label, monitor_hb=str(status or "ok"),
                    site_tab="found", site_tab_url=current_url[:120], dom_items=len(items),
                    **({"dom_last_items_at": _agent_status._now_iso()} if items else {}),
                )

        keys_initialized = bool(mutation_state.get("keys_initialized"))
        previous_keys = mutation_state.get("last_keys") or []
        if not isinstance(previous_keys, list):
            previous_keys = []
        previous_top_keys = mutation_state.get("last_top_keys") or []
        if not isinstance(previous_top_keys, list):
            previous_top_keys = []
        previous_key_set = set(str(k) for k in previous_keys if isinstance(k, str) and k)
        current_key_set = set(current_keys)
        # 2026-05-27 mt050H — when a customer is in the forced-reemit
        # set (added by runner.py after direct_stale_dropped clears
        # the dedup ledgers), drop any of their current_keys from the
        # previous_key_set so the diff treats them as freshly added.
        # Without this, J14N9-class bugs leave the customer silently
        # stuck because the sidebar text didn't change and diff sees
        # added=0.
        if _FORCED_REEMIT_CUSTOMER_NAMES and current_keys:
            forced_now = set(_FORCED_REEMIT_CUSTOMER_NAMES)
            matched_names: set = set()
            for k in current_keys:
                # identity_key format is "{customer_name}|{last_message}".
                # Match on the prefix before the first '|'.
                name = k.split("|", 1)[0] if "|" in k else k
                if name in forced_now:
                    previous_key_set.discard(k)
                    matched_names.add(name)
            if matched_names:
                logger.info(
                    f"[EventMonitor] mt050H forced re-emit for "
                    f"customer(s)={sorted(matched_names)!r} (one-shot, "
                    f"triggered by direct_stale_dropped or similar)"
                )
                _FORCED_REEMIT_CUSTOMER_NAMES.difference_update(matched_names)
        added_keys = [k for k in current_keys if k not in previous_key_set]
        if not keys_initialized and cfg.label == "chat_message_added":
            # First snapshot is baseline — the initial message is handled by
            # the A2A assignment, not the monitor.  Absorb silently.
            added_keys = []
        removed_keys = [k for k in previous_keys if isinstance(k, str) and k not in current_key_set]
        reordered_keys = []
        if keys_initialized and previous_keys and current_keys and previous_keys != current_keys:
            reordered_keys = [k for k in current_keys if k in previous_key_set]
        current_top_keys = current_keys[: min(len(current_keys), int(extractor_cfg.get("top_n") or len(current_keys) or 0))]
        top_changed = bool(keys_initialized and previous_top_keys != current_top_keys)
        added_items = []
        if added_keys:
            added_lookup = set(added_keys)
            for item in items:
                if not isinstance(item, dict):
                    continue
                if key_fields:
                    item_key = str(item.get("identity_key") or "").strip()
                else:
                    item_key = str(item.get(key_field) or "").strip() if key_field else json.dumps(item, sort_keys=True)
                if item_key in added_lookup:
                    added_items.append(item)

        # mt052E (2026-05-29) — recall handling.
        #
        # When a customer recalls a message, the DOM removes its bubble
        # but the sidebar reverts to an OLDER message that's still in
        # the chat thread.  The site does NOT fire a fresh "added" event
        # for that older message because it was already present
        # before — so the prior DOM-diff machinery missed it entirely.
        #
        # Concrete pre-mt052E sequence:
        #   1. customer types msg-A → dom_observed for A
        #   2. customer types msg-B → dom_observed for B
        #   3. PreDispatch dispatches B (or scrape sees B and merges
        #      A+B via mt052A); LLM reply uses B's source_msg_id
        #   4. customer recalls msg-B
        #   5. DOM removes B; sidebar shows A as latest
        #   6. EventMonitor's previous keys had ``cust|B``;
        #      current keys have ``cust|A`` → A is NOT in added_keys
        #      because A wasn't "new" in the snapshot sense
        #   7. LLM reply for B tries to send → source-guard fails
        #      (B's msg_id is gone) → stale_drop; mt050N-#1a clears
        #      the dedup ledger
        #   8. No new dom_observed → A sits forever unanswered
        #
        # The recall fingerprint at this point in the diff:
        #
        #   removed_keys = ['cust|B_text']
        #   current_keys = ['cust|A_text', ...]
        #
        # i.e. a customer in ``removed_keys`` is ALSO in
        # ``current_keys`` but with a different message text.  Treat
        # that as a recall: synthesise an ``added_items`` entry for
        # the customer's current row so the dispatch path picks it up
        # again, and proactively clear the per-customer dedup ledger.
        # The downstream PreDispatch path then re-evaluates the
        # customer; mt050N-#1a's reactive clear becomes redundant for
        # this scenario but stays as a safety net.
        if removed_keys and current_keys and (key_field or key_fields):
            # Extract the customer-name portion of each removed key
            # (format is ``"<customer_name>|<last_message>"`` for
            # the site's sidebar monitor; falls back to the whole key
            # when no pipe present).
            removed_custs: dict[str, str] = {}
            for _rk in removed_keys:
                if not isinstance(_rk, str) or "|" not in _rk:
                    continue
                _cust, _rest = _rk.split("|", 1)
                removed_custs[str(_cust).strip()] = _rest
            if removed_custs:
                # Build a quick (customer → current item) lookup from
                # the current snapshot.
                current_by_cust: dict[str, dict] = {}
                for _it in items:
                    if not isinstance(_it, dict):
                        continue
                    _cust = str(
                        _it.get("customer_id")
                        or _it.get("customer_name")
                        or _it.get("name")
                        or ""
                    ).strip()
                    if _cust:
                        current_by_cust[_cust] = _it
                added_lookup_set = set(added_keys) if added_keys else set()
                recall_added = 0
                for _cust, _old_msg in removed_custs.items():
                    _curr = current_by_cust.get(_cust)
                    if not _curr:
                        # Customer fully disappeared (chat closed).
                        # Not a recall — drop.
                        continue
                    # Compute the customer's current key to compare.
                    if key_fields:
                        _curr_key = str(_curr.get("identity_key") or "").strip()
                    else:
                        _curr_key = (
                            str(_curr.get(key_field) or "").strip()
                            if key_field else ""
                        )
                    if not _curr_key:
                        continue
                    _curr_msg = str(
                        _curr.get("last_message")
                        or _curr.get("latest_message")
                        or _curr.get("message")
                        or ""
                    ).strip()
                    # Recall fingerprint: same customer, different
                    # message text, AND the current row wasn't already
                    # added by the regular diff (avoid double-emit).
                    if _curr_key in added_lookup_set:
                        continue
                    if _curr_msg and _curr_msg == str(_old_msg).strip():
                        # Same message stayed — not a recall.
                        continue
                    added_items.append(_curr)
                    added_lookup_set.add(_curr_key)
                    added_keys.append(_curr_key)
                    recall_added += 1
                    # Clear per-customer dedup ledger so PreDispatch
                    # will actually dispatch the now-visible older
                    # message.  Best-effort: failure must not break
                    # the rest of the DOM-diff loop.
                    try:
                        _mt052e_clear = (
                            _live_chat_bridge().actionable_items
                            .clear_dispatched_identity_keys_for_customer
                        )
                        _cleared = _mt052e_clear(_cust)
                        logger.info(
                            f"[EventMonitor] mt052E recall detected for "
                            f"cust={_cust!r}: removed_msg={_old_msg[:40]!r} "
                            f"→ current_msg={_curr_msg[:40]!r}; "
                            f"cleared {_cleared} identity_key(s); "
                            f"synthesised dom_observed for "
                            f"key={_curr_key[:60]!r}"
                        )
                    except Exception as _mt052e_exc:
                        logger.debug(
                            f"[EventMonitor] mt052E ledger clear failed "
                            f"for cust={_cust!r} (non-fatal): {_mt052e_exc}"
                        )
                if recall_added:
                    logger.info(
                        f"[EventMonitor] mt052E synthesised {recall_added} "
                        f"recall-replay dom_observed entry(s) "
                        f"(removed_count={len(removed_keys)})"
                    )

        # For chat-thread monitors, filter out the agent's own replies so the
        # monitor only fires for genuine customer messages (prevents self-
        # triggering when the agent types a response into the same chat).
        #
        # This filter is *opt-in on the extractor config*: it engages only
        # when the `fields` dict declares a `from` field (i.e. the extractor
        # actually reads a sender marker from each item) AND the monitor
        # carries the `chat_message_added` label (thread-pane convention).
        # Chat-LIST monitors — which watch a conversation index rather than
        # a message thread — do not have a per-item sender and therefore
        # must not be subjected to this filter.  Previously the check was
        # keyed only on the label, so any chat-list monitor that inherited
        # the conventional `chat_message_added` label would have every
        # item silently dropped (`item.get("from")` returned `""` and the
        # customer-only list collapsed to `[]`).
        _extractor_fields = extractor_cfg.get("fields") if isinstance(extractor_cfg, dict) else None
        _extractor_declares_from = (
            isinstance(_extractor_fields, dict) and "from" in _extractor_fields
        )
        if (
            cfg.label == "chat_message_added"
            and added_items
            and _extractor_declares_from
        ):
            customer_only = [
                item for item in added_items
                if str(item.get("from") or "").lower() == "customer"
            ]
            skipped = len(added_items) - len(customer_only)
            if skipped:
                logger.info(
                    f"[EventMonitor] Filtered {skipped} non-customer message(s) "
                    f"from chat_message_added (agent self-reply)"
                )
                added_items = customer_only
                added_keys = [
                    str(item.get(key_field) or item.get("identity_key") or "").strip()
                    for item in added_items
                ] if key_field or key_fields else added_keys[:len(added_items)]

        # Generic opt-in content filter: `filters.require_nonempty_fields`.
        #
        # When present in the extractor config, drop any item whose listed
        # fields are all empty/null/zero.  This is the primary knob for
        # chat-LIST monitors that want to fire only on actionable customer
        # activity (e.g. declare `["unread_badge"]` to suppress re-fires
        # triggered by AI smart-cs auto-replies, system welcome messages,
        # or the agent's own reply all of which mutate `last_message` in
        # the row identity but do not represent work for the bot to do).
        #
        # A field is considered "non-empty" when it is truthy AND its
        # stringified form is not `""`, `"0"`, `"false"`, or `"null"`.
        # This matches how platforms render absent badges (`""` or `"0"`).
        _filter_cfg = extractor_cfg.get("filters") if isinstance(extractor_cfg, dict) else None
        _required_nonempty = (
            _filter_cfg.get("require_nonempty_fields")
            if isinstance(_filter_cfg, dict)
            else None
        )
        if added_items and isinstance(_required_nonempty, list) and _required_nonempty:
            def _is_nonempty(value: Any) -> bool:
                if value is None or value is False:
                    return False
                s = str(value).strip().lower()
                return bool(s) and s not in ("0", "false", "null", "none")

            _required = [str(f) for f in _required_nonempty if f]
            _passed = [
                item for item in added_items
                if all(_is_nonempty(item.get(f)) for f in _required)
            ]
            _dropped = len(added_items) - len(_passed)
            if _dropped:
                logger.info(
                    f"[EventMonitor] Filtered {_dropped} item(s) whose "
                    f"required_nonempty_fields={_required} were empty "
                    f"(label='{cfg.label}')"
                )
                added_items = _passed
                added_keys = [
                    str(item.get(key_field) or item.get("identity_key") or "").strip()
                    for item in added_items
                ] if key_field or key_fields else added_keys[:len(added_items)]

        # Site-specific platform/draft filter at the monitor edge.  The
        # downstream dispatch path has the same guard, but filtering here
        # avoids waking the front-desk graph for "[草稿]..." sidebar echoes
        # and other non-customer platform rows.
        if added_items and (
            "im.jinritemai.com" in (current_url or "")
            or any(
                isinstance(item, dict)
                and (
                    "sidebar_scope" in item
                    or "pending_timer" in item
                    or "closed_marker" in item
                )
                for item in added_items
            )
        ):
            try:
                _lc_bridge = _live_chat_bridge()
                _lc_dispatch_state = _lc_bridge.dispatch_state
                _lc_last_agent_reply_by_customer = _lc_dispatch_state.last_agent_reply_by_customer
                _lc_matches_recent_agent_reply = _lc_dispatch_state.matches_recent_agent_reply
                _lc_normalize_reply_text = _lc_dispatch_state.normalize_reply_text
                _lc_reply_echo_matches = _lc_dispatch_state.reply_echo_matches
                _lc_normalize_customer_key = _lc_bridge.dom._normalize_dispatch_identity_key
                _lc_first_system_row_match = _lc_bridge.system_message_filter.first_system_row_match
                _kept_items = []
                _dropped_reasons = []
                for _item in added_items:
                    _reason = _lc_first_system_row_match(_item)
                    if _reason and isinstance(_item, dict):
                        _pending_marker = any(
                            str(_item.get(k) or "").strip()
                            for k in (
                                "pending_timer",
                                "unread_badge",
                                "unread",
                                "needs_action",
                            )
                        )
                        if _pending_marker:
                            logger.info(
                                f"[EventMonitor] live-chat filter keeping pending "
                                f"system-looking row for thread enrichment: "
                                f"reason={_reason!r} customer={_item.get('customer_name')!r}"
                            )
                            _reason = ""
                        elif ((_live_chat_env("ECAN_LIVE_CHAT_STUCK_RECOVERY") or "") == "1"
                              and not _live_chat_lean_baseline()
                              and "store_assignment_notice" in _reason):
                            # ws086 (Part 1): a brand-new conversation's sidebar row shows the
                            # "客服XXX的小店接入" connect banner as its last_message (NOT the
                            # customer's question) with NO unread badge, so it was dropped as a
                            # system row and the real first message — which lives in the thread
                            # (the merchant can see it) — was never scraped (2026-06-18 cold-start:
                            # the new-conv first message never reaches WS either, so both paths
                            # miss it). Recover like ws055 does for platform_long_no_reply: stamp a
                            # synthetic pending marker so PreDispatch thread-scrapes the real
                            # message, and flag it so the WS-live suppress gate lets it through
                            # (WS provably can't carry a new-conv first message).
                            _item["unread_badge"] = "1"
                            _item["_ecan_coldstart_recovery"] = True
                            logger.info(
                                f"[EventMonitor] ws086 cold-start recovery: keeping store-connect "
                                f"banner row for thread-scrape "
                                f"customer={_item.get('customer_name')!r} (WS missed new conv)")
                            _reason = ""
                    if not _reason and isinstance(_item, dict):
                        _cust_key = _lc_normalize_customer_key(
                            str(
                                _item.get("customer_name")
                                or _item.get("customer_id")
                                or _item.get("name")
                                or ""
                            )
                        )
                        _last_msg_norm = _lc_normalize_reply_text(
                            str(_item.get("last_message") or "")
                        )
                        if _cust_key and _last_msg_norm:
                            # 2026-05-23 mt033: consult the multi-slot
                            # recent-reply ledger first.  Single-slot
                            # last_agent_reply_by_customer only remembers
                            # ONE text; under flood load we type a real
                            # reply + 1-2 placeholders into the same
                            # chat in rapid succession.  The sidebar
                            # preview can echo ANY of those, but the
                            # single slot only holds the LATEST → older
                            # echoes (typically the placeholders) bypass
                            # the filter and get dispatched as new
                            # customer messages.  matches_recent_agent_reply
                            # walks the multi-slot ledger with TTL +
                            # prefix tolerance and returns "" when there
                            # is no match.  Fallback to single-slot is
                            # kept for the case where the multi-slot
                            # has been pruned but the single slot still
                            # has the value (e.g. process just started).
                            _last_msg_raw = str(_item.get("last_message") or "")
                            if _lc_matches_recent_agent_reply(_cust_key, _last_msg_raw):
                                _reason = "dom_echo:recent_agent_reply"
                            elif _lc_reply_echo_matches(
                                _last_msg_norm,
                                _lc_last_agent_reply_by_customer.get(_cust_key, ""),
                            ):
                                _reason = "dom_echo:last_agent_reply"
                    if _reason:
                        _dropped_reasons.append(_reason)
                    else:
                        _kept_items.append(_item)
                if _dropped_reasons:
                    logger.info(
                        f"[EventMonitor] live-chat filter dropped "
                        f"{len(_dropped_reasons)} non-customer item(s): "
                        f"{_dropped_reasons[:5]}"
                    )
                    added_items = _kept_items
                    # ws095: during the cold-start recovery window, stamp pre-existing OVERDUE
                    # rows (unread, but emitting no new WS frame) so the ws086 suppress-bypass
                    # dispatches them despite WS live. WS can't carry a message that predates the
                    # socket, so there's no double-fire (same reasoning as ws086).
                    if added_items and _coldstart_recovery_active():
                        _ws095_n = 0
                        for _it in added_items:
                            if (isinstance(_it, dict)
                                    and not _it.get("_ecan_coldstart_recovery")
                                    and any(str(_it.get(_k) or "").strip()
                                            for _k in ("unread_badge", "unread",
                                                       "pending_timer", "needs_action"))):
                                _it["_ecan_coldstart_recovery"] = True
                                _ws095_n += 1
                        if _ws095_n:
                            logger.info(
                                f"[EventMonitor] ws095 cold-start overdue recovery: stamped "
                                f"{_ws095_n} pre-existing unread row(s) for dispatch despite WS live"
                            )
                    added_keys = [
                        str(item.get(key_field) or item.get("identity_key") or "").strip()
                        for item in added_items
                    ] if key_field or key_fields else added_keys[:len(added_items)]
            except Exception as _lc_filter_exc:
                logger.debug(
                    f"[EventMonitor] live-chat system-message filter failed "
                    f"(non-fatal): {_lc_filter_exc}"
                )

        # -----------------------------------------------------------------
        # Tier-1 Instant ACK: send a canned reply via CDP BEFORE routing
        # to LangGraph.  This stops the SLA clock on the platform while
        # the LLM prepares the real answer (Tier 2).
        #
        # The ACK is only sent for chat_message_added with actual customer
        # messages.  It uses the monitor's independent CDP connection so it
        # doesn't block the agent's main browser session.
        #
        # To enable, set `instant_ack` in the monitor config's extractor:
        #   "extractor": { "instant_ack": "您好！我马上为您查看" }
        # When not set, no ACK is sent (backward compatible).
        # -----------------------------------------------------------------
        if cfg.label == "chat_message_added" and added_items:
            _ack_text = str(
                extractor_cfg.get("instant_ack")
                or getattr(cfg, "instant_ack", "")
                or ""
            ).strip()
            if _ack_text:
                try:
                    _target_id = mutation_state.get("target_id") or ""
                    _ack_client, _ack_sid = await _get_monitor_cdp(
                        mutation_state, session, _target_id
                    )
                    if _ack_client and _ack_sid:
                        _ack_js = (
                            "(function(){"
                            "  var inp = document.querySelector('#msg-input, input[type=\"text\"], textarea, [contenteditable=\"true\"]');"
                            "  if(!inp) return 'NO_INPUT';"
                            "  var nativeSet = Object.getOwnPropertyDescriptor("
                            "    window.HTMLInputElement.prototype, 'value')?.set"
                            "    || Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;"
                            "  if(nativeSet) nativeSet.call(inp, " + json.dumps(_ack_text) + ");"
                            "  else inp.value = " + json.dumps(_ack_text) + ";"
                            "  inp.dispatchEvent(new Event('input', {bubbles:true}));"
                            "  inp.dispatchEvent(new Event('change', {bubbles:true}));"
                            "  var btn = document.querySelector('button[onclick*=\"send\"], button[type=\"submit\"], .send-btn');"
                            "  if(btn){ btn.click(); return 'ACK_SENT'; }"
                            "  if(typeof sendMessage==='function'){ sendMessage(); return 'ACK_SENT_FN'; }"
                            "  return 'NO_SEND_BTN';"
                            "})()"
                        )
                        _ack_result = await _monitor_runtime_evaluate(
                            session,
                            _ack_client,
                            {"expression": _ack_js, "returnByValue": True},
                            session_id=_ack_sid,
                        )
                        _ack_val = ""
                        try:
                            _ack_val = _ack_result.get("result", {}).get("value", "")
                        except Exception:
                            pass
                        logger.info(
                            f"[EventMonitor] Tier-1 instant ACK sent: result={_ack_val}, "
                            f"text='{_ack_text[:40]}'"
                        )
                    else:
                        logger.warning("[EventMonitor] Tier-1 ACK skipped: no CDP client available")
                except Exception as _ack_err:
                    logger.warning(f"[EventMonitor] Tier-1 instant ACK failed: {_ack_err}")

        customer_count = int(data.get("count") or len(items) or 0)
        mutation_state["last_customer_count"] = customer_count
        mutation_state["last_keys"] = current_keys
        mutation_state["last_top_keys"] = current_top_keys
        mutation_state["last_removed_keys"] = removed_keys
        mutation_state["last_reordered_keys"] = reordered_keys
        mutation_state["last_top_changed"] = top_changed
        mutation_state["last_items"] = list(items)
        mutation_state["last_added_items"] = list(added_items)
        mutation_state["keys_initialized"] = True

        logger.debug(
            f"[EventMonitor] DOM snapshot status={status or 'ok'} count={customer_count} "
            f"(was {current_count}) added={len(added_items)} removed={len(removed_keys)} "
            f"reordered={len(reordered_keys)} top_changed={top_changed}"
        )

        emit_on = str(extractor_cfg.get("emit_on") or "added").lower()
        should_emit = False
        if emit_on == "changed":
            should_emit = bool(added_items or removed_keys)
        elif emit_on == "reordered":
            should_emit = bool(reordered_keys)
        elif emit_on == "top_changed":
            should_emit = top_changed
        elif emit_on == "added_or_reordered":
            should_emit = bool(added_items or reordered_keys)
        else:
            should_emit = bool(added_items)

        # B1 force-emit (2026-05-14): when the live-chat pre-dispatch enricher
        # deferred a customer because the typing-lock was busy, the sidebar
        # row doesn't change, so the normal `emit_on=added` logic never
        # fires again for that customer and they get stranded with the
        # smart-CS auto-greeting visible. Force an emit whenever the
        # deferred set is non-empty so the front-desk gets another shot
        # once the typing-lock has released. The set self-empties on
        # successful enrichment, and TTL-prunes stale ghosts.
        #
        # 2026-05-19 Fix C: gated behind tunable EVENT_MONITOR_B1_FORCE_EMIT
        # (per-node override → env ECAN_EVENT_MONITOR_B1_FORCE_EMIT →
        # DEFAULT_EVENT_MONITOR_B1_FORCE_EMIT = False).  v0.9.79 behaviour
        # was OFF.  Under flood load this force-emit fires on every poll
        # for up to _DEFERRED_TTL_S (120 s) after a single typing-lock
        # deferral, multiplying the PreDispatch invocation rate vs
        # v0.9.79.  Combined with the imperfect sidebar-only dedup,
        # that drove the duplicate-dispatch cascade observed in the
        # 2026-05-19 customer flood test.  Note: EventMonitor doesn't
        # have direct access to the per-node state here, so we resolve
        # via the env/default path only — node-level override comes
        # from the skill-editor UI through ECAN_* env if the operator
        # has configured per-tab tunables at the process level.
        try:
            _lc_tunables_b1 = _live_chat_bridge().tunables
            _b1_enabled = _lc_tunables_b1.resolve_bool(
                "EVENT_MONITOR_B1_FORCE_EMIT",
                _lc_tunables_b1.DEFAULT_EVENT_MONITOR_B1_FORCE_EMIT,
                None,
            )
        except Exception:
            _b1_enabled = False
        if _b1_enabled and not should_emit:
            try:
                _has_deferred_typing_lock = _live_chat_bridge().pre_dispatch_enrich.has_deferred
                if _has_deferred_typing_lock():
                    should_emit = True
                    logger.debug(
                        f"[EventMonitor] forcing emit because the live-chat "
                        f"pre-dispatch has deferred customers awaiting "
                        f"typing-lock release (label={cfg.label!r})"
                    )
            except Exception:
                pass

        if should_emit:
            payload = {
                "status": status or "ok",
                "count": customer_count,
                "items": items,
                "added": added_items,
                "removed_keys": removed_keys,
                "key_field": key_field,
                "key_fields": key_fields,
                "reordered_keys": reordered_keys,
                "top_keys": current_top_keys,
                "current_url": current_url,
            }
            sub_id = f"dom_{int(time.time() * 1000)}"
            normalized_event = _build_normalized_browser_event(
                session=session,
                monitor_id=str(getattr(cfg, "id", "") or monitor_set_id),
                label=cfg.label,
                source_type="dom_mutation",
                params_obj={
                    "url": current_url,
                    "body": payload,
                },
                sub_id=sub_id,
                scope="tab",
                change_summary={
                    "mode": emit_on,
                    "added_keys": added_keys,
                    "removed_keys": removed_keys,
                    "reordered_keys": reordered_keys,
                    "top_keys": current_top_keys,
                },
            )
            event_data = {
                "type": "browser_event",
                "sub_type": cfg.label,
                "sub_id": sub_id,
                "event_method": "DOM.polling",
                "domain": "DOM",
                "event": normalized_event,
                "params": {
                    "url": current_url,
                    "method": "DOM_MUTATION",
                    "status": 200,
                    "body": json.dumps(payload),
                    "rule": cfg.label,
                    "detection": "config_driven_dom_diff",
                    "customer_count": customer_count,
                    "previous_count": current_count,
                }
            }
            try:
                _lc_ledger = _live_chat_bridge().trace_ledger.log_event
                # 2026-05-20: anchor placeholder timer deadlines to actual
                # customer-message arrival time, not PreDispatch dispatch
                # time.  Without this, a 20s placeholder fires 25-35s
                # after the customer sent (PreDispatch lag is 5-15s),
                # often missing the site's 30s red-flag refresh cycle.
                try:
                    _lc_ph_timer = _live_chat_bridge().placeholder_timer
                except Exception:
                    _lc_ph_timer = None

                for _item in added_items:
                    if not isinstance(_item, dict):
                        continue
                    _cust = (
                        _item.get("customer_id")
                        or _item.get("customer_name")
                        or _item.get("name")
                        or ""
                    )
                    if not _cust:
                        continue
                    _msg_id = str(_item.get("latest_message_msg_id") or _item.get("msg_id") or "")
                    # Always record per-customer arrival, even when msg_id
                    # is unknown — PreDispatch's enrich will learn the
                    # msg_id later and the get_message_first_seen lookup
                    # falls back to per-customer if no precise record.
                    if _lc_ph_timer is not None:
                        try:
                            _lc_ph_timer.mark_message_first_seen(str(_cust), _msg_id)
                        except Exception:
                            pass
                        # mt052C (2026-05-29): arm the placeholder timer
                        # HERE — at dom_observed time — not at PreDispatch
                        # time.  Pre-mt052C the arm site was in
                        # frontdesk_dispatch._build_assignment_payload
                        # (line 1641), AFTER the front-desk task dequeued
                        # the browser_event and finished its scrape.  When
                        # the front-desk queue is busy (117 "dequeue
                        # SKIPPED" stalls in the 2026-05-29 14:06-14:32
                        # run), arm() fires 21-60s after dom_observed,
                        # leaving the customer staring at a silent chat
                        # for 30-60s before the placeholder appears.
                        # Arming here means the sweeper can fire the
                        # placeholder ~10s after the customer's message
                        # lands regardless of front-desk lag.
                        #
                        # ``source_msg_id`` may be empty at this point —
                        # PreDispatch's enrich learns it later and the
                        # arm-time first_seen lookup falls back to the
                        # per-customer slot.  When PreDispatch's own arm()
                        # later runs with the precise msg_id, it creates
                        # a separate registry entry; both will respect
                        # the per-customer ``cap_per_window`` so duplicate
                        # placeholders don't fire.
                        try:
                            _mt052c_timeout = _live_chat_bridge().placeholder_timeout_s()
                            if _mt052c_timeout > 0:
                                _lc_ph_timer.arm(
                                    customer_key=str(_cust),
                                    source_msg_id=_msg_id,
                                    timeout_s=_mt052c_timeout,
                                )
                        except Exception:
                            pass
                    _lc_ledger(
                        "dom_observed",
                        customer=str(_cust),
                        customer_id=str(_item.get("customer_id") or ""),
                        customer_name=str(_item.get("customer_name") or _item.get("name") or ""),
                        session_id=str(_item.get("session_id") or _item.get("identity_key") or ""),
                        source_msg_id=_msg_id,
                        latest_preview=str(
                            _item.get("latest_message")
                            or _item.get("last_message")
                            or _item.get("message")
                            or ""
                        ),
                        monitor_label=str(cfg.label or ""),
                        sub_id=sub_id,
                        emit_on=emit_on,
                        item_key=str(_item.get(key_field) or _item.get("identity_key") or ""),
                        added_count=len(added_items),
                        total_count=customer_count,
                    )
            except Exception:
                pass
            # live-chat ws: suppress the DOM dispatch ONLY while the WS observer is CONFIRMED
            # live and dispatching (ws_session.is_dispatch_live()) — NOT merely when a
            # dispatch flag is set. Gating on the flag alone deadlocked the whole pipeline
            # when the observer failed to start: DOM suppressed itself with no live WS
            # dispatcher behind it, so nothing delivered (2026-06-05 'sc' total stall).
            # When WS is live it carries the full text; the DOM sidebar preview can be
            # truncated (different dedup keys), so double-firing is avoided.
            _ws_dispatch_live = False
            try:
                _ws_sess_sup = _live_chat_bridge().ws_session
                _ws_dispatch_live = _ws_sess_sup.is_dispatch_live()
            except Exception:
                _ws_dispatch_live = False
            # ws086 (Part 2): cold-start recovery bypass. DOM dispatch is normally suppressed
            # GLOBALLY while WS owns dispatch (is_dispatch_live) — DOM/WS can't dedup per-message
            # (truncated sidebar preview vs full WS text), so it's all-or-nothing. But a
            # store-connect banner row (new conversation) is something WS PROVABLY can't carry
            # (its first message never reaches the tapped socket). When EVERY kept added row is
            # such a cold-start-recovery row, dispatch them anyway — there's no double-fire risk
            # because WS never dispatched them. A mixed cycle (cold-start + normal rows together,
            # rare at low concurrency) stays suppressed to avoid double-firing the normal rows.
            # Gated ECAN_LIVE_CHAT_STUCK_RECOVERY=1.
            _coldstart_only = (
                bool(added_items)
                and not _live_chat_lean_baseline()
                and ((_live_chat_env("ECAN_LIVE_CHAT_STUCK_RECOVERY") or "") == "1"
                     or (_live_chat_env("ECAN_LIVE_CHAT_COLDSTART_RECOVERY_SCRAPE") or "") == "1")
                and all(isinstance(_it, dict) and _it.get("_ecan_coldstart_recovery")
                        for _it in added_items)
            )
            if _ws_dispatch_live and not _coldstart_only:
                if any(isinstance(_it, dict) and _it.get("_ecan_coldstart_recovery")
                       for _it in added_items):
                    logger.info(
                        f"[EventMonitor] ws086 cold-start row DEFERRED (mixed with normal rows "
                        f"this cycle while WS live): added={len(added_items)}")
                logger.info(
                    f"[EventMonitor] DOM dispatch SUPPRESSED (WS dispatch live): "
                    f"label='{cfg.label}', added={len(added_items)}, count={customer_count}"
                )
            else:
                if _ws_dispatch_live and _coldstart_only:
                    logger.info(
                        f"[EventMonitor] ws086 cold-start recovery DISPATCH despite WS live "
                        f"(new conv WS can't carry): added={len(added_items)}")
                _dispatch_to_runners(
                    cfg.label,
                    event_data,
                    target_agent_id=(mutation_state.get("agent_id") or ""),
                )
                # ws075 Phase 0: DOM dispatched while WS was NOT live -> DOM caught new
                # message(s) the WS reader missed. The keystone metric for Phase 4 (can DOM
                # leave the hot path?). Gated on coverage; best-effort, lazy import.
                try:
                    if added_items:
                        _ws_cov = _live_chat_bridge().ws_coverage
                        if _ws_cov.enabled():
                            _ws_cov.note("dom_only_seen", len(added_items))
                except Exception:
                    pass
                logger.info(
                    f"[EventMonitor] DOM diff detected event: label='{cfg.label}', "
                    f"added={len(added_items)}, removed={len(removed_keys)}, reordered={len(reordered_keys)}, count={customer_count}"
                )

    except Exception as e:
        logger.error(f"[EventMonitor] Error in customer change detection: {e}")
        import traceback
        logger.debug(f"[EventMonitor] Customer change detection error traceback: {traceback.format_exc()}")


async def _simulate_dom_change_detection(cfg, bridge_callback, session):
    """Simulate DOM change detection by checking page content."""
    try:
        # Get current page content
        current_url = session.current_url if hasattr(session, 'current_url') else "unknown"
        
        # If we're on the control panel, check for customer changes
        if "control" in current_url:
            # Simulate finding new customers by checking page content
            # In a real implementation, this would use DOM queries
            simulated_content = "New Customer Session Detected"
            
            # Check if content matches filters
            matched = False
            for filter_str in cfg.content_filters:
                if filter_str.lower() in simulated_content.lower():
                    matched = True
                    break
            
            if matched:
                # Build event data
                event_data = {
                    "type": "browser_event",
                    "sub_type": cfg.label,
                    "sub_id": f"dom_{int(time.time() * 1000)}",
                    "event_method": "Page.domContentUpdated",
                    "domain": "Page",
                    "params": {
                        "url": current_url,
                        "method": "DOM_MUTATION",
                        "status": 200,
                        "body": simulated_content,
                        "rule": cfg.label,
                        "detection": "simulated"
                    }
                }
                
                # Dispatch to runners
                _dispatch_to_runners(cfg.label, event_data)
                logger.info(f"[EventMonitor] DOM mutation simulated match: label='{cfg.label}', content='{simulated_content}'")
    except Exception as e:
        logger.debug(f"[EventMonitor] Error in DOM change detection simulation: {e}")


async def _process_dom_mutation(params, cfg, bridge_callback, session):
    """Process DOM mutation events and check for matches."""
    try:
        # Check if this mutation affects customer list
        # Look for added nodes that might contain customer info
        if "nodes" in params:
            for node in params["nodes"]:
                if node.get("nodeName") in ["DIV", "LI", "SPAN", "TR", "TD"]:
                    # Look for customer-related content
                    node_content = node.get("nodeValue", "") or node.get("textContent", "")
                    
                    # Check content filters
                    matched = False
                    for filter_str in cfg.content_filters:
                        if filter_str.lower() in node_content.lower():
                            matched = True
                            break
                    
                    if matched:
                        # Build event data similar to HTTP polling
                        event_data = {
                            "type": "browser_event",
                            "sub_type": cfg.label,
                            "sub_id": f"dom_{int(time.time() * 1000)}",
                            "event_method": "DOM.setChildNodes",
                            "domain": "DOM",
                            "params": {
                                "url": session.current_url if hasattr(session, 'current_url') else "unknown",
                                "method": "DOM_MUTATION",
                                "status": 200,
                                "body": node_content,
                                "rule": cfg.label,
                                "node_info": node
                            }
                        }
                        
                        # Dispatch to runners
                        _dispatch_to_runners(cfg.label, event_data)
                        logger.info(f"[EventMonitor] DOM mutation matched: label='{cfg.label}', content='{node_content[:50]}...'")
                        break
    except Exception as e:
        logger.debug(f"[EventMonitor] Error processing DOM mutation: {e}")


async def _start_websocket_monitor(
    session, cfg: EventMonitorConfig, monitor_set_id: str, target_agent_id: str = ""
):
    """Start a WebSocket monitor for real-time message streams."""
    try:
        bridge_callback = _build_bridge_callback(cfg.label, monitor_set_id, target_agent_id)
        
        # Get CDP client for WebSocket interception
        cdp_client = session.cdp_client if hasattr(session, 'cdp_client') else None
        if not cdp_client:
            logger.error(f"[EventMonitor] No CDP client available for WebSocket monitor '{cfg.label}'")
            return None
        
        # Enable Network domain for WebSocket tracking
        await cdp_client.send_raw("Network.enable", {})
        
        # Store WebSocket state
        ws_state = {
            "enabled": True,
            "callback": bridge_callback,
            "config": cfg,
            "monitor_set_id": monitor_set_id,
            "tracked_connections": set()
        }
        
        # Register WebSocket event handlers
        async def _websocket_created_handler(params):
            """Handle WebSocket creation."""
            try:
                ws_url = params.get("url", "")
                ws_id = params.get("requestId", "")
                
                # Check URL patterns
                for pattern in cfg.url_patterns:
                    if pattern in ws_url:
                        ws_state["tracked_connections"].add(ws_id)
                        logger.debug(f"[EventMonitor] Tracking WebSocket: {ws_url}")
                        break
            except Exception as e:
                logger.debug(f"[EventMonitor] Error in WebSocket created handler: {e}")
        
        async def _websocket_frame_handler(params):
            """Handle WebSocket frame messages."""
            try:
                ws_id = params.get("requestId", "")
                if ws_id not in ws_state["tracked_connections"]:
                    return
                
                payload = params.get("payload", {}).get("data", "")
                
                # Check content filters
                matched = False
                for filter_str in cfg.content_filters:
                    if filter_str.lower() in payload.lower():
                        matched = True
                        break
                
                if matched:
                    # Build event data
                    event_data = {
                        "type": "browser_event",
                        "sub_type": cfg.label,
                        "sub_id": f"ws_{int(time.time() * 1000)}",
                        "event_method": "Network.webSocketFrameReceived",
                        "domain": "Network",
                        "params": {
                            "url": params.get("url", "unknown"),
                            "method": "WEBSOCKET_MESSAGE",
                            "status": 200,
                            "body": payload,
                            "rule": cfg.label,
                            "ws_id": ws_id
                        }
                    }
                    
                    # Dispatch to runners
                    _dispatch_to_runners(cfg.label, event_data, target_agent_id=target_agent_id)
                    logger.info(f"[EventMonitor] WebSocket message matched: label='{cfg.label}', payload='{payload[:50]}...'")
                    
            except Exception as e:
                logger.debug(f"[EventMonitor] Error in WebSocket frame handler: {e}")
        
        # Register handlers
        await cdp_client._event_registry.register("Network.webSocketCreated", _websocket_created_handler)
        await cdp_client._event_registry.register("Network.webSocketFrameReceived", _websocket_frame_handler)
        
        # Create monitor object
        class WebSocketMonitor:
            def __init__(self, state):
                self.state = state
            
            async def stop(self):
                self.state["enabled"] = False
                self.state["tracked_connections"].clear()
                logger.info(f"[EventMonitor] WebSocket monitor stopped: label='{self.state['config'].label}'")
        
        monitor = WebSocketMonitor(ws_state)
        
        logger.info(
            f"[EventMonitor] WebSocket monitor started: "
            f"label='{cfg.label}', url_patterns={cfg.url_patterns}, filters={cfg.content_filters}"
        )
        return monitor
        
    except Exception as e:
        logger.error(f"[EventMonitor] Failed to start WebSocket monitor '{cfg.label}': {e}")
        return None


async def _start_sse_monitor(
    session, cfg: EventMonitorConfig, monitor_set_id: str, target_agent_id: str = ""
):
    """Start a Server-Sent Events (SSE) monitor."""
    try:
        bridge_callback = _build_bridge_callback(cfg.label, monitor_set_id, target_agent_id)
        
        # Get CDP client for response interception
        cdp_client = session.cdp_client if hasattr(session, 'cdp_client') else None
        if not cdp_client:
            logger.error(f"[EventMonitor] No CDP client available for SSE monitor '{cfg.label}'")
            return None
        
        # Enable Network domain
        await cdp_client.send_raw("Network.enable", {})
        
        # Store SSE state
        sse_state = {
            "enabled": True,
            "callback": bridge_callback,
            "config": cfg,
            "monitor_set_id": monitor_set_id,
            "tracked_streams": set()
        }
        
        # Register SSE response handler
        async def _sse_response_handler(params):
            """Handle SSE response streams."""
            try:
                response = params.get("response", {})
                url = response.get("url", "")
                headers = response.get("headers", {})
                
                # Check if this is an SSE stream
                content_type = headers.get("content-type", "").lower()
                if "text/event-stream" not in content_type:
                    return
                
                # Check URL patterns
                stream_matched = False
                for pattern in cfg.url_patterns:
                    if pattern in url:
                        stream_matched = True
                        break
                
                if not stream_matched:
                    return
                
                # Track this stream
                request_id = params.get("requestId", "")
                sse_state["tracked_streams"].add(request_id)
                
                # Get response body
                try:
                    body_result = await cdp_client.send_raw("Network.getResponseBody", {"requestId": request_id})
                    body = body_result.get("body", "")
                    
                    # Parse SSE events (each line is an event)
                    for line in body.split('\n'):
                        if line.startswith('data:'):
                            event_data = line[5:].strip()  # Remove 'data:' prefix
                            
                            # Check content filters
                            matched = False
                            for filter_str in cfg.content_filters:
                                if filter_str.lower() in event_data.lower():
                                    matched = True
                                    break
                            
                            if matched and event_data:
                                # Build event data
                                event = {
                                    "type": "browser_event",
                                    "sub_type": cfg.label,
                                    "sub_id": f"sse_{int(time.time() * 1000)}",
                                    "event_method": "Network.responseReceived",
                                    "domain": "Network",
                                    "params": {
                                        "url": url,
                                        "method": "SSE_EVENT",
                                        "status": response.get("status", 200),
                                        "body": event_data,
                                        "rule": cfg.label,
                                        "stream_id": request_id
                                    }
                                }
                                
                                # Dispatch to runners
                                _dispatch_to_runners(cfg.label, event, target_agent_id=target_agent_id)
                                logger.info(f"[EventMonitor] SSE event matched: label='{cfg.label}', data='{event_data[:50]}...'")
                                
                except Exception as e:
                    logger.debug(f"[EventMonitor] Error getting SSE response body: {e}")
                    
            except Exception as e:
                logger.debug(f"[EventMonitor] Error in SSE response handler: {e}")
        
        # Register handler
        await cdp_client._event_registry.register("Network.responseReceived", _sse_response_handler)
        
        # Create monitor object
        class SSEMonitor:
            def __init__(self, state):
                self.state = state
            
            async def stop(self):
                self.state["enabled"] = False
                self.state["tracked_streams"].clear()
                logger.info(f"[EventMonitor] SSE monitor stopped: label='{self.state['config'].label}'")
        
        monitor = SSEMonitor(sse_state)
        
        logger.info(
            f"[EventMonitor] SSE monitor started: "
            f"label='{cfg.label}', url_patterns={cfg.url_patterns}, filters={cfg.content_filters}"
        )
        return monitor
        
    except Exception as e:
        logger.error(f"[EventMonitor] Failed to start SSE monitor '{cfg.label}': {e}")
        return None

