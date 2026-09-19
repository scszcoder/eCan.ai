"""The permanent record of site changes.

Two properties matter more than the rest, and both are about what the file is
still like in three years:

1. **A newer occurrence never destroys an older one.** The whole point is that
   when Feige redesigns again, the record of the LAST redesign is still there.
   Anything that looks like log rotation is a bug here.

2. **It accumulates structure, not customer data.** A store designed to outlive
   three years of customers must not become an archive of what they typed.
"""

import json
import pathlib

import pytest

from agent.ec_skills.browser_use_extension import drift_journal as dj


@pytest.fixture(autouse=True)
def journal_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("ECAN_DRIFT_JOURNAL_DIR", str(tmp_path / "journal"))
    dj.reset_incident_window()
    yield
    dj.reset_incident_window()


def _events():
    return dj.read_events(limit=100)


# ── detecting the change ───────────────────────────────────────────────────

OLD_SIDEBAR = {
    "anchors_present": ["data_qa_id_nickname", "name_line", "titled_descendant"],
    "anchors_missing": ["legacy_hashed_wrap"],
    "attributes": ["class", "data-qa-id", "data-qa-id=qa-conversation-nickname",
                   "title"],
    "tags": ["div", "span"],
}

# What September's rebuilt frame looked like: the machine id we keyed on is
# simply not emitted any more.
NEW_SIDEBAR = {
    "anchors_present": ["name_line", "titled_descendant"],
    "anchors_missing": ["data_qa_id_nickname", "legacy_hashed_wrap"],
    "attributes": ["class", "title"],
    "tags": ["div", "span"],
}


def test_the_first_sighting_is_a_baseline_not_a_change():
    """A machine seeing a site for the first time has learned nothing about
    whether that site changed."""
    assert dj.note_shape("s", "sidebar_row", OLD_SIDEBAR) is None
    assert _events() == []


def test_an_unchanged_site_is_silent():
    dj.note_shape("s", "sidebar_row", OLD_SIDEBAR)
    assert dj.note_shape("s", "sidebar_row", OLD_SIDEBAR) is None
    assert _events() == []


def test_reordering_is_not_a_change():
    """Ordering noise from a DOM walk must not read as a redesign."""
    dj.note_shape("s", "sidebar_row", {"attributes": ["a", "b", "c"]})
    assert dj.note_shape("s", "sidebar_row", {"attributes": ["c", "a", "b"]}) is None


def test_the_change_that_broke_the_run_is_recorded_as_a_delta():
    dj.note_shape("s", "sidebar_row", OLD_SIDEBAR)
    delta = dj.note_shape("s", "sidebar_row", NEW_SIDEBAR)

    assert delta, "a vanished anchor must register"
    assert "data_qa_id_nickname" in delta["anchors_present"]["lost"]
    assert "data-qa-id" in delta["attributes"]["lost"]

    (event,) = _events()
    assert event["kind"] == "dom_shape_change" or event["kind"] == "shape_change"
    assert "lost" in event["summary"]
    assert event["evidence"]["was"]["attributes"]
    assert event["evidence"]["now"]["attributes"]


def test_the_record_says_which_build_saw_it():
    """Eighteen months later, 'which version of ours was running' is the first
    question asked."""
    dj.note_shape("s", "sidebar_row", OLD_SIDEBAR)
    dj.note_shape("s", "sidebar_row", NEW_SIDEBAR)
    (event,) = _events()
    assert "build" in event and isinstance(event["build"], dict)
    assert event["ts"].endswith("+00:00")       # UTC, comparable across machines


def test_the_new_shape_becomes_the_baseline():
    """Otherwise every subsequent scan re-reports the same change forever."""
    dj.note_shape("s", "sidebar_row", OLD_SIDEBAR)
    dj.note_shape("s", "sidebar_row", NEW_SIDEBAR)
    dj.reset_incident_window()                  # defeat day-coalescing
    assert dj.note_shape("s", "sidebar_row", NEW_SIDEBAR) is None
    assert len(_events()) == 1


def test_changing_back_is_itself_a_change():
    """A site reverting a bad deploy is worth the same record as shipping it."""
    dj.note_shape("s", "sidebar_row", OLD_SIDEBAR)
    dj.note_shape("s", "sidebar_row", NEW_SIDEBAR)
    dj.reset_incident_window()
    assert dj.note_shape("s", "sidebar_row", OLD_SIDEBAR)
    assert len(_events()) == 2


def test_the_baseline_survives_a_restart():
    """Both site changes we have been bitten by happened BETWEEN runs. A
    baseline held only in memory would never have caught either."""
    dj.note_shape("s", "sidebar_row", OLD_SIDEBAR)

    import importlib
    reloaded = importlib.reload(dj)
    reloaded.reset_incident_window()
    assert reloaded.note_shape("s", "sidebar_row", NEW_SIDEBAR)


def test_shapes_are_tracked_per_site_and_per_key():
    dj.note_shape("a", "sidebar_row", OLD_SIDEBAR)
    assert dj.note_shape("b", "sidebar_row", NEW_SIDEBAR) is None   # b is new
    assert dj.note_shape("a", "other_thing", NEW_SIDEBAR) is None   # key is new


# ── websocket payloads, the other way a site moves ─────────────────────────

def test_a_websocket_payload_gaining_and_losing_fields_is_a_change():
    """A site change is not always visible in the DOM. The backend moving is
    the same event and belongs in the same record."""
    dj.note_shape("s", "chat_ws_payload",
                  {"fields": ["msg_type", "talk_id", "nickname", "content"]})
    delta = dj.note_shape("s", "chat_ws_payload",
                          {"fields": ["msg_type", "talk_id", "user_info", "content"]},
                          kind="ws_schema_change")
    assert delta["fields"]["lost"] == ["nickname"]
    assert delta["fields"]["gained"] == ["user_info"]
    assert _events()[0]["kind"] == "ws_schema_change"


# ── never overwritten ──────────────────────────────────────────────────────

def test_occurrences_accumulate_and_never_replace_each_other():
    for i in range(6):
        dj.reset_incident_window()
        dj.note_shape("s", "sidebar_row", {"attributes": [f"attr_{i}"]})
    events = _events()
    assert len(events) == 5          # first sighting was the baseline
    seqs = [e["seq"] for e in events]
    assert len(set(seqs)) == len(seqs), "each occurrence is its own record"


def test_the_platform_module_names_no_business():
    """Platform code stays site-independent. The journal is written to by
    whichever bundle observes a change; it must not know any of them."""
    src = pathlib.Path(dj.__file__).read_text(encoding="utf-8").lower()
    for term in ("feige", "douyin", "jinritemai", "飞鸽", "etsy", "ebay", "ziniao"):
        assert term not in src, (
            f"platform module drift_journal.py mentions '{term}'; business "
            f"specifics belong in hooks/external/<site>/"
        )


def test_there_is_no_size_based_rotation():
    """A log would discard here. This must not."""
    src = pathlib.Path(dj.__file__).read_text(encoding="utf-8").lower()
    for banned in ("rotatingfilehandler", "maxbytes", "backupcount"):
        assert banned not in src


def test_prune_refuses_to_delete_inside_the_retention_floor():
    year = dj._journal_path().stem.split("-")[1]
    dj.note_shape("s", "sidebar_row", OLD_SIDEBAR)
    dj.note_shape("s", "sidebar_row", NEW_SIDEBAR)
    assert _events()

    assert dj.prune(older_than_years=0) == []    # asked for everything
    assert dj.prune(older_than_years=1) == []
    assert _events(), f"the {year} file must survive any prune request"


def test_prune_is_never_called_automatically():
    """The floor only protects anything if nothing schedules a prune."""
    import subprocess
    root = pathlib.Path(dj.__file__).resolve().parents[3]
    hits = subprocess.run(
        ["git", "grep", "-n", "drift_journal.prune", "--", "*.py"],
        cwd=root, capture_output=True, text=True).stdout
    assert not hits.strip(), f"something calls prune(): {hits}"


def test_a_corrupt_line_does_not_lose_the_rest_of_the_file():
    dj.note_shape("s", "sidebar_row", OLD_SIDEBAR)
    dj.note_shape("s", "sidebar_row", NEW_SIDEBAR)
    path = dj._journal_path()
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("{ this is not json\n")
    dj.reset_incident_window()
    dj.note_shape("s", "sidebar_row", {"attributes": ["totally", "different"]})
    assert len(_events()) == 2


# ── it must not accumulate customer data ───────────────────────────────────

def test_free_text_is_reduced_to_its_shape():
    """This file is kept for years. A careless caller must not be able to put a
    customer's message into it."""
    dj.record_event("s", "shape_change", element="row",
                    evidence={"sample": "Hello, my order 8891 has not arrived",
                              "name": "Alice Chen"})
    blob = json.dumps(_events()[0], ensure_ascii=False)
    assert "order 8891" not in blob
    assert "Alice Chen" not in blob
    assert "text" in blob                        # a description survived


def test_cjk_content_is_reduced_too():
    dj.record_event("s", "shape_change", element="row",
                    evidence={"preview": "你好 我的订单还没有收到 请帮我查一下"})
    assert "订单" not in json.dumps(_events()[0], ensure_ascii=False)


def test_structural_names_survive_verbatim():
    """Redaction is worthless if it also destroys the thing being recorded."""
    dj.record_event("s", "shape_change", element="row",
                    evidence={"attributes": ["data-qa-id", "aria-label", "title"]})
    blob = json.dumps(_events()[0])
    for name in ("data-qa-id", "aria-label", "title"):
        assert name in blob


def test_a_shape_observation_cannot_smuggle_content_through():
    delta = dj.note_shape("s", "row", {"attributes": ["a"]})
    dj.note_shape("s", "row", {"attributes": ["a"],
                               "leaked": "customer said her parcel is late"})
    assert "parcel is late" not in json.dumps(_events(), ensure_ascii=False)


def test_one_record_cannot_write_an_unbounded_file():
    dj.record_event("s", "shape_change", element="row",
                    evidence={"names": [f"attr_{i}" for i in range(5000)]},
                    raw_ok=True)
    assert dj._journal_path().stat().st_size < 2 * dj._MAX_EVIDENCE_CHARS


# ── it must never break the run it is observing ────────────────────────────

def test_a_change_repeating_all_day_is_recorded_once():
    """A moved site re-triggers on every scan. Without this, one afternoon
    buries the record under thousands of identical rows."""
    dj.note_shape("s", "sidebar_row", OLD_SIDEBAR, kind="dom_shape_change")
    dj.note_shape("s", "sidebar_row", NEW_SIDEBAR, kind="dom_shape_change")
    for _ in range(500):
        dj.record_event("s", "dom_shape_change", element="sidebar_row",
                        summary="again")
    assert len(_events()) == 1


def test_coalescing_does_not_hide_a_different_kind_of_change():
    """Same element, different failure: the DOM moved AND the socket moved.
    Collapsing those into one record would lose half the story."""
    dj.record_event("s", "dom_shape_change", element="sidebar_row", summary="dom")
    dj.record_event("s", "ws_schema_change", element="sidebar_row", summary="ws")
    assert {e["kind"] for e in _events()} == {"dom_shape_change", "ws_schema_change"}


def test_an_unwritable_journal_does_not_raise(monkeypatch):
    monkeypatch.setattr(dj, "journal_dir",
                        lambda: (_ for _ in ()).throw(OSError("read-only")))
    assert dj.record_event("s", "shape_change") is False
    assert dj.note_shape("s", "row", {"attributes": ["a"]}) is None


@pytest.mark.parametrize("junk", [None, "string", 42, [], object()])
def test_a_junk_shape_is_survivable(junk):
    """Shapes come from JS running in a page we do not control."""
    dj.note_shape("s", "row", junk)              # must not raise


def test_it_is_safe_from_several_threads():
    import threading

    def work(n):
        for i in range(20):
            dj.reset_incident_window()
            dj.record_event(f"s{n}", "shape_change", element=f"e{i}")

    threads = [threading.Thread(target=work, args=(n,)) for n in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()

    for line in dj._journal_path().read_text(encoding="utf-8").splitlines():
        json.loads(line)                          # no interleaved writes


# ── reading it back ────────────────────────────────────────────────────────

def test_events_can_be_filtered_by_site_and_kind():
    dj.note_shape("a", "row", {"attributes": ["x"]})
    dj.note_shape("a", "row", {"attributes": ["y"]})
    dj.note_shape("b", "row", {"attributes": ["x"]})
    dj.note_shape("b", "row", {"attributes": ["z"]}, kind="ws_schema_change")

    assert len(dj.read_events(site="a")) == 1
    assert len(dj.read_events(kind="ws_schema_change")) == 1


def test_stats_say_how_much_history_exists():
    dj.note_shape("s", "row", {"attributes": ["x"]})
    dj.note_shape("s", "row", {"attributes": ["y"]})
    stats = dj.journal_stats()
    assert stats["events"] == 1 and stats["bytes"] > 0


def test_forgetting_a_shape_leaves_the_history_alone():
    dj.note_shape("s", "row", {"attributes": ["x"]})
    dj.note_shape("s", "row", {"attributes": ["y"]})
    assert dj.forget_shape("s", "row") == 1
    assert len(_events()) == 1, "history is immutable"
    assert dj.note_shape("s", "row", {"attributes": ["z"]}) is None   # re-baselined


# ── record numbers must mean one thing per machine ─────────────────────────

def test_record_numbers_continue_across_restarts():
    """Numbers are how a person refers to an entry ("look at #104"). Restarting
    the app used to reset the counter, so two records shared a number and
    `ecan drift show 104` was ambiguous."""
    import importlib

    dj.note_shape("s", "row", {"attributes": ["a"]})
    dj.note_shape("s", "row", {"attributes": ["b"]})
    first = _events()[0]["seq"]

    reloaded = importlib.reload(dj)          # a fresh process
    reloaded.reset_incident_window()
    reloaded.note_shape("s", "row", {"attributes": ["c"]})

    seqs = [e["seq"] for e in reloaded.read_events(limit=100)]
    assert len(set(seqs)) == len(seqs), f"duplicate record numbers: {seqs}"
    assert max(seqs) > first


def test_a_deploy_marker_is_its_own_kind_of_record():
    """A site deploy is not a structural change, and conflating them would make
    the structural record cry wolf on every routine ship."""
    dj.note_shape("s", "build_marker", {"digest": "aaaa"}, kind="site_deploy")
    dj.note_shape("s", "build_marker", {"digest": "bbbb"}, kind="site_deploy")
    (event,) = _events()
    assert event["kind"] == "site_deploy"
    assert dj.read_events(kind="dom_shape_change") == []
