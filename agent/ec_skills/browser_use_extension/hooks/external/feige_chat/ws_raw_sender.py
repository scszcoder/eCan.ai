"""OFF-RENDERER raw Frontier send — SPIKE (ws011), Feige-specific.

The eval-inject send path (ws_session.inject_js → CDP Runtime.evaluate →
``window.__ecan_feige_ws.send``) runs JS on Chrome's single-threaded renderer.
Under 1-vs-N that renderer saturates, every eval takes ~12s, and the send path
wedges (the 2026-06-06 stall). This module bypasses the renderer entirely: eCan
opens its OWN websockets connection to the SAME authed Frontier URL the page uses
and writes the protobuf frame straight to the socket.

OPEN QUESTION this spike exists to answer: does the Frontier server accept a
NON-browser connection that merely replays the page's authed URL (token /
access_key / pigeon_sign), or does it require an app-level login/registration
frame after the WS handshake (anti-bot)? Reading via the page socket is proven;
opening our own is NOT. So this is OFF by default (``ECAN_FEIGE_WS_SEND_RAW=1``),
best-effort, and ALWAYS falls back to eval-inject on any failure — flipping the
flag and watching one live send is the whole validation.

Bootstrap needs exactly ONE cheap renderer eval (cached): read the live socket's
url + Origin + User-Agent + Cookie off the page via the observer's parked CDP
client. After that, every send is fully off-renderer. Delivery confirmation is
unchanged: the server echoes a merchant send to ALL the merchant's sessions
(multi-device sync), so the observer reading the PAGE socket still sees the echo
and the caller's existing wait_confirmed() fires.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import time

from . import ws_session

logger = logging.getLogger("eCan")

_conn = None                 # live websockets client connection (cached)
_conn_params: dict | None = None   # {url, origin, ua, cookie} captured off the page
_conn_params_ts: float = 0.0       # ws066: when _conn_params was captured (token-age diagnostic)
_lock = asyncio.Lock()       # serialize connect/reconnect (not the sends)

# ws082: the loop that OWNS the raw socket. An asyncio websocket is bound to the loop that
# created it; it cannot be used from another loop. ws080 proved the failure mode: read-acks
# (sent from the observer loop, which warms the socket) hit the wire 5/5, but every REPLY —
# dispatched on the SEPARATE direct-delivery worker loop (ledger cross_loop=true) — silently
# fell to in-page eval because raw_send on the worker loop could not use the observer-loop
# socket. We pin the owner loop where the socket is warmed (warmup/keepalive, both on the
# observer loop) and marshal any foreign-loop send onto it via run_coroutine_threadsafe.
_owner_loop = [None]


class _RWLock:
    """ws069: many concurrent readers (in-flight sends), one exclusive writer (the
    age-refresh teardown). A writer waits for in-flight sends to DRAIN and blocks new
    sends from starting while it tears the socket down — closing the ws068 race where a
    240s refresh could close the socket out from under a send already past its freshness
    check. Writer-preference; writers are rare (every _TOKEN_MAX_AGE_S) so reader
    starvation is not a concern."""

    def __init__(self) -> None:
        self._readers = 0
        self._no_readers = asyncio.Event()
        self._no_readers.set()          # set iff reader count == 0
        self._writer = asyncio.Lock()   # held by a writer; gates NEW readers out

    @contextlib.asynccontextmanager
    async def read(self):
        async with self._writer:        # blocked while a writer holds/awaits exclusivity
            self._readers += 1
            self._no_readers.clear()
        try:
            yield
        finally:
            self._readers -= 1
            if self._readers <= 0:
                self._readers = 0
                self._no_readers.set()

    @contextlib.asynccontextmanager
    async def write(self):
        async with self._writer:        # new readers block at read()'s `async with`
            await self._no_readers.wait()   # drain sends already in flight
            yield


_rw = _RWLock()              # ws069: send=read (concurrent), refresh teardown=write (exclusive)

# ws068/ws077: the captured token expires server-side by AGE, NOT by URL change. ws068 set the
# default to 240s, but the ws075 1-vs-3 run decayed FASTER: every CONFIRMED raw send was at
# token_age <=94s while every age-based UNCONFIRMED was >=124s (page_token_changed=False), so
# staleness set in ~100-120s under page-socket churn. ws077 lowers the default to 90s so the
# refresh fires before the failure zone. Tunable; 0 disables the age-based refresh.
_TOKEN_MAX_AGE_S: float = float(os.environ.get("ECAN_FEIGE_WS_RAW_TOKEN_MAX_AGE", "90") or 90)

# ws077: set when the observer sees the page's Frontier socket cycle (Network.webSocketCreated).
# A page reconnect staleness-kills our captured token/connection faster than any age timer can
# catch (the ws075 churn: socket_created=13, ~1/60s -> 6 connect-FAILED + UNCONFIRMED sends), so
# the next send must re-sync + reconnect FRESH regardless of age. Mutated from the observer's
# sync CDP handler; consumed in _ensure_fresh_conn (async, under the RW write-lock).
_page_reconnected = [False]


def note_page_reconnect() -> None:
    """ws077: the observer saw the page Frontier socket (re)created — force the next raw send to
    re-capture a fresh token + reconnect. Cheap, idempotent; no-op if raw send is unused."""
    _page_reconnected[0] = True


def _pin_owner_loop() -> None:
    """ws082: record the loop the raw socket is warmed on (the observer loop). Reply sends on a
    different loop are then marshalled onto it in raw_send. Idempotent; updates if re-warmed."""
    try:
        _owner_loop[0] = asyncio.get_running_loop()
    except Exception:
        pass

_CAPTURE_JS = (
    "(function(){try{var s=window.__ecan_feige_ws;"
    "return JSON.stringify({url:(s&&s.url)||'',origin:location.origin,"
    "ua:navigator.userAgent,cookie:document.cookie});}catch(e){return '';}})()"
)


async def _capture_conn_params() -> dict | None:
    """One-time: read the authed socket URL + Origin/UA/Cookie off the page via the
    observer's parked CDP client. Cached. Returns None if no socket/observer yet."""
    global _conn_params
    if _conn_params is not None:
        return _conn_params
    client, sids = ws_session.get_observer_cdp()
    if client is None or not sids:
        logger.warning("[FEIGE-WS-RAW] no observer CDP handle parked — cannot capture URL")
        return None
    for sid in sids:
        try:
            res = await client.send_raw(
                "Runtime.evaluate",
                {"expression": _CAPTURE_JS, "returnByValue": True},
                session_id=sid,
            )
            val = ((res or {}).get("result") or {}).get("value") or ""
            if not val:
                continue
            data = json.loads(val)
            if data.get("url"):
                global _conn_params_ts
                _conn_params = data
                _conn_params_ts = time.time()   # ws066: stamp capture time for staleness diag
                logger.info(
                    f"[FEIGE-WS-RAW] captured conn params: "
                    f"url={data['url'][:60]}... origin={data.get('origin')!r} "
                    f"ua_len={len(data.get('ua') or '')} cookie_len={len(data.get('cookie') or '')}"
                )
                return _conn_params
        except Exception as e:
            logger.debug(f"[FEIGE-WS-RAW] capture eval failed on sid={sid}: {e}")
    logger.warning("[FEIGE-WS-RAW] socket url not yet available on any tab (no heartbeat seen?)")
    return None


async def _read_live_page_url() -> str:
    """ws066 diag: read the page's CURRENT __ecan_feige_ws.url via the observer CDP WITHOUT
    caching it. Lets us detect whether the page socket rotated its token since we captured ours."""
    client, sids = ws_session.get_observer_cdp()
    if client is None or not sids:
        return ""
    for sid in sids:
        try:
            res = await client.send_raw(
                "Runtime.evaluate",
                {"expression": _CAPTURE_JS, "returnByValue": True},
                session_id=sid,
            )
            val = ((res or {}).get("result") or {}).get("value") or ""
            if val:
                data = json.loads(val)
                if data.get("url"):
                    return str(data["url"])
        except Exception:
            continue
    return ""


def token_age() -> float:
    """ws080: CHEAP current token age in seconds (no CDP eval) — -1.0 if nothing captured.
    Lets the per-send confirm log run ALWAYS when raw is on, without the heavy live-url read."""
    return round(time.time() - _conn_params_ts, 1) if _conn_params_ts else -1.0


async def diag_token_status() -> dict:
    """ws066: per-frame staleness diagnostic for the forced-reconnect raw-send experiment.
    Compares the raw socket's CACHED token to the page's CURRENT socket url, so we can correlate
    an UNCONFIRMED raw send with the page having rotated its token (= stale-token hypothesis).
    Gated by the caller on ECAN_FEIGE_WS_RAW_DIAG=1 (one extra read on the idle observer tab)."""
    age = round(time.time() - _conn_params_ts, 1) if _conn_params_ts else -1.0
    cached = (_conn_params or {}).get("url", "") if _conn_params else ""
    live = await _read_live_page_url()
    return {
        "age_s": age,
        "page_token_changed": (cached != live) if (cached and live) else None,
        "cached_tail": cached[-40:],
        "live_tail": live[-40:],
    }


async def _get_conn():
    """Cached live connection; (re)connect if absent or closed. Returns None on failure."""
    global _conn
    if _conn is not None and getattr(_conn, "close_code", None) is None:
        # close_code is None while open in websockets' asyncio client.
        try:
            if _conn.state.name == "OPEN":
                return _conn
        except Exception:
            pass
    async with _lock:
        # re-check after acquiring (another send may have reconnected)
        if _conn is not None:
            try:
                if _conn.state.name == "OPEN":
                    return _conn
            except Exception:
                pass
        params = await _capture_conn_params()
        if not params:
            return None
        try:
            import websockets
        except Exception as e:
            logger.warning(f"[FEIGE-WS-RAW] websockets lib unavailable: {e}")
            return None
        headers = {}
        if params.get("ua"):
            headers["User-Agent"] = params["ua"]
        if params.get("cookie"):
            headers["Cookie"] = params["cookie"]
        # ws068: retry the connect — the cold-start raw socket is flaky (ws067 had 4
        # OWN-socket-connect-FAILED TimeoutErrors, which drop the FIRST replies to DOM = the
        # "no response from start"). A couple of quick retries warms it past the cold-start.
        for _attempt in range(3):
            try:
                # websockets 15.x asyncio client: additional_headers (not extra_headers).
                _conn = await asyncio.wait_for(
                    websockets.connect(
                        params["url"],
                        additional_headers=headers,
                        origin=params.get("origin") or None,
                        open_timeout=8.0,
                        ping_interval=20.0,
                    ),
                    timeout=10.0,
                )
                logger.info(
                    f"[FEIGE-WS-RAW] OWN Frontier socket CONNECTED (off-renderer send live)"
                    f"{f' on attempt {_attempt + 1}' if _attempt else ''}")
                return _conn
            except Exception as e:
                logger.warning(
                    f"[FEIGE-WS-RAW] OWN socket connect attempt {_attempt + 1}/3 FAILED "
                    f"({type(e).__name__}: {e})")
                _conn = None
                if _attempt < 2:
                    await asyncio.sleep(0.6)
        logger.warning("[FEIGE-WS-RAW] OWN socket connect FAILED after retries — eval-inject fallback")
        return None


async def warmup() -> None:
    """ws068: pre-connect the off-renderer raw socket at observer startup so the FIRST reply
    doesn't eat the cold-start connect latency/timeout (the 'no response from start'). No-op /
    safe if the page socket isn't capturable yet — falls back to lazy connect on first send."""
    _pin_owner_loop()   # ws082: warmup runs on the observer loop → that's the socket's owner
    try:
        if await _get_conn() is not None:
            logger.info("[FEIGE-WS-RAW] warm-start: raw socket pre-connected")
    except Exception as e:
        logger.debug(f"[FEIGE-WS-RAW] warm-start skipped: {e}")


# ws081: PROACTIVE keepalive. The ws080 finding was that raw carried read-acks fine but REPLIES
# hit the lazy re-sync teardown window (socket torn down on re-sync, rebuilt only on the NEXT
# send) and fell to in-page eval — and a token drifted to 133s because the age-refresh only ran
# on a send. This background loop keeps the socket WARM + the token FRESH ahead of time so a reply
# send always finds a live, fresh socket.
_KEEPALIVE_INTERVAL_S: float = float(os.environ.get("ECAN_FEIGE_WS_RAW_KEEPALIVE_S", "20") or 20)
# refresh well BEFORE the hard max age so the token never drifts into the failure zone
_PROACTIVE_AGE_S: float = max(20.0, _TOKEN_MAX_AGE_S * 0.6)
_keepalive_task = [None]


def _conn_open() -> bool:
    try:
        return _conn is not None and _conn.state.name == "OPEN"
    except Exception:
        return False


async def _keepalive_loop() -> None:
    """ws081: keep eCan's raw Frontier socket continuously warm + token fresh in the background.
    Proactively re-syncs at _PROACTIVE_AGE_S (well under the hard max) and reconnects IMMEDIATELY
    under the RW write-lock, instead of the lazy tear-down-on-next-send. Best-effort; no-op until
    the observer CDP handle is parked. Kill-switch: ECAN_FEIGE_WS_RAW_KEEPALIVE=0."""
    global _conn, _conn_params, _conn_params_ts
    while True:
        try:
            await asyncio.sleep(_KEEPALIVE_INTERVAL_S)
            client, sids = ws_session.get_observer_cdp()
            if client is None or not sids:
                continue   # observer not up yet — warmup / lazy connect will handle first use
            _age = token_age()
            reason = ""
            if _page_reconnected[0]:
                reason = "page socket reconnected (webSocketCreated)"
            elif _age >= 0 and _age >= _PROACTIVE_AGE_S:
                reason = f"token proactively aging ({round(_age, 1)}s >= {round(_PROACTIVE_AGE_S, 1)}s)"
            if reason:
                async with _rw.write():           # drain in-flight sends, block new ones
                    _page_reconnected[0] = False
                    _conn_params = None
                    _conn_params_ts = 0.0
                    if _conn is not None:
                        try:
                            await _conn.close()
                        except Exception:
                            pass
                        _conn = None
                    await _get_conn()             # reconnect WARM now, before any reply needs it
                logger.info(
                    f"[FEIGE-WS-RAW] keepalive refreshed socket ({reason}) -> "
                    f"{'warm' if _conn_open() else 'reconnect-pending'} token_age={token_age()}s")
            elif not _conn_open():
                async with _rw.write():
                    await _get_conn()             # socket dropped between sends — warm it back up
                logger.info(
                    f"[FEIGE-WS-RAW] keepalive reconnected dropped socket -> "
                    f"{'warm' if _conn_open() else 'failed'}")
        except asyncio.CancelledError:
            raise
        except Exception as _ke:
            logger.debug(f"[FEIGE-WS-RAW] keepalive tick failed: {_ke}")


def start_keepalive() -> None:
    """ws081: launch the background keepalive once (idempotent). Observer calls it when raw send
    is on. Default ON; ECAN_FEIGE_WS_RAW_KEEPALIVE=0 disables (falls back to ws077 lazy refresh)."""
    if os.environ.get("ECAN_FEIGE_WS_RAW_KEEPALIVE", "1") == "0":
        return
    if _keepalive_task[0] is not None and not _keepalive_task[0].done():
        return
    _pin_owner_loop()   # ws082: keepalive runs on the observer loop → confirm the socket owner
    try:
        _keepalive_task[0] = asyncio.get_running_loop().create_task(_keepalive_loop())
        logger.info(
            f"[FEIGE-WS-RAW] keepalive armed (interval={_KEEPALIVE_INTERVAL_S}s, "
            f"proactive_refresh>={round(_PROACTIVE_AGE_S, 1)}s, hard_max={_TOKEN_MAX_AGE_S}s)")
    except Exception as _se:
        logger.debug(f"[FEIGE-WS-RAW] keepalive arm failed: {_se}")


def invalidate() -> None:
    """ws067 backstop: force the next raw_send to re-capture a fresh token + reconnect. Called
    when a raw send goes UNCONFIRMED (a possible stale-token signal the proactive live-url check
    missed). Cheap insurance — leaves _conn for _ensure_fresh_conn/_get_conn to tear down."""
    global _conn_params, _conn_params_ts
    _conn_params = None
    _conn_params_ts = 0.0


async def _ensure_fresh_conn() -> None:
    """ws067+ws068 — keep the raw socket's token fresh before each send.

    The captured token expires server-side by AGE (~10-15 min), NOT by URL change: ws066 was
    ~50% confirm at token_age 15-27 min while ws067 was 100% at <8 min, with the URL identical
    (page_token_changed=False) throughout. So the PRIMARY refresh is age-based (ws068): once the
    token is older than _TOKEN_MAX_AGE_S, drop it + the raw socket so the next _get_conn()
    re-captures fresh. We also keep the URL-change check (ws067) as a cheap secondary trigger
    (a no-op in practice, but harmless). On either, tear down so the next send reconnects fresh."""
    global _conn, _conn_params, _conn_params_ts
    if not _conn_params:
        return  # nothing cached yet — _get_conn captures fresh anyway
    reason = ""
    if _page_reconnected[0]:
        # ws077: PRIMARY (event-driven) trigger — the page socket cycled, so our token/connection
        # is stale NOW regardless of age. Beats the age timer to the failure zone under churn.
        _page_reconnected[0] = False
        reason = "page Frontier socket reconnected (webSocketCreated)"
    else:
        age = time.time() - _conn_params_ts
        if _TOKEN_MAX_AGE_S > 0 and age >= _TOKEN_MAX_AGE_S:
            reason = f"token aged {round(age, 1)}s >= max {_TOKEN_MAX_AGE_S}s"
        else:
            cached = (_conn_params or {}).get("url", "")
            live = await _read_live_page_url()
            if live and cached and live != cached:
                reason = f"page url rotated old=...{cached[-30:]} new=...{live[-30:]}"
    if not reason:
        return
    logger.info(f"[FEIGE-WS-RAW] re-syncing raw socket ({reason}) — re-capturing fresh token")
    # ws069: exclusive write — wait for in-flight sends to drain, block new ones, THEN tear
    # down. Closes the race where a stale-refresh closed the socket mid-send (→ spurious DOM
    # fallback). The slow live-url read above stays OUTSIDE this lock so it doesn't stall sends.
    async with _rw.write():
        _conn_params = None
        _conn_params_ts = 0.0
        if _conn is not None:
            try:
                await _conn.close()
            except Exception:
                pass
            _conn = None


async def raw_send(frame_bytes: bytes) -> bool:
    """Send one protobuf frame on eCan's OWN Frontier socket. Returns True if the
    bytes hit the wire (delivery is confirmed downstream via the observer echo),
    False on any failure so the caller falls back to eval-inject.

    ws082: the socket is bound to the owner loop (where it's warmed). If this call runs on
    a DIFFERENT loop (the reply path runs on the direct-delivery worker loop), marshal the
    actual send onto the owner loop via run_coroutine_threadsafe — otherwise the worker-loop
    send can't touch the observer-loop socket and silently falls to eval (the ws080 100/0
    read-ack-vs-reply split). Gated ECAN_FEIGE_WS_RAW_CROSS_LOOP=1 (default ON); =0 reverts to
    the inline call (with the diagnostic still logged) so we can A/B the fix against ws080."""
    if not frame_bytes:
        return False
    owner = _owner_loop[0]
    try:
        cur = asyncio.get_running_loop()
    except Exception:
        cur = None
    _cross = owner is not None and cur is not None and owner is not cur
    if _cross:
        # ws082 instrumentation: a cross-loop raw send is the ws080 root cause — make it loud.
        logger.info(
            f"[FEIGE-WS-RAW] cross-loop raw send running_loop={id(cur)} owner_loop={id(owner)} "
            f"owner_running={owner.is_running()}")
        if os.environ.get("ECAN_FEIGE_WS_RAW_CROSS_LOOP", "1") != "0":
            try:
                # run the send ON the owner loop (it owns _conn); await the result here without
                # blocking this loop. 8s cap → a stuck owner loop falls back to eval (drop-safe).
                fut = asyncio.run_coroutine_threadsafe(_raw_send_impl(frame_bytes), owner)
                return await asyncio.wait_for(asyncio.wrap_future(fut), timeout=8.0)
            except Exception as e:
                logger.warning(
                    f"[FEIGE-WS-RAW] cross-loop marshal FAILED ({type(e).__name__}: {e}) "
                    "— eval-inject fallback")
                return False
    return await _raw_send_impl(frame_bytes)


async def _raw_send_impl(frame_bytes: bytes) -> bool:
    """The actual send. Runs on the owner loop (directly for read-acks, via the ws082 marshal
    for foreign-loop reply sends)."""
    if not frame_bytes:
        return False
    # ws067: re-sync to the page's CURRENT token before sending (default ON; kill switch
    # ECAN_FEIGE_WS_RAW_RESYNC=0). This is the fix for the stale-token staleness.
    if os.environ.get("ECAN_FEIGE_WS_RAW_RESYNC", "1") != "0":
        try:
            await _ensure_fresh_conn()
        except Exception as _re:
            logger.debug(f"[FEIGE-WS-RAW] resync check failed (non-fatal): {_re}")
    # ws069: hold the read-lock across get_conn + send so a concurrent age-refresh (writer)
    # can't tear down the socket between capturing `conn` and writing to it. Many sends share
    # the lock concurrently; only a refresh teardown is exclusive.
    async with _rw.read():
        conn = await _get_conn()
        if conn is None:
            return False
        try:
            await asyncio.wait_for(conn.send(bytes(frame_bytes)), timeout=5.0)
            _age = round(time.time() - _conn_params_ts, 1) if _conn_params_ts else -1.0
            try:
                _lid = id(asyncio.get_running_loop())
            except Exception:
                _lid = 0
            logger.info(
                f"[FEIGE-WS-RAW] frame sent off-renderer ({len(frame_bytes)} bytes) "
                f"token_age={_age}s send_loop={_lid} owner_loop={id(_owner_loop[0]) if _owner_loop[0] else 0}")
            return True
        except Exception as e:
            logger.warning(f"[FEIGE-WS-RAW] raw send failed ({type(e).__name__}: {e}) — fallback")
            # drop the (possibly half-dead) connection so the next send reconnects fresh
            global _conn
            try:
                await conn.close()
            except Exception:
                pass
            _conn = None
            return False


async def close() -> None:
    """Best-effort teardown (called on observer stop / shutdown)."""
    global _conn, _conn_params
    c, _conn = _conn, None
    _conn_params = None
    if c is not None:
        try:
            await c.close()
        except Exception:
            pass
