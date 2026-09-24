"""GUI chat routing: never a stand-in agent, never a silent queue into an agent that is not running here."""

import unittest
from types import SimpleNamespace
from unittest import mock

from agent.chats import chat_utils as cu


class Runner:
    def __init__(self):
        self.got = []

    def sync_task_wait_in_line(self, kind, req):
        self.got.append(req)
        return {"ok": True}


def _agent(aid, running=True, **extra):
    a = SimpleNamespace(card=SimpleNamespace(id=aid, name=f"n-{aid}"), runner=Runner(),
                        _running=running, tasks=[], mainwin=None, status="active")
    a.__dict__.update(extra)
    return a


def _mainwin(agents, members=None):
    chat = {"success": True, "data": {"members": [{"userId": m} for m in (members or [])]}}
    svc = SimpleNamespace(get_chat_by_id=lambda cid, deep=False: chat)
    return SimpleNamespace(agents=agents, ec_db_mgr=SimpleNamespace(get_chat_service=lambda: svc))


def _req(receiver=None):
    p = {"chatId": "c1", "senderId": "human"}
    if receiver:
        p["receiverId"] = receiver
    return {"params": p}


class RoutingTests(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(cu, "_notify_chat_undeliverable")
        self.notify = p.start()
        self.addCleanup(p.stop)

    def test_a_running_recipient_gets_the_message(self):
        a = _agent("a1")
        cu.gui_a2a_send_chat(_mainwin([a]), _req("a1"))
        self.assertEqual(len(a.runner.got), 1)

    def test_a_named_recipient_not_in_this_app_is_never_answered_by_another_agent(self):
        other = _agent("someone-else")
        out = cu.gui_a2a_send_chat(_mainwin([other]), _req("remote-agent"))
        self.assertIn("error", out)
        self.assertEqual(other.runner.got, [], "the old last resort handed it to the wrong agent")
        self.notify.assert_called_once()

    def test_a_chat_member_not_in_this_app_is_not_rerouted_either(self):
        other = _agent("someone-else")
        cu.gui_a2a_send_chat(_mainwin([other], members=["human", "remote-agent"]), _req())
        self.assertEqual(other.runner.got, [])

    def test_an_agent_placed_elsewhere_is_not_silently_queued(self):
        away = _agent("a1", running=False)
        with mock.patch.object(cu, "_runs_elsewhere", return_value="store s is assigned to another machine"):
            out = cu.gui_a2a_send_chat(_mainwin([away]), _req("a1"))
        self.assertIn("error", out)
        self.assertEqual(away.runner.got, [])
        self.assertIn("another machine", self.notify.call_args.args[1])

    def test_a_chat_with_no_identifiable_recipient_keeps_the_legacy_fallback(self):
        a = _agent("a1")
        cu.gui_a2a_send_chat(_mainwin([a], members=["human"]), _req())
        self.assertEqual(len(a.runner.got), 1)


class RunsElsewhereTests(unittest.TestCase):
    def test_running_or_starting_agents_are_here(self):
        self.assertEqual(cu._runs_elsewhere(_agent("a", running=True)), "")
        self.assertEqual(cu._runs_elsewhere(_agent("a", running=False, _starting=True)), "")

    def test_a_disabled_agent_is_reported(self):
        self.assertIn("turned off", cu._runs_elsewhere(_agent("a", running=False, status="disabled")))

    def test_a_store_assigned_elsewhere_is_reported_without_claiming(self):
        a = _agent("a", running=False, tasks=[SimpleNamespace(metadata={"task_vars": {"store_id": "s"}})])
        with mock.patch("agent.ec_agents.store_placement.refresh",
                        return_value={"stores": {"s": {"assigned": "other-pc"}}}), \
             mock.patch("agent.ec_agents.vehicle_affinity.resolve_local_vehicle_id", return_value="me"), \
             mock.patch("agent.cloud_api.store_api.store_claim") as claim:
            self.assertIn("another machine", cu._runs_elsewhere(a))
        claim.assert_not_called()

    def test_a_store_agent_in_its_own_store_process_is_reported(self):
        a = _agent("a", running=False, tasks=[SimpleNamespace(metadata={"task_vars": {"store_id": "s"}})])
        from agent.ec_tasks import worker_placement as wp
        with mock.patch("agent.ec_agents.store_placement.refresh", return_value={"stores": {"s": {"assigned": "me"}}}), \
             mock.patch("agent.ec_agents.vehicle_affinity.resolve_local_vehicle_id", return_value="me"), \
             mock.patch.object(wp, "placement_for_agent", return_value=(wp.PLACE_DELEGATE, "s")):
            self.assertIn("store process", cu._runs_elsewhere(a))


if __name__ == "__main__":
    unittest.main()
