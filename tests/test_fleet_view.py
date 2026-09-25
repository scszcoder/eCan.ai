"""What each role sees: a Commander the whole account, a Platoon itself (and its Commander)."""

import json
import unittest
from types import SimpleNamespace
from unittest import mock

import agent.ec_agents.store_placement as sp
from agent.cloud_api.cloud_api import gen_report_vehicles_string
from gui.ipc.w2p_handlers import agent_handler as ah
from gui.ipc.w2p_handlers import vehicle_handler as vh


def _mainwin(role):
    return SimpleNamespace(host_role=role, machine_name="PC-B", ip="10.0.0.2",
                           platform="Windows", processor="AMD64")


class RoleReportTests(unittest.TestCase):
    def test_the_heartbeat_carries_the_role(self):
        q = gen_report_vehicles_string([{"vname": "PC-B:win", "machine_id": "b", "status": "running_idle",
                                         "role": "Platoon"}])
        self.assertIn('\\"role\\": \\"Platoon\\"', q)

    def test_the_role_is_read_back_from_extra_metadata(self):
        self.assertEqual(vh._reported_role({"extra_metadata": json.dumps({"role": "Commander"})}), "Commander")
        self.assertEqual(vh._reported_role({"extra_metadata": {"role": "Platoon"}}), "Platoon")
        self.assertEqual(vh._reported_role({"extra_metadata": "not json"}), "")
        self.assertEqual(vh._reported_role({}), "")


class VehicleScopeTests(unittest.TestCase):
    ENTRIES = [
        {"id": "a", "name": "PC-A", "role": "Commander"},
        {"id": "c", "name": "PC-C", "role": "Platoon"},
        {"id": "pod-1", "name": "pod", "type": "cloud", "role": ""},
    ]

    def _scope(self, role, me="b"):
        with mock.patch.object(vh.AppContext, "get_main_window", return_value=_mainwin(role)), \
             mock.patch("agent.ec_agents.vehicle_affinity.resolve_local_vehicle_id", return_value=me):
            return vh._mark_self_and_scope([dict(e) for e in self.ENTRIES])

    def test_a_platoon_sees_itself_and_its_commander(self):
        out = self._scope("Platoon")
        self.assertEqual(sorted(e["id"] for e in out), ["a", "b"])
        me = next(e for e in out if e["id"] == "b")
        self.assertTrue(me["is_self"])
        self.assertEqual(me["role"], "Platoon")

    def test_a_commander_sees_everything_and_itself(self):
        out = self._scope("Commander", me="a")
        self.assertEqual(sorted(e["id"] for e in out), ["a", "c", "pod-1"])
        self.assertTrue(next(e for e in out if e["id"] == "a")["is_self"])


class AgentScopeTests(unittest.TestCase):
    def _agent(self, aid):
        return SimpleNamespace(card=SimpleNamespace(id=aid), to_dict=lambda owner=None: {"id": aid})

    def _list(self, role):
        where = {"here": "", "away": "machine-a"}
        with mock.patch.object(ah.AppContext, "get_main_window", return_value=_mainwin(role)), \
             mock.patch.object(sp, "where_agent_runs", side_effect=lambda a: where[a.card.id]):
            return ah._with_placement([self._agent("here"), self._agent("away")], "u")

    def test_a_commander_lists_remote_agents_marked_remote(self):
        out = {d["id"]: d for d in self._list("Commander")}
        self.assertTrue(out["here"]["runs_here"])
        self.assertFalse(out["away"]["runs_here"])
        self.assertEqual(out["away"]["runs_on"], "machine-a")

    def test_a_platoon_lists_only_its_own_agents(self):
        self.assertEqual([d["id"] for d in self._list("Platoon")], ["here"])


class WhereAgentRunsTests(unittest.TestCase):
    def _agent(self, vehicle_id=""):
        return SimpleNamespace(mainwin=None, vehicle_id=vehicle_id)

    def test_a_store_agent_runs_where_its_store_is_assigned(self):
        snap = {"stores": {"s1": {"assigned": "machine-a"}}}
        with mock.patch.object(sp, "store_ids_of_agent", return_value=["s1"]), \
             mock.patch.object(sp, "cached", return_value=snap), \
             mock.patch("agent.ec_agents.vehicle_affinity.resolve_local_vehicle_id", return_value="b"):
            self.assertEqual(sp.where_agent_runs(self._agent()), "machine-a")
        with mock.patch.object(sp, "store_ids_of_agent", return_value=["s1"]), \
             mock.patch.object(sp, "cached", return_value=snap), \
             mock.patch("agent.ec_agents.vehicle_affinity.resolve_local_vehicle_id", return_value="machine-a"):
            self.assertEqual(sp.where_agent_runs(self._agent()), "")

    def test_an_unassigned_store_reads_as_here_and_is_never_claimed(self):
        with mock.patch.object(sp, "store_ids_of_agent", return_value=["s1"]), \
             mock.patch.object(sp, "cached", return_value={"stores": {}}), \
             mock.patch("agent.ec_agents.vehicle_affinity.resolve_local_vehicle_id", return_value="b"), \
             mock.patch("agent.cloud_api.store_api.store_claim") as claim:
            self.assertEqual(sp.where_agent_runs(self._agent()), "")
        claim.assert_not_called()

    def test_other_agents_follow_their_vehicle_pin(self):
        with mock.patch.object(sp, "store_ids_of_agent", return_value=[]), \
             mock.patch("agent.ec_agents.vehicle_affinity.agent_launch_allowed", return_value=(False, "pinned")):
            self.assertEqual(sp.where_agent_runs(self._agent("machine-a")), "machine-a")
        with mock.patch.object(sp, "store_ids_of_agent", return_value=[]), \
             mock.patch("agent.ec_agents.vehicle_affinity.agent_launch_allowed", return_value=(True, "local")):
            self.assertEqual(sp.where_agent_runs(self._agent("b")), "")


if __name__ == "__main__":
    unittest.main()
