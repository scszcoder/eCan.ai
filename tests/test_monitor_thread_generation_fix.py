#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reproduction test: LightragServer monitor-thread leak across stop()/start().

Scenario (the race): stop() sets `_monitor_running = False`, but the monitor
thread is mid-`time.sleep(2)` and cannot observe it yet. start() immediately
sets `_monitor_running = True` and spawns a NEW monitor thread. The OLD thread
later wakes, sees True again, and never exits — one leaked thread per restart
cycle, each holding a reference to the server object.

The fix: a monotonically increasing generation counter. stop() bumps it; each
thread captures its creation generation and exits on mismatch regardless of
what happens to the boolean flag.
"""
import os
import sys
import threading
import time
from unittest import mock

FAILURES = []
PASSES = []
RESULT = {'observed_true_after_false': False}


def check(name, cond, detail=""):
    line = f"{name} {detail}".strip()
    if cond:
        PASSES.append(line)
        print(f"  PASS {line}")
    else:
        FAILURES.append(line)
        print(f"  FAIL {line}")


def make_server():
    """Construct a LightragServer bypassing __init__ (which spawns threads
    and calls the real proxy manager). We only need the monitor/health
    generation logic for this test.

    Uses LightragServer.__new__ plus manual attribute setup so stop() can
    run without needing a real process handle.
    """
    import knowledge.lightrag_server as ls

    server = ls.LightragServer.__new__(ls.LightragServer)
    server.__dict__.update({
        'proc': None,
        # Point at our own PID so _monitor_parent's `self.parent_pid` guard
        # is truthy and the loop actually enters (production __init__ sets
        # this to the real parent PID).
        'parent_pid': os.getpid(),
        'restart_count': 0,
        'last_restart_time': 0.0,
        'max_restarts': 50,
        'disable_parent_monitoring': False,
        'extra_env': {},
        '_monitor_running': False,
        '_monitor_thread': None,
        '_self_health_check_thread': None,
        '_thread_generation': 0,
        '_thread_generation_lock': threading.Lock(),
        '_self_health_check_interval': 1,
        '_unhealthy_count': 0,
        '_unhealthy_count_lock': threading.Lock(),
        '_max_unhealthy': 3,
        '_vllm_monitor_event': None,
        '_vllm_error_monitor_thread': None,
        '_stdout_log_handle': None,
        '_stderr_log_handle': None,
        '_pid_file_path': None,
        '_atexit_registered': False,
        '_last_log_paths': (None, None),
        '_proxy_cb_lock': threading.Lock(),
        '_proxy_cb_stopped': False,
        '_proxy_unregister': None,
        '_script_path': None,
        '_vllm_cache': {},
        '_vllm_cache_lock': threading.Lock(),
        '_vllm_cache_file': None,
        '_last_health_check_time': 0,
    })
    return server


def count_monitor_threads():
    return [t.name for t in threading.enumerate()
            if t.name.startswith("Lightrag")]


def main():
    sys.path.insert(0, os.getcwd())
    import knowledge.lightrag_server as ls

    print("=== 7. monitor-thread generation fix ===")

    # --- Test 1: the race condition reproduced with OLD-style boolean logic ---
    # Simulate what the OLD code did: stop() only flips the flag, and a thread
    # mid-sleep re-checks only the boolean. This proves the bug is real.
    class RacyHolder:
        running = True

    racy = RacyHolder()

    def racy_loop():
        time.sleep(0.05)   # fall asleep inside the while window
        # At this point the "main" thread will flip running=False then True
        time.sleep(0.3)
        if racy.running:   # re-check: boolean was set back to True by start()
            RESULT['observed_true_after_false'] = True

    t = threading.Thread(target=racy_loop, daemon=True)
    t.start()
    time.sleep(0.1)
    racy.running = False   # stop()
    time.sleep(0.05)
    racy.running = True    # start() re-sets flag before old thread wakes up
    t.join(timeout=1.0)
    check("OLD boolean-only logic is racy (thread sees True again)",
          RESULT['observed_true_after_false'],
          "(demonstrates the pre-fix bug was real)")

    # --- Test 2: NEW code exits a stale thread even with the same race ---
    server = make_server()
    with mock.patch.object(ls.LightragServer, '_start_server_process',
                           return_value=True), \
         mock.patch.object(ls.LightragServer, 'is_running',
                           return_value=False):
        server.start()

    # Capture the first monitor thread and its generation
    t1 = server._monitor_thread
    gen1 = server._thread_generation
    check("monitor thread started", t1 is not None and t1.is_alive())
    check("generation bumped by start()", gen1 == 1, f"(gen={gen1})")

    # The race: call stop() then immediately start() again. The old thread is
    # inside its time.sleep(2) and cannot observe `_monitor_running=False`.
    server.stop()
    check("stop() bumped generation", server._thread_generation > gen1,
          f"(gen now {server._thread_generation})")

    # start() immediately re-entables everything and spawns a new thread
    with mock.patch.object(ls.LightragServer, '_start_server_process',
                           return_value=True), \
         mock.patch.object(ls.LightragServer, 'is_running',
                           return_value=False):
        server.start()
    t2 = server._monitor_thread
    check("second spawn is a different thread", t1 is not t2)

    # t1 is still (probably) inside its 2s sleep. Give it one full cycle; it
    # must exit on generation mismatch even though _monitor_running is True.
    t1.join(timeout=4.0)
    check("stale monitor thread exits despite _monitor_running=True",
          not t1.is_alive(),
          f"(t1 alive={t1.is_alive()})")

    # New thread must stay alive (it owns the matching generation)
    time.sleep(0.2)
    check("current monitor thread still alive", t2.is_alive())

    # --- Test 3: stop() with no start() still terminates the thread ---
    server2 = make_server()
    with mock.patch.object(ls.LightragServer, '_start_server_process',
                           return_value=True), \
         mock.patch.object(ls.LightragServer, 'is_running',
                           return_value=False):
        server2.start()
    ts = server2._monitor_thread
    server2.stop()
    ts.join(timeout=4.0)
    check("plain stop() joins monitor thread", not ts.is_alive())

    # --- Test 4: health-check thread also exits on stop ---
    with mock.patch.object(ls.LightragServer, '_start_server_process',
                           return_value=True), \
         mock.patch.object(ls.LightragServer, 'is_running',
                           return_value=False):
        server2.start()
    h = server2._self_health_check_thread
    check("health thread started", h is not None and h.is_alive())
    server2.stop()
    h.join(timeout=4.0)
    check("health thread exits on stop()", not h.is_alive())

    # --- Test 5: no Lightrag threads leaked at the end ---
    server.stop()
    server2.stop()
    # stop() already joined the monitor/health threads with bounded timeouts
    # (vllm: 2s, self_health_check: 2.5s, parent-monitor: 3s). 1.0s gives the
    # daemon threads a full wake-up window to observe generation mismatch and
    # exit cleanly before the assertion, eliminating any CI-flaky risk on
    # slow runners where a thread was still inside time.sleep(1) when joined.
    time.sleep(1.0)  # let daemons exit

    live_threads = count_monitor_threads()
    check("no leaked Lightrag threads remain", len(live_threads) == 0,
          f"(live: {live_threads})")

    print()
    print("=" * 60)
    if FAILURES:
        print(f"RESULT: {len(FAILURES)} FAILURES, {len(PASSES)} passed")
        for f in FAILURES:
            print(f"  - {f}")
        print("=" * 60)
        return 1
    print(f"RESULT: ALL {len(PASSES)} CHECKS PASSED")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
