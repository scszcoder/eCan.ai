"""W3 — routing an agent to the right process.

The rule is symmetric, and the half that is easy to get wrong is the worker
side: in the parent, an agent with an isolation key is handed to a worker; in a
worker, an agent **without** one is skipped. Miss that second half and every
worker also runs the account's shared agents, so a customer with four stores
gets four copies of everything — which looks like it works right up until two
copies answer the same message.

The other property under test is that this is inert. Nothing declares an
isolation key today, so every agent must read as unisolated and start in the
parent exactly as before.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from agent.ec_tasks import worker_placement as wp
from agent.ec_tasks.worker_supervisor import ISOLATION_KEY_VAR
from config.constants import APP_NAME   # the app logger's name; "eCan.cn" in CN builds


def _task(key=None):
    class _T:
        pass
    t = _T()
    t.metadata = {"task_vars": ({ISOLATION_KEY_VAR: key} if key else {})}
    return t


def _agent(*keys, name="agent"):
    class _Card:
        pass
    card = _Card()
    card.name = name

    class _A:
        pass
    a = _A()
    a.card = card
    a.tasks = [_task(k) for k in keys]
    return a


class _AsWorker:
    """Run the block as the worker for ``key`` (or as the parent for None)."""

    def __init__(self, key):
        self.key = key

    def __enter__(self):
        self.saved = os.environ.pop(wp.WORKER_KEY_ENV, None)
        if self.key:
            os.environ[wp.WORKER_KEY_ENV] = self.key

    def __exit__(self, *exc):
        os.environ.pop(wp.WORKER_KEY_ENV, None)
        if self.saved is not None:
            os.environ[wp.WORKER_KEY_ENV] = self.saved
        return False


class ParentPlacementTests(unittest.TestCase):
    def test_an_unisolated_agent_runs_here(self):
        # Every agent that exists today. If this ever says anything else, the
        # change stopped being a no-op.
        with _AsWorker(None):
            self.assertEqual(wp.placement_for_agent(_agent(None)),
                             (wp.PLACE_HERE, ""))

    def test_an_agent_with_a_domain_is_delegated(self):
        with _AsWorker(None):
            self.assertEqual(wp.placement_for_agent(_agent("store_a")),
                             (wp.PLACE_DELEGATE, "store_a"))

    def test_an_agent_with_no_tasks_runs_here(self):
        with _AsWorker(None):
            self.assertEqual(wp.placement_for_agent(_agent()), (wp.PLACE_HERE, ""))


class WorkerPlacementTests(unittest.TestCase):
    def test_its_own_domain_runs_here(self):
        with _AsWorker("store_a"):
            self.assertEqual(wp.placement_for_agent(_agent("store_a")),
                             (wp.PLACE_HERE, "store_a"))

    def test_another_domain_is_skipped(self):
        with _AsWorker("store_a"):
            decision, _ = wp.placement_for_agent(_agent("store_b"))
            self.assertEqual(decision, wp.PLACE_SKIP)

    def test_unisolated_agents_are_NOT_run_by_a_worker(self):
        # The asymmetric half. Without it every worker also runs the account's
        # shared agents, so four stores means four copies of each -- and two
        # copies answering one message.
        with _AsWorker("store_a"):
            decision, _ = wp.placement_for_agent(_agent(None))
            self.assertEqual(decision, wp.PLACE_SKIP)


class MultiDomainAgentTests(unittest.TestCase):
    def test_tasks_spanning_two_domains_pick_one_and_complain(self):
        # An agent can only live in one process. Running it in the parent
        # instead would put it alongside everything, which is the sharing this
        # exists to prevent -- so it goes to one domain, loudly.
        agent = _agent("store_a", "store_b")
        with self.assertLogs(APP_NAME, level="ERROR") as captured:
            key = wp.agent_isolation_key(agent)
        self.assertEqual(key, "store_a")
        self.assertIn("isolation domains", "\n".join(captured.output))

    def test_a_front_desk_and_its_qa_share_one_domain_quietly(self):
        # The normal case: several tasks, one store.
        self.assertEqual(wp.agent_isolation_key(_agent("store_a", "store_a")),
                         "store_a")


class FailOpenTests(unittest.TestCase):
    """A placement failure must never stop an agent from starting."""

    def test_an_agent_shaped_unexpectedly_runs_here(self):
        with _AsWorker(None):
            self.assertEqual(wp.placement_for_agent(object()), (wp.PLACE_HERE, ""))
            self.assertEqual(wp.placement_for_agent(None), (wp.PLACE_HERE, ""))

    def test_a_raising_agent_runs_here(self):
        class _Boom:
            @property
            def tasks(self):
                raise RuntimeError("no")
        with _AsWorker(None):
            self.assertEqual(wp.placement_for_agent(_Boom()), (wp.PLACE_HERE, ""))


class SpawnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._p = patch.object(wp, "_worker_runner_dir", lambda: self.tmp)
        self._p.start()

    def tearDown(self):
        self._p.stop()

    def test_dev_launches_the_entry_module(self):
        spec = wp.default_spawner("store_a")
        self.assertEqual(spec.argv[0], sys.executable)
        self.assertIn("-m", spec.argv)
        self.assertIn("agent.ec_tasks.worker_entry", spec.argv)
        self.assertIn("store_a", spec.argv)

    def test_the_worker_is_told_its_key_and_its_instance(self):
        spec = wp.default_spawner("store_a")
        self.assertEqual(spec.env[wp.WORKER_KEY_ENV], "store_a")
        # The instance id is what separates the worker's log, IPC port and
        # single-instance lock while leaving the database shared.
        self.assertEqual(spec.env["ECAN_INSTANCE_ID"], "store_a")

    def test_child_output_goes_to_a_named_file(self):
        spec = wp.default_spawner("store_a")
        self.assertTrue(spec.log_path.endswith("worker-store_a.out.log"))

    def test_a_frozen_build_uses_the_run_script_mechanism(self):
        # sys.executable is the GUI exe in a packaged build, so "-m module"
        # would start a second copy of the app instead of a worker.
        with patch.object(sys, "frozen", True, create=True):
            spec = wp.default_spawner("store_a")
        self.assertEqual(spec.argv, [sys.executable])
        runner = spec.env.get("ECAN_RUN_SCRIPT")
        self.assertTrue(runner and os.path.exists(runner))
        with open(runner, encoding="utf-8") as fh:
            body = fh.read()
        self.assertIn("agent.ec_tasks.worker_entry", body)
        self.assertIn("'store_a'", body)

    def test_a_frozen_runner_survives_an_awkward_key(self):
        with patch.object(sys, "frozen", True, create=True):
            spec = wp.default_spawner("it's_a_store")
        with open(spec.env["ECAN_RUN_SCRIPT"], encoding="utf-8") as fh:
            body = fh.read()
        compile(body, "runner", "exec")   # must be valid Python, not a quoting bug


class DelegateTests(unittest.TestCase):
    def test_a_blank_key_delegates_nothing(self):
        self.assertFalse(wp.delegate_to_worker(""))

    def test_no_spawner_is_reported_not_swallowed(self):
        # Until a worker entry exists, delegation cannot succeed -- and an
        # agent that is neither started here nor started there is offline, so
        # this must be loud.
        from agent.ec_tasks import worker_supervisor as ws
        ws.set_supervisor(None)
        try:
            with self.assertLogs(APP_NAME, level="ERROR"):
                self.assertFalse(wp.delegate_to_worker("store_a"))
        finally:
            ws.set_supervisor(None)

    def test_delegation_starts_the_worker(self):
        from agent.ec_tasks import worker_supervisor as ws
        sup = ws.WorkerSupervisor(lambda key: ws.WorkerSpec(
            argv=[sys.executable, "-c", "import sys; sys.stdin.read()"]))
        ws.set_supervisor(sup)
        try:
            self.assertTrue(wp.delegate_to_worker("store_a"))
            self.assertIsNotNone(sup.worker_status("store_a"))
        finally:
            sup.stop_all(drain_timeout=3.0)
            ws.set_supervisor(None)


class AgentGateTests(unittest.TestCase):
    """The gate has to actually be in the launch path, beside the vehicle one."""

    def _src(self):
        from pathlib import Path
        return Path("agent/ec_agent.py").read_text(encoding="utf-8")

    def test_the_gate_is_wired_into_agent_start(self):
        src = self._src()
        self.assertIn("from agent.ec_tasks.worker_placement import", src)
        self.assertIn("placement_for_agent(self)", src)

    def test_the_gate_fails_open(self):
        # An exception here must not stop an agent starting; that would take a
        # store offline for a placement bug.
        src = self._src()
        self.assertIn("Worker placement gate error (fail-open)", src)

    def test_the_gate_runs_after_the_vehicle_gate(self):
        # Machine first, then process: no point placing an agent that does not
        # belong to this host at all.
        src = self._src()
        self.assertLess(src.index("Vehicle affinity gate error"),
                        src.index("Worker placement gate error"))

    def test_the_gate_runs_before_anything_is_started(self):
        src = self._src()
        self.assertLess(src.index("placement_for_agent(self)"),
                        src.index("# Start A2A server in daemon thread"))


if __name__ == "__main__":
    unittest.main()
