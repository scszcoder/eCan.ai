"""The WS protocol is the other way the site moves, and it moves silently.

`ws_reader.extract_messages` reads named keys out of a decoded frame. When a
key is renamed or stops being populated, nothing raises: the field comes back
empty and the failure surfaces layers downstream as a nameless customer or a
misrouted reply. ws192 and ws193 both presented that way.

These tests hold the watcher to three things: it notices a field going quiet,
it costs nothing on a path that runs per message, and it can never break
decoding.
"""

import json

import pytest

from agent.ec_skills.browser_use_extension import drift_journal as dj
from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    ws_protocol_watch as wpw,
)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("ECAN_DRIFT_JOURNAL_DIR", str(tmp_path / "journal"))
    dj.reset_incident_window()
    wpw.reset()
    yield
    wpw.reset()
    dj.reset_incident_window()


HEALTHY = {
    "type": "text",
    "sender_role": "1",
    "nickname": "Alice",
    "talk_id": "t-1",
    "pigeon_cid": "c-1",
    "security_sender_id": "u-1",
}


def _feed(kv, n=wpw._WINDOW_FRAMES):
    for _ in range(n):
        wpw.observe(dict(kv))


# ── noticing ───────────────────────────────────────────────────────────────

def test_the_first_window_is_a_baseline():
    _feed(HEALTHY)
    assert dj.read_events() == []


def test_a_field_the_decoder_depends_on_going_quiet_is_recorded():
    """The ws193 shape: the backend still sends frames, but the name is gone."""
    _feed(HEALTHY)
    without_name = {k: v for k, v in HEALTHY.items() if k != "nickname"}
    _feed(without_name)

    (event,) = dj.read_events()
    assert event["kind"] == "ws_schema_change"
    assert "nickname" in event["evidence"]["changed"]["core_populated"]["lost"]


def test_a_field_emptied_rather_than_removed_counts_the_same():
    """A key the backend still emits but has stopped filling is the same
    failure, and is the harder one to spot by eye."""
    _feed(HEALTHY)
    _feed({**HEALTHY, "nickname": ""})
    assert dj.read_events(), "an emptied field must register"


def test_a_rename_shows_as_one_field_lost_and_another_gained():
    _feed(HEALTHY)
    renamed = {k: v for k, v in HEALTHY.items() if k != "nickname"}
    renamed["user_display_name"] = "Alice"
    _feed(renamed)

    changed = dj.read_events()[0]["evidence"]["changed"]
    assert "nickname" in changed["core_populated"]["lost"]
    assert "user_display_name" in changed["unexpected_ever_seen"]["gained"]


def test_a_steady_protocol_says_nothing():
    _feed(HEALTHY)
    _feed(HEALTHY)
    _feed(HEALTHY)
    assert dj.read_events() == []


def test_frame_types_carrying_different_fields_do_not_flap():
    """A card frame and a text frame carry different keys. Reporting per frame
    would alternate forever; the window takes the union."""
    card = {"type": "template_card", "sender_role": "1", "talk_id": "t-1",
            "goods_id": "g-9", "generic_search_keywords": "{}"}
    for _ in range(2):
        for _ in range(wpw._WINDOW_FRAMES // 2):
            wpw.observe(dict(HEALTHY))
            wpw.observe(dict(card))
    assert dj.read_events() == [], "mixed frame types are not a schema change"


def test_a_short_run_does_not_report_a_half_empty_window():
    """Ten frames is not evidence that a field is dead."""
    _feed(HEALTHY, n=10)
    assert dj.read_events() == []


def test_flush_on_an_empty_window_claims_nothing():
    """A run that decoded no frames has not observed the backend dropping every
    field at once."""
    assert wpw.flush() is None
    assert dj.read_events() == []


# ── it must never break decoding ───────────────────────────────────────────

@pytest.mark.parametrize("junk", [None, "string", 42, [], object()])
def test_junk_from_the_backend_is_survivable(junk):
    wpw.observe(junk)                       # must not raise


def test_observing_never_raises_even_when_the_journal_explodes(monkeypatch):
    monkeypatch.setattr(dj, "note_shape",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    _feed(HEALTHY)
    _feed({k: v for k, v in HEALTHY.items() if k != "nickname"})


def test_a_chatty_backend_cannot_grow_the_window_without_bound():
    for i in range(500):
        wpw.observe({"type": "text", f"unexpected_{i}": "x"})
    assert len(wpw._unexpected) <= wpw._MAX_UNEXPECTED


def test_it_is_safe_from_several_threads():
    import threading

    def work():
        for _ in range(300):
            wpw.observe(dict(HEALTHY))

    threads = [threading.Thread(target=work) for _ in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()


# ── it must not accumulate customer data ───────────────────────────────────

def test_no_field_value_ever_travels():
    """Values are what customers wrote. The journal is kept for years."""
    _feed(HEALTHY)
    _feed({**HEALTHY, "nickname": "", "talk_id": "t-2"})
    blob = json.dumps(dj.read_events(), ensure_ascii=False)
    assert "Alice" not in blob
    assert "t-1" not in blob and "u-1" not in blob
    assert "nickname" in blob               # the NAME is the point


def test_the_watcher_reads_names_not_values():
    import inspect
    src = inspect.getsource(wpw)
    assert ".add(name" in src or "_populated.add(name)" in src
    # kv.get is used only to test emptiness, never to carry a value out.
    assert "str(kv.get" not in src


# ── the decoder actually calls it ──────────────────────────────────────────

def test_the_frame_decoder_reports_the_protocol_shape():
    import inspect
    from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
        ws_reader,
    )
    src = inspect.getsource(ws_reader.extract_messages)
    assert "_ws_protocol_watch.observe(kv)" in src, (
        "ws protocol changes are no longer reaching the permanent record"
    )


def test_every_key_the_decoder_depends_on_is_watched():
    """A key read by the decoder but missing from EXPECTED_KEYS is one whose
    disappearance would go unrecorded."""
    import inspect, re
    from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
        ws_reader,
    )
    src = inspect.getsource(ws_reader)
    read = set(re.findall(r"""kv\.get\(["']([^"']+)["']\)""", src))
    unwatched = read - set(wpw.EXPECTED_KEYS)
    assert not unwatched, f"decoder reads unwatched keys: {sorted(unwatched)}"

# ── the core/optional split ────────────────────────────────────────────────
#
# A key that rides only one message type is absent from most windows. Judging
# those per window would write a false alarm a day, which is worse than no
# alarm: it teaches everyone to ignore the file.

def test_a_rare_optional_field_appearing_does_not_flap():
    """A handover happens; later windows have none. That is not a change."""
    _feed(HEALTHY)                                   # baseline
    wpw.observe({**HEALTHY, "switch_human_triggered_word": "转人工"})
    _feed(HEALTHY, n=wpw._WINDOW_FRAMES - 1)         # window with the handover
    before = len(dj.read_events())
    _feed(HEALTHY)                                   # quiet window again
    assert len(dj.read_events()) == before, (
        "an optional field going quiet must not read as a site change"
    )


def test_an_optional_field_appearing_for_the_first_time_is_recorded_once():
    """'The backend started sending a new field' is worth exactly one record."""
    _feed(HEALTHY)
    wpw.observe({**HEALTHY, "goods_id": "g-1"})
    _feed(HEALTHY, n=wpw._WINDOW_FRAMES - 1)
    assert len(dj.read_events()) == 1


def test_the_optional_set_survives_a_restart():
    """Seeded from the stored baseline -- otherwise every run's first window
    reports every optional key as lost."""
    wpw.observe({**HEALTHY, "goods_id": "g-1"})
    _feed(HEALTHY, n=wpw._WINDOW_FRAMES - 1)
    dj.reset_incident_window()

    wpw.reset()                                      # a fresh process
    _feed(HEALTHY)
    assert dj.read_events() == [], "a restart is not a site change"


def test_the_split_is_honest_about_what_it_cannot_see():
    """Optional keys are monotonic, so their loss is NOT detectable. That is a
    real limit and the module must say so rather than imply coverage."""
    import inspect
    doc = inspect.getdoc(wpw) or ""
    assert "not* detectable" in doc or "not detectable" in doc


def test_every_expected_key_is_in_exactly_one_bucket():
    assert not (wpw.CORE_KEYS & wpw.OPTIONAL_KEYS)
    assert wpw.EXPECTED_KEYS == wpw.CORE_KEYS | wpw.OPTIONAL_KEYS
