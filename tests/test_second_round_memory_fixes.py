"""Verification for the second round of memory-leak fixes (uncommitted):

  8a. human_intervention._HANDLED_QUESTIONS  — (customer, msg_id) keyed,
      no TTL, never evicted → unbounded.
  8b. human_intervention._RECENT_HUMAN_REPLIES — per-customer dict with no
      key-count cap → unbounded across customers.
  8c. pdd_chat.ws_observer._ECHOES — per-uid dict with no key-count cap.
  9.  lightrag_server monitor/health threads — boolean-flag race leaks one
      thread per restart; generation counter fixes it.

Each check proves (a) the container stayed bounded under a burst far larger
than the cap, and (b) the pruning did not destroy live data that callers
still need.

Run:  python3 tests/test_second_round_memory_fixes.py
Exit code 0 == all checks passed.
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_failures = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"  {status}  {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        _failures.append(name)


def test_handled_questions_cap():
    print("\n=== 8a. human_intervention._HANDLED_QUESTIONS cap ===")
    from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
        human_intervention as hi,
    )

    orig_cap = hi.HANDLED_QUESTIONS_CAP
    hi._HANDLED_QUESTIONS.clear()
    hi._HANDLED_QUESTIONS_TEXT.clear()
    hi.HANDLED_QUESTIONS_CAP = 50
    try:
        # Burst: 500 distinct questions across 5 customers.
        for i in range(500):
            hi.mark_handled(
                f"cust{i % 5}", question_msg_id=f"q{i}",
                msg_id=f"m{i}", bubble_text=f"text{i}",
            )
        n_q = len(hi._HANDLED_QUESTIONS)
        n_t = len(hi._HANDLED_QUESTIONS_TEXT)
        check("_HANDLED_QUESTIONS bounded by cap", n_q <= 55, f"(size={n_q}, cap=50)")
        check("_HANDLED_QUESTIONS_TEXT bounded too", n_t <= 55, f"(size={n_t})")

        # The MOST RECENT question must survive pruning (callers rely on it).
        newest = f"q499"
        check("newest question survives prune",
              hi.is_question_handled("cust4", newest),
              f"(cust4, {newest})")

        # An ancient question must be gone (proves eviction happened).
        oldest = "q0"
        check("oldest question evicted",
              not hi.is_question_handled("cust0", oldest),
              f"(cust0, {oldest})")

        # Text map stays consistent with the timestamp map (no orphans).
        orphan = set(hi._HANDLED_QUESTIONS_TEXT) - set(hi._HANDLED_QUESTIONS)
        check("no orphaned TEXT entries", not orphan, f"({len(orphan)} orphans)")
    finally:
        hi.HANDLED_QUESTIONS_CAP = orig_cap
        hi._HANDLED_QUESTIONS.clear()
        hi._HANDLED_QUESTIONS_TEXT.clear()


def test_recent_human_replies_cap():
    print("\n=== 8b. human_intervention._RECENT_HUMAN_REPLIES cap ===")
    from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
        human_intervention as hi,
    )

    orig_cap = hi.RECENT_HUMAN_REPLY_CUSTOMER_CAP
    hi._RECENT_HUMAN_REPLIES.clear()
    hi.RECENT_HUMAN_REPLY_CUSTOMER_CAP = 20
    try:
        for i in range(300):
            hi.record_human_reply(f"customer_{i}", f"human reply {i}")
        n = len(hi._RECENT_HUMAN_REPLIES)
        check("customer dict bounded by cap", n <= 20, f"(size={n}, cap=20)")

        # The most recently written customer must still resolve.
        check("newest customer reply retrievable",
              hi.get_recent_human_reply("customer_299") == "human reply 299")

        # Per-customer list cap (existing behaviour) must still hold.
        hi._RECENT_HUMAN_REPLIES.clear()
        for i in range(10):
            hi.record_human_reply("solo", f"msg{i}")
        lst = hi._RECENT_HUMAN_REPLIES.get("solo", [])
        check("per-customer list still capped at MAX",
              len(lst) <= hi.RECENT_HUMAN_REPLY_MAX,
              f"(len={len(lst)}, max={hi.RECENT_HUMAN_REPLY_MAX})")
    finally:
        hi.RECENT_HUMAN_REPLY_CUSTOMER_CAP = orig_cap
        hi._RECENT_HUMAN_REPLIES.clear()


def test_pdd_echoes_cap():
    print("\n=== 8c. pdd_chat.ws_observer._ECHOES cap ===")
    from agent.ec_skills.browser_use_extension.hooks.external.pdd_chat import (
        ws_observer as wo,
    )

    orig_cap = wo._ECHO_UID_CAP
    wo._ECHOES.clear()
    wo._ECHO_UID_CAP = 25
    try:
        for i in range(400):
            wo.record_echo(f"uid_{i}", f"echo {i}")
        n = len(wo._ECHOES)
        check("uid dict bounded by cap", n <= 25, f"(size={n}, cap=25)")

        # Most-recent uid must still be queryable.
        now = time.time()
        check("newest uid echo retrievable",
              wo.echoed_since("uid_399", "echo 399", now - 5))

        # Per-uid list cap (existing) still holds.
        wo._ECHOES.clear()
        for i in range(50):
            wo.record_echo("solo_uid", f"m{i}")
        check("per-uid list still capped at 20",
              len(wo._ECHOES["solo_uid"]) <= 20,
              f"(len={len(wo._ECHOES['solo_uid'])})")
    finally:
        wo._ECHO_UID_CAP = orig_cap
        wo._ECHOES.clear()


def test_thread_generation():
    print("\n=== 9. lightrag_server thread-generation race ===")
    import knowledge.lightrag_server as ls
    from unittest import mock

    def make_server():
        s = ls.LightragServer.__new__(ls.LightragServer)
        s.__dict__.update({
            'proc': None, 'parent_pid': os.getpid(),
            'restart_count': 0, 'last_restart_time': 0.0, 'max_restarts': 50,
            'disable_parent_monitoring': False, 'extra_env': {},
            '_monitor_running': False, '_monitor_thread': None,
            '_self_health_check_thread': None,
            '_thread_generation': 0,
            '_thread_generation_lock': threading.Lock(),
            '_self_health_check_interval': 1, '_unhealthy_count': 0,
            '_unhealthy_count_lock': threading.Lock(), '_max_unhealthy': 3,
            '_vllm_monitor_event': None, '_vllm_error_monitor_thread': None,
            '_stdout_log_handle': None, '_stderr_log_handle': None,
            '_pid_file_path': None, '_atexit_registered': False,
            '_last_log_paths': (None, None),
            '_proxy_cb_lock': threading.Lock(), '_proxy_cb_stopped': False,
            '_proxy_unregister': None, '_script_path': None,
            '_vllm_cache': {}, '_vllm_cache_lock': threading.Lock(),
            '_vllm_cache_file': None, '_last_health_check_time': 0,
        })
        return s

    def live_lightrag_threads():
        return [t for t in threading.enumerate() if t.name.startswith("Lightrag")]

    s = make_server()
    with mock.patch.object(ls.LightragServer, '_start_server_process', return_value=True), \
         mock.patch.object(ls.LightragServer, 'is_running', return_value=False):
        s.start()
    t1 = s._monitor_thread
    gen1 = s._current_thread_generation()
    check("monitor thread started", t1 is not None and t1.is_alive())
    check("generation bumped by start()", gen1 == 1, f"(gen={gen1})")

    # Race: stop() then immediate start() while t1 is mid-sleep.
    s.stop()
    check("stop() bumped generation", s._current_thread_generation() > gen1)
    with mock.patch.object(ls.LightragServer, '_start_server_process', return_value=True), \
         mock.patch.object(ls.LightragServer, 'is_running', return_value=False):
        s.start()
    t2 = s._monitor_thread
    check("second spawn is a distinct thread", t1 is not t2)

    t1.join(timeout=5.0)
    check("stale monitor thread exited despite _monitor_running=True",
          not t1.is_alive(), f"(alive={t1.is_alive()})")
    time.sleep(0.2)
    check("current monitor thread still alive", t2.is_alive())

    # Full teardown leaves no Lightrag threads behind.
    s.stop()
    deadline = time.time() + 5
    while time.time() < deadline and live_lightrag_threads():
        time.sleep(0.1)
    check("no leaked Lightrag threads after stop()",
          not live_lightrag_threads(),
          f"(live={[t.name for t in live_lightrag_threads()]})")


def main():
    print("=" * 60)
    print("SECOND-ROUND MEMORY-FIX VERIFICATION")
    print("=" * 60)
    test_handled_questions_cap()
    test_recent_human_replies_cap()
    test_pdd_echoes_cap()
    test_thread_generation()
    print("\n" + "=" * 60)
    if _failures:
        print(f"RESULT: {len(_failures)} FAILED -> {_failures}")
        return 1
    print("RESULT: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
