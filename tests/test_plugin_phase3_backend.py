"""
Phase 3 backend tests: plugin_storage, plugin_config, plugin_gui_server.
"""

from __future__ import annotations

import json
import os
import sys
import textwrap
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.ec_skills.browser_use_extension import (
    plugin_config,
    plugin_gui_server,
    plugin_installer,
    plugin_registry,
    plugin_storage,
)


def _write_bundle_with_gui(parent: Path, name: str) -> Path:
    bd = parent / name
    bd.mkdir(parents=True, exist_ok=True)
    (bd / "hook.yaml").write_text(textwrap.dedent(f"""\
        api_version: 1
        kind: hook_bundle
        bundle: {name}
        version: 1.0.0
        author: "test"
        description: "demo"
        config:
          cooldown_ms: 1500
        config_schema:
          type: object
          properties:
            cooldown_ms:
              type: integer
              minimum: 0
              default: 1500
            quick_replies:
              type: object
              additionalProperties:
                type: string
        gui:
          host_api_version: 1
          slots:
            config_panel:
              entrypoint: "gui/config.html"
              height: 480
            node_config:
              entrypoint: "node.html"
              height: 320
          permissions:
            storage_namespace: {name}
            bridge_methods:
              - config.get
              - storage.get
        hooks:
          - name: demo
            entrypoint: "hooks.py:Demo"
            stage: on_event_normalized
            tier: 1
            priority: 50
    """), encoding="utf-8")
    (bd / "hooks.py").write_text(
        "class Demo:\n"
        "    def __init__(self, config=None, manifest=None): pass\n"
        "    async def run(self, ctx, payload): return None\n",
        encoding="utf-8",
    )
    gui = bd / "gui"
    gui.mkdir(exist_ok=True)
    (gui / "config.html").write_text(
        "<!doctype html><html><body><h1>config</h1></body></html>", encoding="utf-8"
    )
    (gui / "node.html").write_text(
        "<!doctype html><html><body>node</body></html>", encoding="utf-8"
    )
    (gui / "secret.txt").write_text("not html", encoding="utf-8")  # disallowed ext
    return bd


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
class PluginStorageTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._appdata = Path(self._tmp.name) / "appdata"
        self._workspace = Path(self._tmp.name) / "workspace"
        self._appdata.mkdir(parents=True, exist_ok=True)
        self._workspace.mkdir(parents=True, exist_ok=True)
        self._envi_patcher = patch(
            "config.envi.getECBotDataHome", return_value=str(self._appdata),
        )
        self._envi_patcher.start()
        src = _write_bundle_with_gui(self._workspace, "stg_demo")
        plugin_installer.install_from_dir(src)

    def tearDown(self):
        self._envi_patcher.stop()
        self._tmp.cleanup()

    def test_get_missing_returns_default(self):
        self.assertIsNone(plugin_storage.get("stg_demo", "k"))
        self.assertEqual(plugin_storage.get("stg_demo", "k", "def"), "def")

    def test_set_and_get_roundtrip(self):
        plugin_storage.set("stg_demo", "foo", {"a": 1, "b": [1, 2, 3]})
        self.assertEqual(plugin_storage.get("stg_demo", "foo"), {"a": 1, "b": [1, 2, 3]})

    def test_keys_returns_sorted(self):
        plugin_storage.set("stg_demo", "zeta", 1)
        plugin_storage.set("stg_demo", "alpha", 1)
        self.assertEqual(plugin_storage.keys("stg_demo"), ["alpha", "zeta"])

    def test_delete(self):
        plugin_storage.set("stg_demo", "k", 1)
        self.assertTrue(plugin_storage.delete("stg_demo", "k"))
        self.assertFalse(plugin_storage.delete("stg_demo", "k"))

    def test_unknown_bundle_raises(self):
        with self.assertRaises(plugin_storage.StorageError):
            plugin_storage.set("nonexistent", "k", 1)

    def test_size_cap_enforced(self):
        big = "x" * (plugin_storage.MAX_STORAGE_BYTES + 10)
        with self.assertRaises(plugin_storage.StorageLimitError):
            plugin_storage.set("stg_demo", "blob", big)

    def test_non_serializable_value_raises(self):
        with self.assertRaises(plugin_storage.StorageError):
            plugin_storage.set("stg_demo", "k", object())

    def test_atomic_write_leaves_no_temp(self):
        plugin_storage.set("stg_demo", "k", 1)
        bd = Path(plugin_registry.get("stg_demo").install_path)
        leftovers = [n for n in os.listdir(bd) if n.startswith(".storage.") and n.endswith(".tmp")]
        self.assertEqual(leftovers, [])


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
class PluginConfigTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._appdata = Path(self._tmp.name) / "appdata"
        self._workspace = Path(self._tmp.name) / "workspace"
        self._appdata.mkdir(parents=True, exist_ok=True)
        self._workspace.mkdir(parents=True, exist_ok=True)
        self._envi_patcher = patch(
            "config.envi.getECBotDataHome", return_value=str(self._appdata),
        )
        self._envi_patcher.start()
        src = _write_bundle_with_gui(self._workspace, "cfg_demo")
        plugin_installer.install_from_dir(src)

    def tearDown(self):
        self._envi_patcher.stop()
        self._tmp.cleanup()

    def test_initial_get_returns_empty(self):
        self.assertEqual(plugin_config.get("cfg_demo"), {})

    def test_merged_includes_defaults(self):
        merged = plugin_config.merged("cfg_demo")
        self.assertEqual(merged.get("cooldown_ms"), 1500)

    def test_set_persists_and_overrides_default(self):
        result = plugin_config.set("cfg_demo", {"cooldown_ms": 3000})
        self.assertEqual(result["cooldown_ms"], 3000)
        self.assertEqual(plugin_config.merged("cfg_demo")["cooldown_ms"], 3000)

    def test_set_merges_keys(self):
        plugin_config.set("cfg_demo", {"cooldown_ms": 2000})
        plugin_config.set("cfg_demo", {"quick_replies": {"hi": "hello"}})
        cfg = plugin_config.get("cfg_demo")
        self.assertEqual(cfg["cooldown_ms"], 2000)
        self.assertEqual(cfg["quick_replies"], {"hi": "hello"})

    def test_set_rejects_bad_type(self):
        with self.assertRaises(plugin_config.ConfigValidationError):
            plugin_config.set("cfg_demo", {"cooldown_ms": "not an int"})

    def test_set_enforces_minimum(self):
        with self.assertRaises(plugin_config.ConfigValidationError):
            plugin_config.set("cfg_demo", {"cooldown_ms": -1})

    def test_object_of_strings_validates(self):
        with self.assertRaises(plugin_config.ConfigValidationError):
            plugin_config.set("cfg_demo", {"quick_replies": {"hi": 42}})

    def test_replace_overwrites(self):
        plugin_config.set("cfg_demo", {"cooldown_ms": 3000})
        plugin_config.replace("cfg_demo", {})
        self.assertEqual(plugin_config.get("cfg_demo"), {})

    def test_clear_removes_file(self):
        plugin_config.set("cfg_demo", {"cooldown_ms": 3000})
        plugin_config.clear("cfg_demo")
        self.assertEqual(plugin_config.get("cfg_demo"), {})


# ---------------------------------------------------------------------------
# GUI Server
# ---------------------------------------------------------------------------
class PluginGuiServerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._appdata = Path(self._tmp.name) / "appdata"
        self._workspace = Path(self._tmp.name) / "workspace"
        self._appdata.mkdir(parents=True, exist_ok=True)
        self._workspace.mkdir(parents=True, exist_ok=True)
        self._envi_patcher = patch(
            "config.envi.getECBotDataHome", return_value=str(self._appdata),
        )
        self._envi_patcher.start()
        src = _write_bundle_with_gui(self._workspace, "gui_demo")
        plugin_installer.install_from_dir(src)
        plugin_gui_server.start(port=0)

    def tearDown(self):
        plugin_gui_server.stop()
        self._envi_patcher.stop()
        self._tmp.cleanup()

    def _get(self, path: str) -> tuple[int, bytes, dict]:
        url = f"http://127.0.0.1:{plugin_gui_server.port()}{path}"
        req = urllib.request.Request(url)
        try:
            resp = urllib.request.urlopen(req, timeout=2.0)
            return resp.status, resp.read(), dict(resp.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read() if e.fp else b"", dict(e.headers or {})

    def test_get_gui_url_returns_url(self):
        url = plugin_gui_server.get_gui_url("gui_demo", "config_panel")
        self.assertIsNotNone(url)
        assert url is not None
        self.assertTrue(url.endswith("/p/gui_demo/config.html"))

    def test_get_gui_url_strips_leading_gui(self):
        # node_config entrypoint is "node.html" (no gui/ prefix)
        url = plugin_gui_server.get_gui_url("gui_demo", "node_config")
        self.assertIsNotNone(url)
        assert url is not None
        self.assertTrue(url.endswith("/p/gui_demo/node.html"))

    def test_get_gui_url_unknown_slot(self):
        self.assertIsNone(plugin_gui_server.get_gui_url("gui_demo", "nope"))

    def test_get_gui_url_unknown_bundle(self):
        self.assertIsNone(plugin_gui_server.get_gui_url("nope", "config_panel"))

    def test_serves_html_asset_with_csp(self):
        code, body, headers = self._get("/p/gui_demo/config.html")
        self.assertEqual(code, 200)
        self.assertIn(b"<h1>config</h1>", body)
        self.assertIn("Content-Security-Policy", headers)
        self.assertIn("default-src 'none'", headers["Content-Security-Policy"])

    def test_404_for_missing_asset(self):
        code, _, _ = self._get("/p/gui_demo/nope.html")
        self.assertEqual(code, 404)

    def test_404_for_unknown_bundle(self):
        code, _, _ = self._get("/p/unknown/file.html")
        self.assertEqual(code, 404)

    def test_415_for_disallowed_extension(self):
        code, _, _ = self._get("/p/gui_demo/secret.txt")
        self.assertEqual(code, 415)

    def test_403_for_path_traversal(self):
        code, _, _ = self._get("/p/gui_demo/..%2Fhook.yaml")
        self.assertIn(code, (403, 404))  # depends on URL decoding behavior

    def test_rejects_double_dot_segment(self):
        code, _, _ = self._get("/p/gui_demo/../hook.yaml")
        self.assertEqual(code, 403)

    def test_404_for_non_plugin_url(self):
        code, _, _ = self._get("/random")
        self.assertEqual(code, 404)

    def test_start_idempotent(self):
        # Calling start again should return the same port without rebinding.
        p1 = plugin_gui_server.port()
        p2 = plugin_gui_server.start()
        self.assertEqual(p1, p2)


if __name__ == "__main__":
    unittest.main()
