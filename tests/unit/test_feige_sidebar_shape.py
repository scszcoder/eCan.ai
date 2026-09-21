"""What the sidebar is BUILT from, and whether a change to it gets recorded.

The strategy tally (`test_feige_row_name_tagging.py`) says which parser won.
That only moves once a parser has already started failing. This fingerprint
moves the moment the site ships the change — which is the earlier, cheaper
signal, and the one worth keeping forever.

Two incidents define the requirement: the June redesign took the hashed
wrappers away, and the September rebuild stopped emitting `data-qa-id` on
rebuilt frames. Both are anchors going absent. Meanwhile Feige rotates its
build hashes on every deploy, which must NOT register — a permanent record
that fills with routine-deploy noise is worth nothing when the real change
lands.

Business-side test: this is one site's DOM, so it names the site freely. The
platform counterpart asserts the opposite.
"""

import pathlib
import shutil
import subprocess

import pytest

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    sidebar_preview_js as sp,
    site_tools,
)

# Each is a DOM feature some parser depends on. Losing one is an incident.
EXPECTED_ANCHORS = {
    "data_qa_id_nickname",
    "qa_id_fuzzy_name",
    "name_line",
    "name_content",
    "titled_descendant",
    "legacy_hashed_wrap",
    "legacy_hashed_span",
    "preview_msg_content",
    "badge_count",
    "badge_sup",
    "user_label",
    "card_tag",
}


def test_every_parser_hook_is_probed():
    """An anchor missing from the fingerprint is a parser whose death would go
    unrecorded."""
    import re
    probed = set(re.findall(r"'([a-z0-9_]+)':\s+'", sp.SIDEBAR_SHAPE_JS))
    assert EXPECTED_ANCHORS <= probed, (
        f"unprobed parser hooks: {EXPECTED_ANCHORS - probed}"
    )


def test_the_name_parser_and_the_fingerprint_probe_the_same_selectors():
    """If they drift apart, the fingerprint starts watching a DOM feature
    nothing actually depends on — the exact failure ROW_NAME_JS was shared to
    prevent."""
    for selector in ('[data-qa-id="qa-conversation-nickname"]',
                     '[class*="nameLine"]',
                     '[class*="NameContent"]',
                     '.MP1bk3ccfHC9V2SnPCGD',
                     '.Jv6FtqUv5VoYARd2pp4y'):
        assert selector in sp.ROW_NAME_JS
        assert selector in sp.SIDEBAR_SHAPE_JS, (
            f"{selector} is depended on by the name parser but not watched"
        )


def test_the_scan_carries_the_fingerprint_back():
    """It rides the existing scan payload — no second CDP round trip on the
    hot path, which is what killed earlier detection attempts."""
    assert "__ecanSidebarShape" in site_tools._FEIGE_LIST_SESSIONS_JS
    assert "sidebar_shape" in site_tools._FEIGE_LIST_SESSIONS_JS


def test_the_scan_reports_the_fingerprint_to_the_journal():
    import inspect
    src = inspect.getsource(site_tools.feige_list_sessions)
    assert "drift_journal" in src and "note_shape" in src, (
        "site changes are no longer reaching the permanent record"
    )


def test_an_empty_sidebar_is_not_treated_as_a_site_change():
    """Not logged in, wrong tab, or a frame still building all produce zero
    rows. Adopting that as the baseline would make the next healthy scan look
    like a redesign — and would put a false record in a file kept for years."""
    import inspect
    src = inspect.getsource(site_tools.feige_list_sessions)
    assert "and sessions:" in src, (
        "the fingerprint must only be recorded from a scan that saw rows"
    )


# ── depth: the re-nesting blind spot ───────────────────────────────────────
#
# ROW_NAME_JS uses querySelector and does not care how deep an anchor sits.
# ROW_PREVIEW_FALLBACK_JS walks leaves and compares parentElement, so it DOES.
# A presence-only fingerprint would stay silent while a re-nesting broke the
# preview reader — which is the ws189 failure.

def test_the_fingerprint_records_how_deep_each_anchor_sits():
    assert "anchor_depths" in sp.SIDEBAR_SHAPE_JS
    assert "__ecanDepth" in sp.SIDEBAR_SHAPE_JS


def test_the_depth_walk_is_bounded():
    """A malformed tree must not spin: the walk gives up rather than looping."""
    assert "d < 30" in sp.SIDEBAR_SHAPE_JS


def test_the_preview_reader_is_the_reason_depth_is_watched():
    """Keep the two coupled: if the preview reader stops comparing parents,
    this watch is no longer paying for itself; if the watch is dropped while it
    still does, the gap reopens silently."""
    assert "parentElement" in sp.ROW_PREVIEW_FALLBACK_JS, (
        "the preview reader no longer walks parents — re-check whether depth "
        "still needs watching"
    )


def test_the_shipped_baseline_carries_depths():
    """The fingerprint shape changed; a baseline without depths would make
    every install report a day-one change."""
    from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
        baseline,
    )
    depths = baseline.load()["sidebar_row"].get("anchor_depths")
    assert depths, "the shipped baseline was not regenerated"
    assert depths.get("name_line"), "a load-bearing anchor has no recorded depth"


def test_no_customer_text_can_reach_the_fingerprint():
    """It is written to a store kept for three years."""
    js = sp.SIDEBAR_SHAPE_JS
    assert "textContent" not in js, (
        "the fingerprint must read structure, never text"
    )
    # Exactly one attribute value is read, and it is a machine identifier.
    assert js.count(".value") == 1 and "data-qa-id" in js


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_the_fingerprint_behaves(tmp_path):
    """Run the real shipped JS against fake rows for both incidents."""
    js_file = tmp_path / "shape.js"
    js_file.write_text(sp.SIDEBAR_SHAPE_JS, encoding="utf-8")

    harness = pathlib.Path(__file__).resolve().parents[1] / "js" / "sidebar_shape_behaviour.js"
    result = subprocess.run(["node", str(harness), str(js_file)],
                            capture_output=True, text=True)
    print(result.stdout, result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr


# ── every preview reader must carry the structural fallback ────────────────
#
# ws189 replaced a dead hashed preview selector with a leaf-walking fallback
# and wired it into three readers. The fourth — the agent-callable
# `feige_list_sessions` scan — was missed, and read the preview with the dead
# selector alone for the whole of the intervening period. That is the same
# class of drift ROW_NAME_JS was consolidated to stop, on the preview instead
# of the name.

DEAD_PREVIEW_SELECTOR = "lF_M7QiFB0ukHWpMfQde"


def _composed_snippets():
    """Every composed JS blob in site_tools, by attribute name."""
    return {name: value for name, value in vars(site_tools).items()
            if name.startswith("_FEIGE_") and isinstance(value, str)
            and "querySelector" in value}


def test_every_snippet_reading_the_dead_selector_also_has_the_fallback():
    offenders = []
    for name, js in _composed_snippets().items():
        if DEAD_PREVIEW_SELECTOR not in js:
            continue
        if "__ecanRowPreviewFallback" not in js:
            offenders.append(name)
    assert not offenders, (
        f"{offenders} read the preview with a selector documented dead on the "
        f"rebuilt frame, with no structural fallback — this is the ws189 shape"
    )


def test_the_sessions_scan_actually_calls_the_fallback():
    """Composing it in without calling it would look fixed and not be."""
    js = site_tools._FEIGE_LIST_SESSIONS_JS
    assert "function __ecanRowPreviewFallback" in js
    assert "__ecanRowPreviewFallback(el, name)" in js


def test_the_fallback_only_runs_when_the_selectors_miss():
    """It walks every leaf in the row, so it must not run on the happy path."""
    js = site_tools._FEIGE_LIST_SESSIONS_JS
    assert "if (!lastMsg) lastMsg = __ecanRowPreviewFallback" in js
