"""store.* IPC handlers: what they send to store_api and how they report failure."""

import unittest
from unittest import mock

from gui.ipc.w2p_handlers import store_handler as h

REQ = {"id": "t", "method": "store.assign", "params": {}}


def _ok(resp):
    assert resp.get("status") == "success", resp
    return resp.get("result")


class ListTests(unittest.TestCase):
    def test_it_returns_this_machine_id_with_the_stores(self):
        with mock.patch("agent.cloud_api.store_api.store_list",
                        return_value={"stores": [{"storeId": "s1"}], "needsLogin": 1, "misplaced": 0}), \
             mock.patch.object(h, "_this_vehicle_id", return_value="stable-1"):
            data = _ok(h.handle_list(REQ, {}))
        self.assertEqual(data["stores"], [{"storeId": "s1"}])
        self.assertEqual(data["needs_login"], 1)
        self.assertEqual(data["this_vehicle_id"], "stable-1")


class AssignTests(unittest.TestCase):
    def test_this_machine_resolves_to_the_heartbeat_id(self):
        with mock.patch("agent.cloud_api.store_api.store_assign",
                        return_value={"store": {"storeId": "s1"}, "warnings": []}) as call, \
             mock.patch.object(h, "_this_vehicle_id", return_value="stable-1"):
            _ok(h.handle_assign(REQ, {"store_id": "s1", "this_machine": True}))
        self.assertEqual(call.call_args.args, ("s1", "stable-1"))

    def test_no_vehicle_unassigns(self):
        with mock.patch("agent.cloud_api.store_api.store_assign",
                        return_value={"store": {}, "warnings": []}) as call:
            _ok(h.handle_assign(REQ, {"store_id": "s1", "vehicle_id": None}))
        self.assertEqual(call.call_args.args, ("s1", None))

    def test_this_machine_without_an_id_is_refused_not_unassigned(self):
        # Falling through to vehicle_id=None would silently UNASSIGN the store.
        with mock.patch("agent.cloud_api.store_api.store_assign") as call, \
             mock.patch.object(h, "_this_vehicle_id", return_value=""):
            resp = h.handle_assign(REQ, {"store_id": "s1", "this_machine": True})
        self.assertEqual(resp["error"]["code"], "INVALID_PARAMS")
        call.assert_not_called()

    def test_a_404_from_the_cloud_is_a_typed_error(self):
        from agent.cloud_api.store_api import StoreApiError
        with mock.patch("agent.cloud_api.store_api.store_assign",
                        side_effect=StoreApiError("store_assign failed (HTTP 404): no machine")), \
             mock.patch.object(h, "_this_vehicle_id", return_value="stable-1"):
            resp = h.handle_assign(REQ, {"store_id": "s1", "this_machine": True})
        self.assertEqual(resp["error"]["code"], "STORE_API_ERROR")
        self.assertIn("404", resp["error"]["message"])

    def test_signed_out_is_its_own_code(self):
        from agent.cloud_api.store_api import StoreApiUnavailable
        with mock.patch("agent.cloud_api.store_api.store_list",
                        side_effect=StoreApiUnavailable("sign in first")), \
             mock.patch.object(h, "_this_vehicle_id", return_value=""):
            resp = h.handle_list(REQ, {})
        self.assertEqual(resp["error"]["code"], "STORE_API_UNAVAILABLE")


class ArchiveTests(unittest.TestCase):
    def test_restore_is_passed_through(self):
        with mock.patch("agent.cloud_api.store_api.store_archive",
                        return_value={"ok": True}) as call:
            _ok(h.handle_archive(REQ, {"store_id": "s1", "restore": True}))
        self.assertEqual(call.call_args.args, ("s1",))
        self.assertEqual(call.call_args.kwargs, {"restore": True})



class MachinesTests(unittest.TestCase):
    def test_this_machine_first_and_only_cloud_known_machines(self):
        others = [{"id": "far", "name": "Office-PC", "type": "desktop", "status": "active", "source": "cloud"},
                  {"id": "near", "name": "LAN-only", "type": "desktop", "status": "active", "source": "lan"},
                  {"id": "both", "name": "Next-desk", "type": "desktop", "status": "active", "source": "cloud+lan"}]
        with mock.patch.object(h, "_this_vehicle_id", return_value="me"), \
             mock.patch("gui.ipc.w2p_handlers.vehicle_handler._cloud_machines", return_value=others):
            data = _ok(h.handle_machines(REQ, {}))
        ids = [m["id"] for m in data["machines"]]
        # store_assign validates against the cloud row: a LAN-only machine would 404.
        self.assertEqual(ids, ["me", "far", "both"])
        self.assertTrue(data["machines"][0]["this"])


if __name__ == "__main__":
    unittest.main()
