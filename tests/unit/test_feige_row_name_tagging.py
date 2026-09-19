"""The sidebar name parser must keep saying WHICH branch resolved a row.

`__ecanRowName` is six years of scar tissue: `data-qa-id` → `nameLine` →
`NameContent` → the ws110 drift fallback → the ws183 titled-descendant scan →
two legacy hashed classes. Every layer is an incident (ws110, ws183, ws193,
mt062/063, the June redesign), and nobody knows which ones still fire.

Phase 1 of docs/SELF_HEALING_ROADMAP.md tags each branch so a scan can report
the distribution. That evidence decides whether Phase 2 is worth building —
so these tests protect the tagging from being quietly dropped, and protect the
return values from being changed by it.

Business-side test: this file is about one site's parser, so it lives with the
other business tests and names the site freely. The platform counterpart
(`test_element_targeting.py`) asserts the opposite — that platform code names
no site at all.
"""

import re

import pytest

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    sidebar_preview_js as sp,
)

# Every branch that can resolve a name, plus the miss case.
EXPECTED_STRATEGIES = {
    "data_qa_id_nickname",
    "name_line_title",
    "name_line_content",
    "name_content",
    "ws110_fuzzy_qa_id",
    "ws183_titled_scan",
    "legacy_hashed_wrap",
    "legacy_hashed_span",
    "unresolved",
}


def test_every_branch_reports_a_strategy():
    tagged = set(re.findall(r"__ecanRowNameTag\('([a-z0-9_]+)'", sp.ROW_NAME_JS))
    assert tagged == EXPECTED_STRATEGIES, (
        f"branch tags drifted; missing={EXPECTED_STRATEGIES - tagged} "
        f"unexpected={tagged - EXPECTED_STRATEGIES}"
    )


def test_no_branch_returns_untagged():
    """A bare `return <value>` inside the parser would vanish from the tally.

    Only the guard clause (`if(!row||!row.querySelector) return '';`) is
    allowed to return untagged — a null row is not a resolution.
    """
    body = sp.ROW_NAME_JS.split("function __ecanRowName(row){", 1)[1]
    returns = re.findall(r"return ([^;]+);", body)
    untagged = [
        r.strip() for r in returns
        if "__ecanRowNameTag" not in r and r.strip() != "''"
    ]
    assert not untagged, f"untagged returns in __ecanRowName: {untagged}"


def test_the_tag_helper_passes_the_value_straight_through():
    """Tagging must be observation only — it may never alter a name."""
    helper = re.search(r"function __ecanRowNameTag\(strategy, value\)\{(.*?)\n  \}",
                       sp.ROW_NAME_JS, re.S)
    assert helper, "tag helper missing"
    assert "return value;" in helper.group(1), (
        "the tag helper must return its input unchanged"
    )


def test_tagging_failure_cannot_break_name_resolution():
    """A hostile or frozen page must not turn a name into an exception."""
    helper = re.search(r"function __ecanRowNameTag.*?\n  \}", sp.ROW_NAME_JS, re.S)
    assert "try" in helper.group(0) and "catch" in helper.group(0), (
        "tally bookkeeping must be wrapped — a page we do not control can "
        "freeze or redefine the global"
    )


def test_the_tally_global_is_reset_per_scan():
    """Each scan reports its own rows, not a running total since page load."""
    assert "window.__ecanRowNameTally = {}" in sp.ROW_NAME_TALLY_DRAIN_JS


def test_the_scan_hands_the_tally_back():
    """No second CDP round trip on the hot path — it rides the scan payload."""
    from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
        site_tools,
    )
    assert "name_strategies" in site_tools._FEIGE_LIST_SESSIONS_JS
    assert "__ecanRowNameTally" in site_tools._FEIGE_LIST_SESSIONS_JS


def test_the_scan_reports_to_the_platform_recorder():
    import inspect
    from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
        site_tools,
    )
    src = inspect.getsource(site_tools.feige_list_sessions)
    assert "record_from_js_tally" in src, (
        "the scan no longer reports which parser resolved its rows"
    )


@pytest.mark.parametrize("dead_selector", [".MP1bk3ccfHC9V2SnPCGD",
                                           ".Jv6FtqUv5VoYARd2pp4y"])
def test_the_legacy_hashed_selectors_are_still_present_but_last(dead_selector):
    """They are suspected dead — the ws183 titled scan catches anything the
    wrap branch could match, so it is likely unreachable. Keep them until the
    live counter proves it, then delete with evidence rather than by guess.
    """
    js = sp.ROW_NAME_JS
    assert dead_selector in js
    ws183_at = js.index("titledAll")
    assert js.index(dead_selector) > ws183_at, (
        "legacy hashed selectors must stay AFTER the semantic scan"
    )
