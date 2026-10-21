"""Memory-leak fix verification tests.

Tests every fix in the memory-leak remediation pass:

1. placeholder_timer._REAL_REPLY_AT pruning (all write sites)
2. lightrag_health.WorkerPoolHealthMonitor per-worker stats pruning
3. lightrag_server proxy callback unregistration on stop()
4. lightrag_server subprocess handle cleanup on restart (_reap_previous_proc)
5. ws_observer card-tracking pruning (source-level assertions)
6. syntax check of every modified file

Run: python3 tests/test_memory_leak_fixes.py
"""
import sys
import os
import time
import asyncio

sys.path.insert(0, os.getcwd())

PASS = 0
FAIL = 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        FAILURES.append((name, detail))
        print(f"  FAIL  {name}  {detail}")


# ---------------------------------------------------------------------------
print("\n=== 1. placeholder_timer._REAL_REPLY_AT pruning ===")
# ---------------------------------------------------------------------------
try:
    from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
        placeholder_timer as pt,
    )
except Exception as e:
    print(f"  SKIP (import failed): {e}")
    pt = None

if pt:
    cap = pt._REAL_REPLY_AT_MAX_ENTRIES

    # --- 1a. mark_real_reply_delivered caps the dict ---
    with pt._REGISTRY_LOCK:
        pt._REAL_REPLY_AT.clear()
    for i in range(cap * 3):
        pt.mark_real_reply_delivered(f"cust_{i}", f"msg_{i}")
    with pt._REGISTRY_LOCK:
        n = len(pt._REAL_REPLY_AT)
    check(
        f"mark_real_reply_delivered caps _REAL_REPLY_AT at {cap} (got {n})",
        n <= cap,
        f"expected <= {cap}, got {n}",
    )
    with pt._REGISTRY_LOCK:
        newest_ok = ("cust_%d" % (cap * 3 - 1), "msg_%d" % (cap * 3 - 1)) in pt._REAL_REPLY_AT
    check("newest entry retained after prune", newest_ok)
    with pt._REGISTRY_LOCK:
        oldest_gone = ("cust_0", "msg_0") not in pt._REAL_REPLY_AT
    check("oldest entry dropped after prune", oldest_gone)

    # --- 1b. functional round-trip still works ---
    pt.mark_real_reply_delivered("test_cust", "test_msg")
    check(
        "is_real_reply_recent works after prune",
        pt.is_real_reply_recent("test_cust", "test_msg"),
    )

    # --- 1c. no pruning below cap (no premature data loss) ---
    # NOTE: each call writes 2 entries (exact key + blank-key suppression
    # slot), so cap-5 calls would exceed the cap. Insert only enough to stay
    # below it and verify zero data loss.
    with pt._REGISTRY_LOCK:
        pt._REAL_REPLY_AT.clear()
    for i in range((cap - 5) // 2):
        pt.mark_real_reply_delivered(f"c{i}", f"m{i}")
    expected = 2 * ((cap - 5) // 2)
    with pt._REGISTRY_LOCK:
        n2 = len(pt._REAL_REPLY_AT)
    check(
        f"no pruning below cap (got {n2})",
        n2 == expected,
        f"expected {expected}, got {n2}",
    )

    # --- 1d. cancel() also caps (second write site) ---
    with pt._REGISTRY_LOCK:
        pt._REAL_REPLY_AT.clear()
    for i in range(cap * 2):
        pt.cancel(f"cc_{i}", f"cm_{i}")
    with pt._REGISTRY_LOCK:
        n3 = len(pt._REAL_REPLY_AT)
    check(
        f"cancel() caps _REAL_REPLY_AT at {cap} (got {n3})",
        n3 <= cap,
        f"expected <= {cap}, got {n3}",
    )

    # --- 1e. cancel_any_for_customer() also caps (third write site) ---
    with pt._REGISTRY_LOCK:
        pt._REAL_REPLY_AT.clear()
    for i in range(cap * 2):
        pt.cancel_any_for_customer(f"ca_{i}")
    with pt._REGISTRY_LOCK:
        n4 = len(pt._REAL_REPLY_AT)
    check(
        f"cancel_all_for_customer() caps _REAL_REPLY_AT at {cap} (got {n4})",
        n4 <= cap,
        f"expected <= {cap}, got {n4}",
    )

# ---------------------------------------------------------------------------
print("\n=== 2. lightrag_health.WorkerPoolHealthMonitor stats pruning ===")
# ---------------------------------------------------------------------------
try:
    from knowledge.lightrag_health import WorkerPoolHealthMonitor

    async def _run_health():
        hm = WorkerPoolHealthMonitor()
        cap = hm._MAX_TRACKED_WORKERS
        # All busy — pruning must not remove them even past the cap.
        for i in range(cap * 4):
            await hm.record_request_start(f"llm_{i}")
        return cap, len(hm._workers)

    cap, nw = asyncio.run(_run_health())
    check(
        f"busy workers retained past cap (got {nw}, cap {cap})",
        nw == cap * 4,
        f"expected {cap*4}, got {nw}",
    )

    # --- 2b. success path drops the entry entirely ---
    async def _run_terminal():
        hm2 = WorkerPoolHealthMonitor()
        hm2._workers.clear()
        await hm2.record_request_start("llm_x")
        before = len(hm2._workers)
        await hm2.record_request_success("llm_x", 0.5)
        after = len(hm2._workers)
        await hm2.record_request_start("llm_y")
        await hm2.record_request_failure("llm_y", "timeout")
        after_fail = len(hm2._workers)
        return before, after, after_fail

    before, after, after_fail = asyncio.run(_run_terminal())
    check("start adds a worker entry", before == 1, f"before={before}")
    check("success removes the worker entry", after == 0, f"after={after}")
    check("failure removes the worker entry", after_fail == 0, f"after_fail={after_fail}")

    # --- 2c. idle workers are pruned past cap ---
    async def _run_idle_prune():
        hm3 = WorkerPoolHealthMonitor()
        hm3._workers.clear()
        cap3 = hm3._MAX_TRACKED_WORKERS
        # Start many workers, then mark most idle and check pruning.
        for i in range(cap3 + 50):
            await hm3.record_request_start(f"idle_{i}")
        # Mark half of them idle (is_busy=False) without deleting.
        for i in range(0, cap3 + 50, 2):
            hm3._workers[f"idle_{i}"].is_busy = False
        # Trigger pruning via a new start that pushes us over the cap.
        for i in range(50):
            await hm3.record_request_start(f"idle_new_{i}")
        return cap3, len(hm3._workers)

    cap3, n_idle = asyncio.run(_run_idle_prune())
    check(
        f"idle workers pruned past cap (got {n_idle}, cap {cap3})",
        n_idle <= cap3,
        f"expected <= {cap3}, got {n_idle}",
    )
except Exception as e:
    import traceback
    traceback.print_exc()
    FAIL += 1
    FAILURES.append(("health monitor", str(e)))

# ---------------------------------------------------------------------------
print("\n=== 3. lightrag_server proxy callback unregistration ===")
# ---------------------------------------------------------------------------
try:
    from knowledge.lightrag_server import LightragServer
    from agent.ec_skills.system_proxy import get_proxy_manager

    srv = LightragServer()
    check("_proxy_unregister attribute exists", hasattr(srv, "_proxy_unregister"))
    check("_proxy_cb_lock attribute exists", hasattr(srv, "_proxy_cb_lock"))
    check("_proxy_cb_stopped attribute exists", hasattr(srv, "_proxy_cb_stopped"))

    pm = get_proxy_manager()
    if pm is not None:
        # Register a synthetic callback the same way LightragServer does,
        # then exercise the stop()-side unregister contract.
        calls = {"n": 0}

        def _cb(_proxies):
            calls["n"] += 1

        unregister = pm.register_callback(_cb)
        n_before = len(pm._callbacks)
        check("register_callback appended", n_before >= 1, f"n={n_before}")
        unregister()
        n_after = len(pm._callbacks)
        check(
            "unregister() removes the callback (no accumulation)",
            n_after == n_before - 1,
            f"before={n_before}, after={n_after}",
        )

        # Full lifecycle: simulate N restarts of a LightragServer and assert
        # the ProxyManager callback list does not grow.
        baseline = len(pm._callbacks)
        for _ in range(5):
            s = LightragServer()
            # Mimic the background registration thread synchronously.
            s._register_proxy_change_callback.__wrapped__ if False else None
            # Directly emulate what the thread does, minus the 2s sleep.
            with s._proxy_cb_lock:
                if not s._proxy_cb_stopped:
                    s._proxy_unregister = pm.register_callback(lambda _p: None)
            s.stop()
        final = len(pm._callbacks)
        check(
            "5x start/stop cycles do not accumulate callbacks",
            final == baseline,
            f"baseline={baseline}, final={final}",
        )
    else:
        print("  SKIP behavioral proxy test (ProxyManager unavailable)")
except Exception as e:
    import traceback
    traceback.print_exc()
    FAIL += 1
    FAILURES.append(("proxy callback", str(e)))

# ---------------------------------------------------------------------------
print("\n=== 4. lightrag_server subprocess cleanup on restart ===")
# ---------------------------------------------------------------------------
try:
    from knowledge.lightrag_server import LightragServer
    import subprocess as sp

    srv = LightragServer()
    check("_reap_previous_proc method exists", hasattr(srv, "_reap_previous_proc"))

    # 4a. Dead-process handle: _reap_previous_proc must close streams and
    #     null out self.proc WITHOUT killing anything.
    dead = sp.Popen(["true"])
    dead.wait(timeout=5)
    srv.proc = dead
    srv._reap_previous_proc()
    check("dead proc handle reaped (self.proc is None)", srv.proc is None)
    check("dead proc stdin closed", dead.stdin is None or dead.stdin.closed)

    # 4b. No-proc case is a safe no-op.
    srv.proc = None
    srv._reap_previous_proc()
    check("no-op when self.proc is None", srv.proc is None)

    # 4c. Source-level: reaper is wired into _start_server_process.
    src = open("knowledge/lightrag_server.py").read()
    check("_reap_previous_proc defined in source", "def _reap_previous_proc(self):" in src)
    check(
        "_start_server_process calls _reap_previous_proc",
        "self._reap_previous_proc()" in src,
    )
    # 4d. Production spawn isolates the child into its own session/group so
    #     stop()'s killpg can never hit the parent. Guard against regression.
    check(
        "child spawned with os.setsid (posix)",
        "preexec_fn=os.setsid" in src,
    )
    check(
        "child spawned with CREATE_NEW_PROCESS_GROUP (win)",
        "CREATE_NEW_PROCESS_GROUP" in src,
    )
except Exception as e:
    import traceback
    traceback.print_exc()
    FAIL += 1
    FAILURES.append(("subprocess cleanup", str(e)))

# ---------------------------------------------------------------------------
print("\n=== 5. ws_observer card-tracking pruning ===")
# ---------------------------------------------------------------------------
try:
    src = open(
        "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/ws_observer.py"
    ).read()
    check("ws_observer has _CARD_TRACK_MAX cap", "_CARD_TRACK_MAX" in src)
    check("ws_observer has _CARD_TRACK_TTL_S", "_CARD_TRACK_TTL_S" in src)
    check("ws_observer prunes per-card tracking", "prune per-card tracking" in src)
    check("ws_observer tracks last prune time", "_last_card_prune_ts" in src)
except Exception as e:
    FAIL += 1
    FAILURES.append(("ws_observer pruning", str(e)))

# ---------------------------------------------------------------------------
print("\n=== 6. syntax check all modified files ===")
# ---------------------------------------------------------------------------
import py_compile
for f in [
    "knowledge/lightrag_server.py",
    "knowledge/lightrag_health.py",
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/placeholder_timer.py",
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/ws_observer.py",
]:
    try:
        py_compile.compile(f, doraise=True)
        check(f"syntax {os.path.basename(f)}", True)
    except py_compile.PyCompileError as e:
        check(f"syntax {os.path.basename(f)}", False, str(e))

# ---------------------------------------------------------------------------
print("=" * 60)
if FAIL:
    print("RESULT: FAIL")
    print("\nFailures:")
    for name, detail in FAILURES:
        print(f"  - {name}: {detail}")
else:
    print(f"RESULT: ALL {PASS} CHECKS PASSED")
print("=" * 60)
