"""
Integration tests for ``build_system/scripts/generate_appcast.py``.

Drives the full ``generate_appcast()`` pipeline end-to-end with mocked
S3 / COS clients and asserts the resulting XML is well-formed. The
most important assertion is that ``<pubDate>`` renders correctly
regardless of whether the upstream ``LastModified`` is a COS ISO-8601
*string* (which crashed the live CI on 2026-08-13) or a boto3
``datetime``.

These tests run the **real** ``get_package_info`` against a fake S3
client, so a regression that removes the normalization call from
``get_package_info`` will be caught here.
"""

import io
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from build_system.scripts.generate_appcast import AppcastGenerator

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# RFC-822-style pubDate pattern (matches what the appcast XML emits).
PUBDATE_RE = re.compile(
    r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun), "
    r"\d{2} (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) "
    r"\d{4} \d{2}:\d{2}:\d{2} \+0000$"
)


def _bare_generator():
    """Build an ``AppcastGenerator`` without running ``__init__``.

    The constructor instantiates a real boto3 / COS client and reads a
    YAML config from disk; for these tests we only need the few instance
    attributes that ``get_package_info()`` and ``generate_appcast()``
    touch. Using ``object.__new__`` keeps the test hermetic and fast.
    """
    gen = object.__new__(AppcastGenerator)
    gen.app_name = "TestApp"
    gen.app_short_name = "TestApp"
    gen.environment = "development"
    gen.app_id = "intl"
    gen.storage_backend = "s3"
    gen.bucket = "test-bucket"
    gen.region = "us-east-1"
    gen.prefix = "dev"
    gen.channel = "dev"
    gen.base_path = ""
    return gen


class _FakeS3Client:
    """Minimal in-memory fake of the boto3 / COS S3 client.

    Pre-seeded with a mapping of ``(key) -> body`` and a
    ``last_modified_for`` callable that returns whatever shape the test
    wants to simulate (string for COS, datetime for AWS).
    """

    def __init__(self, *, installer_keys, sha256_bodies=None,
                 sig_bodies=None, last_modified_for):
        self._installer_keys = list(installer_keys)
        self._sha256_bodies = sha256_bodies or {}
        self._sig_bodies = sig_bodies or {}
        self._last_modified_for = last_modified_for
        # MagicMock auto-creates anything else (e.g. put_object).

    def list_objects_v2(self, Bucket, Prefix, **kwargs):
        return {
            "Contents": [
                {
                    "Key": key,
                    "Size": 12345,
                    "LastModified": self._last_modified_for(key),
                }
                for key in self._installer_keys
                if key.startswith(Prefix)
            ]
        }

    def get_object(self, Bucket, Key, **kwargs):
        if Key in self._sha256_bodies:
            return {"Body": io.BytesIO(self._sha256_bodies[Key].encode())}
        if Key in self._sig_bodies:
            return {"Body": io.BytesIO(self._sig_bodies[Key])}
        # S3-style: raises ClientError for missing keys.
        from botocore.exceptions import ClientError
        raise ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "not found"}},
            "GetObject",
        )


def _attach_fake_s3(gen, last_modified_for, *,
                    with_signature=True, with_sha256=True):
    """Wire a fake S3 client onto the generator and return it."""
    installer_key = (
        "dev/releases/v1.0.0/windows/amd64/"
        "eCan-1.0.0-windows-amd64-Setup.exe"
    )
    sha256_bodies = {}
    sig_bodies = {}
    if with_sha256:
        sha256_bodies[installer_key + ".sha256"] = "a" * 64
    if with_signature:
        sig_bodies[installer_key + ".sig"] = b"fakesig"
    fake = _FakeS3Client(
        installer_keys=[installer_key],
        sha256_bodies=sha256_bodies,
        sig_bodies=sig_bodies,
        last_modified_for=last_modified_for,
    )
    gen.s3 = fake
    gen.cos = None
    return fake


def _pubdates_from(xml: str):
    """Pull every ``<pubDate>`` element from the rendered XML and return
    the list of (version, pubDate) tuples in document order."""
    root = ET.fromstring(xml)
    items = []
    for item in root.iter("item"):
        title = item.find("title")
        pubdate = item.find("pubDate")
        if title is None or pubdate is None:
            continue
        # Title is 'Version vX.Y.Z'; strip the prefix.
        ver = title.text.removeprefix("Version ") if title.text else ""
        items.append((ver, pubdate.text))
    return items


# ---------------------------------------------------------------------------
# The original CI crash: COS-style ISO-8601 strings
# ---------------------------------------------------------------------------

class TestCosStringLastModifiedEndToEnd:
    """The 2026-08-13 CI failure fed a string ``LastModified`` into
    ``generate_appcast()`` and crashed at ``strftime()``. These tests
    reproduce that path through the real ``get_package_info`` and
    assert the XML renders cleanly."""

    def test_single_cos_string_renders_valid_pubdate(self):
        gen = _bare_generator()
        iso = "2026-08-13T19:02:33.000Z"
        _attach_fake_s3(gen, last_modified_for=lambda key: iso)

        with patch.object(gen, "list_versions", return_value=["v1.0.0"]), \
             patch(
                 "build_system.scripts.generate_appcast."
                 "get_release_notes_from_changelog",
                 return_value="<p>notes</p>",
             ):
            xml = gen.generate_appcast("windows", "amd64")

        assert xml is not None, "generate_appcast returned None"
        pubdates = _pubdates_from(xml)
        assert len(pubdates) == 1
        ver, pubdate = pubdates[0]
        assert ver == "v1.0.0"
        assert PUBDATE_RE.match(pubdate), f"unexpected pubDate: {pubdate!r}"

    def test_two_cos_strings_sort_chronologically(self):
        gen = _bare_generator()
        # Two installs under different release dirs, different LM times.
        installs = [
            (
                "dev/releases/v1.0.0/windows/amd64/"
                "eCan-1.0.0-windows-amd64-Setup.exe",
                "2026-08-13T19:02:33.000Z",
            ),
            (
                "dev/releases/v0.9.0/windows/amd64/"
                "eCan-0.9.0-windows-amd64-Setup.exe",
                "2026-07-04T12:00:00.000Z",
            ),
        ]
        lm_map = dict(installs)
        fake = _FakeS3Client(
            installer_keys=[k for k, _ in installs],
            sha256_bodies={
                k + ".sha256": "a" * 64 for k, _ in installs
            },
            sig_bodies={
                k + ".sig": b"fakesig" for k, _ in installs
            },
            last_modified_for=lambda key: lm_map[key],
        )
        gen.s3 = fake
        gen.cos = None

        with patch.object(
            gen, "list_versions", return_value=["v1.0.0", "v0.9.0"],
        ), patch(
            "build_system.scripts.generate_appcast."
            "get_release_notes_from_changelog",
            return_value="<p>notes</p>",
        ):
            xml = gen.generate_appcast("windows", "amd64")

        pubdates = _pubdates_from(xml)
        # Newest (v1.0.0) on top, regardless of input order.
        assert [v for v, _ in pubdates] == ["v1.0.0", "v0.9.0"]
        for _, pd in pubdates:
            assert PUBDATE_RE.match(pd), f"unexpected pubDate: {pd!r}"


# ---------------------------------------------------------------------------
# The AWS-S3 path: boto3 returns real datetime objects
# ---------------------------------------------------------------------------

class TestBoto3DatetimeLastModifiedEndToEnd:
    """Make sure the fix didn't regress the boto3 path. AWS S3 returns
    a tz-aware ``datetime`` which previously worked, and must still
    work after the refactor."""

    def test_boto3_datetime_renders_valid_pubdate(self):
        gen = _bare_generator()
        lm = datetime(2026, 8, 13, 19, 2, 33, tzinfo=timezone.utc)
        _attach_fake_s3(gen, last_modified_for=lambda key: lm)

        with patch.object(gen, "list_versions", return_value=["v1.0.0"]), \
             patch(
                 "build_system.scripts.generate_appcast."
                 "get_release_notes_from_changelog",
                 return_value="<p>notes</p>",
             ):
            xml = gen.generate_appcast("windows", "amd64")

        pubdates = _pubdates_from(xml)
        assert len(pubdates) == 1
        _, pubdate = pubdates[0]
        assert PUBDATE_RE.match(pubdate), f"unexpected pubDate: {pubdate!r}"


# ---------------------------------------------------------------------------
# Mixed input: COS-string and boto3-datetime in the same appcast
# ---------------------------------------------------------------------------

class TestMixedLastModifiedSources:
    """If the migration from COS to AWS S3 (or vice versa) ever happens
    mid-stream, the appcast must still sort and render correctly."""

    def test_mixed_inputs_sort_and_render(self):
        gen = _bare_generator()
        installs = [
            (
                "dev/releases/v1.0.0/windows/amd64/"
                "eCan-1.0.0-windows-amd64-Setup.exe",
                datetime(2026, 8, 13, 19, 2, 33, tzinfo=timezone.utc),
            ),
            (
                "dev/releases/v0.9.0/windows/amd64/"
                "eCan-0.9.0-windows-amd64-Setup.exe",
                "2026-07-04T12:00:00.000Z",
            ),
        ]
        lm_map = dict(installs)
        fake = _FakeS3Client(
            installer_keys=[k for k, _ in installs],
            sha256_bodies={
                k + ".sha256": "a" * 64 for k, _ in installs
            },
            sig_bodies={
                k + ".sig": b"fakesig" for k, _ in installs
            },
            last_modified_for=lambda key: lm_map[key],
        )
        gen.s3 = fake
        gen.cos = None

        with patch.object(
            gen, "list_versions", return_value=["v1.0.0", "v0.9.0"],
        ), patch(
            "build_system.scripts.generate_appcast."
            "get_release_notes_from_changelog",
            return_value="<p>notes</p>",
        ):
            xml = gen.generate_appcast("windows", "amd64")

        pubdates = _pubdates_from(xml)
        # Newest (v1.0.0) must come first regardless of input type.
        assert [v for v, _ in pubdates] == ["v1.0.0", "v0.9.0"]
        for _, pd in pubdates:
            assert PUBDATE_RE.match(pd)
