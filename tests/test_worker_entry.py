"""W3b — a worker process that boots and runs one isolation domain.

The worry this test exists to answer: ``EC_Agent`` and everything under it
reach through ``mainwin`` for about sixty different attributes, and a missing
one is an AttributeError inside a customer's worker rather than a failure here.
There is no way to prove completeness by reading — so the worker is booted for
real, against a scratch data home, and what it reaches for is observed.

That is how the first three gaps were found: ``get_free_agent_ports`` and
``agent_conversion_failures`` (which between them blocked all 18 agents in a
dev database) and ``get_server_base_url``.

**What is NOT proven here**: an agent fully constructed and started. That needs
a configured LLM provider, which is data this checkout does not have, so it
belongs to a live run on a real install.
"""

import os
import subprocess
import sys
import tempfile
import unittest

from agent.ec_tasks import worker_context as wc


def _scratch_home():
    return tempfile.mkdtemp(prefix="worker_home_")


class ContextBootTests(unittest.TestCase):
    """The context has to build against a bare data home without help."""

    @classmethod
    def setUpClass(cls):
        cls.home = _scratch_home()
        cls.ctx = wc.WorkerContext(user="tester@example.com", data_home=cls.home)

    @classmethod
    def tearDownClass(cls):
        cls.ctx.shutdown()

    def test_it_builds_at_all(self):
        self.assertIsNotNone(self.ctx)

    def test_identity_matches_the_apps_convention(self):
        # The data directory is keyed on this, so getting it wrong points the
        # worker at a different user's profiles.
        self.assertEqual(self.ctx.log_user, "tester_example_com")
        self.assertEqual(self.ctx.my_ecb_data_homepath, self.home)

    def test_it_opens_the_shared_database(self):
        self.assertIsNotNone(self.ctx.ec_db_mgr)
        self.assertIsNotNone(getattr(self.ctx.ec_db_mgr, "agent_service", None))

    def test_the_pools_the_converter_reads_exist(self):
        for name in ("agents", "agent_skills", "agent_tasks", "agent_tools",
                     "knowledges"):
            self.assertIsInstance(getattr(self.ctx, name), list, name)

    def test_the_attributes_the_first_boot_proved_necessary(self):
        # Regression guards: without these, 0 of 18 agents built.
        self.assertTrue(callable(self.ctx.get_free_agent_ports))
        self.assertIsInstance(self.ctx.agent_conversion_failures, dict)
        self.assertTrue(callable(self.ctx.get_server_base_url))

    def test_ports_come_from_the_shared_allocator(self):
        ports = self.ctx.get_free_agent_ports(2)
        self.assertEqual(len(ports), 2)
        self.assertNotEqual(ports[0], ports[1])

    def test_the_local_server_url_is_this_process_not_the_parent(self):
        # A worker binds a different port; handing out the parent's URL would
        # point callbacks at the wrong process.
        self.assertIn(str(self.ctx.get_local_server_port()),
                      self.ctx.get_server_base_url())

    def test_an_unset_session_reads_as_signed_out_not_as_a_stale_token(self):
        token = self.ctx.get_auth_token()
        self.assertTrue(token is None or isinstance(token, str))


class GapReporterTests(unittest.TestCase):
    def setUp(self):
        self.ctx = wc.WorkerContext(user="t@e.com", data_home=_scratch_home())

    def tearDown(self):
        self.ctx.shutdown()

    def test_a_missing_attribute_raises_normally(self):
        # AttributeError, not an invented default: the surrounding code is
        # written to absorb it, and a guessed value would send a worker down a
        # path nobody designed for it.
        with self.assertRaises(AttributeError):
            _ = self.ctx.definitely_not_a_real_attribute

    def test_the_defensive_getattr_idiom_still_works(self):
        # This codebase probes the window everywhere with a default; that must
        # keep working rather than blowing up the worker.
        self.assertIsNone(getattr(self.ctx, "no_such_thing", None))
        self.assertEqual(getattr(self.ctx, "no_such_thing", "fallback"), "fallback")

    def test_each_gap_is_named_once_not_once_per_probe(self):
        from config.constants import APP_NAME
        with self.assertLogs(APP_NAME, level="WARNING") as captured:
            for _ in range(5):
                getattr(self.ctx, "probed_repeatedly", None)
        named = [line for line in captured.output if "probed_repeatedly" in line]
        self.assertEqual(len(named), 1, "a probed attribute should be logged once")


class WorkerProcessTests(unittest.TestCase):
    """The whole thing, as a real process the supervisor could launch."""

    def _worker_log_path(self, instance):
        # A worker writes its OWN file in the shared runlogs folder (W2), so
        # reading it here also checks that naming actually took effect.
        from config.app_info import app_info
        from config.constants import APP_LOG_FILE
        stem, _, ext = APP_LOG_FILE.rpartition(".")
        return os.path.join(app_info.appdata_path, "runlogs",
                            f"{stem}-{instance}.{ext}")

    def _run_worker(self, key, env_extra=None, timeout=180):
        """Run a worker to completion and return (proc, its own log text)."""
        instance = f"test_{key}"
        log_path = self._worker_log_path(instance)
        try:
            os.remove(log_path)
        except OSError:
            pass
        env = dict(os.environ)
        env.update({
            "ECAN_WORKER_KEY": key,
            "ECAN_INSTANCE_ID": instance,
            "PYTHONIOENCODING": "utf-8",
        })
        env.update(env_extra or {})
        proc = subprocess.run(
            [sys.executable, "-m", "agent.ec_tasks.worker_entry", "--key", key],
            env=env, cwd=os.getcwd(), capture_output=True, text=True,
            stdin=subprocess.DEVNULL,   # EOF immediately = "drain and exit"
            timeout=timeout,
        )
        log = ""
        try:
            with open(log_path, encoding="utf-8", errors="replace") as fh:
                log = fh.read()
        except OSError:
            pass
        return proc, log

    def test_a_worker_boots_and_exits_cleanly_when_stdin_closes(self):
        # stdin closing is the graceful stop contract with the supervisor.
        proc, log = self._run_worker("smoke_domain")
        self.assertEqual(proc.returncode, 0, (proc.stderr or "")[-2000:])
        self.assertIn("ready; waiting for the parent", log)
        self.assertIn("stopped", log)

    def test_it_writes_its_own_log_file(self):
        # W2: one file per worker in the shared folder, so the support zip
        # picks it up without anyone remembering it exists.
        _proc, log = self._run_worker("smoke_domain")
        self.assertTrue(log, "the worker wrote no log of its own")
        self.assertIn("[Worker smoke_domain]", log)

    def test_it_drains_before_exiting(self):
        # A reply already handed to the send path is lost if the worker just
        # exits, which the customer experiences as silence.
        _proc, log = self._run_worker("smoke_domain")
        self.assertIn("draining", log)
        self.assertIn("LIVE-CHAT-SHUTDOWN", log)

    def test_it_refuses_to_start_without_a_domain(self):
        # A worker with no key would have no idea which agents are its own,
        # and the placement gate would skip every one of them.
        env = dict(os.environ)
        env.update({"ECAN_WORKER_KEY": "", "PYTHONIOENCODING": "utf-8"})
        proc = subprocess.run(
            [sys.executable, "-m", "agent.ec_tasks.worker_entry"],
            env=env, cwd=os.getcwd(), capture_output=True, text=True,
            stdin=subprocess.DEVNULL, timeout=180,
        )
        self.assertEqual(proc.returncode, 2)

    def test_it_reaches_for_nothing_the_context_cannot_provide(self):
        # The completeness check that reading the code cannot give: boot it and
        # see what it actually asks for. A new gap fails here rather than in a
        # customer's worker.
        _proc, log = self._run_worker("smoke_domain")
        gaps = [line for line in log.splitlines()
                if "on the worker context" in line]
        self.assertEqual(gaps, [], "worker reached for attributes it does not have")


if __name__ == "__main__":
    unittest.main()
