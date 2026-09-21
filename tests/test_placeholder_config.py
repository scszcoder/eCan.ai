"""过渡话术 (placeholder) per-store GUI config — 2026-09-21.

The stand-by line used to be editable only by hand-writing
``<user_data_home>/ecan/placeholder_texts.json``.  It is now editable per store
from the bundle's own config panel, and the GUI deliberately outranks the
``ECAN_FEIGE_PLACEHOLDER_*`` env vars that Fast Deploy seeds — otherwise a
店主 who switches the feature off in the panel keeps getting stand-by lines
because a support engineer once exported the env var on that machine.

These tests pin that precedence, the validation the panel and the runtime must
agree on, and the store stamp the sweeper reads when a placeholder fires.
"""

from __future__ import annotations

import importlib
import sys
import unittest
from unittest import mock

CFG_MOD = (
    "agent.ec_skills.browser_use_extension.hooks.external.feige_chat.placeholder_config"
)
TIMER_MOD = (
    "agent.ec_skills.browser_use_extension.hooks.external.feige_chat.placeholder_timer"
)

ENV_TIMEOUT = "ECAN_FEIGE_PLACEHOLDER_TIMEOUT_S"
ENV_STORE = "ECAN_FEIGE_STORE_ID"


def _fresh(mod_name):
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = _fresh(CFG_MOD)
        self.cfg.invalidate()

    def _fake_plugin_module(self, name, fake):
        """Patch the submodule ATTRIBUTE on the package.

        ``from agent.ec_skills.browser_use_extension import plugin_storage``
        resolves via getattr on the already-imported package, so patching
        sys.modules is order-dependent and silently does nothing once the
        attribute exists.
        """
        import importlib
        import agent.ec_skills.browser_use_extension as _pkg
        # Namespace package: the attribute only exists once the submodule has
        # been imported at least once, so import it before patching.
        importlib.import_module(f"agent.ec_skills.browser_use_extension.{name}")
        return mock.patch.object(_pkg, name, fake)

    def _tiers(self, account=None, store=None):
        """Patch the two tier readers (plugin config + plugin KV)."""
        return mock.patch.multiple(
            self.cfg,
            _account_config=mock.Mock(return_value=dict(account or {})),
            _store_config=mock.Mock(return_value=dict(store or {})),
        )


class PrecedenceTests(_Base):
    def test_no_gui_config_changes_nothing(self) -> None:
        """An install that never opens the panel must behave exactly as before."""
        with self._tiers(), mock.patch.dict("os.environ", {}, clear=False):
            sys.modules["os"].environ.pop(ENV_TIMEOUT, None)
            self.assertIsNone(self.cfg.texts_override(""))
            self.assertIsNone(self.cfg.timeout_override(""))

    def test_account_texts_used_when_no_store_override(self) -> None:
        with self._tiers(account={"placeholder_texts": ["稍等一下"]}):
            self.assertEqual(self.cfg.texts_override("S1"), ["稍等一下"])

    def test_store_override_wins_over_account(self) -> None:
        with self._tiers(
            account={"placeholder_texts": ["account line"]},
            store={"placeholder_texts": ["store line"]},
        ):
            self.assertEqual(self.cfg.texts_override("S1"), ["store line"])

    def test_gui_timeout_wins_over_env(self) -> None:
        with self._tiers(account={"placeholder_timeout_s": 12}), mock.patch.dict(
            "os.environ", {ENV_TIMEOUT: "6"}, clear=False
        ):
            self.assertEqual(self.cfg.timeout_override("S1"), 12.0)
            self.assertEqual(self.cfg.effective_timeout_s("S1"), 12.0)

    def test_gui_switch_off_beats_env(self) -> None:
        """The whole point of the decision: Save must not be silently ignored."""
        with self._tiers(account={"placeholder_enabled": False}), mock.patch.dict(
            "os.environ", {ENV_TIMEOUT: "6"}, clear=False
        ):
            self.assertEqual(self.cfg.timeout_override("S1"), 0.0)
            self.assertEqual(self.cfg.effective_timeout_s("S1"), 0.0)

    def test_env_still_used_when_gui_is_silent(self) -> None:
        with self._tiers(), mock.patch.dict(
            "os.environ", {ENV_TIMEOUT: "6"}, clear=False
        ):
            self.assertIsNone(self.cfg.timeout_override("S1"))
            self.assertEqual(self.cfg.effective_timeout_s("S1"), 6.0)

    def test_enabled_without_a_deadline_uses_documented_default(self) -> None:
        """Switched on but no seconds typed anywhere — 0 would mean 'off'."""
        with self._tiers(account={"placeholder_enabled": True}), mock.patch.dict(
            "os.environ", {}, clear=False
        ):
            sys.modules["os"].environ.pop(ENV_TIMEOUT, None)
            self.assertEqual(
                self.cfg.timeout_override("S1"), self.cfg.DEFAULT_ENABLED_TIMEOUT_S
            )

    def test_store_enable_overrides_account_disable(self) -> None:
        with self._tiers(
            account={"placeholder_enabled": False},
            store={"placeholder_enabled": True, "placeholder_timeout_s": 15},
        ):
            self.assertEqual(self.cfg.timeout_override("S1"), 15.0)

    def test_account_reads_user_choices_not_manifest_defaults(self) -> None:
        """``plugin_config.get`` (user overrides), never ``merged`` — a manifest
        default is not a user choice and must not outrank the operator's env."""
        fake_cfg = mock.Mock()
        fake_cfg.get.return_value = {"placeholder_texts": ["from user file"]}
        fake_cfg.merged.side_effect = AssertionError("must not consult merged()")
        with self._fake_plugin_module("plugin_config", fake_cfg):
            with mock.patch.object(self.cfg, "_store_config", return_value={}):
                self.assertEqual(self.cfg.texts_override("S1"), ["from user file"])
        fake_cfg.get.assert_called_with("feige_chat")


class ValidationTests(_Base):
    def test_sanitize_mirrors_the_loader_rules(self) -> None:
        raw = ["  keep  ", "", "keep", None, "second", 7, "third"]
        self.assertEqual(self.cfg.sanitize_texts(raw), ["keep", "second", "third"])

    def test_sanitize_caps_at_five(self) -> None:
        raw = [f"line {i}" for i in range(9)]
        self.assertEqual(len(self.cfg.sanitize_texts(raw)), self.cfg.MAX_TEXTS)

    def test_sanitize_rejects_unusable_input(self) -> None:
        for raw in (None, {}, "a string", [], ["", "   "], [1, 2]):
            self.assertIsNone(self.cfg.sanitize_texts(raw))

    def test_blank_store_key_falls_back_to_account(self) -> None:
        with self._tiers(account={"placeholder_texts": ["acct"]}) as _:
            self.assertEqual(self.cfg.texts_override(""), ["acct"])


class StoreKeyTests(_Base):
    def test_env_override_wins(self) -> None:
        with mock.patch.dict("os.environ", {ENV_STORE: "shop-42"}, clear=False):
            self.assertEqual(self.cfg.current_store_key(), "shop-42")

    def test_scope_store_key_beats_agent_id(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=False):
            sys.modules["os"].environ.pop(ENV_STORE, None)
            with mock.patch.object(
                self.cfg, "_scope", return_value={"store_key": "S9", "agent_id": "A1"}
            ):
                self.assertEqual(self.cfg.current_store_key(), "S9")

    def test_agent_id_is_the_store_today(self) -> None:
        """Fast Deploy creates one agent per store, so agent_id is the key
        until a platform stamp derived from store_url lands."""
        with mock.patch.dict("os.environ", {}, clear=False):
            sys.modules["os"].environ.pop(ENV_STORE, None)
            with mock.patch.object(self.cfg, "_scope", return_value={"agent_id": "A1"}):
                self.assertEqual(self.cfg.current_store_key(), "A1")

    def test_no_run_context_means_account_wide(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=False):
            sys.modules["os"].environ.pop(ENV_STORE, None)
            with mock.patch.object(self.cfg, "_scope", return_value={}):
                self.assertEqual(self.cfg.current_store_key(), "")


class CacheTests(_Base):
    def test_invalidate_picks_up_a_save(self) -> None:
        """Saving in the panel must take effect without restarting the app."""
        account = {"placeholder_texts": ["before"]}
        with mock.patch.object(self.cfg, "_store_config", return_value={}):
            with mock.patch.object(
                self.cfg, "_account_config", side_effect=lambda: dict(account)
            ):
                self.assertEqual(self.cfg.texts_override("S1"), ["before"])
                account["placeholder_texts"] = ["after"]
                self.cfg.invalidate()
                self.assertEqual(self.cfg.texts_override("S1"), ["after"])

    def test_tier_failure_degrades_to_none(self) -> None:
        """No plugin system (cloud worker, raw-path load) → legacy behaviour."""
        with mock.patch.object(
            self.cfg, "_account_config", side_effect=RuntimeError("no registry")
        ):
            self.assertIsNone(self.cfg.texts_override("S1"))
            self.assertIsNone(self.cfg.timeout_override("S1"))


class StoreRegistryTests(_Base):
    """The panel is an iframe: it can read neither the process env nor the
    pre-GUI text file, so the runtime mirrors both into the store registry.
    If this shape changes, the picker and its hints go blank."""

    def test_registry_entry_carries_what_the_panel_needs(self) -> None:
        written = {}
        fake_storage = mock.Mock()
        fake_storage.get.return_value = {}
        fake_storage.set.side_effect = lambda b, k, v: written.update({k: v})
        with self._fake_plugin_module("plugin_storage", fake_storage):
            with mock.patch.object(self.cfg, "current_store_key", return_value="S1"):
                with mock.patch.object(self.cfg, "current_store_label", return_value="前台小张"):
                    with mock.patch.object(
                        self.cfg, "_legacy_texts", return_value=["旧文件话术"]
                    ):
                        with mock.patch.dict(
                            "os.environ", {ENV_TIMEOUT: "6"}, clear=False
                        ):
                            self.cfg.note_active_store()
        entry = written["stores"]["S1"]
        self.assertEqual(entry["label"], "前台小张")
        self.assertEqual(entry["env_timeout_s"], 6.0)
        self.assertEqual(entry["legacy_texts"], ["旧文件话术"])
        self.assertIn("last_seen", entry)

    def test_registry_written_once_per_process(self) -> None:
        """arm() calls this on the dispatch path — it must not write per turn."""
        fake_storage = mock.Mock()
        fake_storage.get.return_value = {}
        with self._fake_plugin_module("plugin_storage", fake_storage):
            with mock.patch.object(self.cfg, "current_store_key", return_value="S1"):
                for _ in range(5):
                    self.cfg.note_active_store()
        self.assertEqual(fake_storage.set.call_count, 1)

    def test_no_run_context_writes_nothing(self) -> None:
        fake_storage = mock.Mock()
        with self._fake_plugin_module("plugin_storage", fake_storage):
            with mock.patch.object(self.cfg, "current_store_key", return_value=""):
                self.cfg.note_active_store()
        fake_storage.set.assert_not_called()

    def test_registry_failure_never_reaches_the_reply_path(self) -> None:
        fake_storage = mock.Mock()
        fake_storage.get.side_effect = RuntimeError("disk full")
        with self._fake_plugin_module("plugin_storage", fake_storage):
            with mock.patch.object(self.cfg, "current_store_key", return_value="S1"):
                self.cfg.note_active_store()   # must not raise


class TimerWiringTests(unittest.TestCase):
    """The sweeper fires on its own thread, where the run's ContextVar scope is
    gone — so the store has to be stamped on the entry when the turn is armed."""

    def setUp(self) -> None:
        self.cfg = _fresh(CFG_MOD)
        self.cfg.invalidate()
        self.timer = _fresh(TIMER_MOD)
        self.timer._REGISTRY.clear()
        self.timer._PLACEHOLDER_TEXTS_CACHE = None

    def tearDown(self) -> None:
        self.timer._REGISTRY.clear()

    def test_arm_stamps_the_store(self) -> None:
        with mock.patch.object(self.timer, "_current_store_key", return_value="S7"):
            self.timer.arm("客户01", "msg-1", timeout_s=30.0)
        entry = self.timer._REGISTRY[self.timer._make_key("客户01", "msg-1")]
        self.assertEqual(entry.store_key, "S7")

    def test_rearm_keeps_a_known_store(self) -> None:
        with mock.patch.object(self.timer, "_current_store_key", return_value="S7"):
            self.timer.arm("客户01", "msg-1", timeout_s=30.0)
        with mock.patch.object(self.timer, "_current_store_key", return_value=""):
            self.timer.arm("客户01", "msg-1", timeout_s=30.0)
        entry = self.timer._REGISTRY[self.timer._make_key("客户01", "msg-1")]
        self.assertEqual(entry.store_key, "S7")

    def test_texts_resolve_per_store(self) -> None:
        with mock.patch.object(
            self.cfg, "_store_config",
            side_effect=lambda key: {"placeholder_texts": [f"line for {key}"]} if key else {},
        ):
            with mock.patch.object(self.cfg, "_account_config", return_value={}):
                self.assertEqual(self.timer._get_placeholder_texts("S7"), ["line for S7"])
                self.cfg.invalidate()
                self.assertEqual(self.timer._get_placeholder_texts("S8"), ["line for S8"])

    def test_no_gui_config_still_uses_the_legacy_file_tier(self) -> None:
        with mock.patch.object(self.cfg, "_store_config", return_value={}):
            with mock.patch.object(self.cfg, "_account_config", return_value={}):
                with mock.patch.object(
                    self.timer, "_load_placeholder_texts_from_file",
                    return_value=["from the mt048A file"],
                ):
                    self.assertEqual(
                        self.timer._get_placeholder_texts("S7"), ["from the mt048A file"]
                    )


if __name__ == "__main__":
    unittest.main()
