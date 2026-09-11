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
    _letter_suffix_to_ordinal,
    AppcastGenerator,
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


# ---------------------------------------------------------------------------
# Patch letter-suffix support
# ---------------------------------------------------------------------------
#
# Regression guard for the "v0.9.97o cannot see v0.9.97q" bug discovered
# on 2026-09-11. The server-side sort key (used by generate_appcast.py to
# order the <item>s in the appcast XML) and the client-side filter
# (compare_versions in ota/core/appcast.py) must agree. These tests pin
# down the server-side tuple shape and ordering.


class TestLetterSuffixToOrdinal:
    """The helper that turns 'o' → 15, 'q' → 17, 'abc' → (1,2,3)."""

    def test_single_letter_a_to_z(self):
        # Sanity check on the alphabet-to-number mapping.
        assert _letter_suffix_to_ordinal("a") == 1
        assert _letter_suffix_to_ordinal("o") == 15
        assert _letter_suffix_to_ordinal("q") == 17
        assert _letter_suffix_to_ordinal("z") == 26

    def test_single_letter_is_case_insensitive(self):
        assert _letter_suffix_to_ordinal("O") == 15
        assert _letter_suffix_to_ordinal("Q") == 17

    def test_multi_letter_ordered_lexically(self):
        # 'ab' must be < 'ac'; 'abc' must be < 'abd'; etc.
        assert _letter_suffix_to_ordinal("ab") < _letter_suffix_to_ordinal("ac")
        assert _letter_suffix_to_ordinal("abc") < _letter_suffix_to_ordinal("abd")
        assert _letter_suffix_to_ordinal("z") < _letter_suffix_to_ordinal("aa")

    def test_real_build_sequence_orders_correctly(self):
        # The actual eCan patch-suffix sequence used in production.
        seq = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j",
               "k", "l", "m", "n", "o", "p", "q", "r", "s", "t",
               "u", "v", "w", "x", "y", "z"]
        ordinals = [_letter_suffix_to_ordinal(s) for s in seq]
        assert ordinals == sorted(ordinals)


class TestParseVersionPatchLetterSuffix:
    """`parse_version` must return `(major, minor, patch, priority, letter_ord)`
    so that the 5-tuple correctly orders v0.9.97q above v0.9.97o."""

    def _gen(self) -> AppcastGenerator:
        # We only need parse_version; bypass real config loading by passing
        # required constructor args and accepting that we never call run().
        # The constructor still tries to load ota_config.yaml; the test
        # path runs from the repo root so this is fine.
        return AppcastGenerator(environment="production", channel="stable")

    def test_standard_semver(self):
        g = self._gen()
        assert g.parse_version("1.0.0") == (1, 0, 0, 1000, 0)
        assert g.parse_version("v1.2.3") == (1, 2, 3, 1000, 0)

    def test_user_prefixed_version(self):
        g = self._gen()
        # Prefix must be stripped before parsing the numeric core.
        assert g.parse_version("songc_v26.05.04.09.11") == (26, 5, 4, 1000, 0)

    def test_prerelease_rc_lowers_priority(self):
        g = self._gen()
        result = g.parse_version("1.0.0-rc.1")
        assert result[0] == 1 and result[1] == 0 and result[2] == 0
        assert result[3] == 900  # rc priority
        assert result[4] == 0    # no letter suffix

    def test_branch_build_lowers_priority(self):
        g = self._gen()
        result = g.parse_version("0.7.0-v0.9.97d-53bdc77")
        assert result == (0, 7, 0, 0, 0)

    def test_patch_letter_suffix_q_is_newer_than_o(self):
        # The exact case that triggered this fix: client was running
        # v0.9.97o and the appcast contained v0.9.97q. The old code
        # returned (0,9,97,0) for both, so the sort treated them as equal.
        g = self._gen()
        assert g.parse_version("0.9.97o") == (0, 9, 97, 1000, 15)
        assert g.parse_version("0.9.97q") == (0, 9, 97, 1000, 17)
        # Sort order: q > o
        assert g.parse_version("0.9.97q") > g.parse_version("0.9.97o")

    def test_patch_letter_sequence_orders_correctly(self):
        # All single letters from 'a' to 'z' must sort in order after a
        # numeric version.
        g = self._gen()
        versions = ["0.9.97" + ch for ch in "abcdefghijklmnopqrstuvwxyz"]
        parsed = [g.parse_version(v) for v in versions]
        assert parsed == sorted(parsed)

    def test_letter_suffix_outranks_no_suffix_within_same_patch(self):
        # 0.9.97a vs 0.9.97: the letter-suffixed one should sort strictly
        # greater so that eCan clients running 0.9.97 see 0.9.97a as new.
        g = self._gen()
        assert g.parse_version("0.9.97a") > g.parse_version("0.9.97")
        assert g.parse_version("0.9.97") < g.parse_version("0.9.97a")

    def test_numeric_patch_increment_outranks_letter_suffix(self):
        # 0.9.98 must sort greater than 0.9.97z (numeric > any letter).
        g = self._gen()
        assert g.parse_version("0.9.98") > g.parse_version("0.9.97z")

    def test_v_prefix_with_letter_suffix(self):
        # Sparkle-style `v` prefix must coexist with the letter suffix.
        g = self._gen()
        assert g.parse_version("v0.9.97o") == g.parse_version("0.9.97o")

    def test_user_prefixed_letter_suffix(self):
        # alice_v0.9.97k → user_prefix=alice, version=0.9.97k
        # Numeric-only prefixes (e.g. '1050588178_v0.9.97k') are not
        # recognised as user prefixes by _PREFIXED_DIR_RE on the server
        # side (nor by the client-side _split_user_prefix); they fall
        # through to the full-string version parser, which will fail.
        g = self._gen()
        assert g.parse_version("alice_v0.9.97k") == (0, 9, 97, 1000, 11)

    def test_multi_letter_patch_suffix(self):
        # 'ab' < 'ac'; 'abc' < 'abd'.
        g = self._gen()
        assert g.parse_version("0.9.97ab") < g.parse_version("0.9.97ac")
        assert g.parse_version("0.9.97abc") < g.parse_version("0.9.97abd")

    def test_sort_real_build_list(self):
        # End-to-end: sort a realistic mixed list newest-first.
        # Tuple comparison is lexicographic on (major, minor, patch, ...).
        # Priority is only a tiebreaker for the same major.minor.patch,
        # so 1.0.0-rc.1 (major=1) sorts above 0.9.98 (major=0) even
        # though rc has priority 900 < standard 1000.
        g = self._gen()
        versions = [
            "0.9.97n", "0.9.97o", "0.9.97p", "0.9.97q",
            "0.9.97m", "0.9.96", "0.9.98",
            "1.0.0-rc.1", "0.7.0-v0.9.97d-53bdc77",
        ]
        newest_first = sorted(versions, key=g.parse_version, reverse=True)
        # 1.0.0-rc.1 (major=1) > 0.9.98 (major=0)
        assert newest_first[0] == "1.0.0-rc.1"
        # Then 0.9.98 (next numeric major.minor.patch).
        assert newest_first[1] == "0.9.98"
        # Then the 0.9.97 letter-suffix chain sorted descending.
        assert newest_first[2:6] == ["0.9.97q", "0.9.97p", "0.9.97o", "0.9.97n"]
        # Then 0.9.97m.
        assert newest_first[6] == "0.9.97m"
        # Then 0.9.96.
        assert newest_first[7] == "0.9.96"
        # Then the branch build (priority 0).
        assert newest_first[8] == "0.7.0-v0.9.97d-53bdc77"
