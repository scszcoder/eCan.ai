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
import json
import logging
import time

from . import ws_session

logger = logging.getLogger("eCan")

_conn = None                 # live websockets client connection (cached)
_conn_params: dict | None = None   # {url, origin, ua, cookie} captured off the page
_conn_params_ts: float = 0.0       # ws066: when _conn_params was captured (token-age diagnostic)
_lock = asyncio.Lock()       # serialize connect/reconnect (not the sends)

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
            logger.info("[FEIGE-WS-RAW] OWN Frontier socket CONNECTED (off-renderer send live)")
            return _conn
        except Exception as e:
            logger.warning(
                f"[FEIGE-WS-RAW] OWN socket connect FAILED ({type(e).__name__}: {e}) — "
                f"this is the anti-bot answer; falling back to eval-inject"
            )
            _conn = None
            return None


async def raw_send(frame_bytes: bytes) -> bool:
    """Send one protobuf frame on eCan's OWN Frontier socket. Returns True if the
    bytes hit the wire (delivery is confirmed downstream via the observer echo),
    False on any failure so the caller falls back to eval-inject."""
    if not frame_bytes:
        return False
    conn = await _get_conn()
    if conn is None:
        return False
    try:
        await asyncio.wait_for(conn.send(bytes(frame_bytes)), timeout=5.0)
        logger.info(f"[FEIGE-WS-RAW] frame sent off-renderer ({len(frame_bytes)} bytes)")
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
