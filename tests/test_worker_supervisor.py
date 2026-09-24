"""W1 — the worker supervisor skeleton.

One app the operator launches; one child process per isolation domain, launched
by the app. These tests drive real subprocesses, because the whole value of the
design is what happens at a process boundary and a mocked Popen would prove
none of it.

Two properties matter most:

* **Nothing changes for anyone today.** A task with no isolation key runs
  in-process, which is every task that exists. If this regressed, the first
  symptom would be every install spawning processes it never asked for.
* **A broken worker stops being restarted.** Restarting forever turns a crash
  loop into a flapping process nobody notices, which is how "store 6 has been
  offline since Tuesday" happens.
"""

import os
import sys
import tempfile
import time
import unittest

from agent.ec_tasks.worker_supervisor import (
    WorkerSupervisor, WorkerSpec, isolation_key_for_task,
    supervisor, set_supervisor, ISOLATION_KEY_VAR,
)

# A child that stays up until its stdin closes — the graceful-stop contract.
_SLEEPER = (
    "import sys;"
    "sys.stdin.read();"          # blocks until the parent closes the pipe
    "sys.exit(0)"
)
# A child that refuses to die politely: ignores stdin closing.
_STUBBORN = (
    "import time;"
    "time.sleep(120)"
)
# A child that exits immediately — the crash-loop case.
_DIES = "import sys; sys.exit(3)"


def _spec(code, **env):
    return WorkerSpec(argv=[sys.executable, "-c", code], env=env)


def _spawner(code):
    return lambda key: _spec(code)


def _wait_until(pred, timeout=10.0, interval=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(interval)
    return False


def _drive_to_give_up(sup, key, rounds=40):
    """Tick a crash-looping worker until the supervisor gives up.

    Waits for each death first: ticking while the child is still alive is a
    no-op, so without this the loop can run out of rounds on timing alone.
    """
    for _ in range(rounds):
        worker = sup._workers[key]
        _wait_until(lambda: not worker.is_running(), timeout=5.0)
        worker._retry_not_before = 0.0   # skip the wall-clock backoff
        sup.tick()
        status = sup.worker_status(key)
        if status is not None and status.gave_up:
            return True
    return False


class _Task:
    def __init__(self, metadata=None):
        self.metadata = metadata


class IsolationKeyTests(unittest.TestCase):
    def test_reads_the_task_variable(self):
        t = _Task({"task_vars": {ISOLATION_KEY_VAR: "lands_flying_fish"}})
        self.assertEqual(isolation_key_for_task(t), "lands_flying_fish")

    def test_no_key_means_run_in_process(self):
        # This is every task that exists today. It must stay "" or the change
        # is not the no-op it claims to be.
        self.assertEqual(isolation_key_for_task(_Task({"task_vars": {}})), "")
        self.assertEqual(isolation_key_for_task(_Task({})), "")
        self.assertEqual(isolation_key_for_task(_Task(None)), "")
        self.assertEqual(isolation_key_for_task(_Task()), "")

    def test_blank_and_whitespace_are_not_a_domain(self):
        for raw in ("", "   ", None):
            t = _Task({"task_vars": {ISOLATION_KEY_VAR: raw}})
            self.assertEqual(isolation_key_for_task(t), "", repr(raw))

    def test_a_task_shaped_unexpectedly_does_not_raise(self):
        self.assertEqual(isolation_key_for_task(object()), "")
        self.assertEqual(isolation_key_for_task(None), "")
        self.assertEqual(isolation_key_for_task(_Task({"task_vars": "nope"})), "")


class NoRoutingByDefaultTests(unittest.TestCase):
    def test_a_blank_key_never_spawns(self):
        spawned = []

        def _boom(key):
            spawned.append(key)
            raise AssertionError("must not spawn for a blank key")

        sup = WorkerSupervisor(_boom)
        self.assertIsNone(sup.ensure_worker(""))
        self.assertIsNone(sup.ensure_worker("   "))
        self.assertIsNone(sup.ensure_worker(None))
        self.assertEqual(spawned, [])
        self.assertEqual(sup.status(), [])

    def test_the_default_supervisor_has_no_spawner(self):
        # Nothing routes work to a worker yet, so asking for one must fail
        # loudly rather than launch something half-configured.
        set_supervisor(None)
        try:
            self.assertIsNone(supervisor().ensure_worker("store_a"))
        finally:
            set_supervisor(None)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.sup = None

    def tearDown(self):
        if self.sup is not None:
            self.sup.stop_all(drain_timeout=3.0)

    def test_starts_one_process_per_key(self):
        self.sup = WorkerSupervisor(_spawner(_SLEEPER))
        a = self.sup.ensure_worker("store_a")
        b = self.sup.ensure_worker("store_b")
        self.assertTrue(a.running and b.running)
        self.assertNotEqual(a.pid, b.pid)
        self.assertEqual(len(self.sup.status()), 2)

    def test_ensure_is_idempotent(self):
        self.sup = WorkerSupervisor(_spawner(_SLEEPER))
        first = self.sup.ensure_worker("store_a")
        second = self.sup.ensure_worker("store_a")
        self.assertEqual(first.pid, second.pid)
        self.assertEqual(len(self.sup.status()), 1)

    def test_stop_closes_stdin_and_the_child_exits(self):
        # The graceful contract: closing stdin means "no more work, drain".
        self.sup = WorkerSupervisor(_spawner(_SLEEPER))
        st = self.sup.ensure_worker("store_a")
        self.assertTrue(st.running)
        self.sup.stop_worker("store_a", drain_timeout=10.0)
        self.assertIsNone(self.sup.worker_status("store_a"))

    def test_a_child_that_ignores_the_drain_is_terminated(self):
        # Escalation matters: one stubborn worker must not hold the app open.
        self.sup = WorkerSupervisor(_spawner(_STUBBORN))
        self.sup.ensure_worker("store_a")
        t0 = time.time()
        self.sup.stop_worker("store_a", drain_timeout=1.0)
        self.assertLess(time.time() - t0, 20.0)

    def test_stop_all_drains_every_worker(self):
        self.sup = WorkerSupervisor(_spawner(_SLEEPER))
        for key in ("store_a", "store_b", "store_c"):
            self.sup.ensure_worker(key)
        self.sup.stop_all(drain_timeout=10.0)
        self.assertEqual(self.sup.status(), [])

    def test_stop_all_drains_in_parallel_not_in_series(self):
        # Three stubborn workers at a 2s drain each: serial would be 6s+, and
        # eight at 20s would be a three-minute quit the operator resolves with
        # Task Manager -- losing the replies the drain exists to save.
        self.sup = WorkerSupervisor(_spawner(_STUBBORN))
        for key in ("a", "b", "c"):
            self.sup.ensure_worker(key)
        t0 = time.time()
        self.sup.stop_all(drain_timeout=2.0)
        self.assertLess(time.time() - t0, 5.5)

    def test_env_reaches_the_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = os.path.join(tmp, "seen.txt")
            code = (
                "import os;"
                f"open(r'{marker}','w').write(os.environ.get('ECAN_WORKER_KEY',''))"
            )
            self.sup = WorkerSupervisor(
                lambda key: _spec(code, ECAN_WORKER_KEY=key)
            )
            self.sup.ensure_worker("store_a")
            self.assertTrue(_wait_until(lambda: os.path.exists(marker)))
            time.sleep(0.2)
            with open(marker, encoding="utf-8") as fh:
                self.assertEqual(fh.read().strip(), "store_a")


class WindowsHandleTests(unittest.TestCase):
    """Regression: the spawn must not inherit std handles.

    Redirecting any one of the three standard handles on Windows makes
    CreateProcess use STARTF_USESTDHANDLES, and then all three must be valid.
    Inheriting stdout/stderr from a parent that has none -- a packaged GUI app
    with no console, or this test runner under fd capture -- fails the spawn
    with "[WinError 6] The handle is invalid". Caught here first; it would have
    hit the packaged app identically.
    """

    def test_several_workers_spawn_under_captured_std_handles(self):
        sup = WorkerSupervisor(_spawner(_SLEEPER))
        try:
            statuses = [sup.ensure_worker(k) for k in ("a", "b", "c", "d")]
            for st in statuses:
                self.assertTrue(st.running, f"{st.key} failed to spawn: {st.detail}")
            self.assertEqual(len({st.pid for st in statuses}), 4)
        finally:
            sup.stop_all(drain_timeout=5.0)

    def test_child_output_is_captured_when_a_log_path_is_given(self):
        # A worker that dies before its own logging is up leaves its traceback
        # nowhere else, and that is exactly the crash the supervisor must be
        # able to explain.
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "worker.log")
            sup = WorkerSupervisor(lambda key: WorkerSpec(
                argv=[sys.executable, "-c",
                      "import sys; sys.stderr.write('boom-traceback'); sys.exit(1)"],
                log_path=log,
            ))
            try:
                sup.ensure_worker("store_a")
                self.assertTrue(_wait_until(
                    lambda: os.path.exists(log) and os.path.getsize(log) > 0))
                with open(log, encoding="utf-8", errors="replace") as fh:
                    self.assertIn("boom-traceback", fh.read())
            finally:
                sup.stop_all(drain_timeout=3.0)


class RestartTests(unittest.TestCase):
    def setUp(self):
        self.sup = None

    def tearDown(self):
        if self.sup is not None:
            self.sup.stop_all(drain_timeout=2.0)

    def test_a_dead_worker_is_noticed_and_restarted(self):
        self.sup = WorkerSupervisor(_spawner(_DIES))
        self.sup.ensure_worker("store_a")
        self.assertTrue(_wait_until(
            lambda: not self.sup.worker_status("store_a").running))
        self.sup.tick()
        st = self.sup.worker_status("store_a")
        self.assertEqual(st.restarts, 1)
        self.assertEqual(st.last_exit_code, 3)

    def test_one_death_is_counted_once_however_often_tick_runs(self):
        # tick() runs on an interval; counting the same death each pass would
        # inflate the backoff and reach "give up" for a single crash.
        self.sup = WorkerSupervisor(_spawner(_DIES))
        self.sup.ensure_worker("store_a")
        self.assertTrue(_wait_until(
            lambda: not self.sup.worker_status("store_a").running))
        for _ in range(5):
            self.sup.tick()
        self.assertEqual(self.sup.worker_status("store_a").restarts, 1)

    def test_backoff_delays_the_retry(self):
        self.sup = WorkerSupervisor(_spawner(_DIES))
        self.sup.ensure_worker("store_a")
        self.assertTrue(_wait_until(
            lambda: not self.sup.worker_status("store_a").running))
        self.sup.tick()
        # Base backoff is 1s, so an immediate second tick must not restart.
        self.sup.tick()
        self.assertEqual(self.sup.worker_status("store_a").restarts, 1)

    def test_a_crash_loop_is_eventually_given_up_on(self):
        # Restarting forever hides a broken worker behind a flapping process.
        self.sup = WorkerSupervisor(_spawner(_DIES))
        self.sup.ensure_worker("store_a")
        _drive_to_give_up(self.sup, "store_a")
        st = self.sup.worker_status("store_a")
        self.assertTrue(st.gave_up, "supervisor never gave up on a crash loop")
        self.assertIn("failed", st.detail)

    def test_giving_up_stops_further_restarts(self):
        self.sup = WorkerSupervisor(_spawner(_DIES))
        self.sup.ensure_worker("store_a")
        self.assertTrue(_drive_to_give_up(self.sup, "store_a"))
        settled = self.sup.worker_status("store_a").restarts
        for _ in range(3):
            self.sup.tick()
        self.assertEqual(self.sup.worker_status("store_a").restarts, settled)

    def test_an_explicit_ask_clears_the_give_up_latch(self):
        # "Give up" means the supervisor stops retrying on its own, not that
        # the domain is dead forever -- an operator or a retry can ask again.
        self.sup = WorkerSupervisor(_spawner(_DIES))
        self.sup.ensure_worker("store_a")
        self.assertTrue(_drive_to_give_up(self.sup, "store_a"))
        self.sup.ensure_worker("store_a")
        self.assertFalse(self.sup.worker_status("store_a").gave_up)

    def test_a_spawn_failure_counts_toward_giving_up(self):
        # A command that cannot start is as broken as one that crashes, and
        # must not be retried in a tight loop forever.
        self.sup = WorkerSupervisor(
            lambda key: WorkerSpec(argv=["this_binary_does_not_exist_ecan"])
        )
        self.sup.ensure_worker("store_a")
        w = self.sup._workers["store_a"]
        w.started_at = time.time()   # it "attempted" a start
        for _ in range(40):
            w._retry_not_before = 0.0
            self.sup.tick()
            if w.gave_up:
                break
        self.assertTrue(w.gave_up)

    def test_a_stopping_worker_is_not_restarted(self):
        # stop_worker removes it, but the race matters: a tick landing during
        # shutdown must not resurrect what the app is trying to close.
        self.sup = WorkerSupervisor(_spawner(_SLEEPER))
        self.sup.ensure_worker("store_a")
        w = self.sup._workers["store_a"]
        w.stop(drain_timeout=5.0)
        self.sup.tick()
        self.assertFalse(w.is_running())

    def test_a_running_worker_is_left_alone(self):
        self.sup = WorkerSupervisor(_spawner(_SLEEPER))
        st = self.sup.ensure_worker("store_a")
        for _ in range(3):
            self.sup.tick()
        self.assertEqual(self.sup.worker_status("store_a").pid, st.pid)
        self.assertEqual(self.sup.worker_status("store_a").restarts, 0)


class ReconcileTests(unittest.TestCase):
    """How the supervisor learns how many domains exist: it is told.

    Deriving the set here would mean re-implementing "which tasks run on this
    machine" (task rows + agent enablement + vehicle affinity), which already
    lives in the launch path. Two implementations of that would drift, and the
    drift would show up as a store with no worker, silently.
    """

    def setUp(self):
        self.sup = WorkerSupervisor(_spawner(_SLEEPER))

    def tearDown(self):
        self.sup.stop_all(drain_timeout=3.0)

    def test_starts_what_is_missing(self):
        out = self.sup.reconcile(["store_a", "store_b"])
        self.assertEqual(sorted(out["started"]), ["store_a", "store_b"])
        self.assertEqual(len(self.sup.status()), 2)

    def test_stops_a_domain_that_went_away(self):
        # Its tasks were deleted, disabled, or moved to another machine. Left
        # running it holds a browser, a seller session and ~1GB of RSS for
        # work that no longer exists.
        self.sup.reconcile(["store_a", "store_b"])
        out = self.sup.reconcile(["store_a"], drain_timeout=5.0)
        self.assertEqual(out["stopped"], ["store_b"])
        self.assertIsNone(self.sup.worker_status("store_b"))
        self.assertIsNotNone(self.sup.worker_status("store_a"))

    def test_is_idempotent(self):
        first = self.sup.reconcile(["store_a"])
        pid = self.sup.worker_status("store_a").pid
        second = self.sup.reconcile(["store_a"])
        self.assertEqual(second, {"started": [], "stopped": []})
        self.assertEqual(self.sup.worker_status("store_a").pid, pid)
        self.assertEqual(first["started"], ["store_a"])

    def test_an_empty_desired_set_drains_everything(self):
        self.sup.reconcile(["store_a", "store_b"])
        out = self.sup.reconcile([], drain_timeout=5.0)
        self.assertEqual(sorted(out["stopped"]), ["store_a", "store_b"])
        self.assertEqual(self.sup.status(), [])

    def test_blank_keys_are_ignored_not_spawned(self):
        out = self.sup.reconcile(["", "   ", None, "store_a"])
        self.assertEqual(out["started"], ["store_a"])
        self.assertEqual(len(self.sup.status()), 1)


class IsolationKeysForTasksTests(unittest.TestCase):
    def test_collects_distinct_keys_in_order(self):
        from agent.ec_tasks.worker_supervisor import isolation_keys_for_tasks
        tasks = [
            _Task({"task_vars": {ISOLATION_KEY_VAR: "b"}}),
            _Task({"task_vars": {ISOLATION_KEY_VAR: "a"}}),
            _Task({"task_vars": {ISOLATION_KEY_VAR: "b"}}),   # front desk + its Q&A
            _Task({"task_vars": {}}),                          # not isolated
        ]
        self.assertEqual(isolation_keys_for_tasks(tasks), ["b", "a"])

    def test_reads_a_database_row_shape_too(self):
        # Runtime tasks carry task_vars under metadata; DB rows under settings.
        from agent.ec_tasks.worker_supervisor import isolation_keys_for_tasks
        rows = [{"settings": {"task_vars": {ISOLATION_KEY_VAR: "store_a"}}}]
        self.assertEqual(isolation_keys_for_tasks(rows), ["store_a"])

    def test_empty_and_malformed_input(self):
        from agent.ec_tasks.worker_supervisor import isolation_keys_for_tasks
        self.assertEqual(isolation_keys_for_tasks([]), [])
        self.assertEqual(isolation_keys_for_tasks(None), [])
        self.assertEqual(isolation_keys_for_tasks([None, object(), {}]), [])


class StatusTests(unittest.TestCase):
    def test_status_is_serializable_for_the_ui(self):
        sup = WorkerSupervisor(_spawner(_SLEEPER))
        try:
            sup.ensure_worker("store_a")
            rows = sup.status()
            self.assertEqual(len(rows), 1)
            row = rows[0]
            for field in ("key", "pid", "running", "restarts", "gave_up", "detail"):
                self.assertIn(field, row)
            import json
            json.dumps(rows)   # must survive the IPC boundary
        finally:
            sup.stop_all(drain_timeout=3.0)

    def test_unknown_key_has_no_status(self):
        sup = WorkerSupervisor(_spawner(_SLEEPER))
        self.assertIsNone(sup.worker_status("never_started"))


if __name__ == "__main__":
    unittest.main()
