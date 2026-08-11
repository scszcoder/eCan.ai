"""ws124: a dedicated-thread CDP eval lane for the feige_ws_send fallback inject.

The HANDOFF-STARVED scaling wall: the off-DOM WS send falls back to an in-page
Runtime.evaluate ("feige_ws_send") that puts the frame on the page socket. That
eval is marshaled onto the SHARED CDP loop — which is the qasync MAIN loop, because
cdp_use's CDPClient.start() runs its message handler on whatever loop called start()
(client.py: asyncio.create_task(self._handle_messages())). Under a high-concurrency
burst that loop's thread is starved (GIL contention from the 8 skill-pool worker
threads + a queue full of other non-CDP coroutines) so the submitted eval NEVER runs
and stalls 12s (`[CDP-EVAL][EVAL-STALL] kind=HANDOFF-STARVED`).

This lane runs a SEPARATE CDPClient on its OWN dedicated OS thread + event loop,
attached to the Feige send tab. The inject eval is marshaled there instead, so it no
longer waits behind the qasync loop's coroutine queue.

IMPORTANT CAVEAT (why this is gated + must be A/B measured, not assumed): a dedicated
thread does NOT escape the GIL. It removes LOOP-QUEUE contention (effect that the eval
waits behind other work queued on the busy qasync loop), but the CDP thread still
competes for the GIL with the CPU-bound worker threads. So the net win is real but
bounded — measure it against ws123 alone.

Additive + gated ECAN_FEIGE_DEDICATED_CDP_LOOP=1 (default OFF). Every failure returns
None so feige_ws_send_text falls back to the proven shared-loop eval. Marker
[FEIGE-CDP-LANE].
"""
import asyncio
import os
import threading

from utils.logger_helper import logger_helper as logger

# All CDP-client state below is ONLY ever read/written from coroutines running on the
# dedicated loop (_loop[0]); the threading.Lock guards thread/loop creation only.
_thr_lock = threading.Lock()
_thread = [None]
_loop = [None]
_client = [None]
_sid = [None]
_target = [None]
_cdp_url = [None]
_async_lock = [None]   # asyncio.Lock, created lazily ON the dedicated loop


def _run_loop(loop) -> None:
    asyncio.set_event_loop(loop)
    loop.run_forever()


def _ensure_thread():
    """Start the dedicated thread + event loop once (idempotent). Returns the loop."""
    lp = _loop[0]
    if lp is not None and lp.is_running():
        return lp
    with _thr_lock:
        lp = _loop[0]
        if lp is not None and lp.is_running():
            return lp
        lp = asyncio.new_event_loop()
        t = threading.Thread(target=_run_loop, args=(lp,), name="FeigeCDPLane", daemon=True)
        t.start()
        _thread[0] = t
        _loop[0] = lp
        logger.info("[FEIGE-CDP-LANE] dedicated CDP loop thread started")
        return lp


def _resolve_cdp_url(browser_session) -> str:
    url = getattr(browser_session, "cdp_url", None)
    if not url:
        bp = getattr(browser_session, "browser_profile", None)
        url = getattr(bp, "cdp_url", None) if bp else None
    return str(url or "")


async def _reinit(cdp_url: str, target_id: str) -> None:
    """(Re)create the dedicated CDP client attached to target_id. Runs on the dedicated loop."""
    old = _client[0]
    _client[0] = None
    _sid[0] = None
    if old is not None:
        try:
            await old.stop()
        except Exception:
            pass
    from cdp_use import CDPClient

    client = CDPClient(url=cdp_url)
    await client.start()   # message handler now runs on THIS (dedicated) loop
    att = await client.send_raw(
        "Target.attachToTarget", {"targetId": str(target_id), "flatten": True})
    sid = (att or {}).get("sessionId")
    if not sid:
        try:
            await client.stop()
        except Exception:
            pass
        return
    await client.send_raw("Runtime.enable", {}, session_id=sid)
    _client[0] = client
    _sid[0] = sid
    _target[0] = str(target_id)
    _cdp_url[0] = cdp_url
    logger.info(
        f"[FEIGE-CDP-LANE] CDP client attached target=...{str(target_id)[-6:]} "
        f"on {_thread[0].name if _thread[0] else '?'}")


async def _lane_eval(cdp_url: str, target_id: str, expression: str):
    """Runs ENTIRELY on the dedicated loop: ensure client, then Runtime.evaluate."""
    if _async_lock[0] is None:
        _async_lock[0] = asyncio.Lock()
    async with _async_lock[0]:
        if (_client[0] is None or _target[0] != str(target_id)
                or _cdp_url[0] != cdp_url):
            await _reinit(cdp_url, target_id)
    if _client[0] is None:
        return None
    res = await _client[0].send_raw(
        "Runtime.evaluate",
        {"expression": expression, "awaitPromise": True, "returnByValue": True},
        session_id=_sid[0],
    )
    return ((res or {}).get("result") or {}).get("value")


async def eval_inject(browser_session, target_id, expression, timeout_s: float = 8.0):
    """Run the inject eval on the dedicated CDP thread. Returns the eval value, or
    None on any miss (gate off / no url / no target / error / timeout) so the caller
    falls back to the shared-loop eval. Never raises."""
    if os.environ.get("ECAN_FEIGE_DEDICATED_CDP_LOOP", "") != "1":
        return None
    if not target_id:
        return None
    cdp_url = _resolve_cdp_url(browser_session)
    if not cdp_url:
        return None
    try:
        loop = _ensure_thread()
        fut = asyncio.run_coroutine_threadsafe(
            _lane_eval(cdp_url, str(target_id), expression), loop)
        return await asyncio.wait_for(asyncio.wrap_future(fut), timeout=timeout_s)
    except Exception as e:
        logger.debug(f"[FEIGE-CDP-LANE] eval miss (-> shared loop): {type(e).__name__}: {e}")
        return None
