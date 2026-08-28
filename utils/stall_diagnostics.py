"""ws051: stall / congestion diagnostics — nail the CDP send-stall root cause.

The residual 1v8 tail is a CDP `Runtime.evaluate` round-trip stalling 10-21s while
the handler-loop thread does 0 CDP work AND other threads keep logging (so the
process is NOT frozen — only the CDP thread is starved). Inference said "GIL
contention by thread count", but inference isn't proof. This module measures it
directly and dumps the smoking gun.

Three signals, all gated by ECAN_STALL_DIAG=1 (default OFF), low overhead:

1. GIL CANARY (daemon thread). Sleeps a fixed interval, measures how much LONGER
   than the interval it actually took to resume. `time.sleep` releases the GIL,
   so the overshoot == time spent waiting to re-acquire the GIL + be scheduled.
   A multi-second canary lag == the GIL was held away from this thread that long
   == definitive GIL starvation. Loop-agnostic, so it works no matter which loop
   the CDP handler runs on.

2. CPU-CORES-USED (in the canary's periodic report). delta(process_time)/delta
   (wall). ~1.0 == the whole process is pinned to ONE core == classic GIL-bound
   Python (8 threads serialized through the GIL). >1.0 == genuine parallel C work
   (a C extension releasing the GIL). <0.3 == idle / I/O-bound (NOT GIL). This is
   the cleanest one-number GIL verdict.

3. ALL-THREAD STACK DUMP on stall (THE smoking gun). The instant the canary lag
   crosses _STALL_LAG_S, dump every thread's Python stack. Whatever thread is
   sitting in a long C call (json/deepcopy/regex/encode) holding the GIL shows up
   by name + line — no more guessing which operation is the hog. Rate-limited.

Plus an optional asyncio LOOP HEARTBEAT (`ensure_loop_heartbeat(loop)`) attached
to the CDP handler loop so we can compare loop-tick-lag to the canary: both spike
together => GIL; loop spikes but canary fine => the loop is blocked on a sync call
(not GIL) and a separate connection/loop WOULD help.
"""
from __future__ import annotations

import os
import sys
import time
import threading
import traceback
import logging

from utils.logger_helper import logger_helper as logger  # CN app logger is "eCan.cn"

_CANARY_INTERVAL_S = 0.1
_STALL_LAG_S = float(os.environ.get("ECAN_STALL_DIAG_LAG_S", "1.5") or "1.5")
_REPORT_INTERVAL_S = 5.0
# ws087: lowered 20->6 so CONSECUTIVE sync-call blocks each get a live stack dump (the 083 run
# had repeated 2-23s loop blocks 5-20s apart; the old 20s gap swallowed most of them).
_DUMP_MIN_GAP_S = 6.0

_canary_started = threading.Event()
_hb_loops: set[int] = set()
_hb_lock = threading.Lock()
_last_dump_at = [0.0]
# ws087: each attached event loop's last liveness tick (published by _loop_heartbeat) so the
# OFF-LOOP canary thread can detect a SYNC-CALL block (loop frozen but GIL free) in REAL TIME and
# dump the blocked loop thread's stack WHILE it's stuck — the on-loop heartbeat can only notice
# the block after it ends, by which point the blocking frame is gone.
_loop_last_tick: dict[int, float] = {}
_loop_blocked_dumped: set[int] = set()


def enabled() -> bool:
    return os.environ.get("ECAN_STALL_DIAG", "") == "1"


def _dump_all_thread_stacks(reason: str) -> None:
    now = time.perf_counter()
    if now - _last_dump_at[0] < _DUMP_MIN_GAP_S:
        return
    _last_dump_at[0] = now
    try:
        frames = sys._current_frames()
        names = {t.ident: t.name for t in threading.enumerate()}
        out = [f"[STALL-DIAG] ===== ALL-THREAD STACK DUMP ({reason}) ====="]
        for tid, frame in frames.items():
            stack = traceback.format_stack(frame)
            _nm = names.get(tid, "?")
            # ws089: MainThread runs the qasync/Qt event loop — it's the prime suspect for the
            # HANDOFF-STARVED stalls (a busy Qt slot/handler stops the loop pumping our cross-loop
            # CDP sends). Dump its FULL stack deep so the blocking Python frame (the slot/handler)
            # is visible, not just qasync run_forever. Other threads: deepest 6 frames is enough.
            _is_main = (_nm == "MainThread")
            _depth = len(stack) if _is_main else 6
            tail = " <<< ".join(s.strip().replace("\n", " ") for s in stack[-_depth:])
            out.append(f"[STALL-DIAG] thr {_nm}({tid}): {tail[:1800 if _is_main else 700]}")
        logger.warning("\n".join(out))
    except Exception as exc:
        logger.debug(f"[STALL-DIAG] stack dump failed: {exc}")


def dump_stacks_now(reason: str) -> None:
    """ws147: public trigger to dump every thread's stack NOW (throttled by _DUMP_MIN_GAP_S).

    For callers that detect a stall the GIL canary CANNOT see — e.g. a cross-loop marshal
    timing out because the owner CDP loop is blocked. That stall keeps the canary lag LOW (the
    main loop keeps ticking), so the lag-triggered dump never fires. Firing here captures the
    blocked owner-loop thread's stack while it is still stuck. Independent of ECAN_STALL_DIAG so
    it works on a normal run; the caller gates whether to call it.
    """
    _dump_all_thread_stacks(reason)


def _canary_loop() -> None:
    rolling_max = 0.0
    last_report = time.perf_counter()
    last_cpu = time.process_time()
    last_wall = time.perf_counter()
    while True:
        t0 = time.perf_counter()
        time.sleep(_CANARY_INTERVAL_S)
        lag = (time.perf_counter() - t0) - _CANARY_INTERVAL_S
        if lag > rolling_max:
            rolling_max = lag
        if lag >= _STALL_LAG_S:
            logger.warning(
                f"[STALL-DIAG] GIL STALL: canary couldn't resume for {lag:.1f}s after a "
                f"{int(_CANARY_INTERVAL_S * 1000)}ms sleep — GIL was held away this long. "
                f"threads={threading.active_count()}")
            _dump_all_thread_stacks(f"canary lag={lag:.1f}s")
        # ws087: off-loop watchdog for SYNC-CALL blocks. This canary thread keeps running while an
        # attached event loop is frozen on a synchronous call (the case where LOOP STALL fires but
        # the GIL canary above does NOT — i.e. NOT GIL contention, the residual 083/085 wedge). When
        # a loop hasn't ticked for >= _STALL_LAG_S, dump ALL thread stacks NOW, while it's still
        # blocked — the loop thread's stack names the exact blocking call (a CDP eval / requests /
        # blocking lock / sync HTTP on the loop). Dedup per ongoing block via _loop_blocked_dumped.
        _wd_now = time.perf_counter()
        for _lid, _tick in list(_loop_last_tick.items()):
            _blocked = _wd_now - _tick
            if _blocked >= _STALL_LAG_S and _lid not in _loop_blocked_dumped:
                _loop_blocked_dumped.add(_lid)
                logger.warning(
                    f"[STALL-DIAG] LOOP BLOCKED LIVE: loop={_lid} not ticked for {_blocked:.1f}s "
                    f"while the GIL canary is healthy => blocked on a SYNCHRONOUS CALL (NOT GIL). "
                    f"The loop thread's stack below is the blocker:")
                _dump_all_thread_stacks(f"loop={_lid} sync-block {_blocked:.1f}s")
            elif _blocked < _STALL_LAG_S:
                _loop_blocked_dumped.discard(_lid)
        now = time.perf_counter()
        if now - last_report >= _REPORT_INTERVAL_S:
            cpu = time.process_time()
            cores = (cpu - last_cpu) / max(1e-6, now - last_wall)
            last_cpu, last_wall = cpu, now
            try:
                ths = threading.enumerate()
                fam = sorted({t.name.rsplit("-", 1)[0].rsplit("_", 1)[0] for t in ths})
            except Exception:
                fam = []
            logger.info(
                f"[STALL-DIAG] canary lag_max_5s={int(rolling_max * 1000)}ms "
                f"cpu_cores_used={cores:.2f} threads={threading.active_count()} "
                f"families={fam[:14]}")
            rolling_max = 0.0
            last_report = now


def start_canary() -> None:
    """Start the process-wide GIL canary (once). No-op unless ECAN_STALL_DIAG=1."""
    if not enabled() or _canary_started.is_set():
        return
    _canary_started.set()
    try:
        threading.Thread(
            target=_canary_loop, name="stall-diag-canary", daemon=True
        ).start()
        logger.info(
            f"[STALL-DIAG] GIL canary started (stall_lag={_STALL_LAG_S}s, "
            f"interval={int(_CANARY_INTERVAL_S * 1000)}ms). cpu_cores_used~1.0 => GIL-bound.")
    except Exception as exc:
        logger.debug(f"[STALL-DIAG] canary start failed: {exc}")


async def _loop_heartbeat(lid: int) -> None:
    import asyncio
    rolling_max = 0.0
    last_report = time.perf_counter()
    logger.info(f"[STALL-DIAG] loop heartbeat attached to loop={lid}")
    while True:
        # ws087: publish liveness EACH tick so the off-loop canary watchdog can detect a sync-call
        # block in real time. While the loop is frozen this coroutine can't run, so this timestamp
        # goes stale -> the watchdog sees the gap and dumps the blocked stack live.
        _loop_last_tick[lid] = time.perf_counter()
        t0 = time.perf_counter()
        await asyncio.sleep(_CANARY_INTERVAL_S)
        lag = (time.perf_counter() - t0) - _CANARY_INTERVAL_S
        if lag > rolling_max:
            rolling_max = lag
        if lag >= _STALL_LAG_S:
            logger.warning(
                f"[STALL-DIAG] LOOP STALL: loop={lid} didn't tick for {lag:.1f}s "
                f"(compare to canary: both spike => GIL; only loop => blocked on a sync call)")
        now = time.perf_counter()
        if now - last_report >= _REPORT_INTERVAL_S:
            logger.info(f"[STALL-DIAG] loop={lid} lag_max_5s={int(rolling_max * 1000)}ms")
            rolling_max = 0.0
            last_report = now


def ensure_loop_heartbeat(loop) -> None:
    """Attach a heartbeat to *loop* (once per loop). Call with the CDP handler
    loop so its tick-lag can be compared to the GIL canary."""
    if not enabled() or loop is None:
        return
    try:
        if not getattr(loop, "is_running", lambda: False)():
            return
        lid = id(loop)
        with _hb_lock:
            if lid in _hb_loops:
                return
            _hb_loops.add(lid)
        loop.call_soon_threadsafe(lambda: loop.create_task(_loop_heartbeat(lid)))
    except Exception as exc:
        logger.debug(f"[STALL-DIAG] loop heartbeat attach failed: {exc}")
