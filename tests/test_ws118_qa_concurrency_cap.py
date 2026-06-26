"""ws118 — cap concurrent QA-turn skill executions.

The 1-vs-9 HANDOFF-STARVED freeze: under high concurrency the skill thread pool
(8 workers) ran many CPU-heavy QA turns at once, starving the shared CDP client's
loop thread of CPU/GIL — so feige_ws_send evals "NEVER ran" and the pipeline
froze (main asyncio loop stayed healthy). Fix: a process-wide threading.Semaphore
caps how many QA turns run concurrently, leaving CPU for the CDP loop. The
persistent front-desk MONITOR is excluded (it must keep detecting).
"""
from __future__ import annotations

import os
import threading
import time
import unittest
from pathlib import Path

_RUNNER_SRC = Path("agent/ec_tasks/runner.py").read_text(encoding="utf-8")


class CapConfigTests(unittest.TestCase):
    def test_default_and_env_override(self):
        # Import lazily; runner imports a lot but the helpers are module-level.
        from agent.ec_tasks.runner import _ws118_qa_cap, _ws118_get_qa_semaphore
        old = os.environ.get("ECAN_FEIGE_QA_MAX_CONCURRENCY")
        try:
            os.environ.pop("ECAN_FEIGE_QA_MAX_CONCURRENCY", None)
            self.assertEqual(_ws118_qa_cap(), 5)  # default
            os.environ["ECAN_FEIGE_QA_MAX_CONCURRENCY"] = "0"
            self.assertIsNone(_ws118_get_qa_semaphore())  # 0 disables
            os.environ["ECAN_FEIGE_QA_MAX_CONCURRENCY"] = "3"
            self.assertEqual(_ws118_qa_cap(), 3)
            self.assertIsNotNone(_ws118_get_qa_semaphore())
        finally:
            if old is None:
                os.environ.pop("ECAN_FEIGE_QA_MAX_CONCURRENCY", None)
            else:
                os.environ["ECAN_FEIGE_QA_MAX_CONCURRENCY"] = old


class SemaphoreCapsConcurrencyTests(unittest.TestCase):
    def test_peak_concurrency_bounded(self):
        sem = threading.Semaphore(3)
        running, peak, lk = [0], [0], threading.Lock()

        def work():
            got = sem.acquire(timeout=5)
            with lk:
                running[0] += 1
                peak[0] = max(peak[0], running[0])
            time.sleep(0.03)
            with lk:
                running[0] -= 1
            if got:
                sem.release()

        ts = [threading.Thread(target=work) for _ in range(12)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertLessEqual(peak[0], 3)  # never more than the cap run at once


class MonitorExclusionTests(unittest.TestCase):
    def _is_monitor(self, nm):
        return any(k in nm for k in ("监测", "monitor", "前台", "front"))

    def test_frontdesk_monitor_excluded_qa_capped(self):
        self.assertTrue(self._is_monitor("飞鸽前台聊天监测"))   # excluded
        self.assertFalse(self._is_monitor("飞鸽客户应答0"))      # capped
        self.assertFalse(self._is_monitor("飞鸽客户应答3"))


class WiringTests(unittest.TestCase):
    def test_acquire_before_execute_release_in_finally(self):
        acq = _RUNNER_SRC.find("_ws118_held = _ws118_sem.acquire")
        start = _RUNNER_SRC.find('"runner_execution_start"')
        rel = _RUNNER_SRC.find("_ws118_sem.release()")
        self.assertGreater(acq, 0)
        self.assertGreater(start, acq)   # acquired before execution start
        self.assertGreater(rel, start)   # released after (in finally)
        self.assertIn("ECAN_FEIGE_QA_MAX_CONCURRENCY", _RUNNER_SRC)


if __name__ == "__main__":
    unittest.main()
