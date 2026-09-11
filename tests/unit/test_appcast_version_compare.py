"""
Unit tests for ``ota/core/appcast.py::compare_versions`` and its
``_parse_main_version_parts`` / ``_parse_prerelease_parts`` / ``_normalize_version_text``
helpers, plus the public ``select_eligible_versions`` filter that drives
the actual "is there an update?" decision.

Regression guard for the 2026-09-11 incident: a client running
``0.9.97o`` failed to detect ``v0.9.97q`` in the appcast because
``compare_versions`` discarded the trailing letter and reported the two
versions as equal. These tests pin down the corrected behaviour plus
the full surface of supported version formats.
"""

import pytest

from ota.core.appcast import (
    AppcastItem,
    _parse_main_version_parts,
    _parse_prerelease_parts,
    _normalize_version_text,
    compare_versions,
    select_eligible_versions,
    version_tuple,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# _normalize_version_text
# ---------------------------------------------------------------------------


class TestNormalizeVersionText:
    def test_strips_leading_v(self):
        assert _normalize_version_text("v1.0.0") == "1.0.0"

    def test_no_leading_v_unchanged(self):
        assert _normalize_version_text("1.0.0") == "1.0.0"

    def test_strips_build_metadata(self):
        assert _normalize_version_text("1.0.0+build.42") == "1.0.0"

    def test_handles_spaces(self):
        assert _normalize_version_text("  1.0.0  ") == "1.0.0"

    def test_preserves_interior_v(self):
        # Branch builds like "0.7.0-v0.9.97d-53bdc77" start with "0", not
        # "v", so the leading-v strip is a no-op and the whole string
        # flows into the parser unchanged.
        s = "0.7.0-v0.9.97d-53bdc77"
        assert _normalize_version_text(s) == s

    def test_empty_or_none_safe(self):
        assert _normalize_version_text("") == ""
        assert _normalize_version_text(None) == ""


# ---------------------------------------------------------------------------
# _parse_main_version_parts — the function that broke on "0.9.97o"
# ---------------------------------------------------------------------------


class TestParseMainVersionParts:
    def test_standard_semver(self):
        assert _parse_main_version_parts("1.2.3") == [1, 2, 3]

    def test_with_v_prefix(self):
        assert _parse_main_version_parts("v1.2.3") == [1, 2, 3]

    def test_multi_segment(self):
        # Date-coded user builds: 26.05.03.22.22
        assert _parse_main_version_parts("26.05.03.22.22") == [26, 5, 3, 22, 22]

    def test_missing_segments_padded_with_zero(self):
        # Compare_versions pads with 0, but _parse_main_version_parts
        # itself just returns what's there.
        assert _parse_main_version_parts("1.0") == [1, 0]
        assert _parse_main_version_parts("1") == [1]

    def test_patch_letter_suffix_single_letter(self):
        # THE BUG: old code returned [0, 9, 97] for both "0.9.97o" and
        # "0.9.97q". The fix appends the letter ordinal so they differ.
        assert _parse_main_version_parts("0.9.97o") == [0, 9, 97, 15]
        assert _parse_main_version_parts("0.9.97q") == [0, 9, 97, 17]
        assert _parse_main_version_parts("0.9.97a") == [0, 9, 97, 1]
        assert _parse_main_version_parts("0.9.97z") == [0, 9, 97, 26]

    def test_patch_letter_suffix_case_insensitive(self):
        assert _parse_main_version_parts("0.9.97O") == [0, 9, 97, 15]
        assert _parse_main_version_parts("0.9.97Q") == [0, 9, 97, 17]

    def test_patch_multi_letter_suffix(self):
        # Multi-letter suffixes encode as base-27 numbers:
        # 'ab' = 1*27+2 = 29, 'ac' = 1*27+3 = 30, 'abc' = 1*729+2*27+3 = 786.
        assert _parse_main_version_parts("0.9.97ab") == [0, 9, 97, 29]
        assert _parse_main_version_parts("0.9.97abc") == [0, 9, 97, 786]
        assert _parse_main_version_parts("0.9.97zp") == [0, 9, 97, 26 * 27 + 16]

    def test_mixed_tail_stops_parsing(self):
        # "97rc1" is digits-then-mixed-tail. The fix takes the digits and
        # stops; the "rc1" remainder flows into the prerelease section.
        assert _parse_main_version_parts("1.0.97rc1") == [1, 0, 97]

    def test_non_numeric_token_stops_parsing(self):
        # Token like "alpha" or "v0" doesn't start with a digit, so the
        # main-section parser stops and the rest goes to prerelease.
        assert _parse_main_version_parts("1.0.alpha") == [1, 0]
        assert _parse_main_version_parts("0.7.0-v0.9.97d") == [0, 7, 0]


# ---------------------------------------------------------------------------
# compare_versions — the public API
# ---------------------------------------------------------------------------


class TestCompareVersions:
    """Comprehensive matrix covering every supported format."""

    # ----- standard semver -----

    def test_standard_semver_major_increment(self):
        assert compare_versions("2.0.0", "1.99.99") > 0
        assert compare_versions("1.99.99", "2.0.0") < 0

    def test_standard_semver_minor_increment(self):
        assert compare_versions("1.2.0", "1.1.99") > 0

    def test_standard_semver_patch_increment(self):
        assert compare_versions("1.0.1", "1.0.0") > 0

    def test_standard_semver_equal(self):
        assert compare_versions("1.0.0", "1.0.0") == 0

    def test_segment_count_padding(self):
        # 1.0 == 1.0.0 == 1.0.0.0
        assert compare_versions("1.0", "1.0.0") == 0
        assert compare_versions("1.0.0", "1.0.0.0") == 0
        # Shorter segments pad with 0
        assert compare_versions("1.0.0.1", "1.0.0") > 0

    # ----- v prefix -----

    def test_v_prefix_is_stripped(self):
        assert compare_versions("v1.0.0", "1.0.0") == 0
        assert compare_versions("v1.0.1", "v1.0.0") > 0
        # Note: the OTA client only strips ONE leading `v`. A string like
        # "vv1.0.0" becomes "v1.0.0" after normalization, which then fails
        # to parse as a numeric version (the remaining 'v' token breaks
        # the main-section parser) and falls back to [0]. This is a
        # separate quirk from the patch-suffix bug — see _normalize_version_text
        # in ota/core/appcast.py if it ever needs to change.

    # ----- build metadata -----

    def test_build_metadata_ignored(self):
        # 1.0.0+build.42 == 1.0.0 for comparison purposes (per semver).
        assert compare_versions("1.0.0+build.42", "1.0.0") == 0
        assert compare_versions("1.0.0+build.42", "1.0.0+build.99") == 0
        assert compare_versions("1.0.1+build.42", "1.0.0+build.42") > 0

    # ----- prerelease -----

    def test_release_outranks_prerelease(self):
        assert compare_versions("1.0.0", "1.0.0-beta") > 0
        assert compare_versions("1.0.0-rc.1", "1.0.0") < 0

    def test_prerelease_lexical_order(self):
        # semver rule: alpha < beta < preview < rc
        assert compare_versions("1.0.0-alpha", "1.0.0-beta") < 0
        assert compare_versions("1.0.0-beta", "1.0.0-rc") < 0
        assert compare_versions("1.0.0-rc", "1.0.0") < 0

    def test_prerelease_digit_vs_text(self):
        # semver rule: digit < text
        assert compare_versions("1.0.0-1", "1.0.0-alpha") < 0
        assert compare_versions("1.0.0-alpha", "1.0.0-1") > 0

    def test_prerelease_numeric_comparison(self):
        assert compare_versions("1.0.0-rc.1", "1.0.0-rc.2") < 0
        assert compare_versions("1.0.0-rc.9", "1.0.0-rc.10") < 0

    def test_prerelease_longer_wins_when_prefix_equal(self):
        assert compare_versions("1.0.0-alpha", "1.0.0-alpha.1") < 0
        assert compare_versions("1.0.0-alpha.1", "1.0.0-alpha.1.0") < 0

    # ----- multi-segment date-coded builds -----

    def test_multi_segment_date_coded(self):
        assert compare_versions("26.05.04.09.11", "26.05.03.22.22") > 0
        assert compare_versions("26.05.03.22.22", "26.05.04.09.11") < 0
        assert compare_versions("v26.05.03.22.22", "26.05.03.22.22") == 0

    # ----- branch builds -----

    def test_branch_build_strings_compare_by_main_section(self):
        # "0.7.0-v0.9.97d-53bdc77" splits at the first '-' so main=[0,7,0]
        # and prerelease=['v0','9','97d-53bdc77'].
        a = "0.7.0-v0.9.97d-53bdc77"
        b = "0.7.0-v0.9.97e-1234abc"
        assert compare_versions(a, a) == 0
        # 97e > 97d (string compare inside prerelease part)
        assert compare_versions(a, b) < 0

    # ----- THE REGRESSION CASE -----

    def test_patch_letter_suffix_o_vs_q(self):
        # Exact case from the 2026-09-11 incident.
        assert compare_versions("0.9.97o", "0.9.97q") < 0
        assert compare_versions("0.9.97q", "0.9.97o") > 0
        assert compare_versions("0.9.97o", "0.9.97o") == 0

    def test_patch_letter_suffix_sequence_orders_alphabetically(self):
        # All 26 letters must compare in order.
        letters = "abcdefghijklmnopqrstuvwxyz"
        versions = ["0.9.97" + ch for ch in letters]
        for a, b in zip(versions, versions[1:]):
            assert compare_versions(a, b) < 0, (
                f"expected {a} < {b} but compare_versions returned "
                f"{compare_versions(a, b)}"
            )

    def test_patch_letter_suffix_with_v_prefix(self):
        assert compare_versions("v0.9.97o", "v0.9.97q") < 0
        assert compare_versions("v0.9.97q", "0.9.97o") > 0

    def test_patch_letter_suffix_outranks_no_suffix_within_patch(self):
        # 0.9.97a > 0.9.97  (any letter makes the version newer than
        # the bare patch number, since 0 is < 1)
        assert compare_versions("0.9.97a", "0.9.97") > 0
        assert compare_versions("0.9.97", "0.9.97a") < 0

    def test_numeric_patch_increment_outranks_letter_suffix(self):
        # 0.9.98 > 0.9.97z (numeric always wins over any letter)
        assert compare_versions("0.9.98", "0.9.97z") > 0
        assert compare_versions("0.9.97z", "0.9.98") < 0

    def test_multi_letter_patch_suffix(self):
        assert compare_versions("0.9.97ab", "0.9.97ac") < 0
        assert compare_versions("0.9.97abc", "0.9.97abd") < 0
        # 'z' (26) < 'aa' (1,1 base-27 = 28) — but only because of our
        # base-27 encoding. The semantic intent is "any letter is newer
        # than no letter", and lexicographic within the suffix.
        assert compare_versions("0.9.97z", "0.9.97aa") < 0

    def test_case_insensitive_letter_suffix(self):
        assert compare_versions("0.9.97O", "0.9.97q") < 0
        assert compare_versions("0.9.97Q", "0.9.97o") > 0


# ---------------------------------------------------------------------------
# select_eligible_versions — the integration point that drives "is there an
# update?" decisions. The regression must be fixed at every layer.
# ---------------------------------------------------------------------------


class TestSelectEligibleVersions:
    def _item(self, version: str, sparkle_version: str | None = None) -> AppcastItem:
        return AppcastItem(
            version=sparkle_version or version,
            url=f"https://example.com/{version}.exe",
            os="windows",
            arch="amd64",
            length=1,
            content_type="application/octet-stream",
        )

    def test_current_0_9_97o_sees_0_9_97q_as_newer(self):
        # The exact bug: client on 0.9.97o, appcast has v0.9.97q.
        items = [self._item("v0.9.97q")]
        eligible = select_eligible_versions(
            items, platform_tag="windows", current_version="0.9.97o",
            arch_tag="amd64",
        )
        assert len(eligible) == 1
        assert eligible[0].version == "v0.9.97q"

    def test_current_0_9_97o_does_not_see_0_9_97n_as_newer(self):
        items = [self._item("v0.9.97n")]
        eligible = select_eligible_versions(
            items, platform_tag="windows", current_version="0.9.97o",
            arch_tag="amd64",
        )
        # n < o so this is NOT eligible
        assert eligible == []

    def test_current_0_9_97_sees_0_9_97a_as_newer(self):
        # No-suffix < any-suffix
        items = [self._item("v0.9.97a")]
        eligible = select_eligible_versions(
            items, platform_tag="windows", current_version="0.9.97",
            arch_tag="amd64",
        )
        assert len(eligible) == 1

    def test_full_letter_chain_filters_correctly(self):
        # Client on 0.9.97m. Every version from 0.9.97n onward is eligible.
        items = [
            self._item(f"v0.9.97{ch}")
            for ch in "abcdefghijklmnopqrstuvwxyz"
        ]
        eligible = select_eligible_versions(
            items, platform_tag="windows", current_version="0.9.97m",
            arch_tag="amd64",
        )
        eligible_versions = [it.version for it in eligible]
        # Everything from 'n' onward, sorted newest-first.
        assert eligible_versions == [
            "v0.9.97z", "v0.9.97y", "v0.9.97x", "v0.9.97w",
            "v0.9.97v", "v0.9.97u", "v0.9.97t", "v0.9.97s",
            "v0.9.97r", "v0.9.97q", "v0.9.97p", "v0.9.97o",
            "v0.9.97n",
        ]

    def test_empty_item_list_returns_empty(self):
        assert select_eligible_versions(
            [], platform_tag="windows", current_version="0.9.97o",
        ) == []

    def test_release_outranks_prerelease_filter(self):
        # Client on 1.0.0-rc.1 (prerelease) SHOULD see 1.0.0 (release) as
        # an upgrade — release > prerelease by semver rules.
        items = [self._item("v1.0.0")]
        eligible = select_eligible_versions(
            items, platform_tag="windows", current_version="1.0.0-rc.1",
        )
        assert len(eligible) == 1
        assert eligible[0].version == "v1.0.0"

    def test_higher_prerelease_not_eligible(self):
        # Client on 1.0.0-rc.5 should NOT see 1.0.0-rc.2 as an upgrade
        # (lower prerelease numbers are older).
        items = [self._item("v1.0.0-rc.2")]
        eligible = select_eligible_versions(
            items, platform_tag="windows", current_version="1.0.0-rc.5",
        )
        assert eligible == []

    def test_higher_prerelease_is_eligible(self):
        # Client on 1.0.0-rc.5 SHOULD see 1.0.0-rc.10 (rc.10 > rc.5).
        items = [self._item("v1.0.0-rc.10")]
        eligible = select_eligible_versions(
            items, platform_tag="windows", current_version="1.0.0-rc.5",
        )
        assert len(eligible) == 1


# ---------------------------------------------------------------------------
# version_tuple — the legacy helper
# ---------------------------------------------------------------------------


class TestVersionTuple:
    def test_returns_three_tuple(self):
        assert version_tuple("1.2.3") == (1, 2, 3)

    def test_letter_suffix_in_third_position_uses_digit_prefix(self):
        # version_tuple is the legacy helper that only takes the first
        # three X.Y.Z numbers; letter suffix information is lost.
        # compare_versions is the right tool for full comparison.
        assert version_tuple("0.9.97o") == (0, 9, 97)
        assert version_tuple("0.9.97q") == (0, 9, 97)
        # So callers must use compare_versions, not version_tuple, when
        # letter suffixes are in play.
