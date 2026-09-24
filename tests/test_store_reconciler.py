"""Store reconciler: each heartbeat, running store agents are made to match placement."""

import unittest
from types import SimpleNamespace
from unittest import mock

from agent.ec_agents import store_reconciler as rc
from agent.ec_agents.store_placement import RUN, SKIP


class FakeAgent:
    def __init__(self, name, store="shop", running=False, **extra):
        self.card = SimpleNamespace(name=name)
        self.tasks = [SimpleNamespace(metadata={"task_vars": {"store_id": store} if store else {}})]
        self._running = running
        self.calls = []
        self.__dict__.update(extra)

    def start(self):
        self.calls.append("start")
        self._running = True

    def stop(self, reason=""):
        self.calls.append("stop")
        self._running = False
        self._stopped = True


def _run(agents, verdicts, isolated=(), process_keys=None, calls=None):
    """process_keys: agent name -> store-process key (its own process); default none."""
    mw = SimpleNamespace(agents=agents)
    keys = process_keys or {}

    def recon(ks):
        if calls is not None:
            calls.append(("reconcile", sorted(ks)))
        return {"started": [], "stopped": []}
    with mock.patch("agent.ec_agents.store_placement.refresh"), \
         mock.patch("agent.ec_agents.store_placement.placement_for_agent",
                    side_effect=lambda a: (verdicts[a.card.name], "test")), \
         mock.patch.object(rc, "_is_isolated", side_effect=lambda a: a.card.name in isolated), \
         mock.patch.object(rc, "_store_process_key", side_effect=lambda a: keys.get(a.card.name, "")), \
         mock.patch.object(rc, "_reconcile_store_processes", side_effect=recon):
        return rc.reconcile(mw)


class ReconcileTests(unittest.TestCase):
    def test_assigned_away_stops_and_assigned_here_starts(self):
        away, here = FakeAgent("away", running=True), FakeAgent("here", running=False)
        done = _run([away, here], {"away": SKIP, "here": RUN})
        self.assertEqual((away.calls, here.calls), (["stop"], ["start"]))
        self.assertEqual((done["started"], done["stopped"]), (["here"], ["away"]))

    def test_a_settled_machine_does_nothing(self):
        a, b = FakeAgent("a", running=True), FakeAgent("b", running=False)
        done = _run([a, b], {"a": RUN, "b": SKIP})
        self.assertEqual((done["started"], done["stopped"]), ([], []))
        self.assertEqual((a.calls, b.calls), ([], []))

    def test_agents_without_a_store_are_not_touched(self):
        plain = FakeAgent("plain", store=None, running=True)
        _run([plain], {"plain": SKIP})
        self.assertEqual(plain.calls, [])

    def test_disabled_and_isolated_agents_are_left_alone(self):
        off = FakeAgent("off", status="disabled")
        iso = FakeAgent("iso")
        _run([off, iso], {"off": RUN, "iso": RUN}, isolated={"iso"})
        self.assertEqual((off.calls, iso.calls), ([], []))

    def test_an_agent_stopped_in_this_process_is_not_revived(self):
        # Its tasks stay cancelled; a half-revived agent is worse than a warning.
        back = FakeAgent("back", _stopped=True)
        _run([back], {"back": RUN})
        _run([back], {"back": RUN})
        self.assertEqual(back.calls, [])
        self.assertTrue(back._restart_warned)

    def test_a_failing_start_is_not_retried_every_heartbeat(self):
        bad = FakeAgent("bad")
        bad.start = mock.Mock(side_effect=RuntimeError("boom"))
        _run([bad], {"bad": RUN})
        _run([bad], {"bad": RUN})
        self.assertEqual(bad.start.call_count, 1)

    def test_one_bad_agent_does_not_stop_the_pass(self):
        broken = FakeAgent("broken", running=True)
        broken.stop = mock.Mock(side_effect=RuntimeError("boom"))
        fine = FakeAgent("fine")
        done = _run([broken, fine], {"broken": SKIP, "fine": RUN})
        self.assertEqual(done["started"], ["fine"])


class StoreProcessTests(unittest.TestCase):
    """The three phases: a store is never live in two places at once."""

    def _ordered(self, agents):
        calls = []
        for a in agents:
            a.start = (lambda a=a: (calls.append(("start", a.card.name)), setattr(a, "_running", True)))
            a.stop = (lambda reason="", a=a: (calls.append(("stop", a.card.name)), setattr(a, "_running", False)))
        return calls

    def test_moving_into_its_own_process_stops_here_before_the_process_starts(self):
        a = FakeAgent("shop_a", running=True)
        calls = self._ordered([a])
        _run([a], {"shop_a": RUN}, process_keys={"shop_a": "douyin-a"}, calls=calls)
        self.assertEqual(calls, [("stop", "shop_a"), ("reconcile", ["douyin-a"])])

    def test_moving_back_drains_the_process_before_starting_here(self):
        a = FakeAgent("shop_a", running=False)
        calls = self._ordered([a])
        _run([a], {"shop_a": RUN}, process_keys={}, calls=calls)
        self.assertEqual(calls, [("reconcile", []), ("start", "shop_a")])

    def test_a_store_in_its_process_is_not_started_here(self):
        a = FakeAgent("shop_a", running=False)
        calls = self._ordered([a])
        _run([a], {"shop_a": RUN}, process_keys={"shop_a": "douyin-a"}, calls=calls)
        self.assertEqual(calls, [("reconcile", ["douyin-a"])])

    def test_a_store_placed_elsewhere_gets_no_process(self):
        a = FakeAgent("shop_a", running=False)
        calls = self._ordered([a])
        _run([a], {"shop_a": SKIP}, process_keys={"shop_a": "douyin-a"}, calls=calls)
        self.assertEqual(calls, [("reconcile", [])])


class WiringTests(unittest.TestCase):
    def _src(self, path):
        from pathlib import Path
        return Path(path).read_text(encoding="utf-8")

    def test_reconcile_runs_before_the_report_on_each_heartbeat(self):
        src = self._src("gui/MainGUI.py")
        self.assertLess(src.index("_reconcile_stores(self)"), src.index("_report_local_stores(self)"))

    def test_start_is_guarded_against_a_second_concurrent_call(self):
        src = self._src("agent/ec_agent.py")
        self.assertIn('if getattr(self, "_starting", False) or getattr(self, "_running", False):', src)

    def test_a_single_agent_stop_leaves_other_stores_monitors_alone(self):
        self.assertIn("self.runner.stop(cleanup_monitors=False)", self._src("agent/ec_agent.py"))


if __name__ == "__main__":
    unittest.main()
