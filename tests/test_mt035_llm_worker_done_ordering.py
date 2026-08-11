"""mt035 — the LLM async worker must signal completion to the caller
BEFORE attempting event-loop teardown.

Background
----------
Customer 2026-05-24 09:25:50 packet 130cm trace:
  - ``ainvoke`` succeeded in 18.5s with a valid send_chat reply
    (chatcmpl-c32b6499 "亲，按身高选对应尺码就可以...")
  - ``finally`` ran cleanup (asyncio.gather pending + shutdown_asyncgens +
    shutdown_default_executor)
  - cleanup hung for 32 seconds on a saturated httpx pool
  - outer 45 s wall-clock fired → result discarded
  - retry took another 4.6s; total customer-visible latency = 56s

Before mt035 the worker called ``done.set()`` at the END of finally
(after teardown).  When teardown hung, the caller never observed
completion and treated the call as a timeout, discarding a perfectly
good response.

Fix: ``done.set()`` is now the first statement in the outer finally —
fires the instant ainvoke returns (or raises).  Teardown still runs,
but its completion is no longer a correctness condition.

These tests are source-level guards.  Behavioural tests against the
real worker would need to mock ainvoke + simulate a hung shutdown,
which couples to httpx/openai internals; we already have the
production trace as the behavioural evidence.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path


SRC = Path("agent/ec_skills/build_node.py").read_text(encoding="utf-8")


class WorkerDoneOrderingTests(unittest.TestCase):
    """The ``_worker`` closure in ``_invoke_async_with_thread_timeout``
    must call ``done.set()`` BEFORE the asyncio teardown block."""

    def test_mt035_marker_present(self) -> None:
        self.assertIn("2026-05-24 mt035", SRC)

    def test_worker_function_exists(self) -> None:
        self.assertIn("def _worker():", SRC)
        # Specifically the variant inside _invoke_async_with_thread_timeout
        self.assertIn("_invoke_async_with_thread_timeout", SRC)

    def test_done_set_fires_before_pending_task_cleanup(self) -> None:
        """The whole point of mt035: ``done.set()`` is on top of the
        outer ``finally`` block, immediately followed by best-effort
        teardown.  The OLD ordering put ``done.set()`` at the bottom
        of teardown — a hung ``shutdown_default_executor`` blocked it
        and the caller never observed completion.
        """
        # Locate the _worker closure body
        worker_idx = SRC.find("def _worker():")
        self.assertGreater(worker_idx, -1)

        # Slice out the worker function (next 80 lines should cover it)
        worker_block = SRC[worker_idx : worker_idx + 4000]

        # The outer finally must call done.set() BEFORE the cleanup
        # asyncio.gather call.  We assert ordering by finding both
        # markers and checking their positions.
        done_set_idx = worker_block.find("done.set()")
        gather_idx = worker_block.find("asyncio.gather(*pending")
        self.assertGreater(done_set_idx, -1, "done.set() must exist in _worker")
        self.assertGreater(gather_idx, -1, "asyncio.gather pending must exist")
        self.assertLess(
            done_set_idx,
            gather_idx,
            "done.set() must appear BEFORE asyncio.gather(*pending) — "
            "if cleanup hangs, the caller still gets the result. "
            "mt035 regression: ordering reverted to pre-mt035.",
        )

        # Same ordering vs the ACTUAL shutdown_default_executor CALL
        # (not the mt035 explainer comment that references the same name).
        shutdown_call_idx = worker_block.find(
            "loop.run_until_complete(loop.shutdown_default_executor())"
        )
        if shutdown_call_idx > 0:
            self.assertLess(
                done_set_idx,
                shutdown_call_idx,
                "done.set() must appear BEFORE the shutdown_default_executor "
                "call — that call is the primary teardown hang in the "
                "customer's trace.",
            )

        # Same ordering vs loop.close
        close_idx = worker_block.find("loop.close()")
        self.assertGreater(close_idx, -1)
        self.assertLess(
            done_set_idx,
            close_idx,
            "done.set() must appear BEFORE loop.close()",
        )

    def test_inner_try_isolates_result_capture(self) -> None:
        """The result/error capture is in its own try/except so the
        outer finally (where done.set() lives) is reached regardless of
        what happens inside ainvoke."""
        worker_idx = SRC.find("def _worker():")
        worker_block = SRC[worker_idx : worker_idx + 4000]

        # The new layout has a nested try (inner = capture, outer =
        # done.set() + teardown).
        try_count = worker_block.count("try:")
        self.assertGreaterEqual(
            try_count,
            2,
            "_worker must use nested try blocks (inner for ainvoke + result "
            "capture, outer with finally for done.set + cleanup) so "
            "done.set() fires even if the inner block raises.",
        )


class HeartbeatTimeoutContractTests(unittest.TestCase):
    """The caller's wait loop must remain unchanged — it still uses
    ``done.wait(timeout=...)`` with periodic heartbeats up to
    ``timeout_sec + 5.0`` seconds, and raises ``TimeoutError`` only
    when ``done.is_set()`` is False at the end.  mt035 doesn't change
    this — it just makes ``done.set()`` reliable."""

    def test_wait_limit_is_timeout_plus_five(self) -> None:
        self.assertIn("wait_limit = max(1.0, timeout_sec + 5.0)", SRC)

    def test_heartbeat_every_15s(self) -> None:
        self.assertIn("heartbeat_step = 15.0", SRC)

    def test_timeout_raised_only_when_done_not_set(self) -> None:
        self.assertIn("if not done.is_set():", SRC)
        # The error message format is what we grep production logs for
        self.assertIn("LLM async worker timed out", SRC)


class TeardownIsBestEffortTests(unittest.TestCase):
    """mt035 explicitly accepts that the teardown may now run AFTER
    the caller has moved on.  The worker thread is daemon=True so
    leaks are bounded by process lifetime.  The teardown block still
    wraps every call in try/except Exception: pass so it never raises
    out of the worker."""

    def test_worker_thread_is_daemon(self) -> None:
        self.assertIn("daemon=True,", SRC)

    def test_teardown_blocks_swallow_exceptions(self) -> None:
        worker_idx = SRC.find("def _worker():")
        worker_block = SRC[worker_idx : worker_idx + 4000]
        # The teardown try block must end with "except Exception: pass"
        self.assertIn("except Exception:\n", worker_block)


if __name__ == "__main__":
    unittest.main()
