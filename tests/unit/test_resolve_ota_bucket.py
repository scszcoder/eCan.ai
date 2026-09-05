"""
Unit tests for ``build_system/scripts/resolve_ota_bucket.py``.

This script is the single source of truth for OTA bucket / region /
prefix that both ``upload_to_s3.py`` / ``upload_to_cos.py`` and the
``shared-download-links.yml`` / ``shared-cos-download-links.yml``
workflows read.

These tests guard against:

* Drift between the upload side and the download-links side
  (the original bug: a missing ``COS_BUCKET`` GitHub secret caused the
  download-links job to silently skip the step summary, even though
  uploads succeeded).
* The script silently defaulting when ``ota_config.yaml`` is malformed.
* The script picking up the wrong ``cos_*`` / ``s3_*`` fields when
  ``--app`` is cn vs intl.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "build_system" / "scripts" / "resolve_ota_bucket.py"
REAL_CONFIG = REPO_ROOT / "ota" / "config" / "ota_config.yaml"


def _run(args: list[str], env_overrides: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Run the helper as a subprocess (matches the workflow invocation)."""
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def _parse_keyvalue_lines(stdout: str) -> dict[str, str]:
    """Parse ``KEY=VALUE\\n`` output (one record per line, no quoting)."""
    result: dict[str, str] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        k, _, v = line.partition("=")
        result[k.strip()] = v
    return result


# ----------------------------------------------------------------------------
# CLI argument contract
# ----------------------------------------------------------------------------


class TestCliArgs:
    def test_cn_production(self):
        result = _run(["--app", "cn", "--env", "production"])
        assert result.returncode == 0, result.stderr
        parsed = _parse_keyvalue_lines(result.stdout)
        assert parsed["OTA_BUCKET"] == "ecan-releases-1251680599"
        assert parsed["OTA_REGION"] == "ap-shanghai"
        # Aliases consumed by `render_download_links.py`. Must match
        # the OTA_* values exactly so the rendered URL prefix is built
        # from the same source-of-truth.
        assert parsed["BUCKET_NAME"] == parsed["OTA_BUCKET"]
        assert parsed["BUCKET_REGION"] == parsed["OTA_REGION"]
        assert parsed["OTA_PREFIX"] == "production"
        assert parsed["OTA_APP"] == "cn"
        assert parsed["OTA_ENV"] == "production"
        # S3 fields must NOT leak into CN output.
        assert "S3_BUCKET" not in parsed
        assert "AWS_REGION" not in parsed

    def test_intl_production(self):
        result = _run(["--app", "intl", "--env", "production"])
        assert result.returncode == 0, result.stderr
        parsed = _parse_keyvalue_lines(result.stdout)
        assert parsed["OTA_BUCKET"] == "ecan-releases"
        assert parsed["OTA_REGION"] == "us-east-1"
        assert parsed["BUCKET_NAME"] == parsed["OTA_BUCKET"]
        assert parsed["BUCKET_REGION"] == parsed["OTA_REGION"]
        assert parsed["OTA_PREFIX"] == "production"
        assert parsed["OTA_APP"] == "intl"
        # COS fields must NOT leak into intl output.
        assert "COS_BUCKET" not in parsed
        assert "ap-shanghai" not in result.stdout

    def test_cn_test(self):
        result = _run(["--app", "cn", "--env", "test"])
        parsed = _parse_keyvalue_lines(result.stdout)
        assert parsed["OTA_PREFIX"] == "test"

    def test_intl_test(self):
        result = _run(["--app", "intl", "--env", "test"])
        parsed = _parse_keyvalue_lines(result.stdout)
        assert parsed["OTA_PREFIX"] == "test"

    def test_cn_simulation(self):
        result = _run(["--app", "cn", "--env", "simulation"])
        parsed = _parse_keyvalue_lines(result.stdout)
        assert parsed["OTA_PREFIX"] == "simulation"

    def test_intl_staging(self):
        result = _run(["--app", "intl", "--env", "staging"])
        parsed = _parse_keyvalue_lines(result.stdout)
        assert parsed["OTA_PREFIX"] == "staging"


# ----------------------------------------------------------------------------
# Error paths
# ----------------------------------------------------------------------------


class TestErrorPaths:
    def test_missing_env(self):
        result = _run(["--app", "cn", "--env", "bogus"])
        assert result.returncode != 0
        assert "environments.bogus" in result.stderr

    def test_unknown_app(self):
        # argparse rejects choices before the script can run; exit code is 2.
        result = _run(["--app", "global", "--env", "production"])
        assert result.returncode == 2
        assert "invalid choice" in result.stderr

    def test_missing_config(self, tmp_path: Path):
        fake = tmp_path / "nope.yaml"
        result = _run(["--app", "cn", "--env", "production", "--config", str(fake)])
        assert result.returncode != 0
        assert "OTA config not found" in result.stderr


# ----------------------------------------------------------------------------
# Output format contract (must be ``KEY=VALUE\n`` for $GITHUB_ENV)
# ----------------------------------------------------------------------------


class TestOutputFormat:
    def test_every_line_is_keyvalue(self):
        """Each stdout line must be parseable as KEY=VALUE for $GITHUB_ENV."""
        result = _run(["--app", "cn", "--env", "production"])
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        for line in lines:
            assert "=" in line, f"non-keyvalue line: {line!r}"
            k, _, v = line.partition("=")
            # No spaces around the value (env files split on whitespace).
            assert " " not in v, f"value has space (env file split!): {line!r}"

    def test_no_ansi_color(self):
        """Workflows append this to $GITHUB_ENV; colour codes would corrupt env."""
        result = _run(["--app", "cn", "--env", "production"])
        assert "\x1b[" not in result.stdout

    def test_stderr_clean_when_successful(self):
        result = _run(["--app", "cn", "--env", "production"])
        assert result.stderr.strip() == ""

    def test_bucket_aliases_match_ota_values(self):
        """Regression guard: the script used to be called from the
        workflow followed by two `echo "BUCKET_NAME=${OTA_BUCKET}"`
        lines, but `$OTA_BUCKET` was empty in that same step (shell
        variables from `$GITHUB_ENV` are only materialised after the
        step exits), so the echo wrote `BUCKET_NAME=`. We now emit the
        aliases from the script itself; verify they match.
        """
        for app, env in (("cn", "production"), ("cn", "test"),
                         ("intl", "production"), ("intl", "test")):
            result = _run(["--app", app, "--env", env])
            assert result.returncode == 0, f"{app}/{env}: {result.stderr}"
            parsed = _parse_keyvalue_lines(result.stdout)
            assert parsed["BUCKET_NAME"] == parsed["OTA_BUCKET"], (
                f"{app}/{env}: BUCKET_NAME={parsed['BUCKET_NAME']!r} != "
                f"OTA_BUCKET={parsed['OTA_BUCKET']!r}"
            )
            assert parsed["BUCKET_REGION"] == parsed["OTA_REGION"], (
                f"{app}/{env}: BUCKET_REGION={parsed['BUCKET_REGION']!r} != "
                f"OTA_REGION={parsed['OTA_REGION']!r}"
            )
            # Sanity: neither alias should be empty (the original bug).
            assert parsed["BUCKET_NAME"], f"{app}/{env}: BUCKET_NAME is empty"
            assert parsed["BUCKET_REGION"], f"{app}/{env}: BUCKET_REGION is empty"


# ----------------------------------------------------------------------------
# Malformed config protection
# ----------------------------------------------------------------------------


class TestMalformedConfig:
    def test_missing_bucket_field(self, tmp_path: Path):
        bad = tmp_path / "ota_config.yaml"
        bad.write_text(
            "common:\n"
            "  app_name: eCan\n"
            # cos_bucket / s3_bucket both missing
            "  cos_region: ap-shanghai\n"
            "  s3_region: us-east-1\n"
            "environments:\n"
            "  production:\n"
            "    cos_prefix: production\n"
            "    s3_prefix: production\n",
            encoding="utf-8",
        )
        result = _run(["--app", "cn", "--env", "production", "--config", str(bad)])
        assert result.returncode != 0
        assert "cos_bucket" in result.stderr

    def test_missing_region_field(self, tmp_path: Path):
        bad = tmp_path / "ota_config.yaml"
        bad.write_text(
            "common:\n"
            "  cos_bucket: bucket-1251680599\n"
            "  # cos_region missing\n"
            "  s3_bucket: bucket\n"
            "  s3_region: us-east-1\n"
            "environments:\n"
            "  production:\n"
            "    cos_prefix: production\n"
            "    s3_prefix: production\n",
            encoding="utf-8",
        )
        result = _run(["--app", "cn", "--env", "production", "--config", str(bad)])
        assert result.returncode != 0
        assert "cos_region" in result.stderr

    def test_missing_env_section(self, tmp_path: Path):
        bad = tmp_path / "ota_config.yaml"
        bad.write_text(
            "common:\n"
            "  cos_bucket: bucket-1251680599\n"
            "  cos_region: ap-shanghai\n"
            "environments:\n"
            "  # production missing\n"
            "  test:\n"
            "    cos_prefix: test\n",
            encoding="utf-8",
        )
        result = _run(["--app", "cn", "--env", "production", "--config", str(bad)])
        assert result.returncode != 0
        assert "environments.production" in result.stderr


# ----------------------------------------------------------------------------
# Cross-side drift guard (the actual reason this script exists)
# ----------------------------------------------------------------------------


class TestCrossSideDrift:
    """Verify the resolver returns the same values the uploader reads.

    upload_to_cos.py / upload_to_s3.py both load
    ota/config/ota_config.yaml directly. If anyone changes the schema or
    the keys, this test catches the drift before it lands.
    """

    def test_cn_matches_upload_to_cos_constants(self):
        result = _run(["--app", "cn", "--env", "production"])
        parsed = _parse_keyvalue_lines(result.stdout)
        # Values from ota/config/ota_config.yaml as of writing.
        assert parsed["OTA_BUCKET"] == "ecan-releases-1251680599"
        assert parsed["OTA_REGION"] == "ap-shanghai"

    def test_intl_matches_upload_to_s3_constants(self):
        result = _run(["--app", "intl", "--env", "production"])
        parsed = _parse_keyvalue_lines(result.stdout)
        assert parsed["OTA_BUCKET"] == "ecan-releases"
        assert parsed["OTA_REGION"] == "us-east-1"


# ----------------------------------------------------------------------------
# Workflow contract tests — the calling reusable workflows must invoke this
# correctly. If a workflow drops the step, or hard-codes a secret read, the
# download-links summary will silently no-op (the bug this script fixes).
# ----------------------------------------------------------------------------


class TestWorkflowsInvokeResolver:
    """Static checks that the reusable workflows call resolve_ota_bucket.py.

    These are the regression tests for the original bug: ``secrets.COS_BUCKET``
    (or ``secrets.S3_BUCKET``) being unset would skip the entire summary
    step. The fix is to read from ota_config.yaml via this script. If
    anyone reverts to reading from secrets, these tests fail.
    """

    @staticmethod
    def _read(path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def test_cn_workflow_invokes_resolver(self):
        text = self._read(REPO_ROOT / ".github/workflows/shared-cos-download-links.yml")
        assert "resolve_ota_bucket.py" in text, (
            "shared-cos-download-links.yml must invoke resolve_ota_bucket.py "
            "to read the OTA bucket from ota_config.yaml. Reading from "
            "secrets.COS_BUCKET causes the download-links summary to be "
            "silently skipped when the secret is unset."
        )
        assert "--app cn" in text

    def test_intl_workflow_invokes_resolver(self):
        text = self._read(REPO_ROOT / ".github/workflows/shared-download-links.yml")
        assert "resolve_ota_bucket.py" in text, (
            "shared-download-links.yml must invoke resolve_ota_bucket.py "
            "to read the OTA bucket from ota_config.yaml. Reading from "
            "secrets.S3_BUCKET causes the download-links summary to be "
            "silently skipped when the secret is unset."
        )
        assert "--app intl" in text

    @staticmethod
    def _strip_comments(text: str) -> str:
        """Drop YAML comment lines so historical mentions don't fail the test."""
        return "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith("#")
        )

    def test_cn_workflow_does_not_reference_cos_bucket_secret(self):
        text = self._strip_comments(
            self._read(REPO_ROOT / ".github/workflows/shared-cos-download-links.yml")
        )
        # Allow the comment that explains what we replaced, but no live
        # `secrets.COS_BUCKET` read or `if: env.COS_BUCKET != 'NOT_SET'`
        # gate. The historical bug is exactly that pattern.
        assert "secrets.COS_BUCKET" not in text
        assert "if: env.COS_BUCKET" not in text

    def test_intl_workflow_does_not_reference_s3_bucket_secret_for_links(self):
        text = self._strip_comments(
            self._read(REPO_ROOT / ".github/workflows/shared-download-links.yml")
        )
        assert "secrets.S3_BUCKET" not in text
        assert "if: env.S3_BUCKET" not in text

    def test_cn_workflow_url_pattern_uses_bucket_with_appid(self):
        """The historical bug also produced wrong URLs:
        ``https://{bucket}-{region}.cos.{region}.myqcloud.com``.
        The bucket value already includes the APPID, so the URL must
        not append ``-${region}``.
        """
        text = self._read(REPO_ROOT / ".github/workflows/shared-cos-download-links.yml")
        # Look for the exact bad pattern.
        assert "BUCKET_NAME}-${BUCKET_REGION}.cos" not in text, (
            "COS URL construction must not append -${BUCKET_REGION} to "
            "BUCKET_NAME; the bucket value from ota_config.yaml already "
            "includes the APPID suffix (ecan-releases-1251680599). See "
            "https://ecan-releases-1251680599.cos.ap-shanghai.myqcloud.com"
            " for the canonical URL format."
        )
        # And the good pattern must be present.
        assert "BUCKET_NAME}.cos.${BUCKET_REGION}.myqcloud.com" in text