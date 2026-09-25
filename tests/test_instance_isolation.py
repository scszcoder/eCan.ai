"""Multi-instance isolation — one process per store on one machine.

The single-instance mutex is a *gate*: opening it permits a second process.
That is only safe once the data home and the IPC port are already separate, or
two instances share one ecan.db and truncate each other's eCan.log. These
tests pin both halves of that invariant, and above all pin the default: with
``ECAN_INSTANCE_ID`` unset, every existing install must behave exactly as
before — same path, same port 4668, same mutex name.
"""

import os
import unittest
from unittest.mock import patch

from config.instance import (
    instance_id, instance_suffix, instance_port, instance_log_filename, ENV_VAR,
)


def _env(value):
    """Set ECAN_INSTANCE_ID, or remove it when value is None."""
    if value is None:
        return patch.dict(os.environ, {}, clear=False)
    return patch.dict(os.environ, {ENV_VAR: value}, clear=False)


class _NoInstance:
    """Guarantee ECAN_INSTANCE_ID is absent regardless of the ambient env."""

    def __enter__(self):
        self._saved = os.environ.pop(ENV_VAR, None)

    def __exit__(self, *exc):
        if self._saved is not None:
            os.environ[ENV_VAR] = self._saved
        return False


class LogFilenameTests(unittest.TestCase):
    """One file per worker, in the folder the support zip already collects."""

    def test_default_instance_keeps_the_plain_name(self):
        with _NoInstance():
            self.assertEqual(instance_log_filename("eCan.log"), "eCan.log")

    def test_a_worker_gets_its_own_file_beside_it(self):
        with _env("store_b"):
            self.assertEqual(instance_log_filename("eCan.log"), "eCan-store_b.log")

    def test_the_extension_is_preserved(self):
        # It has to stay a .log, or the zip and every viewer stop recognising it.
        with _env("w1"):
            self.assertTrue(instance_log_filename("eCan.log").endswith(".log"))

    def test_a_name_without_an_extension(self):
        with _env("w1"):
            self.assertEqual(instance_log_filename("eCan"), "eCan-w1")

    def test_only_the_last_dot_is_treated_as_the_extension(self):
        with _env("w1"):
            self.assertEqual(instance_log_filename("a.b.log"), "a.b-w1.log")


class DefaultInstanceIsUnchangedTests(unittest.TestCase):
    """Nothing may move for an install that never sets the variable."""

    def test_the_log_filename_is_unchanged(self):
        with _NoInstance():
            self.assertEqual(instance_log_filename("eCan.log"), "eCan.log")

    def test_id_and_suffix_are_empty(self):
        with _NoInstance():
            self.assertEqual(instance_id(), "")
            self.assertEqual(instance_suffix(), "")

    def test_port_is_exactly_the_base(self):
        with _NoInstance():
            self.assertEqual(instance_port(4668), 4668)

    def test_blank_and_whitespace_count_as_unset(self):
        for raw in ("", "   ", "\t"):
            with _env(raw):
                self.assertEqual(instance_id(), "", repr(raw))
                self.assertEqual(instance_port(4668), 4668, repr(raw))


class InstanceIdSanitizingTests(unittest.TestCase):
    def test_keeps_safe_characters(self):
        with _env("store_b-2"):
            self.assertEqual(instance_id(), "store_b-2")

    def test_replaces_path_and_mutex_hostile_characters(self):
        # The id becomes a directory name AND a Windows mutex name; a stray
        # backslash would silently create a nested directory or a global
        # namespace entry.
        with _env("store b/2\\x:y"):
            got = instance_id()
            for bad in (" ", "/", "\\", ":"):
                self.assertNotIn(bad, got)

    def test_strips_leading_and_trailing_separators(self):
        with _env("--store--"):
            self.assertEqual(instance_id(), "store")

    def test_caps_the_length(self):
        with _env("x" * 200):
            self.assertLessEqual(len(instance_id()), 32)

    def test_an_id_of_only_unsafe_characters_degrades_to_default(self):
        # Better to run as the default instance than to build a path from "-".
        with _env("///"):
            self.assertEqual(instance_id(), "")


class InstancePortTests(unittest.TestCase):
    def test_named_instance_moves_off_the_base(self):
        with _env("store_b"):
            self.assertNotEqual(instance_port(4668), 4668)

    def test_port_is_stable_across_calls(self):
        # Must not use hash(): it is salted per process, so the same instance
        # would land on a different port every launch.
        with _env("store_b"):
            self.assertEqual(instance_port(4668), instance_port(4668))

    def test_different_instances_usually_differ(self):
        ports = set()
        for name in ("store_a", "store_b", "store_c", "store_d"):
            with _env(name):
                ports.add(instance_port(4668))
        self.assertGreater(len(ports), 1)

    def test_stays_in_a_predictable_block(self):
        for name in ("a", "store_b", "z" * 32):
            with _env(name):
                p = instance_port(4668)
                self.assertGreater(p, 4668)
                self.assertLessEqual(p, 4668 + 199)


class ExplicitPortOverrideWinsTests(unittest.TestCase):
    def test_env_port_beats_the_derived_one(self):
        from agent.mcp.config import get_local_port
        with _env("store_b"), patch.dict(
            os.environ, {"ECAN_LOCAL_SERVER_PORT": "5000"}, clear=False
        ):
            self.assertEqual(get_local_port(), 5000)

    def test_derived_port_is_used_when_no_override(self):
        from agent.mcp.config import get_local_port
        saved = os.environ.pop("ECAN_LOCAL_SERVER_PORT", None)
        try:
            with _env("store_b"):
                self.assertEqual(get_local_port(), instance_port(4668))
        finally:
            if saved is not None:
                os.environ["ECAN_LOCAL_SERVER_PORT"] = saved


class WiringTests(unittest.TestCase):
    """The three consumers must actually consult the instance module.

    Source-level assertions rather than runtime ones: these live in app
    startup (appdata resolution, mutex acquisition) which cannot be exercised
    without booting Qt, and the cost of a silent regression here is two
    instances sharing one database.
    """

    def _read(self, rel):
        from pathlib import Path
        return Path(rel).read_text(encoding="utf-8")

    def test_the_data_home_is_NOT_instance_scoped(self):
        # Workers are workers of one app. Scoping the data home would give each
        # its own database, its own browser profiles and its own login, and
        # hide all of it from the GUI. An earlier revision did scope it, which
        # was right only while instances were independent apps.
        src = self._read("config/app_info.py")
        self.assertNotIn('f"instance-{_inst}"', src)
        self.assertNotIn("instance appdata path", src)

    def test_the_log_file_is_instance_scoped(self):
        # The one thing that genuinely cannot be shared: concurrent writers
        # from several processes corrupt each other's lines.
        src = self._read("utils/logger_helper.py")
        self.assertIn("instance_log_filename(APP_LOG_FILE)", src)

    def test_mutex_and_file_lock_are_instance_scoped(self):
        src = self._read("utils/single_instance.py")
        self.assertIn("from config.instance import instance_suffix", src)
        # Windows named mutex — the primary gate.
        self.assertIn(".AI.SingleInstance{instance_suffix()}", src)
        # The cross-platform file lock is the gate everywhere else.
        self.assertIn('app_id = f"{_app_short_name}.AI{instance_suffix()}"', src)

    def test_local_port_is_instance_scoped(self):
        src = self._read("agent/mcp/config.py")
        self.assertIn("from config.instance import instance_port", src)

    def test_local_server_no_longer_hardcodes_the_port(self):
        src = self._read("gui/LocalServer.py")
        self.assertNotIn("def _run_starlette(self, port=4668)", src)
        self.assertNotIn("def start_local_server_early(port: int = 4668)", src)

    def test_the_port_the_server_actually_binds_follows_the_instance(self):
        # LocalServer binds main_win.get_local_server_port(), which reads this
        # setting -- NOT _run_starlette's default. A literal fallback here
        # would make a second instance collide on 4668 and fail to start.
        src = self._read("gui/config/general_settings.py")
        self.assertIn("str(get_local_port())", src)
        self.assertNotIn('self._data.get("local_server_port", "4668")', src)

    def test_ui_url_carries_the_live_port(self):
        # The page loads from file://, so it cannot infer the port from its
        # origin and would otherwise use a build-time constant.
        src = self._read("gui/core/web_engine_view.py")
        self.assertIn('q.addQueryItem("port"', src)
        ts = self._read("gui_v2/src/services/api/api-router.ts")
        self.assertIn("new URLSearchParams(window.location.search).get('port')", ts)


if __name__ == "__main__":
    unittest.main()
