"""
Tests for OTA ``appcast_base`` override routing and the local OTA
server's ``/latest.json`` endpoint.

The contract under test:

  - ``_local_appcast_base()`` honors ANY non-empty
    ``appcast_base`` (INTL) / ``appcast_base_cos`` (CN) on the active
    environment — both local (``http://127.0.0.1:8080``) and remote
    public hosts (``https://ecan-releases.s3.us-east-1.amazonaws.com/test``
    etc.) qualify. The previous "127.0.0.1/localhost only" heuristic
    is gone: it forced the canonical environments (``test`` /
    ``staging`` / ``simulation`` / ``production``) to silently fall
    through to ``get_storage_url``, which works for INTL but for the
    CN app picks the wrong bucket family in some configs and loses
    the bucket-name override that ``appcast_base_cos`` is meant to
    carry.

  - When an override IS declared, ``get_appcast_url`` builds
    ``{base}/channels/{channel}/{filename}`` — same path shape as
    ``get_storage_url`` so a client uploaded via the public pipeline
    reads identically whether it resolves through the override or
    the fallback.

  - The ``language`` suffix is ALWAYS honored (no longer dropped for
    dev) so per-language copies (e.g. ``appcast-...zh-CN.xml``)
    resolve whether they live in S3/COS or on the local server.

  - ``AppcastGenerator.build_latest_json`` emits a payload whose
    top-level shape (``version`` / ``channel`` / ``environment`` /
    ``platforms``) and per-platform sub-shape (``version`` /
    ``url`` / ``file_size`` / ``sha256`` / ``signature``) match what
    ``build_system/scripts/generate_appcast.py::generate_latest_json``
    uploads to S3/COS.

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


class TestAppcastBaseOverride:
    """``_local_appcast_base`` honors any non-empty ``appcast_base``
    field — local AND remote public hosts both count. The override
    path is the canonical way ``test`` / ``staging`` / ``simulation``
    / ``production`` reach the bucket."""

    @pytest.mark.parametrize("app_id,expected_base", [
        ("intl", "https://ecan-releases.s3.us-east-1.amazonaws.com/test"),
        ("cn",   "https://ecan-releases-1251680599.cos.ap-shanghai.myqcloud.com/test"),
    ])
    def test_test_env_override_honored(self, app_id, expected_base):
        config = _fresh_config(app_id, "test")
        assert config._local_appcast_base() == expected_base

    @pytest.mark.parametrize("env", ["staging", "simulation", "production"])
    @pytest.mark.parametrize("app_id", ["intl", "cn"])
    def test_non_test_env_override_honored(self, app_id, env):
        """``staging`` / ``simulation`` / ``production`` also declare
        ``appcast_base`` to a public host — the override must be
        honored so the bucket/region routing lives in YAML, not in
        hardcoded URL-building code."""
        config = _fresh_config(app_id, env)
        base = config._local_appcast_base()
        assert base != ""
        assert base.startswith("https://")
        assert "127.0.0.1" not in base
        assert "localhost" not in base

    @pytest.mark.parametrize("env", ["development", "test", "staging", "simulation", "production"])
    @pytest.mark.parametrize("app_id", ["intl", "cn"])
    def test_every_env_routes_via_yaml_only(self, app_id, env):
        """Regression guard for the user's invariant:

            "Only changing ``environment:`` in ota_config.yaml should
            swap OTA endpoints."

        For each (env × app_id) pair, ``get_appcast_url`` and
        ``get_latest_json_url`` must produce the URL declared in the
        YAML — no code change required. If anyone later hard-codes a
        branch that bypasses ``appcast_base`` for one environment, this
        test fails before the change ships.
        """
        config = _fresh_config(app_id, env)
        env_block = config._config["environments"][env]
        expected_base = (
            env_block.get("appcast_base_cos")
            if app_id == "cn"
            else env_block.get("appcast_base")
        )
        expected_channel = env_block["channel"]

        # get_appcast_url builds {base}/channels/{channel}/{filename}.
        url = config.get_appcast_url("macos", "aarch64")
        assert url == (
            f"{expected_base}/channels/{expected_channel}/"
            f"appcast-macos-aarch64.xml"
        )

        # get_latest_json_url is {base}/latest.json (no channel segment).
        latest = config.get_latest_json_url()
        assert latest == f"{expected_base}/latest.json"

        # And the language suffix is preserved even on the override path.
        url_zh = config.get_appcast_url("macos", "aarch64", "zh-CN")
        assert url_zh == (
            f"{expected_base}/channels/{expected_channel}/"
            f"appcast-macos-aarch64.zh-CN.xml"
        )

    def test_development_env_local_override_honored(self):
        """``development`` env declares ``appcast_base = 127.0.0.1:8080``;
        the override must be honored so the local OTA test server is
        reachable."""
        config = _fresh_config("intl", "development")
        assert config._local_appcast_base() == "http://127.0.0.1:8080"

    def test_undeclared_base_returns_empty(self):
        """An env block with no ``appcast_base`` declared must NOT
        silently fall back to anything — the caller should fall
        through to ``get_storage_url``."""
        config = _fresh_config("intl", "development")
        config._config["environments"]["development"].pop("appcast_base", None)
        assert config._local_appcast_base() == ""

    def test_cn_falls_back_to_appcast_base_when_cos_missing(self):
        """CN loader falls back from ``appcast_base_cos`` to plain
        ``appcast_base`` so a CN app that's missing the COS-specific
        override still resolves something rather than failing closed."""
        config = _fresh_config("cn", "test")
        # Strip appcast_base_cos; appcast_base (the INTL field) stays.
        config._config["environments"]["test"].pop("appcast_base_cos", None)
        base = config._local_appcast_base()
        assert base != ""
        # Falls back to the INTL-shape field, which on CN routes
        # through ``get_storage_url`` anyway — the override returns
        # the value the env block actually has.
        assert base == "https://ecan-releases.s3.us-east-1.amazonaws.com/test"

    def test_intl_does_not_read_appcast_base_cos(self):
        """INTL loader must not accidentally read the CN-specific
        field (and vice versa) — keeps the two app families' bucket
        routing independent."""
        config = _fresh_config("intl", "test")
        # Replace the INTL field with a sentinel; populate COS field
        # with a different URL. INTL should ignore the COS field.
        config._config["environments"]["test"]["appcast_base"] = (
            "https://intl.example/test"
        )
        config._config["environments"]["test"]["appcast_base_cos"] = (
            "https://cos.example/test"
        )
        assert config._local_appcast_base() == "https://intl.example/test"


class TestGetAppcastUrlOverride:
    """``get_appcast_url`` builds ``{base}/channels/{channel}/{filename}``
    when an override is declared. Path shape matches
    ``get_storage_url`` so upload + read paths agree."""

    @pytest.mark.parametrize("app_id", ["intl", "cn"])
    def test_test_env_appcast_url_uses_declared_base(self, app_id):
        config = _fresh_config(app_id, "test")
        url = config.get_appcast_url("macos", "aarch64")
        # test channel = "beta" (see ota_config.yaml)
        if app_id == "intl":
            assert url == (
                "https://ecan-releases.s3.us-east-1.amazonaws.com/test/"
                "channels/beta/appcast-macos-aarch64.xml"
            )
        else:
            assert url == (
                "https://ecan-releases-1251680599.cos.ap-shanghai.myqcloud.com/test/"
                "channels/beta/appcast-macos-aarch64.xml"
            )

    @pytest.mark.parametrize("app_id", ["intl", "cn"])
    def test_production_env_appcast_url_uses_declared_base(self, app_id):
        config = _fresh_config(app_id, "production")
        url = config.get_appcast_url("macos", "aarch64")
        # production channel = "stable"
        if app_id == "intl":
            assert url == (
                "https://ecan-releases.s3.us-east-1.amazonaws.com/production/"
                "channels/stable/appcast-macos-aarch64.xml"
            )
        else:
            assert url == (
                "https://ecan-releases-1251680599.cos.ap-shanghai.myqcloud.com/production/"
                "channels/stable/appcast-macos-aarch64.xml"
            )

    @pytest.mark.parametrize("app_id", ["intl", "cn"])
    def test_language_suffix_honored_under_override(self, app_id):
        """Per-language copies (e.g. ``appcast-...zh-CN.xml``) live in
        S3/COS under ``channels/{channel}/`` — the override path must
        preserve the suffix (it was previously dropped for dev, which
        would have broken CN locale clients against a remote test
        bucket that DOES ship per-language copies)."""
        config = _fresh_config(app_id, "test")
        url = config.get_appcast_url("macos", "aarch64", "zh-CN")
        assert url.endswith("/test/channels/beta/appcast-macos-aarch64.zh-CN.xml")

    def test_undeclared_base_falls_through_to_storage_url(self):
        """When no ``appcast_base`` is declared, ``get_appcast_url``
        falls through to ``get_storage_url`` so the path shape
        (``{prefix}/channels/...``) is the same."""
        config = _fresh_config("intl", "development")
        config._config["environments"]["development"].pop("appcast_base", None)
        url = config.get_appcast_url("macos", "aarch64")
        # ``development`` has no ``appcast_base`` → falls through to
        # ``get_storage_url`` which yields {s3_prefix}/channels/...
        assert url == (
            "https://ecan-releases.s3.us-east-1.amazonaws.com/dev/"
            "channels/dev/appcast-macos-aarch64.xml"
        )

    def test_development_env_local_base_routes_to_8080(self):
        """Regression guard for the original dev-routing behavior:
        a development build pointed at the in-tree OTA test server
        must continue to resolve to ``127.0.0.1:8080``."""
        config = _fresh_config("intl", "development")
        url = config.get_appcast_url("macos", "aarch64")
        assert url == (
            "http://127.0.0.1:8080/channels/dev/appcast-macos-aarch64.xml"
        )


class TestGetLatestJsonUrlOverride:
    """``get_latest_json_url`` honors ``appcast_base`` the same way
    ``get_appcast_url`` does — appends ``/latest.json`` to the
    declared base instead of going through ``get_storage_url``."""

    @pytest.mark.parametrize("app_id", ["intl", "cn"])
    def test_test_env_latest_json_uses_declared_base(self, app_id):
        config = _fresh_config(app_id, "test")
        url = config.get_latest_json_url()
        if app_id == "intl":
            assert url == (
                "https://ecan-releases.s3.us-east-1.amazonaws.com/test/latest.json"
            )
        else:
            assert url == (
                "https://ecan-releases-1251680599.cos.ap-shanghai.myqcloud.com/test/latest.json"
            )

    @pytest.mark.parametrize("app_id", ["intl", "cn"])
    def test_development_env_latest_json_uses_local_base(self, app_id):
        config = _fresh_config(app_id, "development")
        url = config.get_latest_json_url()
        assert url == "http://127.0.0.1:8080/latest.json"

    def test_undeclared_base_falls_through_to_storage_url(self):
        config = _fresh_config("intl", "development")
        config._config["environments"]["development"].pop("appcast_base", None)
        url = config.get_latest_json_url()
        assert url == (
            "https://ecan-releases.s3.us-east-1.amazonaws.com/dev/latest.json"
        )


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
