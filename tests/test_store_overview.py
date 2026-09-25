"""Stores page data: per-store agents/tasks/outcomes, meter names, cloud+local merge."""

import unittest
from types import SimpleNamespace
from unittest import mock

from agent.ec_agents import store_overview as so


def _task(tid, store):
    return SimpleNamespace(id=tid, name=f"t-{tid}",
                           metadata={"task_vars": {"store_id": store} if store else {}})


def _agent(aid, *tasks, running=True):
    return SimpleNamespace(card=SimpleNamespace(id=aid, name=f"a-{aid}"), tasks=list(tasks),
                           _running=running, status="active")


class SummarizeAgentsTests(unittest.TestCase):
    def test_agents_and_tasks_group_under_their_store(self):
        out = so.summarize_agents([
            _agent("fd", _task("t1", "shop-a")),
            _agent("qa", _task("t2", "shop-a"), _task("t3", "shop-b"), running=False),
            _agent("plain", _task("t4", None)),
        ])
        self.assertEqual(sorted(out), ["shop-a", "shop-b"])
        self.assertEqual([a["id"] for a in out["shop-a"]["agents"]], ["fd", "qa"])
        self.assertEqual([t["id"] for t in out["shop-a"]["tasks"]], ["t1", "t2"])
        # An agent serving two stores appears under both, with its own state.
        self.assertEqual(out["shop-b"]["agents"], [{"id": "qa", "name": "a-qa", "running": False, "status": "active"}])

    def test_an_agent_with_two_tasks_in_one_store_is_listed_once(self):
        out = so.summarize_agents([_agent("qa", _task("t1", "s"), _task("t2", "s"))])
        self.assertEqual(len(out["s"]["agents"]), 1)
        self.assertEqual(len(out["s"]["tasks"]), 2)


class SummarizeMetersTests(unittest.TestCase):
    def test_windows_merge_per_meter_and_carry_the_declared_name(self):
        rows = {
            7: [{"scenario_code": "cs_chat", "meter_code": "message_replied", "store_id": "s", "quantity": 12}],
            30: [{"scenario_code": "cs_chat", "meter_code": "message_replied", "store_id": "s", "quantity": 80},
                 {"scenario_code": "x", "meter_code": "y", "store_id": "s", "quantity": 3},
                 {"scenario_code": "cs_chat", "meter_code": "message_replied", "store_id": "", "quantity": 9}],
        }
        out = so.summarize_meters(rows)
        self.assertEqual(list(out), ["s"], "account-wide outcomes belong to no single store")
        replied = next(m for m in out["s"] if m["meter_code"] == "message_replied")
        self.assertEqual((replied["d7"], replied["d30"]), (12, 80))
        self.assertEqual(replied["display_name_zh"], "客服回复")   # from feige_chat/hook.yaml
        undeclared = next(m for m in out["s"] if m["meter_code"] == "y")
        self.assertEqual((undeclared["d7"], undeclared["d30"], undeclared["source"]), (0, 3, "undeclared"))


class MeterRegistryTests(unittest.TestCase):
    def test_the_feige_bundle_declaration_is_read(self):
        from agent.ec_skills.meter_registry import declared_meters
        m = declared_meters(refresh=True).get(("cs_chat", "message_replied"))
        self.assertIsNotNone(m)
        self.assertEqual((m["unit"], m["source"]), ("条", "bundle:feige_chat"))


class OverviewHandlerTests(unittest.TestCase):
    def _call(self, cloud_rows=None, cloud_exc=None, local=None):
        from gui.ipc.w2p_handlers import store_handler as h
        lst = mock.Mock(side_effect=cloud_exc) if cloud_exc else mock.Mock(return_value={"stores": cloud_rows or []})
        with mock.patch("app_context.AppContext.get_main_window", return_value=SimpleNamespace()), \
             mock.patch("agent.ec_agents.store_overview.local_store_overview", return_value=local or {}), \
             mock.patch("agent.cloud_api.store_api.store_list", lst), \
             mock.patch.object(h, "_this_vehicle_id", return_value="me"):
            resp = h.handle_overview({"id": "t", "method": "store.overview", "params": {}}, {})
        self.assertEqual(resp["status"], "success", resp)
        return resp["result"]

    def test_cloud_and_local_merge_and_either_side_alone_still_shows(self):
        loc = {"a": {"agents": [{"id": "x"}], "tasks": [], "meters": []},
               "local-only": {"agents": [], "tasks": [], "meters": []}}
        out = self._call(cloud_rows=[{"storeId": "a", "assignedVehicleId": "me"},
                                     {"storeId": "cloud-only"}], local=loc)
        by = {s["storeId"]: s for s in out["stores"]}
        self.assertEqual(by["a"]["local"]["agents"], [{"id": "x"}])
        self.assertEqual(by["cloud-only"]["local"]["agents"], [])
        self.assertFalse(by["local-only"]["cloudKnown"])
        self.assertEqual(out["this_vehicle_id"], "me")

    def test_no_cloud_degrades_to_local_with_a_reason(self):
        out = self._call(cloud_exc=RuntimeError("signed out"), local={"a": {"agents": [], "tasks": [], "meters": []}})
        self.assertEqual([s["storeId"] for s in out["stores"]], ["a"])
        self.assertIn("signed out", out["cloud_error"])


if __name__ == "__main__":
    unittest.main()
