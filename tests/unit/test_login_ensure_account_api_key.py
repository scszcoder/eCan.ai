"""A freshly-signed-in CN account must end up with a usable eCanAI proxy key.

Field complaint (2026-10-14): a new account signs in, the ``accounts`` row is
provisioned (``_ensure_cloud_account``), but the per-account API key is never
minted/synced, so the ``ecanai`` provider has no bearer and every proxied LLM
call fails. ``cloudbase_handler`` now mirrors the Account-page get-or-create +
sync at login.

These pin the branch logic of ``_sync_account_api_key_if_missing`` (the
testable core of the background safety net) and that the login response wires
the safety net in next to ``_ensure_cloud_account``.
"""

import re
import unittest
from pathlib import Path
from unittest.mock import patch

import gui.ipc.w2p_handlers.cloudbase_handler as h

import agent.cloud_api.api_keys as api_keys
import gui.ipc.w2p_handlers.user_handler as user_handler
import gui.manager.provider_settings_helper as provider_helper


class _Win:  # a stand-in MainWindow; the helper only passes it through
    pass


class SyncIfMissingBranchTests(unittest.TestCase):
    def setUp(self):
        self.synced = []
        patcher = patch.object(
            user_handler, "_cn_session_token", lambda mw: "SESSION_TOK"
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        def _sync(key, main_window=None):
            self.synced.append(key)
            return True, None

        p2 = patch.object(provider_helper, "sync_account_api_key_to_ecanai", _sync)
        p2.start()
        self.addCleanup(p2.stop)

    def test_already_synced_makes_no_network_call(self):
        with patch.object(api_keys, "get_local_synced_api_key", return_value="sk-local"), \
             patch.object(api_keys, "ensure_api_key") as ensure:
            status = h._sync_account_api_key_if_missing(_Win())
        self.assertEqual(status, "present")
        ensure.assert_not_called()
        self.assertEqual(self.synced, [], "must not re-sync when a key is present")

    def test_created_key_is_synced(self):
        with patch.object(api_keys, "get_local_synced_api_key", return_value=""), \
             patch.object(api_keys, "ensure_api_key",
                          return_value={"apiKey": "sk-new", "created": True}):
            status = h._sync_account_api_key_if_missing(_Win())
        self.assertEqual(status, "created")
        self.assertEqual(self.synced, ["sk-new"])

    def test_existing_cloud_key_fetched_and_synced(self):
        # reinstall case: cloud still has the key, local copy was lost
        with patch.object(api_keys, "get_local_synced_api_key", return_value=""), \
             patch.object(api_keys, "ensure_api_key",
                          return_value={"apiKey": "sk-old", "created": False}):
            status = h._sync_account_api_key_if_missing(_Win())
        self.assertEqual(status, "fetched")
        self.assertEqual(self.synced, ["sk-old"])

    def test_no_key_from_server_syncs_nothing(self):
        with patch.object(api_keys, "get_local_synced_api_key", return_value=""), \
             patch.object(api_keys, "ensure_api_key",
                          return_value={"apiKey": "", "created": False}):
            status = h._sync_account_api_key_if_missing(_Win())
        self.assertEqual(status, "no_key")
        self.assertEqual(self.synced, [])

    def test_sync_failure_is_reported(self):
        with patch.object(api_keys, "get_local_synced_api_key", return_value=""), \
             patch.object(api_keys, "ensure_api_key",
                          return_value={"apiKey": "sk-new", "created": True}), \
             patch.object(provider_helper, "sync_account_api_key_to_ecanai",
                          return_value=(False, "lightrag restart failed")):
            status = h._sync_account_api_key_if_missing(_Win())
        self.assertTrue(status.startswith("sync_failed:"))
        self.assertIn("lightrag restart failed", status)


class LoginWiringTests(unittest.TestCase):
    def test_login_response_calls_ensure_account_api_key(self):
        src = Path("gui/ipc/w2p_handlers/cloudbase_handler.py").read_text(encoding="utf-8")
        body = re.search(
            r"def _build_login_response\(.*?(?=\ndef |\Z)", src, re.DOTALL
        )
        self.assertTrue(body, "_build_login_response body must be locatable")
        self.assertIn("_ensure_account_api_key()", body.group(0),
                      "login must fire the API-key safety net next to _ensure_cloud_account")


if __name__ == "__main__":
    unittest.main()
