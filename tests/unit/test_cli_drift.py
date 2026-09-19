"""`ecan drift` — the readback surface.

The journal's whole value depends on someone being able to read it eighteen
months later. Without this the data exists and is never used, which is the
same as not having it.

These tests are about the surface staying usable and staying read-only: the
one thing a command here must never do is delete history.
"""

import json
import pathlib

import pytest
from click.testing import CliRunner

from agent.ec_skills.browser_use_extension import drift_journal as dj
from cli.drift.commands import drift


@pytest.fixture(autouse=True)
def journal_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("ECAN_DRIFT_JOURNAL_DIR", str(tmp_path / "journal"))
    dj.reset_incident_window()
    yield
    dj.reset_incident_window()


@pytest.fixture
def history():
    """A machine that has seen a deploy and then a breaking change."""
    dj.note_shape("feige_chat", "sidebar_build_marker", {"digest": "aaaa"},
                  kind="site_deploy")
    dj.note_shape("feige_chat", "sidebar_build_marker", {"digest": "bbbb"},
                  kind="site_deploy")
    dj.reset_incident_window()
    dj.note_shape("feige_chat", "sidebar_row",
                  {"anchors_present": ["data_qa_id_nickname", "name_line"]})
    dj.note_shape("feige_chat", "sidebar_row",
                  {"anchors_present": ["name_line"]}, kind="dom_shape_change")
    return dj.read_events(limit=10)


def _run(*args):
    """Invoke a command and capture what it actually printed.

    `get_output()` is a singleton that captures `sys.stdout` when first built,
    and CliRunner swaps stdout per invocation — so a cached one writes to a
    closed stream on the second call. Dropping it lets each run build against
    the live stream, which is what makes these assertions about real output
    rather than about a mock.
    """
    import cli.base.output as output_module
    output_module._global_output = None
    try:
        return CliRunner().invoke(drift, list(args))
    finally:
        output_module._global_output = None


# ── it has to be readable ──────────────────────────────────────────────────

def test_list_shows_what_moved(history):
    result = _run("list")
    assert result.exit_code == 0
    assert "data_qa_id_nickname" in result.output
    assert "dom_shape_change" in result.output


def test_an_empty_journal_says_so_without_sounding_broken():
    """Nothing recorded is the NORMAL state — changes are rare. It must not
    read as an error."""
    result = _run("list")
    assert result.exit_code == 0
    assert "No site changes recorded" in result.output


def test_list_can_be_filtered_to_the_deploy_calendar(history):
    result = _run("list", "--kind", "site_deploy")
    assert result.exit_code == 0
    assert "site_deploy" in result.output
    assert "dom_shape_change" not in result.output


def test_show_gives_the_full_delta(history):
    seq = next(e["seq"] for e in history if e["kind"] == "dom_shape_change")
    result = _run("show", str(seq))
    assert result.exit_code == 0
    assert "what changed" in result.output
    assert "data_qa_id_nickname" in result.output


def test_show_on_a_missing_record_fails_cleanly(history):
    result = _run("show", "999999")
    assert result.exit_code == 1


def test_stats_states_the_retention_promise():
    """Someone reading this needs to know the file is not rotated, or they will
    assume it is and not trust it."""
    result = _run("stats")
    assert result.exit_code == 0
    assert "3 years" in result.output
    assert "rotated" in result.output and "overwritten" in result.output


def test_shapes_shows_the_live_baseline(history):
    result = _run("shapes")
    assert result.exit_code == 0
    assert "sidebar_row" in result.output


def test_every_command_can_emit_json(history):
    for args in (["list"], ["stats"], ["shapes"]):
        result = _run(*args, "--json")
        assert result.exit_code == 0, f"{args} failed"
        json.loads(result.output)           # must be parseable verbatim


# ── it must never destroy history ──────────────────────────────────────────

def test_there_is_no_delete_or_prune_command():
    """The journal's value is that the previous change is still there when the
    next one lands. A convenient `drift clear` would quietly undo that."""
    names = set(drift.commands)
    for banned in ("delete", "clear", "prune", "reset", "rm", "purge"):
        assert banned not in names, f"`ecan drift {banned}` would destroy history"


def test_the_commands_never_write(history):
    src = pathlib.Path(
        __import__("cli.drift.commands", fromlist=["x"]).__file__
    ).read_text(encoding="utf-8")
    for banned in ("record_event", "note_shape", "prune(", "unlink", "forget_shape"):
        assert banned not in src, f"a read-only surface must not call {banned}"

    before = dj.journal_stats()
    for args in (["list"], ["stats"], ["shapes"]):
        _run(*args)
    assert dj.journal_stats() == before


def test_it_is_registered_on_the_top_level_cli():
    from cli.main import cli
    assert "drift" in cli.commands
