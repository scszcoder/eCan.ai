"""Each store runs in its own logged-in browser: store profile -> task identity -> fingerprint browser."""

import asyncio
import enum
import os
import unittest
from types import SimpleNamespace
from unittest import mock

import cli.deploy.commands as cmds
from agent.ec_skills.browser_node.build_helpers import browser_type_for_identity


class BT(enum.Enum):
    CHROME = "chrome"
    FINGERPRINT = "fingerprint"
    ADSPOWER = "adspower"


class BrowserTypeRuleTests(unittest.TestCase):
    def test_a_task_naming_a_profile_runs_in_the_fingerprint_browser(self):
        # The 飞鸽 skills attach a plain Chrome; without this every store
        # would share the one default browser.
        self.assertEqual(browser_type_for_identity(BT.CHROME, "shop-a-login", BT), (BT.FINGERPRINT, True))

    def test_no_profile_changes_nothing(self):
        self.assertEqual(browser_type_for_identity(BT.CHROME, "", BT), (BT.CHROME, False))
        self.assertEqual(browser_type_for_identity(BT.CHROME, None, BT), (BT.CHROME, False))

    def test_vendor_browsers_keep_their_own_meaning_of_the_id(self):
        self.assertEqual(browser_type_for_identity(BT.ADSPOWER, "env-123", BT), (BT.ADSPOWER, False))
        self.assertEqual(browser_type_for_identity(BT.FINGERPRINT, "p", BT), (BT.FINGERPRINT, False))

    def test_both_browser_paths_apply_the_rule(self):
        from pathlib import Path
        for f in ("agent/ec_skills/browser_node/build_helpers.py", "agent/ec_skills/browser_node/session.py"):
            src = Path(f).read_text(encoding="utf-8")
            self.assertIn("browser_type_for_identity(", src, f)


class DeployIdentityTests(unittest.TestCase):
    def _ctx(self, rec):
        ctx = SimpleNamespace(db=SimpleNamespace(store_service=SimpleNamespace(get_store=lambda sid: rec)))
        return ctx

    def test_the_stores_profile_becomes_the_tasks_identity(self):
        log = []
        out = cmds._store_browser_identity(self._ctx({"browser_profile_id": "p1"}), "shop-a", log)
        self.assertEqual(out, {"browser_profile_id": "p1"})

    def test_a_store_without_a_profile_says_so(self):
        log = []
        self.assertEqual(cmds._store_browser_identity(self._ctx({"browser_profile_id": None}), "s", log), {})
        self.assertTrue(any("no login profile" in line for line in log))

    def test_the_deploy_writes_it_onto_every_task(self):
        from pathlib import Path
        src = Path("cli/deploy/commands.py").read_text(encoding="utf-8")
        i = src.index("def _add_task(")
        body = src[i:i + 900]
        self.assertIn('settings["browser_identity"] = dict(identity)', body)


class WorkerNeverGuessesItsBrowserTests(unittest.TestCase):
    def test_no_9228_probe_inside_a_store_worker(self):
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import tab_lifecycle as tl
        session = SimpleNamespace(cdp_url=None, browser_profile=None)
        with mock.patch.dict(os.environ, {"ECAN_WORKER_KEY": "shop-b"}), \
             mock.patch("urllib.request.urlopen") as probe:
            url = asyncio.run(tl._resolve_cdp_url(session))
        self.assertEqual(url, "")
        probe.assert_not_called()

    def test_a_single_store_install_still_probes(self):
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import tab_lifecycle as tl
        session = SimpleNamespace(cdp_url=None, browser_profile=None)
        env = {k: v for k, v in os.environ.items() if k != "ECAN_WORKER_KEY"}
        with mock.patch.dict(os.environ, env, clear=True), \
             mock.patch("urllib.request.urlopen", side_effect=OSError("nothing on 9228")) as probe:
            asyncio.run(tl._resolve_cdp_url(session))
        probe.assert_called_once()


if __name__ == "__main__":
    unittest.main()
