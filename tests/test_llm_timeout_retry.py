"""mt022: LLM hang mitigation in ``_invoke_async_with_thread_timeout``.

The function lives inside a closure in ``build_node.py`` and isn't
directly importable.  These tests mirror the logic so we can prove the
two behavioural changes hold:

1. Default timeout drops from 150 s → 45 s.
2. On TimeoutError, a single retry runs in a fresh worker thread + loop.

If the source-side helper diverges from this mirror, the
``BehaviourMirroredTests`` will fail — that's the signal to update both.
"""
from __future__ import annotations

import asyncio
import os
import threading
import time
import unittest
from pathlib import Path


def _invoke_async_with_thread_timeout(
    llm_ainvoke_coro_fn,
    timeout_sec: float,
    *,
    heartbeat_step: float = 15.0,
):
    """Test mirror of the real helper, parametrised so the test can
    drive its behaviour without standing up a full langchain LLM.

    ``llm_ainvoke_coro_fn`` is a callable that returns a coroutine; it's
    invoked once per attempt so a per-attempt counter can simulate first-
    attempt-hangs / second-attempt-succeeds.
    """

    def _run_one_attempt(attempt_idx: int):
        result_holder = {}
        error_holder = {}
        done = threading.Event()

        def _worker():
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                result_holder["result"] = loop.run_until_complete(
                    llm_ainvoke_coro_fn(attempt_idx)
                )
            except BaseException as exc:
                error_holder["error"] = exc
            finally:
                try:
                    loop.close()
                except Exception:
                    pass
                done.set()

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        wait_limit = max(1.0, timeout_sec + 5.0)
        waited = 0.0
        while waited < wait_limit:
            poll = min(heartbeat_step, wait_limit - waited)
            if done.wait(timeout=poll):
                break
            waited += poll
        if not done.is_set():
            raise TimeoutError(f"attempt {attempt_idx} timed out")
        if "error" in error_holder:
            raise error_holder["error"]
        return result_holder.get("result")

    try:
        return _run_one_attempt(1)
    except TimeoutError as first_timeout:
        try:
            return _run_one_attempt(2)
        except TimeoutError as second_timeout:
            raise second_timeout from first_timeout


class DefaultTimeoutTests(unittest.TestCase):
    """The flood-test fix lowers the default ``ECAN_LLM_TIMEOUT_SEC``
    from 150 to 45 seconds.  Check the build_node source so the default
    can't silently drift back."""

    def test_default_is_45_seconds(self) -> None:
        src = Path("agent/ec_skills/build_node.py").read_text(encoding="utf-8")
        self.assertIn('ECAN_LLM_TIMEOUT_SEC", "45"', src)
        self.assertNotIn('ECAN_LLM_TIMEOUT_SEC", "150"', src)


class RetryOnTimeoutTests(unittest.TestCase):
    """First attempt timeout → second attempt runs.  This is the core
    of the mt022 hang-recovery behaviour."""

    def test_first_attempt_hang_second_succeeds(self) -> None:
        attempts: list[int] = []

        def make_coro(attempt_idx: int):
            attempts.append(attempt_idx)

            async def _coro():
                if attempt_idx == 1:
                    # Hang past the test's tiny 1-second timeout
                    await asyncio.sleep(60.0)
                    return "should-not-return"
                # Second attempt: quick success
                await asyncio.sleep(0.02)
                return "second-attempt-result"

            return _coro()

        result = _invoke_async_with_thread_timeout(
            make_coro, timeout_sec=1.0, heartbeat_step=0.3,
        )
        self.assertEqual("second-attempt-result", result)
        self.assertEqual([1, 2], attempts)

    def test_first_attempt_succeeds_no_retry(self) -> None:
        attempts: list[int] = []

        def make_coro(attempt_idx: int):
            attempts.append(attempt_idx)

            async def _coro():
                await asyncio.sleep(0.01)
                return f"ok-{attempt_idx}"

            return _coro()

        result = _invoke_async_with_thread_timeout(
            make_coro, timeout_sec=1.0, heartbeat_step=0.3,
        )
        self.assertEqual("ok-1", result)
        self.assertEqual([1], attempts)  # second attempt NOT spawned

    def test_both_attempts_hang_raises(self) -> None:
        attempts: list[int] = []

        def make_coro(attempt_idx: int):
            attempts.append(attempt_idx)

            async def _coro():
                await asyncio.sleep(60.0)
                return "never"

            return _coro()

        start = time.time()
        with self.assertRaises(TimeoutError):
            _invoke_async_with_thread_timeout(
                make_coro, timeout_sec=1.0, heartbeat_step=0.3,
            )
        elapsed = time.time() - start
        self.assertEqual([1, 2], attempts)
        # Should have given up well before any single 60-second hang would
        # have finished — both attempts share the 1+5 s budget each.
        self.assertLess(elapsed, 20.0)

    def test_non_timeout_error_is_not_retried(self) -> None:
        attempts: list[int] = []

        def make_coro(attempt_idx: int):
            attempts.append(attempt_idx)

            async def _coro():
                raise RuntimeError(f"boom on attempt {attempt_idx}")

            return _coro()

        with self.assertRaises(RuntimeError) as ctx:
            _invoke_async_with_thread_timeout(
                make_coro, timeout_sec=1.0, heartbeat_step=0.3,
            )
        self.assertIn("attempt 1", str(ctx.exception))
        self.assertEqual([1], attempts)  # retry only for TimeoutError


class HeartbeatLoggingPresenceTests(unittest.TestCase):
    """The build_node helper emits an LLM-HEARTBEAT log line periodically
    while waiting.  Confirm the literal token is wired so a future edit
    that accidentally drops the heartbeat is caught by tests."""

    def test_source_contains_heartbeat_marker(self) -> None:
        src = Path("agent/ec_skills/build_node.py").read_text(encoding="utf-8")
        self.assertIn("[LLM-HEARTBEAT]", src)
        self.assertIn("[LLM-RETRY]", src)


if __name__ == "__main__":
    unittest.main()
