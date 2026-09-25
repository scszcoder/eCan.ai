"""Store processes: only when this machine serves 2+ stores of one platform."""

import os
import unittest
from types import SimpleNamespace
from unittest import mock

from agent.ec_agents import store_isolation as si


def _mainwin(platforms):
    svc = SimpleNamespace(get_store=lambda sid: {"platform": platforms.get(sid, "")})
    return SimpleNamespace(ec_db_mgr=SimpleNamespace(store_service=svc))


def _agent(*stores, status="active", name="a"):
    return SimpleNamespace(card=SimpleNamespace(name=name), status=status,
                           tasks=[SimpleNamespace(metadata={"task_vars": {"store_id": s}}) for s in stores])


class PolicyTests(unittest.TestCase):
    def test_two_stores_of_one_platform_each_get_a_process(self):
        mw = _mainwin({"a": "douyin", "b": "douyin", "c": "etsy"})
        self.assertEqual(si.isolated_store_ids(mw, ["a", "b", "c"]), {"a", "b"})

    def test_one_store_per_platform_stays_in_process(self):
        mw = _mainwin({"a": "douyin", "c": "etsy"})
        self.assertEqual(si.isolated_store_ids(mw, ["a", "c"]), set())

    def test_stores_without_a_platform_are_never_grouped(self):
        self.assertEqual(si.isolated_store_ids(_mainwin({}), ["x", "y"]), set())

    def test_only_stores_served_here_count(self):
        snap = {"stores": {"elsewhere": {"assigned": "other-pc"}, "gone": {"status": "archived"},
                           "mine": {"assigned": "me"}}}
        agents = [_agent("mine"), _agent("unassigned"), _agent("elsewhere"), _agent("gone"),
                  _agent("off", status="disabled")]
        self.assertEqual(si.stores_served_here(None, agents, snap, "me"), ["mine", "unassigned"])


class KeyTests(unittest.TestCase):
    def test_in_the_app_an_isolated_store_gets_its_own_key(self):
        env = {k: v for k, v in os.environ.items() if k != "ECAN_WORKER_KEY"}
        with mock.patch.dict(os.environ, env, clear=True), \
             mock.patch.object(si, "isolated_here", return_value={"douyin-a"}):
            self.assertEqual(si.store_isolation_key(_agent("douyin-a")), "douyin-a")
            self.assertEqual(si.store_isolation_key(_agent("etsy-1")), "")
            self.assertEqual(si.store_isolation_key(_agent()), "")

    def test_inside_a_store_process_only_its_own_store_matches(self):
        # No policy recomputation in the child: it cannot disagree with the parent.
        with mock.patch.dict(os.environ, {"ECAN_WORKER_KEY": "douyin-a"}), \
             mock.patch.object(si, "isolated_here", side_effect=AssertionError("child must not decide")):
            self.assertEqual(si.store_isolation_key(_agent("douyin-a")), "douyin-a")
            self.assertEqual(si.store_isolation_key(_agent("douyin-b")), "douyin-b")
            self.assertEqual(si.store_isolation_key(_agent()), "")

    def test_the_worker_gate_uses_it_and_an_explicit_key_still_wins(self):
        from agent.ec_tasks import worker_placement as wp
        env = {k: v for k, v in os.environ.items() if k != "ECAN_WORKER_KEY"}
        with mock.patch.dict(os.environ, env, clear=True), \
             mock.patch.object(si, "isolated_here", return_value={"douyin-a"}):
            self.assertEqual(wp.placement_for_agent(_agent("douyin-a")), (wp.PLACE_DELEGATE, "douyin-a"))
            explicit = SimpleNamespace(card=SimpleNamespace(name="x"), tasks=[
                SimpleNamespace(metadata={"task_vars": {"store_id": "douyin-a", "isolation_key": "hand"}})])
            self.assertEqual(wp.agent_isolation_key(explicit), "hand")


class ReportingTests(unittest.TestCase):
    def test_a_store_in_its_own_process_is_reported_running_not_released(self):
        from agent.ec_agents import store_reporter as sr
        with mock.patch.object(sr, "_store_process_keys", return_value=["douyin-a"]):
            self.assertEqual(sr.local_store_ids(SimpleNamespace(agents=[])), ["douyin-a"])


if __name__ == "__main__":
    unittest.main()
