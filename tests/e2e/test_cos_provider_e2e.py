"""
End-to-end tests for ``utils.storage.tencent_cos.TencentCOSProvider``.

These tests hit the REAL Tencent Cloud COS bucket. They are opt-in:

  - Skipped by default in CI (no real credentials available).
  - Run explicitly with::

      export ECAN_TENCENT_SECRET_ID=AKIDxxxxxxxxxxxxxxxxxxxxxxxx
      export ECAN_TENCENT_SECRET_KEY=xxxxxxxxxxxxxxxxxxxxxxxx
      export ECAN_COS_E2E_BUCKET=7363-sccb0-d0gc5398xf028be6a-1251680599  # must match TCB COS bucket
      export ECAN_COS_E2E_REGION=ap-shanghai                              # must match TCB COS region
      export ECAN_COS_E2E_PREFIX=e2e_probe/              # default
      python3 -m pytest tests/e2e/test_cos_provider_e2e.py -v

  - Or via the unified runner::

      python3 -m tests.framework.runners --categories e2e --include-cloud

What they verify
----------------
  1. ``upload_file`` writes the file to the bucket and returns a usable URL.
  2. ``file_exists`` reports True after upload, False after delete.
  3. ``download_file`` round-trips the bytes (SHA256 matches).
  4. ``generate_presigned_url`` returns a URL that GETs the same bytes.
  5. ``delete_file`` is idempotent: deleting twice does not raise.

What they do NOT verify
-----------------------
  - The Intl S3 provider (covered by parallel tests under ``test_s3_provider_e2e.py``
    if/when added; the Intl CI path is covered by ``tests/integration/test_ota_cn_intl_flow.py``).
  - OTA artifact uploads (covered by ``scripts/ota_regression_test.py`` against the
    local mock update server, since the OTA bucket is owned by CI/CD and uses a
    different bucket than the runtime app-storage bucket — see
    ``utils/storage/base.py`` for the two-bucket convention).
  - The pre-signed-URL PUT path used by ``cloudbase-graphql/storage/cos-file-ops.js``;
    the current ``TencentCOSProvider`` only exposes a download presigner and that
    gap is tracked separately.

Bucket choice
-------------
The default ``ECAN_COS_E2E_BUCKET=7363-sccb0-d0gc5398xf028be6a-1251680599``
matches the TCB COS bucket that this CAM sub-account can access.
Tests write under ``ECAN_COS_E2E_PREFIX`` (default ``e2e_probe/``) so they are
easy to spot and to clean out by hand if the teardown ever leaves something
behind. Use a different prefix per CI run to avoid concurrent-run collisions::

      ECAN_COS_E2E_PREFIX="e2e_$BUILD_ID/"
"""
from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

import pytest

# Marker + skipif pattern matches tests/e2e/test_auth_flow.py:201-204.
# Tests are skipped unless both real-credential env vars are set AND the
# optional cos-python-sdk-v5 dependency is importable. We resolve both at
# collection time so missing-deps shows as SKIP, not ERROR.
_TENCENT_ID = os.environ.get("ECAN_TENCENT_SECRET_ID", "")
_TENCENT_KEY = os.environ.get("ECAN_TENCENT_SECRET_KEY", "")
_HAVE_CREDS = bool(_TENCENT_ID and _TENCENT_KEY)

try:
    import qcloud_cos  # noqa: F401  - presence check only
    _HAVE_SDK = True
except ImportError:
    _HAVE_SDK = False

pytestmark = [
    pytest.mark.e2e,
    # No ``@pytest.mark.cloud`` here on purpose: ``tests/conftest.py`` adds a
    # blanket skip to every cloud-marked test, and there is no public
    # ``--run-cloud`` useroption wired up to undo that. Instead we use the
    # same env-var-driven skipif pattern as ``tests/e2e/test_auth_flow.py:201``
    # so the only way to actually run these tests is to opt in by exporting
    # real credentials (i.e. the user already has COS access). If we later
    # wire up a real ``--run-cloud`` flag, re-add ``pytest.mark.cloud`` here.
    pytest.mark.skipif(
        not _HAVE_CREDS,
        reason="Real COS credentials not set. Define ECAN_TENCENT_SECRET_ID and "
               "ECAN_TENCENT_SECRET_KEY to run this test against the real bucket.",
    ),
    pytest.mark.skipif(
        not _HAVE_SDK,
        reason="cos-python-sdk-v5 is not installed in this environment. "
               "Install with: pip install cos-python-sdk-v5",
    ),
]


# ---------------------------------------------------------------------------
# Config + fixtures
# ---------------------------------------------------------------------------

# Bucket/region/prefix are read once at module import. If you change them
# in CI, restart the pytest process.
_TEST_BUCKET = os.environ.get("ECAN_COS_E2E_BUCKET", "7363-sccb0-d0gc5398xf028be6a-1251680599")
_TEST_REGION = os.environ.get("ECAN_COS_E2E_REGION", "ap-shanghai")
_TEST_PREFIX = os.environ.get("ECAN_COS_E2E_PREFIX", "e2e_probe/").rstrip("/") + "/"


def _make_provider():
    """
    Build a real ``TencentCOSProvider`` pointed at the test bucket/region.

    We bypass ``get_config().is_cn()`` because the provider reads
    ``storage_region`` / ``storage_bucket`` from ``config._endpoints``, and
    building a full ``AppConfigLoader`` in the e2e layer drags in unrelated
    config (auth_config.yml, app_manifest.json, etc). A small shim object
    is enough for the provider under test.
    """
    from utils.storage.tencent_cos import TencentCOSProvider

    class _EndpointShim:
        # TencentCOSProvider accesses config._endpoints.get(...) (line 21), so
        # the shim must expose _endpoints as an attribute whose value has .get().
        def __init__(self, d: dict):
            self._d = d

        @property
        def _endpoints(self):
            # Return self so that config._endpoints.get("key") resolves through
            # Python's attribute lookup chain to self.get("key").
            return self

        def get(self, k: str, default=None):
            return self._d.get(k, default)

    endpoints = _EndpointShim({
        "storage_region": _TEST_REGION,
        "storage_bucket": _TEST_BUCKET,
        "cdn": "",  # no CDN in tests — exercises the direct myqcloud.com path
    })

    return TencentCOSProvider(endpoints)


@pytest.fixture(scope="module")
def cos():
    """Module-scoped provider so we only spin up the SDK once per test file."""
    return _make_provider()


@pytest.fixture()
def test_key(cos):
    """
    Unique remote key per test. We always attempt cleanup at teardown so
    failed tests don't leave junk in the bucket.
    """
    name = f"{_TEST_PREFIX}{uuid.uuid4().hex}.bin"
    yield name
    # Best-effort cleanup. If this fails the object is harmless: the prefix
    # is dedicated to e2e probes and can be wiped by hand.
    try:
        cos.delete_file(name)
    except Exception:  # pragma: no cover - teardown
        pass


@pytest.fixture()
def sample_file(tmp_path: Path) -> Path:
    """A small but non-trivial payload (4 KiB of pseudo-random bytes)."""
    p = tmp_path / "payload.bin"
    p.write_bytes(uuid.uuid4().bytes * 64)  # 1024 * 16/256 mix → unique per test
    return p


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCosProviderRoundTrip:
    """End-to-end COS file round-trip: upload → exists → download → delete."""

    def test_upload_returns_url_pointing_at_test_bucket(
        self, cos, test_key, sample_file
    ):
        url = cos.upload_file(str(sample_file), test_key)
        assert url, "upload_file must return a non-empty URL"
        # Either direct COS URL or CDN; both should reference the test bucket.
        assert _TEST_BUCKET in url, (
            f"URL {url!r} does not reference test bucket {_TEST_BUCKET!r}"
        )
        assert test_key in url, f"URL {url!r} does not embed the remote key"

    def test_file_exists_true_after_upload(self, cos, test_key, sample_file):
        cos.upload_file(str(sample_file), test_key)
        assert cos.file_exists(test_key) is True

    def test_download_round_trips_bytes(self, cos, test_key, sample_file, tmp_path):
        cos.upload_file(str(sample_file), test_key)
        dst = tmp_path / "downloaded.bin"
        ok = cos.download_file(test_key, str(dst))
        assert ok is True
        assert dst.exists()
        # SHA256 of the original must match the downloaded bytes.
        assert _sha256(sample_file) == _sha256(dst), (
            "Downloaded bytes do not match the uploaded source — silent corruption"
        )

    def test_generate_presigned_url_is_getable(self, cos, test_key, sample_file):
        """
        The presigned URL must be GET-able and return the same bytes we
        uploaded. We use ``urllib`` (stdlib) so this test does not require
        ``requests``.
        """
        import urllib.error
        import urllib.request

        cos.upload_file(str(sample_file), test_key)
        url = cos.generate_presigned_url(test_key, expires_in=300)
        assert url, "presigned URL must be non-empty"
        # Tencent COS returns sig/query string in the URL; sanity-check the
        # shape so a regression that returns a public CDN URL still surfaces.
        assert "cos." in url or "myqcloud.com" in url, (
            f"Unexpected presigned URL shape: {url!r}"
        )

        with urllib.request.urlopen(url, timeout=30) as resp:
            body = resp.read()
        assert hashlib.sha256(body).hexdigest() == _sha256(sample_file), (
            "Presigned URL GET returned bytes that do not match the upload"
        )

    def test_delete_file_makes_key_disappear(self, cos, test_key, sample_file):
        cos.upload_file(str(sample_file), test_key)
        assert cos.file_exists(test_key) is True
        assert cos.delete_file(test_key) is True
        # After delete, head_object should raise inside the provider; it
        # catches the exception and returns False.
        assert cos.file_exists(test_key) is False

    def test_delete_is_idempotent(self, cos):
        """
        Deleting a non-existent key is COS-idiomatic: the API is idempotent (DELETE on
        a non-existent object returns HTTP 200, not 404). The current provider wraps this
        in a bare try/except that catches nothing → returns True. We assert that
        calling delete on a phantom key does NOT raise (idempotent contract) and
        returns True (COS convention for delete-non-existent = success).
        """
        nonexistent = f"{_TEST_PREFIX}{uuid.uuid4().hex}-never-existed.bin"
        # Must not raise — COS DELETE is idempotent (HTTP 200 even if key is absent)
        result = cos.delete_file(nonexistent)
        assert result is True, (
            "delete_file on a non-existent key should return True (COS idempotent DELETE)"
        )

    def test_file_exists_false_for_random_key(self, cos):
        """A freshly-minted random key should not exist."""
        phantom = f"{_TEST_PREFIX}{uuid.uuid4().hex}-phantom.bin"
        assert cos.file_exists(phantom) is False


class TestCosProviderUploadUrlShape:
    """
    Verify the URL shape returned by ``upload_file`` matches the documented
    contract. This is the URL that downstream code (e.g. the GUI) embeds in
    user-facing views, so its format is part of the public surface.
    """

    def test_upload_url_uses_bucket_subdomain_when_no_cdn(
        self, cos, test_key, sample_file
    ):
        url = cos.upload_file(str(sample_file), test_key)
        # No cdn_domain was provided to the provider, so the URL must fall
        # back to the direct ``<bucket>.cos.<region>.myqcloud.com`` form.
        assert f"{_TEST_BUCKET}.cos.{_TEST_REGION}.myqcloud.com" in url
        assert not url.startswith("/"), "URL must be absolute"

    def test_upload_url_encodes_remote_key_verbatim(
        self, cos, sample_file
    ):
        # Pick a key with characters that are valid in COS but easy to mangle
        # through a URL re-encoder (dashes, dots, digits).
        key = f"{_TEST_PREFIX}{uuid.uuid4().hex}-upload-shape-test.bin"
        try:
            url = cos.upload_file(str(sample_file), key)
            assert key in url, (
                f"Remote key {key!r} not embedded verbatim in URL {url!r}"
            )
        finally:
            cos.delete_file(key)
