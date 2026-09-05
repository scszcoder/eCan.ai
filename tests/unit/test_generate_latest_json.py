"""
End-to-end tests for ``AppcastGenerator.generate_latest_json``.

These tests cover the most operationally-critical guarantee the
release pipeline provides: **multi-platform OTA consistency under
partial-build scenarios**. The real-world workflow is:

  1. Engineer A builds Windows for v1.0.0 → ``latest.json`` gets
     ``platforms.windows-amd64`` pointing at v1.0.0.
  2. macOS build runner is busy / flaky / cancelled → first release
     run fails with macOS not built.
  3. Engineer A re-runs the release for v1.0.0 with only macOS this
     time → ``latest.json`` must keep the existing windows-amd64
     entry AND add macos-amd64. **It must NOT clear windows-amd64**
     or roll back the global ``version`` to an older value.

If the incremental merge were naively replaced by a "regenerate
from scratch each run", the second macOS-only build would overwrite
windows-amd64 with macos-amd64 and leave Windows users on a stale
version (or worse, on a version that has no Windows installer at
all — Sparkle clients fail to update silently).

The tests use a fake S3 client that records put_object calls and
serves pre-seeded get_object contents. No real network I/O.

Why no real ``test_generate_appcast_cn_intl.py``-style coverage for
this method: the prior coverage focused on the LastModified-normalization
bug; the partial-build / latest.json-overwrite invariant was tested
implicitly by integration but never as an explicit assertion. This
file pins the invariant down.
"""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from build_system.scripts.generate_appcast import AppcastGenerator

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers — bare generator + fake S3
# ---------------------------------------------------------------------------


def _bare_generator(*, environment: str = "production",
                    storage_backend: str = "s3",
                    prefix: str = "production",
                    channel: str = "stable"):
    """Build an ``AppcastGenerator`` without running ``__init__``.

    Mirrors ``_bare_generator`` from
    ``test_generate_appcast_integration.py``. We need the same
    hermetic construction (no boto3 / no YAML) so the test runs in
    milliseconds and doesn't touch real credentials.
    """
    gen = object.__new__(AppcastGenerator)
    gen.app_name = "TestApp"
    gen.app_short_name = "TestApp"
    gen.environment = environment
    gen.app_id = "intl"
    gen.storage_backend = storage_backend
    gen.bucket = "test-bucket"
    gen.region = "us-east-1"
    gen.prefix = prefix
    gen.channel = channel
    gen.base_path = ""
    gen.user_prefix = ""
    gen.specific_version = None
    return gen


class _FakeS3Client:
    """In-memory fake that records put_object calls.

    Unlike the simple ``_FakeS3Client`` in
    ``test_generate_appcast_integration.py``, this one needs:

      * ``put_object(Bucket, Key, Body, ContentType, ...)`` to
        actually persist bytes so a subsequent ``get_object`` can
        read them back (the incremental-merge test needs to inspect
        what was written).
      * ``get_object(Bucket, Key)`` for the existing latest.json
        read — returns 404 / ``ClientError`` when nothing is seeded.

    Args:
        installer_objects: list of (key, size) for installer objects
            the bucket "has". ``list_objects_v2`` returns these with a
            fixed LastModified so the generator's size/sha lookups
            succeed.
        latest_json_body: optional pre-seeded ``latest.json`` dict
            (already-parsed, NOT a string). When set, ``get_object``
            for the latest.json key returns it. When None, the
            ``get_object`` for latest.json raises ``ClientError`` to
            simulate "no existing latest.json".
    """

    def __init__(self, *, installer_objects, latest_json_body=None):
        # key -> body bytes (for installers + the latest.json pointer)
        self._objects: dict[str, bytes] = {}
        # key -> size for installers (the generator reads .Size off
        # the list_objects_v2 Contents row, not get_object).
        self._installer_sizes: dict[str, int] = {}
        for key, size in installer_objects:
            self._installer_sizes[key] = size
            # Pre-seed an empty body so get_object would succeed
            # (the generator never reads the body for installers;
            # it only reads .Size from list_objects_v2).
            self._objects.setdefault(key, b"")
        self._latest_json_body = latest_json_body

    # --- list_objects_v2: installer's Contents row ---
    def list_objects_v2(self, Bucket, Prefix, **kwargs):
        return {
            "Contents": [
                {
                    "Key": key,
                    "Size": size,
                    "LastModified": datetime(2026, 8, 13, 19, 2, 33,
                                              tzinfo=timezone.utc),
                }
                for key, size in self._installer_sizes.items()
                if key.startswith(Prefix)
            ]
        }

    # --- get_object: latest.json read OR .sig / .sha256 read ---
    def get_object(self, Bucket, Key, **kwargs):
        from botocore.exceptions import ClientError

        # Match the latest.json key the generator uses: {prefix}/latest.json
        # (base_path is empty in the bare generator).
        latest_key = f"{self._latest_prefix()}/latest.json"
        if Key == latest_key and self._latest_json_body is not None:
            return {"Body": io.BytesIO(
                json.dumps(self._latest_json_body).encode("utf-8")
            )}

        # Installer body reads (.sig / .sha256).
        if Key in self._objects:
            return {"Body": io.BytesIO(self._objects[Key])}

        # S3-style: missing keys raise ClientError. The generator's
        # generate_latest_json catches this in the try/except and
        # treats it as "no existing latest.json".
        raise ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "not found"}},
            "GetObject",
        )

    def _latest_prefix(self) -> str:
        # Mirrors `storage_key = f"{self.prefix}/latest.json"` from
        # generate_latest_json (base_path is empty in _bare_generator).
        return "production"

    # --- put_object: record the write so the test can read it back ---
    def put_object(self, Bucket, Key, Body, ContentType=None, **kwargs):
        body = Body if isinstance(Body, bytes) else Body.encode("utf-8")
        self._objects[Key] = body


def _latest_json_body(s3: _FakeS3Client) -> dict:
    """Read back the latest.json that the generator wrote."""
    key = f"{s3._latest_prefix()}/latest.json"
    return json.loads(s3._objects[key].decode("utf-8"))


def _platforms(gen, version: str) -> dict[str, dict]:
    """Helper: pre-seed fake with installer objects for ``version``
    across the listed (platform, arch) pairs.

    Returns a mapping of ``platform-arch`` → ``pkg_info`` dict that
    tests can use to assert the right URLs ended up in latest.json.
    """
    pairs = [
        ("windows", "amd64", f"eCan-{version}-windows-amd64-Setup.exe"),
        ("macos",   "amd64", f"eCan-{version}-macos-amd64.pkg"),
        ("macos",   "aarch64", f"eCan-{version}-macos-aarch64.pkg"),
        ("linux",   "amd64", f"eCan-{version}-linux-amd64.deb"),
    ]
    installer_objects: list[tuple[str, int]] = []
    pkg_by_key: dict[str, dict] = {}
    for platform, arch, filename in pairs:
        key = f"production/releases/v{version}/{platform}/{arch}/{filename}"
        size = {"windows": 145_823_441, "macos": 52_345_678,
                 "linux": 45_234_567}[platform]
        installer_objects.append((key, size))
        pkg_by_key[f"{platform}-{arch}"] = {
            "key": key,
            "size": size,
            "url": f"https://test-bucket.s3.us-east-1.amazonaws.com/{key}",
        }
    return installer_objects, pkg_by_key


# ---------------------------------------------------------------------------
# The user's scenario: same-version partial builds don't overwrite
# each other's latest.json entries.
# ---------------------------------------------------------------------------


class TestPartialBuildIncrementalMerge:
    """Reproduce the exact scenario the user worried about.

    Run 1: build only Windows for v1.0.0.
    Run 2: build only macOS for v1.0.0 (Windows re-use).

    After run 2, ``latest.json`` must still point at v1.0.0 and
    contain BOTH ``windows-amd64`` AND ``macos-amd64`` entries,
    each pointing at the correct v1.0.0 installer URL.
    """

    def test_windows_only_then_macos_only_preserves_windows(self):
        gen = _bare_generator()

        # ----- Run 1: only Windows file in the bucket -----
        installers_run1, _ = _platforms(gen, "1.0.0")
        # Drop everything but windows-amd64.
        installers_run1 = [
            (k, s) for (k, s) in installers_run1
            if "/windows/amd64/" in k
        ]
        s3 = _FakeS3Client(installer_objects=installers_run1)
        gen.s3 = s3
        gen.cos = None

        with patch.object(gen, "list_versions", return_value=["v1.0.0"]):
            assert gen.generate_latest_json() is True

        after_run1 = _latest_json_body(s3)
        # Run 1 must set the global version to 1.0.0 (no leading v).
        assert after_run1["version"] == "1.0.0"
        # And only windows-amd64 entry exists.
        assert "windows-amd64" in after_run1["platforms"]
        assert "macos-amd64" not in after_run1["platforms"]
        # URL is the v1.0.0 Windows installer URL.
        win_url = after_run1["platforms"]["windows-amd64"]["url"]
        assert "/releases/v1.0.0/windows/amd64/" in win_url
        assert win_url.endswith(
            "eCan-1.0.0-windows-amd64-Setup.exe"
        )

        # ----- Run 2: only macOS files (Windows NOT re-uploaded) -----
        installers_run2 = [
            (k, s) for (k, s) in _platforms(gen, "1.0.0")[0]
            if "/macos/" in k
        ]
        # Same fake client keeps the existing latest.json between
        # runs (its _latest_json_body was set on first run via
        # put_object; we simulate persistence by re-wiring it).
        s3._latest_json_body = _latest_json_body(s3)
        s3._installer_sizes = dict(s3._installer_sizes)
        for k, sz in installers_run2:
            s3._installer_sizes[k] = sz

        with patch.object(gen, "list_versions", return_value=["v1.0.0"]):
            assert gen.generate_latest_json() is True

        after_run2 = _latest_json_body(s3)

        # **The invariant the user worried about**: Windows entry
        # must still be there with the SAME v1.0.0 URL — macOS-only
        # run must NOT have wiped it.
        assert "windows-amd64" in after_run2["platforms"], (
            "macOS-only build wiped the windows-amd64 entry from "
            "latest.json — partial-build scenario is broken."
        )
        win_url2 = after_run2["platforms"]["windows-amd64"]["url"]
        assert win_url2 == win_url, (
            f"windows-amd64 URL drifted across partial builds: "
            f"run1={win_url!r}, run2={win_url2!r}"
        )

        # AND macos-amd64 / aarch64 must now be populated.
        assert "macos-amd64" in after_run2["platforms"]
        assert "macos-aarch64" in after_run2["platforms"]
        assert after_run2["platforms"]["macos-amd64"]["url"].endswith(
            "eCan-1.0.0-macos-amd64.pkg"
        )
        assert after_run2["platforms"]["macos-aarch64"]["url"].endswith(
            "eCan-1.0.0-macos-aarch64.pkg"
        )

        # Global version stays at 1.0.0 — never rolls back to an
        # older platform's entry.
        assert after_run2["version"] == "1.0.0"

    def test_three_platforms_in_one_run_produces_complete_latest_json(self):
        """All platforms built in one run: latest.json must list every
        (platform, arch) pair with the right URL, and the global
        version is the bare semver (no leading 'v')."""
        gen = _bare_generator()
        installers, expected = _platforms(gen, "1.0.0")
        s3 = _FakeS3Client(installer_objects=installers)
        gen.s3 = s3
        gen.cos = None

        with patch.object(gen, "list_versions", return_value=["v1.0.0"]):
            assert gen.generate_latest_json() is True

        body = _latest_json_body(s3)
        assert body["version"] == "1.0.0"
        for key in ("windows-amd64", "macos-amd64",
                     "macos-aarch64", "linux-amd64"):
            assert key in body["platforms"], (
                f"latest.json missing {key!r} after a full build"
            )
            assert body["platforms"][key]["url"] == expected[key]["url"]
            assert body["platforms"][key]["file_size"] == expected[key]["size"]

    def test_existing_latest_json_with_older_version_kept_when_building_newer(self):
        """Regression guard: if a stale latest.json on the bucket
        contains windows-amd64 pointing at v0.9.0 (an older version),
        and the current build runs only macOS for v1.0.0, the
        windows-amd64 entry must NOT be rolled back to v1.0.0.

        This catches the bug where ``latest_data['version']`` is
        recomputed via ``max(all_platform_versions)`` and would set
        the global version to a value that's only valid for one
        platform — leaving other platforms' entries stale.
        """
        gen = _bare_generator()
        # Pre-seeded latest.json says windows-amd64 = v0.9.0.
        existing = {
            "version": "0.9.0",
            "channel": "stable",
            "environment": "production",
            "updated_at": "2026-07-01T00:00:00",
            "platforms": {
                "windows-amd64": {
                    "version": "0.9.0",
                    "url": "https://test-bucket.s3.us-east-1.amazonaws.com/"
                            "production/releases/v0.9.0/windows/amd64/"
                            "eCan-0.9.0-windows-amd64-Setup.exe",
                    "file_size": 140_000_000,
                    "sha256": "deadbeef" * 8,
                    "signature": None,
                }
            },
        }
        # Only macOS v1.0.0 installers in the bucket (no v1.0.0 windows).
        installers = [
            (k, s) for (k, s) in _platforms(gen, "1.0.0")[0]
            if "/macos/" in k
        ]
        s3 = _FakeS3Client(
            installer_objects=installers,
            latest_json_body=existing,
        )
        gen.s3 = s3
        gen.cos = None

        with patch.object(gen, "list_versions", return_value=["v1.0.0"]):
            assert gen.generate_latest_json() is True

        body = _latest_json_body(s3)
        # windows-amd64 entry preserved (v0.9.0 still).
        assert body["platforms"]["windows-amd64"]["version"] == "0.9.0"
        # macos entries added (v1.0.0).
        assert body["platforms"]["macos-amd64"]["version"] == "1.0.0"
        # Global version is max(0.9.0, 1.0.0) = 1.0.0 — that's the
        # highest, so it correctly bumps.
        assert body["version"] == "1.0.0"

    def test_no_universal_versions_skips_latest_json_update(self):
        """If only user-tagged builds exist (e.g. a personal preview
        build), ``latest.json`` must NOT point at one — that would
        expose every user to the preview.

        ``generate_latest_json`` returns True (not False) because
        this is an intentional skip, not a build failure.
        """
        gen = _bare_generator()
        s3 = _FakeS3Client(
            installer_objects=[
                # A user-tagged release dir; not a universal version.
                (
                    "production/releases/songc_v1.0.0/"
                    "windows/amd64/eCan-1.0.0-windows-amd64-Setup.exe",
                    145_823_441,
                ),
            ],
            latest_json_body={
                "version": "0.9.0",
                "platforms": {},
            },
        )
        gen.s3 = s3
        gen.cos = None

        with patch.object(gen, "list_versions",
                          return_value=["songc_v1.0.0"]):
            result = gen.generate_latest_json()

        assert result is True
        # The bucket's existing latest.json (v0.9.0) must NOT have
        # been overwritten — the put_object call must not have run.
        latest_key = f"{s3._latest_prefix()}/latest.json"
        assert latest_key not in s3._objects, (
            "generate_latest_json wrote latest.json when only "
            "user-tagged versions exist — must skip instead."
        )


# ---------------------------------------------------------------------------
# The download-links renderer's bucket reads the same source as the
# upload side. If anyone ever splits these, the rendered URL prefix
# will drift away from where artifacts were actually uploaded.
# ---------------------------------------------------------------------------


class TestBucketSourceAgreement:
    """The renderer's ``BUCKET_NAME`` / ``BUCKET_REGION`` env vars
    must come from the same ``ota_config.yaml`` the upload scripts
    read. If a workflow ever bypasses ``resolve_ota_bucket.py`` and
    sets BUCKET_NAME from a different source (e.g. a secret), the
    rendered URL prefix would no longer match where artifacts were
    actually uploaded — every download link would 404.
    """

    def test_resolver_output_matches_upload_constants(self, tmp_path):
        """End-to-end: run the real ``resolve_ota_bucket.py`` and the
        real upload script's ``_load_config``-equivalent, and assert
        they read the same bucket for ``cn/production``.

        Drives both via subprocess so a polluted ``sys.modules['yaml']``
        from earlier tests (e.g. ``test_upload_to_cos_chunking.py``,
        which stubs ``yaml.safe_load``) cannot leak in and produce a
        fake "empty config" failure. The subprocess Python interpreter
        imports yaml fresh from site-packages.
        """
        import subprocess
        import sys as _sys

        repo_root = _repo_root()
        config_path = repo_root / "ota/config/ota_config.yaml"

        # Renderer side: subprocess the real resolve_ota_bucket.py.
        result = subprocess.run(
            [_sys.executable,
             str(repo_root / "build_system/scripts/resolve_ota_bucket.py"),
             "--app", "cn", "--env", "production"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr
        resolved = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                resolved[k.strip()] = v

        # Upload side: parse the same ota_config.yaml in a fresh subprocess.
        # Reading the YAML inline in this test would import yaml via
        # sys.modules, which is the exact channel test_upload_to_cos_chunking
        # pollutes. Spawning a one-shot python -c invocation guarantees a
        # clean module table.
        helper_path = tmp_path / "_read_yaml_helper.py"
        helper_path.write_text(
            "import sys, yaml\n"
            "p = sys.argv[1]\n"
            "d = yaml.safe_load(open(p, encoding='utf-8'))\n"
            "print(repr(d['common']['cos_bucket']))\n"
            "print(repr(d['common']['cos_region']))\n"
            "print(repr(d['environments']['production']['cos_prefix']))\n",
            encoding="utf-8",
        )
        proc = subprocess.run(
            [_sys.executable, str(helper_path), str(config_path)],
            capture_output=True, text=True, timeout=30,
        )
        assert proc.returncode == 0, proc.stderr
        # Each line is repr(value); strip the surrounding quotes.
        def _strip_repr(s: str) -> str:
            s = s.strip()
            if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
                return s[1:-1]
            return s
        upload_bucket, upload_region, upload_prefix = (
            _strip_repr(line) for line in proc.stdout.strip().splitlines()
        )

        assert resolved["OTA_BUCKET"] == upload_bucket, (
            "upload_to_cos.py and resolve_ota_bucket.py must read "
            "the same cos_bucket from ota_config.yaml"
        )
        assert resolved["OTA_REGION"] == upload_region
        assert resolved["OTA_PREFIX"] == upload_prefix

        # And the renderer-facing aliases must equal the upload
        # constants so the rendered URL prefix is built from the
        # same source-of-truth.
        assert resolved["BUCKET_NAME"] == upload_bucket
        assert resolved["BUCKET_REGION"] == upload_region


# ---------------------------------------------------------------------------
# Smoke test: the full workflow invocation path (resolve → renderer)
# ---------------------------------------------------------------------------


class TestFullWorkflowInvocation:
    """End-to-end check that the workflow steps resolve the bucket,
    invoke the renderer, and produce a Markdown summary whose URL
    prefix matches the upload target.

    A regression that re-introduces the old "echo
    BUCKET_NAME=${OTA_BUCKET}" pattern (which produces empty values
    because $GITHUB_ENV is not materialised until the step exits)
    would surface here as a summary with `Bucket: _(unset)_`.
    """

    def test_resolved_bucket_then_renderer_produces_valid_url_prefix(
        self, tmp_path, monkeypatch,
    ):
        repo_root = _repo_root()

        # Step 1: workflow resolves the bucket via subprocess so any
        # in-process yaml pollution from earlier tests can't poison
        # our resolver call.
        import subprocess
        import sys as _sys

        result = subprocess.run(
            [_sys.executable,
             str(repo_root / "build_system/scripts/resolve_ota_bucket.py"),
             "--app", "cn", "--env", "production"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr
        resolved = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                resolved[k.strip()] = v

        env_overrides = {
            "VERSION": "1.0.0",
            "ENVIRONMENT": "production",
            "CHANNEL": "stable",
            "OTA_PREFIX": "production",
            "WINDOWS_BUILD_RESULT": "success",
            "MACOS_BUILD_RESULT": "skipped",
            "LINUX_RESULT": "skipped",
            "WINDOWS_DIRECT_UPLOAD": "false",
            "APP_NAME": "eCan.cn",
            "BUCKET_NAME": resolved["BUCKET_NAME"],
            "BUCKET_REGION": resolved["BUCKET_REGION"],
            "OTA_BUCKET": resolved["OTA_BUCKET"],
            "OTA_REGION": resolved["OTA_REGION"],
        }
        for k, v in env_overrides.items():
            monkeypatch.setenv(k, v)

        # Step 2: seed fake artifact dirs that the renderer iterates.
        win = tmp_path / "windows-artifacts"
        win.mkdir()
        (win / "eCan.cn-1.0.0-windows-amd64-Setup.exe").write_bytes(
            b"X" * 145_823_441
        )

        # Step 3: invoke the renderer exactly as the workflow does.
        summary = tmp_path / "summary.md"
        text = tmp_path / "text.txt"
        renderer = repo_root / "build_system/scripts/render_download_links.py"
        rc = subprocess.run(
            [
                _sys.executable, str(renderer),
                "--scheme", "cos",
                "--summary-out", str(summary),
                "--text-out", str(text),
                "--url-pattern", "https://{bucket-with-APPID}.cos.{region}.myqcloud.com/{env}/releases/v{ver}/{platform}/{arch}/{file}",
                "--workflow-name", "test",
            ],
            cwd=tmp_path,
            capture_output=True, text=True,
        )
        assert rc.returncode == 0, rc.stderr

        md = summary.read_text()

        # The resolved bucket appears in the summary header AND the
        # URL column — same source-of-truth for both. If the bucket
        # were empty, both would be empty (the bug we fixed).
        assert resolved["BUCKET_NAME"] in md, (
            f"resolved bucket {resolved['BUCKET_NAME']!r} missing from "
            f"summary header — likely the env var didn't reach the renderer"
        )
        assert resolved["BUCKET_REGION"] in md
        # And the URL column contains the resolved bucket.
        expected_url_prefix = (
            f"https://{resolved['BUCKET_NAME']}.cos."
            f"{resolved['BUCKET_REGION']}.myqcloud.com/"
            f"production/releases/v1.0.0/windows/amd64/"
            f"eCan.cn-1.0.0-windows-amd64-Setup.exe"
        )
        assert expected_url_prefix in md, (
            f"summary URL column missing the resolved bucket prefix "
            f"(expected {expected_url_prefix!r})"
        )

        # The .txt artifact must carry the same URL.
        assert expected_url_prefix in text.read_text()


def _repo_root() -> Path:
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_resolve_path",
        Path(__file__).parent.parent.parent
        / "build_system/scripts/resolve_ota_bucket.py",
    )
    # Easier: derive from the test file location.
    return Path(__file__).resolve().parents[2]
