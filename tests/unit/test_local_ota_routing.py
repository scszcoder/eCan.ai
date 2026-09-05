"""
Tests for dev-environment routing of ``get_appcast_url`` /
``get_latest_json_url`` and the local OTA server's ``/latest.json``
endpoint.

The contract under test:

  - When ``environment == "development"`` AND
    ``appcast_base`` (INTL) / ``appcast_base_cos`` (CN) points at a
    local host (``127.0.0.1`` / ``localhost``), both
    ``get_appcast_url`` and ``get_latest_json_url`` must build URLs off
    that local base instead of the public S3/COS bucket.

  - For ``test`` / ``staging`` / ``simulation`` / ``production``, the
    public bucket URLs must continue to be returned even if the
    same ``appcast_base`` field happens to be set to a public host
    (the loader only treats the field as a local override when it
    parses as ``127.0.0.1`` or ``localhost``).

  - ``AppcastGenerator.build_latest_json`` emits a payload whose
    top-level shape (``version`` / ``channel`` / ``environment`` /
    ``platforms``) and per-platform sub-shape (``version`` /
    ``url`` / ``file_size`` / ``sha256`` / ``signature``) match what
    ``build_system/scripts/generate_appcast.py::generate_latest_json``
    uploads to S3/COS, so a dev client reads either source
    identically.

  - The local ``/latest.json`` route returns ``Cache-Control: max-age=60``
    so dev iteration loops don't hammer disk scans.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clear_ota_cache():
    import sys
    for k in list(sys.modules.keys()):
        if k == "ota" or k.startswith("ota."):
            del sys.modules[k]


def _fresh_config(app_id: str, environment: str):
    """Force a freshly-loaded OTAConfig pinned to ``environment``.

    Mirrors the existing ``test_ota_config.py::_reload_ota_config``
    pattern but exposes the env override without a file write — the
    only thing under test is which branch the loader picks, not the
    YAML content.
    """
    _clear_ota_cache()
    with patch.dict("os.environ", {"ECAN_APP_ID": app_id}, clear=False):
        from ota.config import loader
        loader._ota_config = None
        config = loader.get_ota_config(reload=True)
        # ``_config['environment']`` is the loader's own backing field;
        # mutating it here is the documented test seam used elsewhere
        # in the suite (see test_ota_config.TestOTAConfigEnvironments).
        config._config["environment"] = environment
        return config


# ---------------------------------------------------------------------------
# Loader routing
# ---------------------------------------------------------------------------


class TestLocalAppcastBase:
    """``get_appcast_url`` / ``get_latest_json_url`` route dev traffic
    to the local OTA test server and leave non-dev traffic on the
    public bucket."""

    @pytest.mark.parametrize("app_id", ["intl", "cn"])
    def test_dev_env_appcast_url_uses_local_base(self, app_id):
        config = _fresh_config(app_id, "development")
        url = config.get_appcast_url("macos", "aarch64")
        assert url == "http://127.0.0.1:8080/appcast-macos-aarch64.xml"

    @pytest.mark.parametrize("app_id", ["intl", "cn"])
    def test_dev_env_latest_json_url_uses_local_base(self, app_id):
        config = _fresh_config(app_id, "development")
        url = config.get_latest_json_url()
        assert url == "http://127.0.0.1:8080/latest.json"

    def test_dev_env_appcast_url_ignores_language_suffix(self):
        """Local server's appcast doesn't ship per-language copies;
        the URL must collapse to the bare ``appcast-*.xml`` even when
        the caller passes ``language='zh-CN'``."""
        config = _fresh_config("cn", "development")
        url = config.get_appcast_url("macos", "aarch64", "zh-CN")
        assert url == "http://127.0.0.1:8080/appcast-macos-aarch64.xml"

    @pytest.mark.parametrize("env", ["test", "staging", "simulation", "production"])
    @pytest.mark.parametrize("app_id", ["intl", "cn"])
    def test_non_dev_env_uses_public_bucket(self, app_id, env):
        """Even if ``appcast_base`` happens to be set on the env block
        (test/staging/simulation/production all set it to the public
        S3/COS host), the loader must NOT treat public hosts as local
        overrides — it only honors the override when the base parses
        as ``127.0.0.1`` / ``localhost``."""
        config = _fresh_config(app_id, env)
        url = config.get_appcast_url("macos", "aarch64")
        assert "127.0.0.1" not in url
        assert "localhost" not in url
        assert "channels/" in url  # public path is ``channels/{channel}/...``

    @pytest.mark.parametrize("env", ["test", "staging", "simulation", "production"])
    def test_non_dev_env_latest_json_uses_public_bucket(self, env):
        config = _fresh_config("intl", env)
        url = config.get_latest_json_url()
        assert url.endswith(f"/{env}/latest.json")
        assert "127.0.0.1" not in url

    def test_local_base_heuristic_rejects_public_https(self):
        """Defense-in-depth: if a future env block accidentally sets
        ``appcast_base`` to a real S3/COS host in dev (misconfig), the
        loader must not silently rewrite URLs — it must fall through
        to the public bucket path so the misconfig is visible (not
        silently "working" against the wrong host)."""
        config = _fresh_config("intl", "development")
        # Replace dev's appcast_base with a public S3 URL.
        config._config["environments"]["development"]["appcast_base"] = (
            "https://ecan-releases.s3.us-east-1.amazonaws.com"
        )
        url = config.get_appcast_url("macos", "aarch64")
        assert url.startswith("https://ecan-releases.s3.us-east-1.amazonaws.com/")
        assert "127.0.0.1" not in url


# ---------------------------------------------------------------------------
# ``AppcastGenerator.build_latest_json``
# ---------------------------------------------------------------------------


class TestBuildLatestJson:
    """``build_latest_json`` produces a payload whose shape matches
    the remote ``generate_appcast.py::generate_latest_json`` output."""

    def _bare_generator(self):
        """Construct an ``AppcastGenerator`` without ``__init__`` so we
        don't need a Jinja2 template on disk for the latest.json path."""
        from ota.server.appcast_generator import AppcastGenerator
        gen = object.__new__(AppcastGenerator)
        gen.server_root = str(Path(__file__).resolve().parent.parent.parent / "ota" / "server")
        gen.signatures_dir = gen.server_root
        return gen

    def _write_fake_dist(self, tmp_path: Path) -> Path:
        """Drop three fake ``eCan-`` artifacts into ``tmp_path`` to
        exercise multi-platform ``build_latest_json``."""
        for name in (
            "eCan-1.2.3-macos-aarch64.pkg",
            "eCan-1.2.3-windows-amd64-Setup.exe",
            "eCan-1.2.3-linux-amd64.deb",
        ):
            (tmp_path / name).write_bytes(b"fake payload")
        return tmp_path

    def test_payload_top_level_shape(self, tmp_path):
        gen = self._bare_generator()
        dist_dir = self._write_fake_dist(tmp_path)
        payload = gen.build_latest_json(
            base_url="http://127.0.0.1:8080",
            dist_dir=dist_dir,
            channel="dev",
            environment="development",
        )
        assert payload is not None
        # Same top-level keys as the remote upload path.
        assert set(payload.keys()) >= {
            "version", "channel", "environment", "updated_at", "platforms"
        }
        assert payload["channel"] == "dev"
        assert payload["environment"] == "development"
        # Global ``version`` matches the highest per-platform version
        # (mirrors the remote generator's invariant).
        assert payload["version"] == "1.2.3"

    def test_platforms_keys_match_remote_schema(self, tmp_path):
        gen = self._bare_generator()
        dist_dir = self._write_fake_dist(tmp_path)
        payload = gen.build_latest_json(
            base_url="http://127.0.0.1:8080",
            dist_dir=dist_dir,
        )
        assert payload is not None
        platforms = payload["platforms"]
        # Same slot naming as remote (and as ``get_package_info``).
        assert set(platforms.keys()) == {
            "macos-aarch64", "windows-amd64", "linux-amd64",
        }
        for slot, info in platforms.items():
            # Same per-platform sub-shape as remote.
            assert "version" in info
            assert "url" in info
            assert "file_size" in info
            assert "sha256" in info
            assert "signature" in info
            # ``url`` is built off the local base so a click-through on
            # dev actually downloads from the test server.
            assert info["url"].startswith("http://127.0.0.1:8080/downloads/")

    def test_empty_dist_returns_none(self, tmp_path):
        gen = self._bare_generator()
        payload = gen.build_latest_json(
            base_url="http://127.0.0.1:8080",
            dist_dir=tmp_path,
        )
        assert payload is None

    def test_higher_version_wins_within_same_slot(self, tmp_path):
        """Two builds for the same platform/arch slot → keep the
        higher-version one (mirrors the remote max-version invariant).
        """
        gen = self._bare_generator()
        (tmp_path / "eCan-1.2.3-macos-aarch64.pkg").write_bytes(b"old")
        (tmp_path / "eCan-1.2.4-macos-aarch64.pkg").write_bytes(b"new")
        payload = gen.build_latest_json(
            base_url="http://127.0.0.1:8080",
            dist_dir=tmp_path,
        )
        assert payload is not None
        assert payload["version"] == "1.2.4"
        assert "eCan-1.2.4-macos-aarch64.pkg" in payload["platforms"]["macos-aarch64"]["url"]

    def test_no_accelerated_url_in_local_payload(self, tmp_path):
        """Local server has no CDN; the ``accelerated_url`` field that
        the remote generator emits for CloudFront/COS-accelerated
        variants must NOT appear in the local payload (its absence
        signals to clients that the URL is the only copy)."""
        gen = self._bare_generator()
        self._write_fake_dist(tmp_path)
        payload = gen.build_latest_json(
            base_url="http://127.0.0.1:8080",
            dist_dir=tmp_path,
        )
        for slot, info in payload["platforms"].items():
            assert "accelerated_url" not in info, (
                f"local latest.json must not advertise an accelerated URL "
                f"(slot={slot})"
            )


# ---------------------------------------------------------------------------
# ``/latest.json`` Flask route
# ---------------------------------------------------------------------------


class TestLatestJsonRoute:
    """The local OTA server's ``/latest.json`` endpoint serves the
    ``build_latest_json`` payload with the right headers."""

    def test_route_serves_payload(self, tmp_path):
        # Build the Flask app + a fake dist with one package.
        (tmp_path / "eCan-1.0.0-macos-aarch64.pkg").write_bytes(b"x")

        from ota.server.update_server import app
        # The module-level ``appcast_gen`` is bound at import time and
        # points at the real project dist/; swap its ``_scan_dist_directory``
        # for the duration of this test to redirect the scan at tmp_path.
        from ota.server import update_server as srv

        with patch.object(srv.appcast_gen, "_scan_dist_directory") as scan:
            def _fake_scan(dist_dir):
                # Honor what build_latest_json passes (the real dist_dir)
                # but return our fake pkg.
                return {
                    "eCan-1.0.0-macos-aarch64.pkg": {
                        "file_size": 1,
                        "sha256": "deadbeef" * 8,
                        "signature": "deadbeef" * 8,
                        "version": "1.0.0",
                        "os_type": "macos",
                        "arch": "aarch64",
                    }
                }
            scan.side_effect = _fake_scan

            client = app.test_client()
            resp = client.get("/latest.json")

        assert resp.status_code == 200
        body = json.loads(resp.data)
        assert body["version"] == "1.0.0"
        assert "macos-aarch64" in body["platforms"]
        # Cache header prevents dev iteration loops from re-scanning disk.
        assert resp.headers.get("Cache-Control") == "max-age=60"

    def test_route_404_when_no_packages(self):
        from ota.server.update_server import app
        from ota.server import update_server as srv

        with patch.object(srv.appcast_gen, "_scan_dist_directory", return_value={}):
            client = app.test_client()
            resp = client.get("/latest.json")

        assert resp.status_code == 404
