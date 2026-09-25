"""A store's login on the machine that runs it: the local store record wins; a foreign id fails closed."""

import importlib
import unittest
from types import SimpleNamespace
from unittest import mock

# Same import order as tests/unit/test_task_browser_identity.py: prep_skills_run
# is part of an import cycle that build_helpers resolves.
from agent.ec_skills.browser_node import build_helpers  # noqa: F401


def _psr():
    return importlib.import_module("agent.ec_skills.prep_skills_run")


class LocalizeTests(unittest.TestCase):
    def test_this_machines_store_record_wins(self):
        psr = _psr()
        with mock.patch.object(psr, "_local_store_profile", return_value="b-login"):
            out = psr._localize_browser_identity({"store_id": "s"}, {"browser_profile_id": "a-login"})
        self.assertEqual(out["browser_profile_id"], "b-login")

    def test_a_store_task_without_identity_gets_the_local_profile(self):
        psr = _psr()
        with mock.patch.object(psr, "_local_store_profile", return_value="b-login"):
            self.assertEqual(psr._localize_browser_identity({"store_id": "s"}, None),
                             {"browser_profile_id": "b-login"})

    def test_a_profile_from_another_machine_is_kept_so_the_launch_fails_closed(self):
        # Dropping it would fall back to the default browser -- possibly
        # another store's logged-in Chrome.
        psr = _psr()
        with mock.patch.object(psr, "_local_store_profile", return_value=""), \
             mock.patch.object(psr, "_profile_exists", return_value=False), \
             mock.patch.object(psr.logger, "warning") as warn:
            out = psr._localize_browser_identity({"store_id": "s"}, {"browser_profile_id": "a-login"})
        self.assertEqual(out["browser_profile_id"], "a-login")
        warn.assert_called_once()

    def test_a_local_profile_is_kept_as_is(self):
        psr = _psr()
        with mock.patch.object(psr, "_local_store_profile", return_value=""), \
             mock.patch.object(psr, "_profile_exists", return_value=True):
            out = psr._localize_browser_identity({}, {"browser_profile_id": "mine", "cdp_port": "9230"})
        self.assertEqual(out, {"browser_profile_id": "mine", "cdp_port": "9230"})

    def test_apply_task_vars_seeds_the_localized_identity(self):
        psr = _psr()
        task = SimpleNamespace(name="t", metadata={"task_vars": {"store_id": "s"},
                                                   "browser_identity": {"browser_profile_id": "a-login"}})
        state = {}
        with mock.patch.object(psr, "_local_store_profile", return_value="b-login"):
            psr.apply_task_vars(task, state)
        self.assertEqual(state["attributes"]["browser_profile_id"], "b-login")


class HeartbeatForAllRolesTests(unittest.TestCase):
    def test_non_commanders_heartbeat_and_run_store_placement(self):
        from pathlib import Path
        src = Path("gui/MainGUI.py").read_text(encoding="utf-8")
        i = src.index('if "Commander" in self.host_role:\n                    # Skip cloud heartbeat')
        branch = src[i:i + 3000]
        self.assertIn("elif time.time() >= self._cloud_vehicle_report_backoff_until:", branch)
        self.assertIn("await self._cloud_heartbeat_and_placement(self_report)", branch)


if __name__ == "__main__":
    unittest.main()
