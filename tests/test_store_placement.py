"""Store placement: the store's assignment, not the vehicle pin, decides where it runs."""

import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from agent.ec_agents import store_placement as sp

ME, OTHER = "me-pc", "other-pc"


def _snap(**stores):
    return {"fetched_at": 0, "stores": stores}


def _e(assigned=None, reported=None, online=None, status="active"):
    return {"assigned": assigned, "reported": reported, "reported_online": online, "status": status}


class DecideStoreTests(unittest.TestCase):
    def test_assigned_here_runs(self):
        self.assertEqual(sp.decide_store("s", ME, _snap(s=_e(ME)))[0], sp.RUN)

    def test_assigned_elsewhere_never_runs_whatever_the_pin(self):
        self.assertEqual(sp.decide_store("s", ME, _snap(s=_e(OTHER)))[0], sp.SKIP)

    def test_unassigned_runs_only_if_the_claim_wins(self):
        self.assertEqual(sp.decide_store("s", ME, _snap(), claim=lambda s: True)[0], sp.RUN)
        self.assertEqual(sp.decide_store("s", ME, _snap(s=_e()), claim=lambda s: False)[0], sp.SKIP)

    def test_moving_in_waits_for_the_previous_holder(self):
        # Gap over duplicate: assigned here, still running on OTHER.
        self.assertEqual(sp.decide_store("s", ME, _snap(s=_e(ME, OTHER, True)))[0], sp.SKIP)
        # Released, or the holder is offline: go.
        self.assertEqual(sp.decide_store("s", ME, _snap(s=_e(ME, None)))[0], sp.RUN)
        self.assertEqual(sp.decide_store("s", ME, _snap(s=_e(ME, OTHER, False)))[0], sp.RUN)

    def test_archived_never_runs(self):
        self.assertEqual(sp.decide_store("s", ME, _snap(s=_e(ME, status="archived")))[0], sp.SKIP)

    def test_no_cloud_and_no_cache_runs(self):
        # Owner decision D2.
        verdict, why = sp.decide_store("s", ME, None)
        self.assertEqual(verdict, sp.RUN)
        self.assertTrue(why.startswith("unknown"))

    def test_a_claim_that_cannot_be_made_is_treated_as_unknown(self):
        def boom(_):
            raise RuntimeError("timeout")
        self.assertEqual(sp.decide_store("s", ME, _snap(), claim=boom)[0], sp.RUN)


def _agent(*store_ids):
    tasks = [SimpleNamespace(metadata={"task_vars": {"store_id": s}}) for s in store_ids]
    return SimpleNamespace(tasks=tasks, mainwin=SimpleNamespace(my_ecb_data_homepath=""),
                           card=SimpleNamespace(name="a"))


class PlacementForAgentTests(unittest.TestCase):
    def _run(self, agent, snapshot, won=True):
        claims = []

        def fake_claim(store_id, vehicle_id):
            claims.append(store_id)
            return {"won": won}
        with mock.patch.object(sp, "refresh", return_value=snapshot), \
             mock.patch("agent.ec_agents.vehicle_affinity.resolve_local_vehicle_id", return_value=ME), \
             mock.patch("agent.cloud_api.store_api.store_claim", side_effect=fake_claim):
            return sp.placement_for_agent(agent), claims

    def test_an_agent_without_a_store_is_not_governed(self):
        agent = SimpleNamespace(tasks=[SimpleNamespace(metadata={"task_vars": {}})])
        self.assertEqual(sp.placement_for_agent(agent), (None, ""))

    def test_the_second_machine_skips_the_first_machines_store(self):
        # The duplicate-reply bug: pin '3' is adopted everywhere; the store is not.
        (verdict, _), _ = self._run(_agent("shop"), _snap(shop=_e(OTHER)))
        self.assertEqual(verdict, sp.SKIP)

    def test_an_unassigned_store_is_claimed_then_run(self):
        (verdict, _), claims = self._run(_agent("shop"), _snap())
        self.assertEqual((verdict, claims), (sp.RUN, ["shop"]))

    def test_a_multi_store_agent_runs_only_if_every_store_is_here(self):
        (verdict, _), _ = self._run(_agent("a", "b"), _snap(a=_e(ME), b=_e(ME)))
        self.assertEqual(verdict, sp.RUN)
        (verdict, _), _ = self._run(_agent("a", "b"), _snap(a=_e(ME), b=_e(OTHER)))
        self.assertEqual(verdict, sp.SKIP)

    def test_nothing_is_claimed_while_another_store_blocks_the_agent(self):
        # Else "new" would end up assigned here with no agent running it.
        (verdict, _), claims = self._run(_agent("new", "b"), _snap(b=_e(OTHER)))
        self.assertEqual((verdict, claims), (sp.SKIP, []))


class GateWiringTests(unittest.TestCase):
    """Mirrors test_worker_placement: importing EC_Agent pulls the browser stack."""

    def _src(self):
        from pathlib import Path
        return Path("agent/ec_agent.py").read_text(encoding="utf-8")

    def test_the_gate_is_wired_into_agent_start(self):
        src = self._src()
        self.assertIn("from agent.ec_agents.store_placement import", src)
        self.assertIn("_store_placement(self)", src)

    def test_a_store_agent_bypasses_the_fail_open_vehicle_pin(self):
        self.assertIn('(True, "store-placement") if _store_governed else agent_launch_allowed(self)',
                      self._src())

    def test_the_store_gate_runs_first_and_before_anything_starts(self):
        src = self._src()
        self.assertLess(src.index("_store_placement(self)"), src.index("agent_launch_allowed(self)"))
        self.assertLess(src.index("_store_placement(self)"), src.index("# Start A2A server in daemon thread"))

    def test_running_is_only_set_once_everything_started(self):
        src = self._src()
        self.assertLess(src.index("self._start_wan_subscriptions()\n"), src.index("self._running = True"))


class CacheTests(unittest.TestCase):
    def setUp(self):
        sp._mem.clear()
        self.addCleanup(sp._mem.clear)
        self.dir = tempfile.mkdtemp()
        self.mw = SimpleNamespace(my_ecb_data_homepath=self.dir)

    def test_a_fetch_is_persisted_and_survives_a_cloud_outage(self):
        rows = {"stores": [{"storeId": "s", "assignedVehicleId": ME, "reportedVehicleId": None,
                            "reportedVehicleOnline": None, "status": "active"}]}
        with mock.patch("agent.cloud_api.store_api.store_list", return_value=rows):
            self.assertEqual(sp.refresh(self.mw, force=True)["stores"]["s"]["assigned"], ME)
        self.assertTrue(os.path.exists(os.path.join(self.dir, sp.CACHE_FILE)))
        sp._mem.clear()   # a fresh process
        with mock.patch("agent.cloud_api.store_api.store_list", side_effect=RuntimeError("down")):
            snap = sp.refresh(self.mw, force=True)
        self.assertEqual(snap["stores"]["s"]["assigned"], ME)

    def test_no_cloud_and_no_cache_is_none(self):
        with mock.patch("agent.cloud_api.store_api.store_list", side_effect=RuntimeError("down")):
            self.assertIsNone(sp.refresh(self.mw, force=True))


if __name__ == "__main__":
    unittest.main()
