"""A build ships what it expects, so a fresh install detects drift on day one.

The hole this closes: the journal compares against the last shape seen *on this
machine*, so a fresh install adopts whatever it sees first as normal. The first
machine to meet a redesign therefore records it as correct and never flags it —
only the *second* change would ever be caught, which is the wrong one.

The tests split into three concerns:

1. The mechanism (platform): does a shipped baseline actually get used, and does
   the record say which baseline it was measured against?
2. The shipped file (business): is what we ship self-consistent and free of the
   fields that would make every install cry wolf on day one?
3. The loop: can a healthy machine produce the next build's baseline?
"""

import json
import pathlib

import pytest

from agent.ec_skills.browser_use_extension import drift_journal as dj


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("ECAN_DRIFT_JOURNAL_DIR", str(tmp_path / "journal"))
    dj.reset_incident_window()
    dj._SHIPPED.clear()
    yield
    dj._SHIPPED.clear()
    dj.reset_incident_window()


EXPECTED = {"anchors_present": ["data_qa_id_nickname", "name_line"],
            "attributes": ["class", "data-qa-id", "title"]}
AS_FOUND = {"anchors_present": ["name_line"],
            "attributes": ["class", "title"]}


# ── 1. the mechanism ───────────────────────────────────────────────────────

def test_without_a_shipped_baseline_a_fresh_install_stays_silent():
    """Today's behaviour, and the hole: nothing to compare against."""
    assert dj.note_shape("s", "row", AS_FOUND) is None
    assert dj.read_events() == []


def test_with_a_shipped_baseline_the_FIRST_sighting_reports():
    """The whole point. No local history, and it still catches the change."""
    dj.register_shipped_baseline("s", {"row": EXPECTED})
    delta = dj.note_shape("s", "row", AS_FOUND)
    assert delta, "a fresh install did not detect drift against the shipped shape"
    assert "data_qa_id_nickname" in delta["anchors_present"]["lost"]
    assert dj.read_events()


def test_a_machine_matching_the_shipped_shape_says_nothing():
    """The false-positive floor: every healthy install must be silent, or the
    first run of every deployment writes a phantom record."""
    dj.register_shipped_baseline("s", {"row": EXPECTED})
    assert dj.note_shape("s", "row", EXPECTED) is None
    assert dj.read_events() == []


def test_the_record_says_which_baseline_it_was_measured_against():
    """A difference from the SHIPPED shape can also mean an old build or a
    rollout bucket. Whoever reads this in a year needs to know which it was."""
    dj.register_shipped_baseline("s", {"row": EXPECTED})
    dj.note_shape("s", "row", AS_FOUND)
    (event,) = dj.read_events()
    assert event["evidence"]["compared_against"] == "shipped"
    assert "shipped" in str(event["evidence"]["previous_shape_held_since"])


def test_a_local_history_takes_precedence_over_the_shipped_shape():
    """Once a machine has its own history that is the better baseline — it
    reflects what this install actually sees, rollout bucket included."""
    dj.register_shipped_baseline("s", {"row": EXPECTED})
    dj.note_shape("s", "row", AS_FOUND)          # adopts AS_FOUND locally
    dj.reset_incident_window()
    assert dj.note_shape("s", "row", AS_FOUND) is None
    (event,) = dj.read_events()
    assert event["evidence"]["compared_against"] == "shipped"


def test_a_later_change_is_measured_locally_not_against_the_build():
    dj.register_shipped_baseline("s", {"row": EXPECTED})
    dj.note_shape("s", "row", AS_FOUND)
    dj.reset_incident_window()
    dj.note_shape("s", "row", {"anchors_present": [], "attributes": ["class"]})
    kinds = [e["evidence"]["compared_against"] for e in dj.read_events()]
    assert "local" in kinds, "a second change was still blamed on the build"


def test_a_shipped_baseline_only_applies_to_its_own_site_and_keys():
    dj.register_shipped_baseline("s", {"row": EXPECTED})
    assert dj.note_shape("other_site", "row", AS_FOUND) is None
    assert dj.note_shape("s", "other_key", AS_FOUND) is None


def test_registering_junk_does_not_raise():
    for junk in (None, "string", 42, []):
        dj.register_shipped_baseline("s", junk)     # must not raise


# ── 2. what we actually ship ───────────────────────────────────────────────

BUNDLE = (pathlib.Path(__file__).resolve().parents[2] / "agent" / "ec_skills"
          / "browser_use_extension" / "hooks" / "external" / "feige_chat")


def test_the_bundle_ships_a_baseline():
    from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
        baseline,
    )
    shapes = baseline.load()
    assert "sidebar_row" in shapes and "ws_message_fields" in shapes


def test_the_shipped_file_records_where_it_came_from():
    """A baseline of unknown origin is worse than none: you cannot tell a real
    change from a bad baseline."""
    raw = json.loads((BUNDLE / "baseline.json").read_text(encoding="utf-8"))
    assert raw.get("_provenance"), "no provenance recorded"
    assert any("layouts.json" in line or "export-baseline" in line
               for line in raw["_provenance"])


def test_the_shipped_shape_carries_no_deploy_marker():
    """The marker rotates on every site deploy. Shipping one would make every
    install report a deploy on its first scan."""
    from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
        baseline,
    )
    row = baseline.load()["sidebar_row"]
    assert "build_marker" not in row
    assert "rows_sampled" not in row


def test_the_shipped_ws_shape_claims_no_monotonic_history():
    """`optional_ever_seen` grows over a machine's life. A fresh install has
    legitimately seen none, so shipping a populated set would make it report
    them all as lost on day one."""
    from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
        baseline,
    )
    ws = baseline.load()["ws_message_fields"]
    assert ws["optional_ever_seen"] == []
    assert ws["unexpected_ever_seen"] == []


def test_the_shipped_core_keys_match_the_watcher():
    """If they drift apart, every install reports a schema change immediately."""
    from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
        baseline, ws_protocol_watch as wpw,
    )
    ws = baseline.load()["ws_message_fields"]
    assert set(ws["core_populated"]) == set(wpw.CORE_KEYS)


def test_a_healthy_machine_matching_the_shipped_shape_is_silent():
    """End to end on the real shipped file: the fingerprint of the layout we
    believe is current must not read as a change."""
    from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
        baseline,
    )
    baseline.register()
    shapes = baseline.load()
    assert dj.note_shape("feige_chat", "sidebar_row", shapes["sidebar_row"]) is None
    assert dj.read_events() == []


def test_the_bundle_registers_its_baseline_where_shapes_are_reported():
    import inspect
    from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
        site_tools, ws_protocol_watch,
    )
    assert "_baseline.register()" in inspect.getsource(site_tools.feige_list_sessions)
    assert "_baseline.register()" in inspect.getsource(ws_protocol_watch)


def test_registration_is_idempotent_and_cheap():
    """It sits next to a per-scan call; re-reading the file every scan would be
    a needless cost on the hot path."""
    from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
        baseline,
    )
    baseline._REGISTERED = False
    calls = []
    original = baseline.load
    baseline.load = lambda: (calls.append(1), original())[1]
    try:
        for _ in range(20):
            baseline.register()
    finally:
        baseline.load = original
    assert len(calls) == 1


def test_a_missing_baseline_file_degrades_to_machine_local(monkeypatch):
    from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
        baseline,
    )
    monkeypatch.setattr(baseline, "_BASELINE_FILE",
                        pathlib.Path("does") / "not" / "exist.json")
    assert baseline.load() == {}


# ── 3. the loop ────────────────────────────────────────────────────────────

def test_a_healthy_machine_can_produce_the_next_baseline():
    """S12 step 5: the fleet's winner becomes build N+1's baseline, and the
    mechanism for that is this export."""
    import cli.base.output as output_module
    from click.testing import CliRunner
    from cli.drift.commands import drift

    dj.note_shape("feige_chat", "sidebar_row",
                  {"anchors_present": ["name_line"], "build_marker": {"digest": "a"},
                   "rows_sampled": 12, "optional_ever_seen": ["goods_id"]})

    output_module._global_output = None
    try:
        result = CliRunner().invoke(
            drift, ["export-baseline", "--site", "feige_chat"])
    finally:
        output_module._global_output = None

    assert result.exit_code == 0, result.output
    start = result.output.index("{")
    payload = json.loads(result.output[start:result.output.rindex("}") + 1])

    assert "sidebar_row" in payload
    row = payload["sidebar_row"]
    assert "build_marker" not in row, "a rotating marker must not be shipped"
    assert "rows_sampled" not in row
    assert row["optional_ever_seen"] == [], "monotonic sets must ship empty"
    assert any("HEALTHY" in line for line in payload["_provenance"]), (
        "the export must warn that a baseline from a broken machine teaches "
        "every future install that broken is normal")


def test_exporting_from_a_machine_with_no_history_refuses():
    import cli.base.output as output_module
    from click.testing import CliRunner
    from cli.drift.commands import drift

    output_module._global_output = None
    try:
        result = CliRunner().invoke(drift, ["export-baseline", "--site", "nope"])
    finally:
        output_module._global_output = None
    assert result.exit_code == 1
