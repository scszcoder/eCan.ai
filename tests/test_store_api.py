"""The client half of the cloud store registry.

Three things are worth pinning here, because each has already gone wrong once
somewhere in this system:

* **One machine, one id.** ``store_assign`` validates a store's machine against
  the row the vehicles heartbeat registered. The client had three identities
  for one machine, so a second one here would 404 every assignment against a
  machine that is plainly online.
* **A URL-derived store id is refused.** Every 飞鸽 seller shares one
  workstation URL, so such an id is identical for every store and would merge
  them into one healthy-looking row — one cost bucket, one set of settings.
* **A profile's contents never travel.** This module forwards a descriptor its
  caller built and never reaches for the registry itself.
"""

import json
import unittest
from unittest.mock import patch

from agent.cloud_api import store_api


class UrlDerivedIdTests(unittest.TestCase):
    def test_rejects_the_feige_workstation_url(self):
        self.assertTrue(store_api.looks_url_derived(
            "https://im.jinritemai.com/pc_seller_v2/main/workspace"))

    def test_rejects_the_bare_host_and_path_form(self):
        # What resolve_store_id's URL fallback actually produces.
        self.assertTrue(store_api.looks_url_derived("im.jinritemai.com/pc_seller_v2"))

    def test_accepts_a_real_store_name(self):
        for ok in ("lands_flying_fish", "飞鱼旗舰店", "store-2", "shop.one"):
            self.assertFalse(store_api.looks_url_derived(ok), ok)

    def test_blank_is_not_url_derived(self):
        # Blank is rejected elsewhere as "required"; it is not this error.
        self.assertFalse(store_api.looks_url_derived(""))


class ReportItemTests(unittest.TestCase):
    def test_builds_a_minimal_item(self):
        item = store_api.build_store_report_item("lands_flying_fish")
        self.assertEqual(item, {"store_id": "lands_flying_fish",
                                "login_state": "unknown"})

    def test_carries_the_descriptor_verbatim(self):
        descriptor = {"id": "p1", "store_id": "s1", "has_proxy": False}
        item = store_api.build_store_report_item(
            "s1", profile=descriptor, login_state="needs_login")
        self.assertEqual(item["profile"], descriptor)
        self.assertEqual(item["login_state"], "needs_login")

    def test_refuses_a_url_derived_id_with_an_actionable_message(self):
        with self.assertRaises(ValueError) as caught:
            store_api.build_store_report_item("im.jinritemai.com/pc_seller_v2")
        self.assertIn("Fast Deploy", str(caught.exception))

    def test_refuses_an_unknown_login_state(self):
        # The values are profile_registry's verbatim; anything else is rejected
        # per item by the server, so catching it here saves a round trip.
        with self.assertRaises(ValueError):
            store_api.build_store_report_item("s1", login_state="probably_fine")

    def test_accepts_every_real_login_state(self):
        for state in ("unknown", "ok", "needs_login"):
            item = store_api.build_store_report_item("s1", login_state=state)
            self.assertEqual(item["login_state"], state)

    def test_store_id_is_required(self):
        with self.assertRaises(ValueError):
            store_api.build_store_report_item("   ")


class _Resp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self.text = json.dumps(body if body is not None else {"success": True})


class _Calls(list):
    def __call__(self, url, **kwargs):
        self.append((url, kwargs))
        return self.response


def _patched(response=None, token="tok", url="https://x/ecbAccountManager"):
    calls = _Calls()
    calls.response = response or _Resp()
    return calls, patch.multiple(
        "agent.cloud_api.turn_queue",
        _account_manager_url=lambda: url,
        _session_bearer_token=lambda: token,
    ), patch.object(store_api.requests, "post", calls)


class TransportTests(unittest.TestCase):
    def test_sends_the_action_and_the_session_bearer(self):
        calls, p_tq, p_post = _patched()
        with p_tq, p_post:
            store_api.store_report("vehicle-1", [{"store_id": "s1"}])
        _url, kwargs = calls[0]
        self.assertEqual(kwargs["json"]["action"], "store_report")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer tok")

    def test_never_sends_an_owner(self):
        # The server takes the owner from the verified identity; a
        # client-supplied one would be a claim, not a fact.
        calls, p_tq, p_post = _patched()
        with p_tq, p_post:
            store_api.store_report("vehicle-1", [{"store_id": "s1"}])
            store_api.store_list()
            store_api.store_assign("s1", "vehicle-1")
        for _url, kwargs in calls:
            self.assertNotIn("owner", json.dumps(kwargs["json"]))

    def test_a_401_is_reported_as_unavailable_not_as_a_failure(self):
        # An expired session is fixed by signing in, not by retrying.
        calls, p_tq, p_post = _patched(_Resp(401, {"message": "nope"}))
        with p_tq, p_post:
            with self.assertRaises(store_api.StoreApiUnavailable):
                store_api.store_list()

    def test_no_credential_does_not_even_attempt_the_call(self):
        calls, p_tq, p_post = _patched(token="")
        with p_tq, p_post:
            with self.assertRaises(store_api.StoreApiUnavailable):
                store_api.store_list()
        self.assertEqual(len(calls), 0)

    def test_a_server_error_is_surfaced(self):
        calls, p_tq, p_post = _patched(_Resp(400, {"error": "bad store"}))
        with p_tq, p_post:
            with self.assertRaises(store_api.StoreApiError) as caught:
                store_api.store_list()
        self.assertIn("bad store", str(caught.exception))

    def test_non_json_is_surfaced_rather_than_crashing(self):
        class _Html:
            status_code = 200
            text = "<html>gateway</html>"
        calls, p_tq, p_post = _patched(_Html())
        with p_tq, p_post:
            with self.assertRaises(store_api.StoreApiError):
                store_api.store_list()


class ReportTests(unittest.TestCase):
    def test_vehicle_id_is_required(self):
        # Reporting without the id the heartbeat registered is what makes
        # assignment 404 against an online machine.
        with self.assertRaises(ValueError):
            store_api.store_report("", [{"store_id": "s1"}])

    def test_an_empty_report_is_a_no_op_not_a_call(self):
        calls, p_tq, p_post = _patched()
        with p_tq, p_post:
            out = store_api.store_report("vehicle-1", [])
        self.assertEqual(len(calls), 0)
        self.assertEqual(out["accepted"], 0)

    def test_too_many_stores_is_refused_before_the_round_trip(self):
        stores = [{"store_id": f"s{i}"} for i in range(store_api.MAX_STORES_PER_REPORT + 1)]
        with self.assertRaises(ValueError):
            store_api.store_report("vehicle-1", stores)

    def test_a_rejected_item_is_logged_at_warning(self):
        from config.constants import APP_NAME
        body = {"success": True, "accepted": 1, "rejected": 1, "results": [
            {"storeId": "good", "ok": True},
            {"storeId": "bad", "ok": False, "error": "url-derived store_id"},
        ]}
        calls, p_tq, p_post = _patched(_Resp(200, body))
        with p_tq, p_post:
            with self.assertLogs(APP_NAME, level="WARNING") as captured:
                store_api.store_report("vehicle-1", [{"store_id": "good"}])
        joined = "\n".join(captured.output)
        self.assertIn("bad", joined)
        self.assertIn("url-derived", joined)


class ListAndAssignTests(unittest.TestCase):
    def test_list_scopes_to_a_machine_when_asked(self):
        calls, p_tq, p_post = _patched()
        with p_tq, p_post:
            store_api.store_list(vehicle_id="vehicle-1")
        self.assertEqual(calls[0][1]["json"]["input"]["vehicle_id"], "vehicle-1")

    def test_list_without_a_machine_is_the_whole_account(self):
        calls, p_tq, p_post = _patched()
        with p_tq, p_post:
            store_api.store_list()
        self.assertNotIn("vehicle_id", calls[0][1]["json"]["input"])

    def test_assign_passes_null_to_unassign(self):
        calls, p_tq, p_post = _patched()
        with p_tq, p_post:
            store_api.store_assign("s1", None)
        self.assertIsNone(calls[0][1]["json"]["input"]["vehicle_id"])

    def test_assign_refuses_a_url_derived_id(self):
        with self.assertRaises(ValueError):
            store_api.store_assign("im.jinritemai.com/pc_seller_v2", "vehicle-1")

    def test_assign_warnings_are_surfaced_not_swallowed(self):
        # "reports ['qa'] without 'front_desk'" means no desktop session, so a
        # chat front desk cannot run there -- advisory, but the operator needs it.
        from config.constants import APP_NAME
        body = {"success": True, "store": {}, "warnings": ["machine reports no front_desk"]}
        calls, p_tq, p_post = _patched(_Resp(200, body))
        with p_tq, p_post:
            with self.assertLogs(APP_NAME, level="WARNING") as captured:
                store_api.store_assign("s1", "vehicle-1")
        self.assertIn("front_desk", "\n".join(captured.output))

    def test_archive_and_restore(self):
        calls, p_tq, p_post = _patched()
        with p_tq, p_post:
            store_api.store_archive("s1")
            store_api.store_archive("s1", restore=True)
        self.assertNotIn("restore", calls[0][1]["json"]["input"])
        self.assertIs(calls[1][1]["json"]["input"]["restore"], True)


class HeartbeatIdentityTests(unittest.TestCase):
    """The heartbeat must register the SAME id store_report sends."""

    def test_the_mutation_uses_the_stable_machine_id(self):
        from agent.cloud_api.cloud_api import gen_report_vehicles_string
        query = gen_report_vehicles_string([
            {"vname": "DESKTOP-ABC:win", "machine_id": "stable-uuid-1",
             "status": "online"},
        ])
        self.assertIn('id: "stable-uuid-1"', query)
        # The display name stays readable -- a UUID on the fleet screen is not.
        self.assertIn('name: "DESKTOP-ABC:win"', query)

    def test_it_falls_back_to_the_name_when_no_stable_id_is_given(self):
        # Remote Commander vehicles have no stable id to offer.
        from agent.cloud_api.cloud_api import gen_report_vehicles_string
        query = gen_report_vehicles_string([{"vname": "OTHER:win", "status": "online"}])
        self.assertIn('id: "OTHER:win"', query)

    def test_capabilities_are_sent_as_a_json_array(self):
        # The server's placement check reads exactly this shape; the legacy
        # {"functions": ...} object is not it.
        from agent.cloud_api.cloud_api import gen_report_vehicles_string
        query = gen_report_vehicles_string([
            {"vname": "d:win", "machine_id": "m1", "capabilities": ["qa", "front_desk"]},
        ])
        # Assert on the capabilities FIELD, not the whole query: "functions"
        # also lives in extra_metadata, which is always present.
        self.assertIn('capabilities: "[', query)      # an array...
        self.assertNotIn('capabilities: "{', query)   # ...not the legacy object
        self.assertIn("qa", query)
        self.assertIn("front_desk", query)

    def test_the_legacy_functions_shape_still_works(self):
        from agent.cloud_api.cloud_api import gen_report_vehicles_string
        query = gen_report_vehicles_string([{"vname": "d:win", "functions": "rpa"}])
        self.assertIn("functions", query)

    def test_a_working_machine_reports_online(self):
        # Seen live: status "running_idle" made store_assign warn that a
        # heartbeating machine was "not online right now".
        from agent.cloud_api.cloud_api import gen_report_vehicles_string
        for working in ("running_idle", "running_working"):
            query = gen_report_vehicles_string([{"vname": "d:win", "status": working}])
            self.assertIn('status: "online"', query)
            self.assertIn(working, query)   # still carried, in extra_metadata
        query = gen_report_vehicles_string([{"vname": "d:win", "status": "offline"}])
        self.assertIn('status: "offline"', query)

    def test_a_new_stable_id_is_registered_under_that_id(self):
        # Seen live: updateVehicles answered NOT_FOUND for the stable id, and
        # the add fallback matched on vname, so the row was never created.
        from unittest import mock
        from agent.cloud_api import cloud_api
        sent = []

        def fake_request(query, *_a, **_k):
            sent.append(query)
            if "addVehicles" in query:
                return {"data": {"addVehicles": [{"id": "stable-uuid-1", "success": True}]}}
            if len(sent) == 1:
                return {"data": {"updateVehicles": [
                    {"id": "stable-uuid-1", "success": False, "error": "NOT_FOUND: Not found"}]}}
            return {"data": {"updateVehicles": [{"id": "stable-uuid-1", "success": True}]}}

        with mock.patch.object(cloud_api, "appsync_http_request", side_effect=fake_request):
            cloud_api.send_report_vehicles_to_cloud(
                None, "tok", [{"vname": "DESKTOP-ABC:win", "machine_id": "stable-uuid-1"}], "ep")
        adds = [q for q in sent if "addVehicles" in q]
        self.assertEqual(len(adds), 1)
        self.assertIn('"stable-uuid-1"', adds[0])

    def test_the_heartbeat_and_the_local_row_agree(self):
        # The fix: one machine, one identity. If these ever diverge again,
        # store_assign 404s against a machine that is plainly online.
        from agent.ec_agents.vehicle_affinity import (
            local_vehicle_report_fields, resolve_local_vehicle_id,
        )
        fields = local_vehicle_report_fields()
        self.assertEqual(fields.get("machine_id"), resolve_local_vehicle_id())

    def test_the_heartbeat_carries_the_capability_list(self):
        from agent.ec_agents.vehicle_affinity import (
            local_vehicle_report_fields, machine_capabilities,
        )
        self.assertEqual(local_vehicle_report_fields().get("capabilities"),
                         machine_capabilities())


if __name__ == "__main__":
    unittest.main()
