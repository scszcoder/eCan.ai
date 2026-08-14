"""
Unit tests for ``build_system/scripts/generate_appcast.py``.

Currently focused on the ``LastModified`` normalization bug: the COS
S3-compatible client returns ``LastModified`` as an ISO-8601 string,
while boto3 against AWS S3 returns a real ``datetime``. The chronological
sort key and the XML ``pubDate`` formatter both need a real ``datetime``,
so we normalize once at the source.
"""

import sys
from datetime import datetime, timezone, timedelta

import pytest

from build_system.scripts.generate_appcast import (
    _normalize_last_modified,
    _to_release_dir,
    _split_release_dir,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# _normalize_last_modified
# ---------------------------------------------------------------------------

class TestNormalizeLastModified:
    """The COS-string vs boto3-datetime split is the whole point of the
    helper; both branches must yield a tz-aware UTC ``datetime``."""

    def test_cos_iso_string_with_z_suffix(self):
        # This is the exact shape that crashed generate_appcast.py in CI
        # on 2026-08-13: `obj['LastModified']` was a string ending in 'Z'.
        result = _normalize_last_modified("2026-08-13T19:02:33.000Z")

        assert isinstance(result, datetime)
        assert result.tzinfo is not None
        assert result.utcoffset() == timedelta(0)
        assert result.year == 2026
        assert result.month == 8
        assert result.day == 13
        assert result.hour == 19
        assert result.minute == 2
        assert result.second == 33
        assert result.microsecond == 0

    def test_cos_iso_string_with_offset(self):
        # Some COS SDK versions emit an explicit '+00:00' rather than 'Z'.
        result = _normalize_last_modified("2026-08-13T19:02:33.000+00:00")

        assert result.tzinfo is not None
        assert result.utcoffset() == timedelta(0)

    def test_cos_iso_string_with_positive_offset_preserved(self):
        # Non-UTC strings must keep their offset (we only re-tag *naive*
        # datetimes as UTC).
        result = _normalize_last_modified("2026-08-13T19:02:33+08:00")

        assert result.utcoffset() == timedelta(hours=8)
        # Converting back to UTC yields the original wall-clock hour - 8.
        assert result.astimezone(timezone.utc).hour == 11

    def test_boto3_aware_datetime_is_preserved(self):
        # AWS S3 returns a tz-aware datetime (boto3 with `datetime` payloads).
        original = datetime(2026, 8, 13, 19, 2, 33, tzinfo=timezone.utc)

        result = _normalize_last_modified(original)

        # Same value, same tz — we don't accidentally rewrite it.
        assert result is original

    def test_boto3_aware_datetime_non_utc_preserved(self):
        # boto3 typically returns UTC, but if a custom client ever returns
        # a non-UTC aware datetime, we must keep the offset intact.
        original = datetime(2026, 8, 13, 19, 2, 33,
                            tzinfo=timezone(timedelta(hours=8)))

        result = _normalize_last_modified(original)

        assert result is original
        assert result.utcoffset() == timedelta(hours=8)

    def test_naive_datetime_is_tagged_utc(self):
        # Defensive: a rare caller that hands us a naive datetime should
        # NOT crash, and the XML pubDate is rendered with `+0000` so the
        # assumption is explicit.
        naive = datetime(2026, 8, 13, 19, 2, 33)

        result = _normalize_last_modified(naive)

        assert result.tzinfo is timezone.utc
        assert result.utcoffset() == timedelta(0)

    def test_result_is_sortable(self):
        # The chronological-by-LastModified sort at line ~947 requires the
        # values to be orderable. After normalization, two COS strings
        # that the old code would have sorted *lexicographically* (which
        # happens to match for ISO-8601 but is fragile) now sort by real
        # time even when the format differs.
        older = _normalize_last_modified("2026-01-01T00:00:00.000Z")
        newer = _normalize_last_modified("2026-12-31T23:59:59.999Z")

        assert older < newer

    def test_result_supports_strftime(self):
        # The XML pubDate formatter calls .strftime('%a, %d %b %Y %H:%M:%S +0000').
        # This is the exact crash that motivated the fix.
        normalized = _normalize_last_modified("2026-08-13T19:02:33.000Z")

        formatted = normalized.strftime('%a, %d %b %Y %H:%M:%S +0000')

        # Don't pin the weekday name (locale-dependent), just the structure.
        assert formatted.endswith("13 Aug 2026 19:02:33 +0000")
        assert " 2026 " in formatted


# ---------------------------------------------------------------------------
# Round-trip with the XML formatter
# ---------------------------------------------------------------------------

class TestPubDateFormatRoundTrip:
    """End-to-end check that a COS-style LastModified value flows through
    ``strftime`` into a valid RFC-2822-style pubDate string."""

    def test_cos_string_renders_valid_pubdate(self):
        # The shape Sparkle clients expect (RFC-822-ish).
        normalized = _normalize_last_modified("2026-08-13T19:02:33.000Z")
        rendered = normalized.strftime('%a, %d %b %Y %H:%M:%S +0000')

        # %a renders 'Thu,' (with comma). Use a regex that matches the
        # full RFC-822-shaped pubDate format, regardless of platform locale
        # for weekday/month abbreviations.
        import re
        pattern = (
            r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun), "
            r"\d{2} (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) "
            r"\d{4} \d{2}:\d{2}:\d{2} \+0000$"
        )
        assert re.match(pattern, rendered), f"unexpected pubDate: {rendered!r}"


# ---------------------------------------------------------------------------
# Sibling helpers — quick smoke tests so we know the test harness imports
# the whole module without side-effects.
# ---------------------------------------------------------------------------

class TestSiblingHelpers:
    def test_to_release_dir_universal(self):
        assert _to_release_dir("1.0.0") == "v1.0.0"

    def test_to_release_dir_with_user_prefix(self):
        assert _to_release_dir("26.05.04", "songc") == "songc_v26.05.04"

    def test_split_release_dir_universal(self):
        assert _split_release_dir("v1.0.0") == (None, "1.0.0")

    def test_split_release_dir_user_prefix(self):
        assert _split_release_dir("songc_v1.0.0") == ("songc", "1.0.0")
