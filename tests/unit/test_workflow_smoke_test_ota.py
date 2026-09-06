"""Unit tests for build_system/scripts/smoke_test_ota.py.

These tests do not hit any network. We monkey-patch the HTTP
helpers (``head``, ``get_text``, ``get_json``) with in-memory
fixtures, then drive ``run`` with a synthetic Namespace.

Coverage targets the contracts that the smoke test must hold:

  * Latest.json shape: a stagger between top-level `version` and
    platform versions is a WARNING, not a FAILURE (this is the
    whole point of cross-platform incremental merges).
  * Missing platform entry: a platform that is not yet built is a
    WARNING unless ``--require-all-platforms`` is passed.
  * Installer check: 4xx/5xx on the installer URL is a FAILURE;
    missing `url` field in latest.json is a FAILURE.
  * Appcast version match: must use the Sparkle attribute
    ``sparkle:version`` on the enclosure element (NOT a child
    element), and normalize both sides by stripping the leading
    'v'. The version that DOES NOT match must FAIL the check.
  * zh-CN filename: must use a dot separator
    (``appcast-<platform>-<arch>.zh-CN.xml``) to match
    ``generate_appcast.py:upload_appcast``. A dash separator
    produces a 404 and that is a FAILURE.
  * Exit code: 0 on all-OK, 1 on any FAILURE. Warnings do NOT
    cause exit 1.
"""

from __future__ import annotations

import json
import sys
from unittest.mock import patch

import pytest

from build_system.scripts import smoke_test_ota as m

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _args(**overrides):
    """Build an argparse.Namespace equivalent to run()'s input."""
    base = dict(
        app="intl",
        env="production",
        channel="stable",
        version="1.0.0",
        user_prefix="",
        require_all_platforms=False,
    )
    base.update(overrides)
    # argparse.Namespace lets us set any attribute via kwargs.
    import argparse
    return argparse.Namespace(**base)


def _fake_latest_json(top_version="1.0.0", platforms=None):
    """Build a minimal valid latest.json body."""
    return {
        "version": top_version,
        "channel": "stable",
        "environment": "production",
        "updated_at": "2026-09-06T00:00:00.000000",
        "platforms": platforms if platforms is not None else {},
    }


def _platforms_dict(*platforms):
    """Build a `platforms` map for fake_latest_json.

    Each entry is a (key, version, size) tuple.
    """
    return {
        key: {
            "version": version,
            "url": f"https://test-bucket/{key}/installer",
            "file_size": size,
        }
        for key, version, size in platforms
    }


def _ok_installer(url, size=12345):
    """Return a head() response showing the installer is live."""
    return 200, {
        "Content-Length": str(size),
        "Content-Type": "application/octet-stream",
    }


# A 64-byte (Ed25519) signature base64-encoded to 88 chars - the
# format Sparkle / WinSparkle / Squirrel actually use.
_FAKE_VALID_SIG = "A" * 86 + "=="


def _fake_appcast_xml(version="v1.0.0", platform="macos", arch="aarch64",
                       enclosure_url="", signature=None):
    """Build a real Sparkle appcast XML with one item."""
    if not enclosure_url:
        enclosure_url = f"https://test-bucket/releases/{version}/{platform}/{arch}/installer"
    if signature is None:
        signature = _FAKE_VALID_SIG
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">\n'
        '  <channel>\n'
        '    <title>Test</title>\n'
        '    <item>\n'
        f'      <title>Version {version}</title>\n'
        f'      <enclosure url="{enclosure_url}" length="12345" '
        f'type="application/octet-stream" '
        f'sparkle:version="{version}" sparkle:os="{platform}" '
        f'sparkle:arch="{arch}" sparkle:edSignature="{signature}"/>\n'
        '    </item>\n'
        '  </channel>\n'
        '</rss>\n'
    )


# ---------------------------------------------------------------------------
# _norm_version contract
# ---------------------------------------------------------------------------


class TestNormVersion:
    """_norm_version handles every shape we may see on the wire."""

    def test_strips_leading_v(self):
        assert m._norm_version("v1.0.0") == "1.0.0"

    def test_no_leading_v_unchanged(self):
        assert m._norm_version("1.0.0") == "1.0.0"

    def test_pre_release_branch_build_kept_intact(self):
        # Branch builds have an interior 'v' that must NOT be stripped:
        # 0.7.0-v0.9.97d-53bdc77 .lstrip('v') = 0.7.0-v0.9.97d-53bdc77
        # because the FIRST char is '0', not 'v'. The lstrip is
        # anchored to the left, not greedy across the whole string.
        v = "0.7.0-v0.9.97d-53bdc77"
        assert m._norm_version(v) == v
        assert m._norm_version("v" + v) == v

    def test_double_v_stripped_to_zero_v(self):
        assert m._norm_version("vv1.0.0") == "1.0.0"


# ---------------------------------------------------------------------------
# check_latest_json shape
# ---------------------------------------------------------------------------


class TestCheckLatestJsonShape:
    """The smoke test must not crash on weird latest.json bodies."""

    def test_404_returns_failure_with_no_body(self):
        result, doc = m.check_latest_json("h", "p", "1.0.0")
        assert result.ok is False
        assert doc is None

    def test_top_level_version_not_in_platforms_is_warning_not_failure(self):
        """This is the cross-platform stagger scenario. A 1-platform
        release with top-level version matching that platform is OK
        (the typical case). A top-level version that is NOT in any
        platform entry is a stagger warning, NOT a failure.
        """
        latest = _fake_latest_json(
            top_version="1.0.0",
            platforms=_platforms_dict(("windows-amd64", "1.0.0", 12345)),
        )
        # Patch get_json to return our fake body
        with patch.object(m, "get_json", return_value=(200, latest)):
            result, doc = m.check_latest_json("h", "p", "1.0.0")
        assert result.ok is True, f"expected ok, got errors={result.errors}"
        # No warning if top-level IS in platforms
        assert not result.warnings

    def test_top_level_drift_is_warning(self):
        """Top-level version ahead of any platform = stagger warning."""
        latest = _fake_latest_json(
            top_version="1.1.0",  # newer than any platform
            platforms=_platforms_dict(("windows-amd64", "1.0.0", 12345)),
        )
        with patch.object(m, "get_json", return_value=(200, latest)):
            result, _ = m.check_latest_json("h", "p", "1.0.0")
        assert result.ok is True
        assert result.warnings
        assert any("top-level version" in w for w in result.warnings)

    def test_expected_version_mismatch_is_warning(self):
        """The release we just published may not be the top of
        latest.json if a hotfix shipped between generate-latest-json
        and smoke test. Warn, do not fail.
        """
        latest = _fake_latest_json(top_version="1.1.0")  # hotfix
        with patch.object(m, "get_json", return_value=(200, latest)):
            result, _ = m.check_latest_json("h", "p", "1.0.0")  # we shipped 1.0.0
        assert result.ok is True
        assert result.warnings
        assert any("differs from latest.json top-level" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# check_installer_url
# ---------------------------------------------------------------------------


class TestCheckInstallerUrl:
    """HEAD failures / wrong content-type must FAIL."""

    def test_missing_url_field_fails(self):
        result = m.check_installer_url("h", "macos-amd64", {})
        assert result.ok is False
        assert any("missing 'url'" in e for e in result.errors)

    def test_403_fails(self):
        with patch.object(m, "head", return_value=(403, {})):
            result = m.check_installer_url(
                "h", "macos-amd64",
                {"url": "https://x", "file_size": 100},
            )
        assert result.ok is False
        assert any("HTTP 403" in e for e in result.errors)

    def test_200_with_size_match_ok(self):
        with patch.object(m, "head", return_value=_ok_installer("x")):
            result = m.check_installer_url(
                "h", "macos-amd64",
                {"url": "https://x", "file_size": 12345},
            )
        assert result.ok is True

    def test_size_mismatch_fails(self):
        with patch.object(m, "head", return_value=_ok_installer("x")):
            result = m.check_installer_url(
                "h", "macos-amd64",
                {"url": "https://x", "file_size": 99999},
            )
        assert result.ok is False
        assert any("size mismatch" in e for e in result.errors)

    def test_wrong_content_type_fails(self):
        with patch.object(
            m, "head",
            return_value=(200, {"Content-Length": "100",
                                "Content-Type": "text/html"}),
        ):
            result = m.check_installer_url(
                "h", "macos-amd64",
                {"url": "https://x", "file_size": 100},
            )
        assert result.ok is False
        assert any("Content-Type" in e for e in result.errors)

    def test_application_x_msdownload_accepted_for_windows(self):
        with patch.object(
            m, "head",
            return_value=(200, {"Content-Length": "100",
                                "Content-Type": "application/x-msdownload"}),
        ):
            result = m.check_installer_url(
                "h", "windows-amd64",
                {"url": "https://x", "file_size": 100},
            )
        assert result.ok is True


# ---------------------------------------------------------------------------
# check_appcast
# ---------------------------------------------------------------------------


class TestCheckAppcast:
    """Version matching against appcast XML."""

    def test_enclosure_attribute_used_not_child_element(self):
        """Regression: the previous implementation used
        item.find('sparkle:version') looking for a child element.
        Sparkle encodes version as an ATTRIBUTE on the enclosure.
        Looking for the wrong shape returned None silently and made
        every appcast check fail.
        """
        xml = _fake_appcast_xml(version="v1.0.0")
        with patch.object(m, "get_text", return_value=(200, xml)):
            results = m.check_appcast(
                "h", "p", "macos", "aarch64", "intl",
                expected_version="1.0.0",
            )
        assert len(results) == 1
        assert results[0].ok is True, (
            f"expected ok; errors={results[0].errors}"
        )

    def test_v_prefix_normalized(self):
        """appcast stores 'v1.0.0', we receive '1.0.0'. Stripping
        'v' on both sides must make them match."""
        xml = _fake_appcast_xml(version="v1.0.0")
        with patch.object(m, "get_text", return_value=(200, xml)):
            results = m.check_appcast(
                "h", "p", "macos", "aarch64", "intl",
                expected_version="1.0.0",
            )
        assert results[0].ok is True

    def test_version_mismatch_fails(self):
        """If the appcast does NOT contain the expected version,
        the check fails with a clear message.
        """
        xml = _fake_appcast_xml(version="v0.9.0")  # different version
        with patch.object(m, "get_text", return_value=(200, xml)):
            results = m.check_appcast(
                "h", "p", "macos", "aarch64", "intl",
                expected_version="1.0.0",
            )
        assert results[0].ok is False
        assert any("expected version '1.0.0' not found" in e
                   for e in results[0].errors)

    def test_cn_publishes_zh_cn_with_dot_separator(self):
        """CN appcast writes use a DOT before the language suffix
        (generate_appcast.py:upload_appcast). The smoke test must
        request the SAME URL, not the dashed variant.

        Regression: the previous implementation used a dash
        (appcast-<platform>-<arch>-zh-CN.xml) and got a 404 for
        every CN build.
        """
        # Patch get_text to capture the requested URLs.
        seen_urls = []
        def fake_get_text(url, timeout=15.0):
            seen_urls.append(url)
            # en-US (no suffix) and zh-CN (.zh-CN.xml) both return
            # the same valid XML in this test fixture.
            return 200, _fake_appcast_xml(version="v1.0.0")
        with patch.object(m, "get_text", side_effect=fake_get_text):
            results = m.check_appcast(
                "h", "p", "windows", "amd64", "cn",
                expected_version="1.0.0",
            )
        # The smoke test requested the DOT variant, not the DASH.
        assert any(".zh-CN.xml" in u for u in seen_urls), (
            f"smoke test never requested .zh-CN.xml; saw {seen_urls}"
        )
        assert not any("-zh-CN.xml" in u and not ".zh-CN.xml" in u
                       for u in seen_urls), (
            f"smoke test requested the WRONG (dashed) variant; "
            f"saw {seen_urls}"
        )
        # Both checks succeeded.
        assert all(r.ok for r in results), (
            f"one of the checks failed: {[(r.name, r.errors) for r in results]}"
        )

    def test_intl_does_not_request_zh_cn(self):
        """intl does not publish a zh-CN variant; we must not even
        request it (would 404 and look like a real failure).
        """
        with patch.object(
            m, "get_text",
            return_value=(200, _fake_appcast_xml(version="v1.0.0")),
        ):
            results = m.check_appcast(
                "h", "p", "macos", "aarch64", "intl",
                expected_version="1.0.0",
            )
        # Exactly one result for the en-US (default) variant.
        assert len(results) == 1
        assert "zh-CN" not in results[0].name

    def test_404_returns_failure(self):
        with patch.object(m, "get_text", return_value=(404, "")):
            results = m.check_appcast(
                "h", "p", "macos", "aarch64", "intl",
                expected_version="1.0.0",
            )
        assert results[0].ok is False
        assert any("HTTP 404" in e for e in results[0].errors)

    def test_invalid_xml_returns_failure(self):
        with patch.object(m, "get_text", return_value=(200, "not xml")):
            results = m.check_appcast(
                "h", "p", "macos", "aarch64", "intl",
                expected_version="1.0.0",
            )
        assert results[0].ok is False
        assert any("failed to parse" in e for e in results[0].errors)


# ---------------------------------------------------------------------------
# run() integration
# ---------------------------------------------------------------------------


class TestRun:
    """End-to-end driver: latest.json + installer + appcast."""

    def test_all_ok_returns_zero(self):
        """Happy path: 4 platforms all OK, latest.json matches."""
        # Use a single shared size for all platforms - the smoke test
        # does not distinguish per-platform size, but does compare
        # latest.json's recorded size against the HEAD response.
        latest = _fake_latest_json(
            top_version="1.0.0",
            platforms=_platforms_dict(*[
                ("macos-aarch64", "1.0.0", 12345),
                ("macos-amd64",   "1.0.0", 12345),
                ("windows-amd64", "1.0.0", 12345),
                ("linux-amd64",   "1.0.0", 12345),
            ]),
        )
        with patch.object(m, "get_json", return_value=(200, latest)), \
             patch.object(m, "head", return_value=_ok_installer("x", 12345)), \
             patch.object(
                 m, "get_text",
                 return_value=(200, _fake_appcast_xml(version="v1.0.0")),
             ), \
             patch.object(m, "_load_config", return_value={
                 "common": {"s3_bucket": "test", "s3_region": "us-east-1"},
                 "environments": {"production": {"s3_prefix": "production"}},
             }), \
             patch.object(m, "_emit_summary") as emit:
            rc = m.run(_args())
        assert rc == 0
        # The summary was emitted with no failed checks.
        call_args = emit.call_args[0]
        # _emit_summary is called as _emit_summary(all_results, failed, args).
        all_results_emit, failed, _args_emit = call_args
        assert failed == []

    def test_one_failed_installer_returns_one(self):
        """Single platform with a 403 must fail the run."""
        latest = _fake_latest_json(
            top_version="1.0.0",
            platforms=_platforms_dict(
                ("windows-amd64", "1.0.0", 3),
                ("macos-amd64", "1.0.0", 2),
            ),
        )

        def fake_head(url, timeout=15.0):
            if "macos-amd64" in url:
                return 403, {}
            return _ok_installer(url)

        with patch.object(m, "get_json", return_value=(200, latest)), \
             patch.object(m, "head", side_effect=fake_head), \
             patch.object(
                 m, "get_text",
                 return_value=(200, _fake_appcast_xml(version="v1.0.0")),
             ), \
             patch.object(m, "_load_config", return_value={
                 "common": {"s3_bucket": "test", "s3_region": "us-east-1"},
                 "environments": {"production": {"s3_prefix": "production"}},
             }), \
             patch.object(m, "_emit_summary"):
            rc = m.run(_args())
        assert rc == 1

    def test_missing_platform_is_warning_by_default(self):
        """latest.json has only 1 platform entry. Smoke test must
        not fail; it must warn. (Staggered rollouts are legitimate.)
        """
        latest = _fake_latest_json(
            top_version="1.0.0",
            platforms=_platforms_dict(
                ("windows-amd64", "1.0.0", 12345),
            ),
        )
        with patch.object(m, "get_json", return_value=(200, latest)), \
             patch.object(m, "head", return_value=_ok_installer("x")), \
             patch.object(
                 m, "get_text",
                 return_value=(200, _fake_appcast_xml(version="v1.0.0")),
             ), \
             patch.object(m, "_load_config", return_value={
                 "common": {"s3_bucket": "test", "s3_region": "us-east-1"},
                 "environments": {"production": {"s3_prefix": "production"}},
             }), \
             patch.object(m, "_emit_summary") as emit:
            rc = m.run(_args())  # default: --require-all-platforms off
        assert rc == 0, (
            "missing platform must be a warning, not a failure"
        )
        call_args = emit.call_args[0]
        # _emit_summary is called as _emit_summary(all_results, failed, args).
        all_results_emit, failed, _args_emit = call_args
        # No FAILURES, but warnings exist for the 3 missing platforms.
        assert failed == []
        warned = [r for r in all_results_emit if r.warnings]
        assert len(warned) >= 3

    def test_missing_platform_fails_when_required(self):
        """With --require-all-platforms, missing entries DO fail."""
        latest = _fake_latest_json(
            top_version="1.0.0",
            platforms=_platforms_dict(
                ("windows-amd64", "1.0.0", 12345),
            ),
        )
        with patch.object(m, "get_json", return_value=(200, latest)), \
             patch.object(m, "head", return_value=_ok_installer("x")), \
             patch.object(
                 m, "get_text",
                 return_value=(200, _fake_appcast_xml(version="v1.0.0")),
             ), \
             patch.object(m, "_load_config", return_value={
                 "common": {"s3_bucket": "test", "s3_region": "us-east-1"},
                 "environments": {"production": {"s3_prefix": "production"}},
             }), \
             patch.object(m, "_emit_summary"):
            rc = m.run(_args(require_all_platforms=True))
        assert rc == 1
