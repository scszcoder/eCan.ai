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

# CN builds name the app logger "eCan.cn" (propagate=False) — a bare
# getLogger("eCan") record never reaches its handlers, silencing this
# module's entire log output in packaged CN apps (v0.9.95u incident:
# the WS reader looked dead because none of its lines could land).
from utils.logger_helper import logger_helper as logger

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


# ws184: strong refs for parked-card dispatch tasks (ws048 lesson: an
# unreferenced create_task is GC'd under load and the dispatch silently dies).
_PARK_TASKS: set = set()


def _park_card_dispatch(item: dict, talk_id: str, dispatch_fn) -> None:
    """ws184: hold a nameless card:<talk> dispatch until the talk resolves to a
    real customer name (click-bind / cmid-join / uid bridge), then dispatch the
    WS-carried content under that identity. Falls back to the synthetic
    dispatch (pre-ws184 behavior) at ECAN_FEIGE_CARD_PARK_S (default 12s)."""
    talk = str(talk_id or "")
    try:
        park_s = float(os.environ.get("ECAN_FEIGE_CARD_PARK_S", "12") or 12)
    except (TypeError, ValueError):
        park_s = 12.0
    park_s = max(1.0, park_s)

    async def _wait_and_dispatch():
        deadline = time.time() + park_s
        resolved = ""
        while time.time() < deadline:
            await asyncio.sleep(1.0)
            # ws192: talk-match-guarded resolve — rejects a name that provably
            # belongs to a DIFFERENT talk (stale/cross _talk_to_name or uid
            # bridge), which would mis-deliver and split the dedup key.
            _nm = str(ws_session.name_for_talk_verified(talk) or "")
            if _nm:
                resolved = _nm
                break
        if resolved:
            waited = park_s - max(0.0, deadline - time.time())
            for _k in ("customer_name", "name", "session_id", "customer_id"):
                item[_k] = resolved
            item["identity_key"] = f"{resolved}|{item.get('last_message', '')}"
            ws_session.restick_identity(talk, resolved)   # ws070 map: card: -> real
            logger.info(
                f"[FEIGE-WS-CARD] ws184 park resolved conv {talk} -> "
                f"cust={resolved!r} after {waited:.1f}s — dispatching the WS card "
                f"content under the real identity (no DOM paint wait)")
            try:
                from . import placeholder_timer as _ph184
                _ph184.mark_message_first_seen(resolved, item.get("msg_id"))
            except Exception:
                pass
        else:
            logger.info(
                f"[FEIGE-WS-CARD] ws184 park expired ({park_s:.0f}s) for conv "
                f"{talk} — dispatching synthetic {item.get('customer_name')!r} "
                f"(pre-ws184 path)")
        # ws186: the direct-QA lane never passes through the ws101 DOM enrich, so
        # attach the captured card-JSON detail (价格/券/发货) here — by dispatch
        # time (1-12s after the card frame) the page has long since fetched
        # getTemplateCardDataV2 and the store has it.
        try:
            from . import product_detail_store as _pds186
            _et = _pds186.enrich_card_text(str(item.get("last_message") or ""))
            if _et != item.get("last_message"):
                item["last_message"] = _et
                item["latest_message"] = _et
                logger.info(
                    f"[FEIGE-WS-CARD] ws186 card-JSON detail attached for conv {talk} "
                    f"text={_et[:100]!r}")
        except Exception:
            pass
        # ws191: the park path is, by design, the DELAYED second path (it waited
        # up to park_s for a name bind). If the same talk was already dispatched
        # under another identity (the named WS frame / DOM front-desk), sending
        # here duplicates the answer to one conversation (live 2026-09-05:
        # talk 7682040317431907610 answered 券后28元 AND 券后38元). Drop instead.
        try:
            from . import dispatch_state as _ds191
            _mid = str(item.get("msg_id") or "")
            if _ds191.talk_recently_dispatched(talk, _mid):
                logger.info(
                    f"[FEIGE-WS-CARD] ws191 conv {talk} already dispatched under "
                    f"another identity — dropping duplicate parked dispatch "
                    f"(cust={item.get('customer_name')!r})")
                return
            _ds191.note_talk_dispatched(talk, _mid)
        except Exception:
            pass
        try:
            dispatch_fn(item)
        except Exception as _de:
            logger.debug(f"[FEIGE-WS-SHADOW] ws184 parked dispatch_fn error: {_de}")

    try:
        t = asyncio.get_running_loop().create_task(_wait_and_dispatch())
        _PARK_TASKS.add(t)
        t.add_done_callback(_PARK_TASKS.discard)
        logger.info(
            f"[FEIGE-WS-CARD] ws184 parked nameless card conv {talk} for up to "
            f"{park_s:.0f}s awaiting a name bind (click-bind/cmid-join/uid-bridge)")
    except Exception as _pe:
        logger.warning(f"[FEIGE-WS-CARD] ws184 park failed ({_pe}) — dispatching synthetic now")
        try:
            dispatch_fn(item)
        except Exception as _de:
            logger.debug(f"[FEIGE-WS-SHADOW] dispatch_fn error: {_de}")


_ENV = "ECAN_FEIGE_WS_READER"


_DISPATCH_ENV = "ECAN_FEIGE_WS_DISPATCH"

_FEIGE_ENV_DUMPED = [False]


def _dump_feige_env() -> None:
    """ws079: log the full Feige env config ONCE per process so every run log is
    self-describing. Cross-revision performance comparison MUST account for env flags —
    e.g. WS_SEND_RAW flips the reply send lane (raw vs in-page WS eval), which was the
    actual differentiator between the OK ws072 (raw OFF, 41 in-page deliveries) and the
    stuck ws077/078 (raw ON, ~0 delivered). Never compare two runs without this line."""
    if _FEIGE_ENV_DUMPED[0]:
        return
    _FEIGE_ENV_DUMPED[0] = True
    try:
        _envs = {k: v for k, v in os.environ.items()
                 if k.startswith("ECAN_FEIGE") or k in ("ECAN_A2A_LOCAL_FASTPATH",)}
        logger.info("[FEIGE-ENV] " + " ".join(f"{k}={v}" for k, v in sorted(_envs.items())))
    except Exception:
        pass


# ws190: ONE observer per Chrome endpoint (+label), shared by every browser
# session that attaches to that Chrome. Live 2026-09-04 22:36: five per-customer
# chat-scoped sessions (node scope, card:…, 陆地飞鱼, 肽斯特, …) each started its
# own observer against the same Chrome; every incoming frame was dispatched 5×
# to 5 Q&A agents → 4 duplicate replies to one product card. Old observers were
# never torn down either (reconnect-follow re-attached them to every new tab).
# Registry key -> {"client", "dispatchers": [fn, ...], "handles": set, "alive"}.
# The FIRST dispatcher is the active one; stopping a subscriber hands over to
# the next; the real CDP client is stopped only with the last subscriber.
_SHARED_OBSERVERS: dict = {}


class _SharedObserverHandle:
    """What start_ws_shadow_observer returns: a per-subscriber token. Passing it
    to stop_ws_shadow_observer unsubscribes; the shared client stops only when
    no subscriber remains."""
    __slots__ = ("key", "dispatch_fn")

    def __init__(self, key: str, dispatch_fn):
        self.key = key
        self.dispatch_fn = dispatch_fn

    @property
    def client(self):
        _e = _SHARED_OBSERVERS.get(self.key)
        return _e.get("client") if _e else None


def _shared_dispatch(entry: dict, item: dict) -> None:
    """Route a detected message to the active (first) subscriber only."""
    fns = entry.get("dispatchers") or []
    if fns:
        fns[0](item)


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
    if not ws_session.ws_enabled("reader"):
        return None

    cdp_url = getattr(session, "cdp_url", None)
    if not cdp_url:
        bp = getattr(session, "browser_profile", None)
        cdp_url = getattr(bp, "cdp_url", None) if bp else None
    if not cdp_url:
        logger.warning("[FEIGE-WS-SHADOW] no cdp_url on session — observer not started")
        return None

    # ws190: reuse the observer already watching this Chrome (see registry note).
    _key = f"{cdp_url}|{label}"
    _existing = _SHARED_OBSERVERS.get(_key)
    if _existing is not None and _existing.get("alive"):
        _probe_ok = False
        try:
            await asyncio.wait_for(_existing["client"].send_raw("Target.getTargets", {}), timeout=3.0)
            _probe_ok = True
        except Exception as _probe_err:
            logger.warning(f"[FEIGE-WS-SHADOW] ws190 shared observer probe failed ({_probe_err}) — starting fresh")
        if _probe_ok:
            if dispatch_fn is not None:
                _existing["dispatchers"].append(dispatch_fn)
            _h = _SharedObserverHandle(_key, dispatch_fn)
            _existing["handles"].add(_h)
            logger.info(
                f"[FEIGE-WS-SHADOW] ws190 reusing shared observer for {cdp_url} label={label!r} "
                f"(subscribers={len(_existing['handles'])}) — NOT starting a second observer "
                f"(one per session dispatched every frame N×, live 2026-09-04)")
            return _h
        _SHARED_OBSERVERS.pop(_key, None)

    _entry: dict = {"client": None, "dispatchers": ([dispatch_fn] if dispatch_fn is not None else []),
                    "handles": set(), "alive": True}

    def _dispatch_current(item: dict) -> None:
        _shared_dispatch(_entry, item)

    ws_session.set_dispatch_live(False)   # reset; only flips True once we confirm-start below
    _dump_feige_env()   # ws079: record the env config so the run log is self-describing
    do_dispatch = dispatch_fn is not None and ws_session.ws_enabled("dispatch")
    do_read_ack = ws_session.ws_enabled("read_ack")

    try:
        from cdp_use import CDPClient

        client = CDPClient(url=cdp_url)
        await client.start()
        _entry["client"] = client

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
        # ws080: the ctor/onclose reconnect tap (window.WebSocket wrap + 20s drain) is now on
        # its OWN flag ECAN_FEIGE_WS_CTOR_DIAG — it produced 0 useful events and added load, so
        # it must NOT ride RAW_DIAG anymore (we want RAW_DIAG=1 for the per-send confirm detail
        # WITHOUT the dead ctor wrap). Default OFF.
        _diag_on = os.environ.get("ECAN_FEIGE_WS_CTOR_DIAG", "") == "1"
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
        # ws094: product-card dedup is TIME-WINDOWED, not permanent. A card retransmits
        # ~5-15x in <1s (ws027) — the window collapses that burst — but a customer who
        # RE-SHARES the same product card minutes later is starting a NEW turn (they want
        # to ask about it again) and MUST dispatch. The old permanent `seen` membership
        # dropped every re-share forever (2026-06-19: sc re-shared 女童套装 at 10:47:02 ->
        # 10+ frames, 0 dispatch -> no reply, and the follow-up '就这款' had no card context
        # -> LLM asked the customer to re-send the link). key -> last-seen ts.
        _card_seen_ts: dict = {}
        # ws113: re-push storm guard. A stuck read-ack cursor makes Feige re-push
        # the SAME card every ~1-2 min (> the 15s dedup window), so each re-push
        # reads as a fresh re-share and re-dispatches — live 2026-06-24 a single
        # nameless card re-emitted 389x / drove 107 LLM calls over 34 min = a
        # dispatch storm that stalled the app. Cap re-dispatches per card.
        _card_last_ts: dict = {}     # key -> ts of the most recent re-emission
        _card_run_count: dict = {}   # key -> consecutive re-emissions with no quiet gap
        _card_storm_logged: dict = {}    # key -> True once the storm warning is logged
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
        _fast_rearm_ts = [0.0]               # ws136: throttle the immediate re-arm on reconnect

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
                    try:
                        from utils import agent_status as _agent_status
                        _agent_status.report(detection="ws")
                    except Exception:
                        pass
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
                        # ws094: time-windowed (NOT permanent) — suppress only the <1s
                        # retransmit burst; allow a deliberate re-share after the window.
                        # Kill switch: ECAN_FEIGE_CARD_RESHARE=0 restores permanent dedup.
                        key = f"card|{m.conversation_id}|{m.text}"
                        if os.environ.get("ECAN_FEIGE_CARD_RESHARE", "1") != "0":
                            try:
                                _win = float(os.environ.get("ECAN_FEIGE_CARD_DEDUP_WINDOW_S", "15") or 15)
                            except (TypeError, ValueError):
                                _win = 15.0
                            _now = time.time()
                            _prev = _card_seen_ts.get(key)
                            if _prev is not None and (_now - _prev) < _win:
                                return  # retransmit burst -> suppress
                            # ws113: re-push storm guard. The 15s window can't tell a
                            # server re-push (stuck cursor) from a human re-share. A storm
                            # re-pushes CONTINUOUSLY (every ~1-2 min, no quiet gap); a human
                            # re-shares occasionally, after a quiet stretch. Count consecutive
                            # re-emissions and reset the run only after RESET_S of quiet —
                            # allow the first STORM_MAX, suppress the rest until it goes
                            # quiet. Caps the 389x storm at STORM_MAX while a deliberate
                            # re-share (after quiet) still passes. Disable: =0.
                            if os.environ.get("ECAN_FEIGE_CARD_STORM_GUARD", "1") != "0":
                                try:
                                    _storm_reset = float(
                                        os.environ.get("ECAN_FEIGE_CARD_STORM_RESET_S", "300") or 300)
                                    _storm_max = int(
                                        os.environ.get("ECAN_FEIGE_CARD_STORM_MAX", "3") or 3)
                                except (TypeError, ValueError):
                                    _storm_reset, _storm_max = 300.0, 3
                                _last_ts = _card_last_ts.get(key)
                                _run = (0 if (_last_ts is None or (_now - _last_ts) >= _storm_reset)
                                        else _card_run_count.get(key, 0))
                                _run += 1
                                _card_last_ts[key] = _now      # update even when suppressing
                                _card_run_count[key] = _run     # so the run only resets on quiet
                                if _run > _storm_max:
                                    if not _card_storm_logged.get(key):
                                        _card_storm_logged[key] = True
                                        logger.warning(
                                            f"[FEIGE-WS-CARD] ws113 re-push storm guard: card "
                                            f"key={key[:90]!r} re-emitted {_run}x with no quiet gap "
                                            f"(>{_storm_max}) — suppressing re-dispatch (server "
                                            f"re-push loop, likely a stuck read-ack cursor). "
                                            f"Re-share resumes after {_storm_reset:.0f}s quiet.")
                                    return
                                _card_storm_logged.pop(key, None)  # fresh storm can re-log
                            _card_seen_ts[key] = _now
                            # fall through to dispatch (re-share is a new turn)
                        else:
                            if key in seen:
                                return
                            seen.add(key)
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
                        # ws132: a cold-start reopened session's 人工 often arrives NAMELESS
                        # (m.customer_name empty), so the [微笑] handover ack was armed under ''
                        # and never delivered — 陆地飞鱼 waited 2.4min until re-asking. Resolve the
                        # real customer via the talk_id bridge (ws025/ws127) so the ack targets the
                        # actual conversation immediately. Falls back to the raw name/id if the
                        # bridge can't resolve yet.
                        _hm_cust = (m.customer_name
                                    or ws_session.name_for_talk(m.conversation_id)
                                    or m.customer_name)
                        human_mode.note_customer_turn(_hm_cust, m.ts_ms)
                        if human_mode.is_human_trigger(m.text):
                            try:
                                from . import placeholder_timer as _hm_ph
                                # ws163: a fresh WS frame is an authoritative NEW 人工
                                # request (new msg_id) — clear the 600s re-dedup stamp
                                # first, or a startup ws159 arm for a STALE in-thread
                                # 转人工 (whose ack the placeholder guard may even have
                                # swallowed) blocks this genuine one (live 2026-07-10
                                # 'sc' 19:41:56 → no ack, platform warned 19:43). The
                                # re-dedup still protects the scrape path, which CAN
                                # re-match the same old row every tick.
                                _hm_ph.clear_handover_ack(_hm_cust)
                                _hm_ph.note_handover_ack_needed(_hm_cust)
                                logger.info(
                                    f"[HumanMode] 人工 trigger from cust={_hm_cust!r} "
                                    f"(raw={m.customer_name!r}) text={m.text[:40]!r} — ack "
                                    f"{human_mode.human_ack_text()!r}, skipping LLM dispatch")
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
                        # ws184: park a nameless card:<talk> dispatch briefly instead of
                        # sending a decoy turn to QA. On the 2026-07-26 17:51 1-vs-3 burst
                        # the two synthetic card dispatches produced undeliverable replies
                        # (ws173 card_row_ambiguous) whose ws141 resolve-waits held the
                        # global typing lock 8s EACH, deferring every named enrich a full
                        # backstop tick — while the named rows resolved 5-9s later anyway.
                        # Park until name_for_talk resolves (fed by the ws184 click-bind,
                        # the ws177 cmid-join, or the uid bridge), then dispatch the SAME
                        # WS-carried content under the real identity — no DOM paint
                        # dependency. Timeout -> dispatch synthetic (status quo).
                        if (
                            m.msg_type == "template_card"
                            and str(m.customer_name or "").startswith("card:")
                            and os.environ.get("ECAN_FEIGE_CARD_PARK", "1") != "0"
                        ):
                            _park_card_dispatch(item, m.conversation_id, _dispatch_current)
                        else:
                            # ws191: this is a primary (non-parked) dispatch — record
                            # the talk claim so a later parked card for the SAME
                            # conversation is dropped instead of answering twice.
                            # ws186: also enrich the card text with the authoritative
                            # getTemplateCardDataV2 detail so this fast path cites the
                            # same 券后价/原价 the parked lane would (fixes the
                            # 券后28元 vs 券后38元 split on the same product).
                            try:
                                from . import dispatch_state as _ds191b
                                _talk_n = str(getattr(m, "conversation_id", "") or "")
                                if _talk_n:
                                    _ds191b.note_talk_dispatched(
                                        _talk_n, str(item.get("msg_id") or ""))
                            except Exception:
                                pass
                            try:
                                from . import product_detail_store as _pds191
                                _etn = _pds191.enrich_card_text(str(item.get("last_message") or ""))
                                if _etn and _etn != item.get("last_message"):
                                    item["last_message"] = _etn
                                    item["latest_message"] = _etn
                            except Exception:
                                pass
                            try:
                                _dispatch_current(item)
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
                    # ws077: the page socket cycled — tell the raw sender to re-sync + reconnect
                    # fresh on its next send (a reconnect staleness-kills our token faster than the
                    # age timer; the ws075 churn drove 6 connect-FAILED + UNCONFIRMED raw sends).
                    if os.environ.get("ECAN_FEIGE_WS_SEND_RAW", "") == "1":
                        try:
                            from . import ws_raw_sender as _wsr_rc
                            _wsr_rc.note_page_reconnect()
                        except Exception:
                            pass
                    # ws136: IMMEDIATELY re-enable Network + re-arm the socket hook on the
                    # reconnected socket, instead of waiting up to ~40s for the frames-stale
                    # health loop. The cold-start reconnect churn (手动关闭 OR natural reopen) was
                    # dropping the frame that carries the customer's security_sender_id during that
                    # gap -> uid=N -> first-contact AND ws130 route-seed both fail -> NO-ROUTE ->
                    # DOM -> Session-not-found -> the cold-start card was undeliverable for minutes
                    # (natural cold-start 21:05: wscap died 21:05:24, card arrived 21:05:36 uid=N).
                    # Throttled 1/2s, best-effort. Reversible: ECAN_FEIGE_WS_RECONNECT_FAST_REARM=0.
                    if os.environ.get("ECAN_FEIGE_WS_RECONNECT_FAST_REARM", "1") != "0":
                        _now_rr = time.time()
                        if _now_rr - _fast_rearm_ts[0] >= 2.0:
                            _fast_rearm_ts[0] = _now_rr

                            async def _fast_rearm():
                                _ok = 0
                                for _s in list(sids):
                                    try:
                                        await client.send_raw("Network.enable", {}, session_id=_s)
                                        await client.send_raw(
                                            "Runtime.evaluate",
                                            {"expression": ws_session.arm_socket_hook_js(),
                                             "returnByValue": True},
                                            session_id=_s)
                                        _ok += 1
                                    except Exception:
                                        pass
                                logger.info(
                                    f"[FEIGE-WS-RECONNECT] ws136 fast re-arm on {_ok}/{len(sids)} "
                                    f"tab(s) after socket create (close cold-start uid-drop gap)")

                            try:
                                asyncio.get_running_loop().create_task(_fast_rearm())
                            except Exception:
                                pass
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

        # ws097 (Phase 1 of B): capture Feige's own conversation-list / history / product-detail
        # HTTP responses off the Network layer (the SPA already fetches them). This is the off-DOM
        # source for BOTH (a) recovering OVERDUE conversations the DOM sidebar doesn't render
        # (getCSReceptionInServiceAssist = conv list) and (b) reading product-card details
        # (券后价/券立减/物流) the shared-card WS frame doesn't carry (it only has goods_id+title).
        # Phase 1 just LOGS a bounded raw sample per endpoint so we learn the response shape; Phase 2
        # parses + dispatches. Gated ECAN_FEIGE_WS_PRIME_API=1 (the flag that was set-but-unimplemented).
        _PRIME_EPS = ("getCSReceptionInServiceAssist", "get_by_conversation", "get_user_message",
                      "getShopReception", "queryConv", "/goods", "/product", "promotion", "coupon", "/sku",
                      # ws099: conv-list candidates for OVERDUE recovery. The captured
                      # getCSReceptionInServiceAssist returned item_list:[] every time —
                      # it is NOT the conversation list. Widen the named net AND (below)
                      # content-detect the list endpoint-agnostically so one run pins it.
                      "getConversationList", "conversation/list", "conv_list", "conversationList",
                      "getReception", "reception/list", "unread", "message/list", "/conversation")
        _prime_seen_ep: dict = {}
        _url_seen: set = set()        # ws099 firehose: distinct IM-host paths, bounded
        _convlist_logged = [0]        # ws099 content-detect cap (list, for closure mutation)
        _json_fetches = [0]           # ws102 HARD cap on content-detect body fetches

        # ws099: endpoint-NAME-agnostic conv-list detector. Returns
        # (count, elem_keys, first_elem) when the JSON body carries an array of
        # conversation-shaped objects, else None — so we find the overdue conv
        # list whatever URL serves it, instead of guessing endpoint names.
        # ws102: tightened to STRONG conv-specific keys only. The ws100 run
        # false-positived on /backstage/open/id_to_openid (keys user_id/open_id);
        # require a key that genuinely marks a conversation row (last_message /
        # unread_count / conversation_id) so id-mapping endpoints don't match.
        _CONV_KEYS = ("conversation_id", "conv_id", "conversationId", "conversation_short_id",
                      "last_message", "last_msg", "unread_count", "unreadCount", "talk_id")

        def _looks_like_convlist(txt):
            try:
                obj = json.loads(txt)
            except Exception:
                return None
            best = [None]

            def _scan(node, depth=0):
                if depth > 6:
                    return
                if isinstance(node, list):
                    if node and isinstance(node[0], dict):
                        k = set(node[0].keys())
                        if any(ck in k for ck in _CONV_KEYS):
                            if best[0] is None or len(node) > best[0][0]:
                                best[0] = (len(node), sorted(k)[:14], node[0])
                    for it in node[:50]:
                        _scan(it, depth + 1)
                elif isinstance(node, dict):
                    for v in node.values():
                        _scan(v, depth + 1)

            _scan(obj)
            return best[0]

        def _on_response_received(params, session_id=None):
            try:
                if os.environ.get("ECAN_FEIGE_WS_PRIME_API", "") != "1":
                    return
                resp = (params.get("response", {}) or {})
                url = str(resp.get("url") or "")
                if "jinritemai" not in url:
                    return
                mime = str(resp.get("mimeType") or "")
                # ws099 firehose: log every distinct IM-host path ONCE (no body
                # fetch) so the full endpoint surface is visible to pick the list.
                try:
                    from urllib.parse import urlsplit
                    _path = urlsplit(url).path
                except Exception:
                    _path = url[:90]
                if _path not in _url_seen and len(_url_seen) < 120:
                    _url_seen.add(_path)
                    logger.info(
                        f"[FEIGE-API-URL] path={_path} mime={mime} status={resp.get('status')}")
                _ep = next((ep for ep in _PRIME_EPS if ep in url), "")
                _ep_room = bool(_ep) and _prime_seen_ep.get(_ep, 0) < 3
                # ws102: HARD-bound the content-detect body fetches. The ws099
                # version kept fetching every JSON IM response for the whole run
                # because _convlist_logged only advanced on a (rare) hit — extra
                # CDP getResponseBody load on the observer that degraded the card
                # scrape (ws100 was worse than ws099). Cap the ATTEMPTS, not just
                # the hits.
                _json_room = (
                    ("json" in mime)
                    and (_json_fetches[0] < 12)
                    and (_convlist_logged[0] < 4)
                )
                if not _ep_room and not _json_room:
                    return
                rid = params.get("requestId")
                if not rid:
                    return
                if _ep_room:
                    _prime_seen_ep[_ep] = _prime_seen_ep.get(_ep, 0) + 1
                if _json_room:
                    _json_fetches[0] += 1

                async def _fetch():
                    try:
                        b = await client.send_raw(
                            "Network.getResponseBody", {"requestId": rid}, session_id=session_id)
                        txt = str(b.get("body") or "")
                        if b.get("base64Encoded"):
                            try:
                                txt = base64.b64decode(txt).decode("utf-8", "replace")
                            except Exception:
                                pass
                        if _ep_room:
                            logger.info(
                                f"[FEIGE-PRIME-API] ep={_ep} url={url[:90]} len={len(txt)} "
                                f"sample={txt[:700]!r}")
                        if _json_room:
                            cand = _looks_like_convlist(txt)
                            if cand:
                                _convlist_logged[0] += 1
                                logger.info(
                                    f"[FEIGE-CONVLIST-CANDIDATE] path={_path} count={cand[0]} "
                                    f"elem_keys={cand[1]} sample={str(cand[2])[:500]!r}")
                    except Exception as _e:
                        logger.debug(f"[FEIGE-PRIME-API] getResponseBody failed ep={_ep}: {_e}")
                try:
                    asyncio.get_running_loop().create_task(_fetch())
                except Exception:
                    pass
            except Exception:
                pass

        client._event_registry.register("Network.webSocketFrameReceived", _on_frame)
        client._event_registry.register("Network.webSocketFrameSent", _on_sent)
        client._event_registry.register("Network.webSocketCreated", _on_socket_created)
        client._event_registry.register("Network.responseReceived", _on_response_received)
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
        # ws068: warm-start the off-renderer raw socket now that the observer CDP handle is parked
        # (so ws_raw_sender can capture the token), so the FIRST reply doesn't eat the cold-start
        # connect latency/timeout (the "no response from start"). No-op unless ECAN_FEIGE_WS_SEND_RAW=1.
        if os.environ.get("ECAN_FEIGE_WS_SEND_RAW", "") == "1":
            try:
                from . import ws_raw_sender as _wsr_warm
                asyncio.get_running_loop().create_task(_wsr_warm.warmup())
                _wsr_warm.start_keepalive()   # ws081: keep the raw socket warm + token fresh proactively
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
        _SHARED_OBSERVERS[_key] = _entry
        _h0 = _SharedObserverHandle(_key, dispatch_fn)
        _entry["handles"].add(_h0)
        return _h0
    except Exception as exc:
        logger.warning(f"[FEIGE-WS-SHADOW] failed to start: {exc}")
        return None


async def stop_ws_shadow_observer(client: Any) -> None:
    """Best-effort teardown. ws190: a _SharedObserverHandle only unsubscribes —
    the shared CDP client (and the WS-owns-dispatch flag) is torn down with the
    LAST subscriber, so one session's monitor stop can't blind the others."""
    if isinstance(client, _SharedObserverHandle):
        _entry = _SHARED_OBSERVERS.get(client.key)
        if _entry is None:
            return
        _entry["handles"].discard(client)
        if client.dispatch_fn is not None:
            try:
                _entry["dispatchers"].remove(client.dispatch_fn)
            except ValueError:
                pass
        if _entry["handles"]:
            logger.info(
                f"[FEIGE-WS-SHADOW] ws190 shared observer kept alive "
                f"(subscribers={len(_entry['handles'])}); dispatcher handed to the next session")
            return
        _SHARED_OBSERVERS.pop(client.key, None)
        _entry["alive"] = False
        client = _entry.get("client")
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
