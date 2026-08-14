"""
Backend-parity tests for ``build_system/scripts/generate_appcast.py``.

The same code drives both:

  * **CN / COS** — ``storage_backend='cos'``, ``app_id='cn'`` — the
    ``qcloud_cos`` S3-compatible client. ``LastModified`` arrives as an
    ISO-8601 *string*; download URLs are ``https://{bucket}.cos.{region}.myqcloud.com/...``;
    no S3 Transfer Acceleration.

  * **INTL / S3** — ``storage_backend='s3'``, ``app_id='intl'`` — the
    standard boto3 client. ``LastModified`` arrives as a tz-aware
    ``datetime``; download URLs are ``https://{bucket}.s3.{region}.amazonaws.com/...``;
    S3 Transfer Acceleration is supported.

These tests wire a single fake client that speaks both protocols, then
drive the real ``get_package_info`` and ``generate_appcast`` for each
backend and assert the resulting appcast XML is identical (modulo the
expected URL-shape differences).

A regression in either backend — e.g. someone removing the
``_normalize_last_modified`` call, or hardcoding an AWS-shaped URL
in the COS branch — will be caught here.
"""

import io
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from build_system.scripts.generate_appcast import AppcastGenerator

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Constants & helpers
# ---------------------------------------------------------------------------

# RFC-822 pubDate pattern (what the appcast XML emits).
PUBDATE_RE = re.compile(
    r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun), "
    r"\d{2} (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) "
    r"\d{4} \d{2}:\d{2}:\d{2} \+0000$"
)

CN_BUCKET = "ecan-releases-1251680599"
CN_REGION = "ap-shanghai"
INTL_BUCKET = "ecan-releases-intl"
INTL_REGION = "us-east-1"

INSTALLER_KEY = (
    "dev/releases/v1.0.0/windows/amd64/"
    "eCan-1.0.0-windows-amd64-Setup.exe"
)


def _bare_generator(*, backend: str, app_id: str, bucket: str, region: str):
    """Build an ``AppcastGenerator`` without running ``__init__``.

    Mirrors the minimum state the real ``__init__`` sets, scoped to what
    ``get_package_info()`` and ``generate_appcast()`` actually touch.
    """
    gen = object.__new__(AppcastGenerator)
    gen.app_name = "eCan.cn" if app_id == "cn" else "eCan"
    gen.app_short_name = "eCan.cn" if app_id == "cn" else "eCan"
    gen.environment = "development"
    gen.app_id = app_id
    gen.storage_backend = backend
    gen.bucket = bucket
    gen.region = region
    gen.prefix = "dev"
    gen.channel = "dev"
    gen.base_path = ""
    return gen


class _DualBackendFake:
    """A single fake that speaks both the COS and S3 protocols.

    ``last_modified_for(key)`` returns whatever shape the test wants:

      * COS path:    returns an ISO-8601 *string* with ``'Z'`` suffix.
      * INTL path:   returns a tz-aware ``datetime``.

    ``list_objects`` (no ``_v2``) is what COS calls; ``list_objects_v2``
    is what boto3 calls. Both return the same response shape so the
    production code's branch is the only thing that decides which one
    is used.
    """

    def __init__(self, *, installer_keys, last_modified_for,
                 sha256_bodies=None, sig_bodies=None,
                 list_objects_v2_response=None):
        self._installer_keys = list(installer_keys)
        self._last_modified_for = last_modified_for
        self._sha256_bodies = sha256_bodies or {}
        self._sig_bodies = sig_bodies or {}
        # Optional override: when set, list_objects_v2 returns this dict
        # verbatim. Used by tests that want to drive `list_versions` via
        # the S3 path.
        self._list_objects_v2_response = list_objects_v2_response
        # Track which protocol was used; assertions can verify the
        # production code took the right branch.
        self.calls_cos = []
        self.calls_s3 = []

    # --- COS protocol ---
    def list_objects(self, Bucket, Prefix, **kwargs):
        self.calls_cos.append((Bucket, Prefix, kwargs))
        return self._build_listing(Prefix, kwargs)

    # --- INTL / boto3 protocol ---
    def list_objects_v2(self, Bucket, Prefix, **kwargs):
        self.calls_s3.append((Bucket, Prefix, kwargs))
        if self._list_objects_v2_response is not None:
            return self._list_objects_v2_response
        # Otherwise mirror the COS shape.
        return self._build_listing(Prefix, kwargs)

    def _build_listing(self, Prefix, kwargs):
        Delimiter = kwargs.get("Delimiter")
        if Delimiter == "/":
            # Build CommonPrefixes from any installer_key whose first
            # path segment after Prefix is unique.
            prefixes = set()
            for key in self._installer_keys:
                if not key.startswith(Prefix):
                    continue
                rest = key[len(Prefix):]
                if "/" in rest:
                    sub = rest.split("/", 1)[0]
                    prefixes.add(Prefix + sub + "/")
            return {
                "CommonPrefixes": [{"Prefix": p} for p in sorted(prefixes)],
                "Contents": [],
            }
        # Plain object listing (used by get_package_info).
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
        from botocore.exceptions import ClientError
        raise ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "not found"}},
            "GetObject",
        )


def _attach_fake(gen, fake, *, backend: str):
    """Wire the fake client onto the generator's correct slot."""
    if backend == "cos":
        gen.cos = fake
        gen.s3 = None
    else:
        gen.s3 = fake
        gen.cos = None


def _fake_for_cn(last_modified_for=None):
    """Convenience: build a fully-loaded CN/COS fake with sha256 + sig."""
    if last_modified_for is None:
        last_modified_for = lambda key: "2026-08-13T19:02:33.000Z"
    return _DualBackendFake(
        installer_keys=[INSTALLER_KEY],
        last_modified_for=last_modified_for,
        sha256_bodies={INSTALLER_KEY + ".sha256": "a" * 64},
        sig_bodies={INSTALLER_KEY + ".sig": b"fakesig"},
    )


def _fake_for_intl(last_modified_for=None):
    """Convenience: build a fully-loaded INTL/S3 fake with sha256 + sig."""
    if last_modified_for is None:
        last_modified_for = lambda key: datetime(
            2026, 8, 13, 19, 2, 33, tzinfo=timezone.utc,
        )
    return _DualBackendFake(
        installer_keys=[INSTALLER_KEY],
        last_modified_for=last_modified_for,
        sha256_bodies={INSTALLER_KEY + ".sha256": "a" * 64},
        sig_bodies={INSTALLER_KEY + ".sig": b"fakesig"},
    )


def _items_from(xml: str):
    """Parse the rendered appcast XML and return a list of item dicts."""
    root = ET.fromstring(xml)
    items = []
    for item in root.iter("item"):
        title = item.find("title")
        pubdate = item.find("pubdate") or item.find("pubDate")
        enclosure = item.find("enclosure")
        items.append({
            "version": (
                title.text.removeprefix("Version ") if title is not None and title.text else ""
            ),
            "pubdate": pubdate.text if pubdate is not None else None,
            "enclosure_url": enclosure.get("url") if enclosure is not None else None,
            "enclosure_length": enclosure.get("length") if enclosure is not None else None,
        })
    return items


def _run_generate_appcast(gen, versions):
    """Drive ``generate_appcast`` end-to-end with a fake client attached.

    Patches ``get_release_notes_from_changelog`` to skip CHANGELOG.md I/O
    and ``list_versions`` to return ``versions`` (so the test fully
    controls which releases are in scope).
    """
    with patch.object(gen, "list_versions", return_value=list(versions)), \
         patch(
             "build_system.scripts.generate_appcast."
             "get_release_notes_from_changelog",
             return_value="<p>notes</p>",
         ):
        return gen.generate_appcast("windows", "amd64")


# ---------------------------------------------------------------------------
# CN (Tencent COS) — string LastModified, COS URL shape
# ---------------------------------------------------------------------------

class TestCnCosBackend:
    """The CN app routes through COS. ``LastModified`` comes back as a
    string; download URLs use the ``cos.<region>.myqcloud.com`` shape;
    S3 Transfer Acceleration is unavailable."""

    def test_cn_string_lastmodified_renders_valid_pubdate(self):
        gen = _bare_generator(
            backend="cos", app_id="cn",
            bucket=CN_BUCKET, region=CN_REGION,
        )
        fake = _fake_for_cn()
        _attach_fake(gen, fake, backend="cos")

        xml = _run_generate_appcast(gen, ["v1.0.0"])

        items = _items_from(xml)
        assert len(items) == 1
        assert items[0]["pubdate"] is not None
        assert PUBDATE_RE.match(items[0]["pubdate"]), \
            f"unexpected pubDate: {items[0]['pubdate']!r}"

    def test_cn_uses_cos_list_objects_not_s3(self):
        # The original 2026-08-13 bug was specific to the COS branch.
        # Verify the production code actually took the COS branch by
        # asserting which fake method was invoked.
        gen = _bare_generator(
            backend="cos", app_id="cn",
            bucket=CN_BUCKET, region=CN_REGION,
        )
        fake = _fake_for_cn()
        _attach_fake(gen, fake, backend="cos")

        _run_generate_appcast(gen, ["v1.0.0"])

        # get_package_info calls list_objects; list_versions is patched
        # out, so we only see the package-info call here.
        assert any(call[0] == CN_BUCKET for call in fake.calls_cos), \
            "expected cos.list_objects to be called"
        assert fake.calls_s3 == [], \
            "INTL/S3 list_objects_v2 must not be called from CN backend"

    def test_cn_download_url_uses_myqcloud_endpoint(self):
        gen = _bare_generator(
            backend="cos", app_id="cn",
            bucket=CN_BUCKET, region=CN_REGION,
        )
        fake = _fake_for_cn()
        _attach_fake(gen, fake, backend="cos")

        xml = _run_generate_appcast(gen, ["v1.0.0"])

        items = _items_from(xml)
        url = items[0]["enclosure_url"]
        assert url is not None
        # COS endpoint shape, not AWS S3.
        assert url == (
            f"https://{CN_BUCKET}.cos.{CN_REGION}.myqcloud.com/"
            f"{INSTALLER_KEY}"
        )
        assert "amazonaws.com" not in url, \
            "CN app must not emit AWS S3 URLs"
        assert "s3-accelerate" not in url, \
            "COS has no S3 Transfer Acceleration"

    def test_cn_accelerated_url_is_none(self):
        # The COS branch sets accelerated_url = None; the rendered XML
        # uses the regular download_url as the enclosure URL. There's
        # no separate accelerated attribute on the enclosure element,
        # so this test pins the "no accelerated URL" behavior at the
        # dict level by inspecting the package_info flow indirectly:
        # the enclosure url must NOT be the AWS transfer-acceleration
        # endpoint.
        gen = _bare_generator(
            backend="cos", app_id="cn",
            bucket=CN_BUCKET, region=CN_REGION,
        )
        fake = _fake_for_cn()
        _attach_fake(gen, fake, backend="cos")

        with patch.object(gen, "list_versions", return_value=["v1.0.0"]), \
             patch(
                 "build_system.scripts.generate_appcast."
                 "get_release_notes_from_changelog",
                 return_value="<p>notes</p>",
             ):
            pkg = gen.get_package_info("v1.0.0", "windows", "amd64")

        assert pkg is not None
        # CN has no Transfer Acceleration; the field is explicitly None
        # per the production code.
        assert pkg["accelerated_url"] is None
        assert "myqcloud.com" in pkg["download_url"]

    def test_cn_handles_cos_string_with_offset_instead_of_z(self):
        # Some COS SDK versions emit '...+00:00' rather than '...Z'.
        # The fix should accept both shapes.
        gen = _bare_generator(
            backend="cos", app_id="cn",
            bucket=CN_BUCKET, region=CN_REGION,
        )
        fake = _fake_for_cn(
            last_modified_for=lambda key: "2026-08-13T19:02:33.000+00:00"
        )
        _attach_fake(gen, fake, backend="cos")

        xml = _run_generate_appcast(gen, ["v1.0.0"])
        items = _items_from(xml)
        assert PUBDATE_RE.match(items[0]["pubdate"]), \
            f"unexpected pubDate: {items[0]['pubdate']!r}"


# ---------------------------------------------------------------------------
# INTL (AWS S3) — datetime LastModified, AWS URL shape
# ---------------------------------------------------------------------------

class TestIntlS3Backend:
    """The INTL app routes through AWS S3. ``LastModified`` comes back
    as a tz-aware ``datetime``; download URLs use the
    ``s3.<region>.amazonaws.com`` shape; S3 Transfer Acceleration is
    available."""

    def test_intl_datetime_lastmodified_renders_valid_pubdate(self):
        gen = _bare_generator(
            backend="s3", app_id="intl",
            bucket=INTL_BUCKET, region=INTL_REGION,
        )
        fake = _fake_for_intl()
        _attach_fake(gen, fake, backend="s3")

        xml = _run_generate_appcast(gen, ["v1.0.0"])

        items = _items_from(xml)
        assert len(items) == 1
        assert PUBDATE_RE.match(items[0]["pubdate"]), \
            f"unexpected pubDate: {items[0]['pubdate']!r}"

    def test_intl_uses_s3_list_objects_v2_not_cos(self):
        gen = _bare_generator(
            backend="s3", app_id="intl",
            bucket=INTL_BUCKET, region=INTL_REGION,
        )
        fake = _fake_for_intl()
        _attach_fake(gen, fake, backend="s3")

        _run_generate_appcast(gen, ["v1.0.0"])

        assert any(call[0] == INTL_BUCKET for call in fake.calls_s3), \
            "expected s3.list_objects_v2 to be called"
        assert fake.calls_cos == [], \
            "CN/COS list_objects must not be called from INTL backend"

    def test_intl_download_url_uses_amazonaws_endpoint(self):
        gen = _bare_generator(
            backend="s3", app_id="intl",
            bucket=INTL_BUCKET, region=INTL_REGION,
        )
        fake = _fake_for_intl()
        _attach_fake(gen, fake, backend="s3")

        xml = _run_generate_appcast(gen, ["v1.0.0"])

        items = _items_from(xml)
        url = items[0]["enclosure_url"]
        assert url == (
            f"https://{INTL_BUCKET}.s3.{INTL_REGION}.amazonaws.com/"
            f"{INSTALLER_KEY}"
        )
        assert "myqcloud.com" not in url, \
            "INTL app must not emit COS URLs"

    def test_intl_exposes_accelerated_url_on_package_info(self):
        # INTL has S3 Transfer Acceleration; the dict carries a real
        # accelerated_url, but the rendered XML only uses the regular
        # download_url as the enclosure URL (Sparkle's <enclosure> has
        # a single url attribute). Pin both pieces of the contract.
        gen = _bare_generator(
            backend="s3", app_id="intl",
            bucket=INTL_BUCKET, region=INTL_REGION,
        )
        fake = _fake_for_intl()
        _attach_fake(gen, fake, backend="s3")

        with patch.object(gen, "list_versions", return_value=["v1.0.0"]), \
             patch(
                 "build_system.scripts.generate_appcast."
                 "get_release_notes_from_changelog",
                 return_value="<p>notes</p>",
             ):
            pkg = gen.get_package_info("v1.0.0", "windows", "amd64")

        assert pkg is not None
        assert pkg["accelerated_url"] is not None
        assert "s3-accelerate.amazonaws.com" in pkg["accelerated_url"]
        assert "amazonaws.com" in pkg["download_url"]


# ---------------------------------------------------------------------------
# Cross-backend parity — the contract every client depends on
# ---------------------------------------------------------------------------

class TestCnIntlParity:
    """The two backends must produce equivalent appcasts modulo the
    expected URL-shape differences. If they ever diverge on anything
    else (pubDate format, item order, enclosure length, etc.) this
    test catches it."""

    def test_pubdate_is_byte_identical_across_backends(self):
        # Same release, same LastModified instant, two backends.
        # The COS branch returns the LM as a string; the INTL branch
        # returns it as a datetime. After normalization, both must
        # render the exact same pubDate string.
        same_instant_str = "2026-08-13T19:02:33.000Z"
        same_instant_dt = datetime(2026, 8, 13, 19, 2, 33, tzinfo=timezone.utc)

        # CN run
        gen_cn = _bare_generator(
            backend="cos", app_id="cn",
            bucket=CN_BUCKET, region=CN_REGION,
        )
        _attach_fake(
            gen_cn,
            _fake_for_cn(last_modified_for=lambda k: same_instant_str),
            backend="cos",
        )
        xml_cn = _run_generate_appcast(gen_cn, ["v1.0.0"])

        # INTL run
        gen_intl = _bare_generator(
            backend="s3", app_id="intl",
            bucket=INTL_BUCKET, region=INTL_REGION,
        )
        _attach_fake(
            gen_intl,
            _fake_for_intl(last_modified_for=lambda k: same_instant_dt),
            backend="s3",
        )
        xml_intl = _run_generate_appcast(gen_intl, ["v1.0.0"])

        pd_cn = _items_from(xml_cn)[0]["pubdate"]
        pd_intl = _items_from(xml_intl)[0]["pubdate"]
        assert pd_cn == pd_intl, (
            f"CN/INTL pubDate diverged:\n  CN={pd_cn!r}\n  INTL={pd_intl!r}"
        )

    def test_item_count_and_order_match_across_backends(self):
        versions = ["v1.0.0", "v0.9.0"]
        same_lm = lambda key: "2026-08-13T19:02:33.000Z"
        same_lm_intl = lambda key: datetime(
            2026, 8, 13, 19, 2, 33, tzinfo=timezone.utc,
        )

        # CN
        gen_cn = _bare_generator(
            backend="cos", app_id="cn",
            bucket=CN_BUCKET, region=CN_REGION,
        )
        cn_installs = [
            f"dev/releases/{v}/windows/amd64/eCan-{v.lstrip('v')}-windows-amd64-Setup.exe"
            for v in versions
        ]
        _attach_fake(
            gen_cn,
            _DualBackendFake(
                installer_keys=cn_installs,
                last_modified_for=same_lm,
                sha256_bodies={k + ".sha256": "a" * 64 for k in cn_installs},
                sig_bodies={k + ".sig": b"fakesig" for k in cn_installs},
            ),
            backend="cos",
        )
        xml_cn = _run_generate_appcast(gen_cn, versions)

        # INTL
        gen_intl = _bare_generator(
            backend="s3", app_id="intl",
            bucket=INTL_BUCKET, region=INTL_REGION,
        )
        intl_installs = [
            f"dev/releases/{v}/windows/amd64/eCan-{v.lstrip('v')}-windows-amd64-Setup.exe"
            for v in versions
        ]
        _attach_fake(
            gen_intl,
            _DualBackendFake(
                installer_keys=intl_installs,
                last_modified_for=same_lm_intl,
                sha256_bodies={k + ".sha256": "a" * 64 for k in intl_installs},
                sig_bodies={k + ".sig": b"fakesig" for k in intl_installs},
            ),
            backend="s3",
        )
        xml_intl = _run_generate_appcast(gen_intl, versions)

        cn_versions = [i["version"] for i in _items_from(xml_cn)]
        intl_versions = [i["version"] for i in _items_from(xml_intl)]
        assert cn_versions == intl_versions == versions

        # Item length is identical.
        cn_lengths = [i["enclosure_length"] for i in _items_from(xml_cn)]
        intl_lengths = [i["enclosure_length"] for i in _items_from(xml_intl)]
        assert cn_lengths == intl_lengths


# ---------------------------------------------------------------------------
# Defensive: a real boto3 client that returns naive datetimes (rare, but
# documented) should still produce valid pubDate — the helper tags
# naive values as UTC rather than crashing.
# ---------------------------------------------------------------------------

class TestNaiveDatetimeFallback:
    def test_intl_with_naive_datetime_still_renders(self):
        gen = _bare_generator(
            backend="s3", app_id="intl",
            bucket=INTL_BUCKET, region=INTL_REGION,
        )
        # A custom fake that hands back a naive datetime (defensive).
        naive_lm = datetime(2026, 8, 13, 19, 2, 33)  # no tzinfo
        _attach_fake(
            gen,
            _fake_for_intl(last_modified_for=lambda k: naive_lm),
            backend="s3",
        )

        xml = _run_generate_appcast(gen, ["v1.0.0"])
        items = _items_from(xml)
        assert PUBDATE_RE.match(items[0]["pubdate"]), \
            f"unexpected pubDate: {items[0]['pubdate']!r}"
