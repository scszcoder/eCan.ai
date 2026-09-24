"""store_reporter: which stores this machine reports, and what it sends."""

import unittest
from types import SimpleNamespace
from unittest import mock

from agent.ec_agents import store_reporter as sr


def _task(**task_vars):
    return SimpleNamespace(metadata={"task_vars": task_vars})


def _agent(*tasks, here=True):
    # "here" = actually running on this machine (store placement let it start).
    return SimpleNamespace(tasks=list(tasks), _running=here)


def _mainwin(*agents):
    return SimpleNamespace(agents=list(agents))


class _Patched(unittest.TestCase):
    def setUp(self):
        patches = [
            # No cloud in unit tests: the release check sees an empty registry
            # unless a test sets self.snapshot.
            mock.patch("agent.ec_agents.store_placement.refresh", lambda mw, force=False: self.snapshot),
            mock.patch(
                "agent.ec_skills.browser_use_extension.fingerprint.profile_registry.list_profiles",
                lambda: self.profiles,
            ),
        ]
        self.profiles = []
        self.snapshot = None
        for p in patches:
            p.start()
            self.addCleanup(p.stop)


class LocalStoreIdsTests(_Patched):
    def test_explicit_ids_only_deduplicated(self):
        mw = _mainwin(
            _agent(_task(store_id="shop-a"), _task(store_id="shop-b")),
            _agent(_task(store_id="shop-a"), _task()),
        )
        self.assertEqual(sr.local_store_ids(mw), ["shop-a", "shop-b"])

    def test_the_url_fallback_is_not_a_store(self):
        # Every 飞鸽 seller shares this URL; resolve_store_id would return the
        # same id for all of them.
        mw = _mainwin(_agent(_task(store_url="https://im.jinritemai.com/pc_seller_v2/main")))
        self.assertEqual(sr.local_store_ids(mw), [])

    def test_agents_not_running_here_are_not_reported(self):
        mw = _mainwin(_agent(_task(store_id="elsewhere"), here=False))
        self.assertEqual(sr.local_store_ids(mw), [])


class BuildReportTests(_Patched):
    def test_login_state_comes_from_the_profile_descriptor(self):
        self.profiles = [{"id": "p1", "store_id": "shop-a", "login_state": "ok",
                          "user_data_dir": r"C:\secret\dir",
                          "proxy": {"host": "h", "password": "s3cret"}}]
        items = sr.build_local_store_report(_mainwin(_agent(_task(store_id="shop-a"))))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["login_state"], "ok")
        self.assertEqual(items[0]["profile"]["id"], "p1")
        # The descriptor, never the profile.
        flat = repr(items)
        self.assertNotIn("secret", flat)
        self.assertNotIn("s3cret", flat)

    def test_a_store_without_a_profile_is_unknown(self):
        items = sr.build_local_store_report(_mainwin(_agent(_task(store_id="shop-a"))))
        self.assertEqual(items, [{"store_id": "shop-a", "login_state": "unknown"}])

    def test_a_url_shaped_explicit_id_is_skipped_not_sent(self):
        mw = _mainwin(_agent(_task(store_id="https://im.jinritemai.com/x"), _task(store_id="ok-shop")))
        items = sr.build_local_store_report(mw)
        self.assertEqual([i["store_id"] for i in items], ["ok-shop"])


class ReportTests(_Patched):
    def test_nothing_to_report_makes_no_call(self):
        with mock.patch("agent.cloud_api.store_api.store_report") as call:
            self.assertIsNone(sr.report_local_stores(_mainwin()))
        call.assert_not_called()

    def test_it_reports_under_the_heartbeat_id(self):
        mw = _mainwin(_agent(_task(store_id="shop-a")))
        with mock.patch("agent.ec_agents.vehicle_affinity.resolve_local_vehicle_id",
                        return_value="stable-1"), \
             mock.patch("agent.cloud_api.store_api.store_report",
                        return_value={"accepted": 1}) as call:
            self.assertEqual(sr.report_local_stores(mw), {"accepted": 1})
        vid, items = call.call_args.args
        self.assertEqual(vid, "stable-1")
        self.assertEqual(items[0]["store_id"], "shop-a")

    def test_a_store_recorded_here_but_not_running_is_released(self):
        # Moved away, or this process restarted without it: the machine taking
        # it over waits for exactly this release.
        self.snapshot = {"stores": {
            "gone": {"reported": "stable-1"},
            "shop-a": {"reported": "stable-1"},
            "elsewhere": {"reported": "other-pc"},
        }}
        mw = _mainwin(_agent(_task(store_id="shop-a")))
        with mock.patch("agent.ec_agents.vehicle_affinity.resolve_local_vehicle_id",
                        return_value="stable-1"),              mock.patch("agent.cloud_api.store_api.store_report",
                        return_value={"accepted": 2}) as call:
            sr.report_local_stores(mw)
        items = call.call_args.args[1]
        self.assertIn({"store_id": "gone", "running": False}, items)
        self.assertFalse(any(i.get("store_id") == "elsewhere" for i in items),
                         "never release another machine's store")
        self.assertTrue(any(i.get("store_id") == "shop-a" and i.get("running") is not False
                            for i in items))

    def test_nothing_running_and_nothing_to_release_makes_no_call(self):
        self.snapshot = {"stores": {"x": {"reported": "other-pc"}}}
        with mock.patch("agent.ec_agents.vehicle_affinity.resolve_local_vehicle_id",
                        return_value="stable-1"),              mock.patch("agent.cloud_api.store_api.store_report") as call:
            self.assertIsNone(sr.report_local_stores(_mainwin(_agent(_task(store_id="a"), here=False))))
        call.assert_not_called()

    def test_a_signed_out_session_does_not_raise(self):
        from agent.cloud_api.store_api import StoreApiUnavailable
        mw = _mainwin(_agent(_task(store_id="shop-a")))
        with mock.patch("agent.ec_agents.vehicle_affinity.resolve_local_vehicle_id",
                        return_value="stable-1"), \
             mock.patch("agent.cloud_api.store_api.store_report",
                        side_effect=StoreApiUnavailable("sign in first")):
            self.assertIsNone(sr.report_local_stores(mw))


if __name__ == "__main__":
    unittest.main()
