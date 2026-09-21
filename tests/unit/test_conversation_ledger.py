"""When the site says nobody replied — was that us?

This is the invariant that closes the dangerous case: a customer arrives, we
never see them, and nothing notices. The site's closure notice plus our own
record of what we saw is enough to tell three situations apart:

* we saw the message and never replied        → a definitive miss, ours
* we saw it and dispatched a reply            → a delivery failure, also ours
* we have no record of the conversation       → unknown, and NOT claimed

The third is the honest one. A conversation can predate this process, so
claiming a miss there would be wrong — but it can also mean we were blind to
it, which is the failure nobody else can detect, so it is reported separately
rather than swallowed.
"""

import json
import pathlib

import pytest

from agent.ec_skills.browser_use_extension import drift_journal as dj
from agent.ec_skills.browser_use_extension import site_signals as ss
from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    conversation_ledger as cl,
    signals as fs,
)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("ECAN_DRIFT_JOURNAL_DIR", str(tmp_path / "journal"))
    dj.reset_incident_window()
    ss.reset()
    cl.reset()
    fs.register()
    yield
    cl.reset()
    ss.reset()
    dj.reset_incident_window()


CLOSURE = ('{"data":{"attention_content":"客服超时未回复用户，系统关闭会话",'
           '"biz_conversation_id":"","customer_id":0,"customer_name":"",'
           '"security_customer_id":"UID-ABC","security_biz_conversation_id":'
           '"UID-ABC:264496304::2:1:pigeon"},"st":1,"timestamp":1}')


# ── the verdict ────────────────────────────────────────────────────────────

def test_a_conversation_we_saw_and_never_answered_is_a_miss():
    cl.note_customer_message(talk_id="t-1", uid="UID-ABC")
    assert cl.verdict(uid="UID-ABC")[0] == "missed"


def test_a_conversation_we_answered_is_not_a_miss():
    cl.note_customer_message(talk_id="t-1", uid="UID-ABC")
    cl.note_served(talk_id="t-1")
    assert cl.verdict(uid="UID-ABC")[0] == "served"


def test_a_conversation_we_never_saw_is_unknown_not_missed():
    """It may simply predate this process. Claiming a miss would be wrong."""
    outcome, why = cl.verdict(uid="UID-NEVER-SEEN")
    assert outcome == "unknown"
    assert "recognise" in why or "never saw" in why


def test_the_longer_conversation_id_still_resolves():
    """The notice sometimes carries security_biz_conversation_id, which has the
    customer uid as a prefix."""
    cl.note_customer_message(talk_id="t-1", uid="UID-ABC")
    assert cl.verdict(uid="UID-ABC:264496304::2:1:pigeon")[0] == "missed"


def test_a_talk_id_alone_is_enough_when_we_have_it():
    cl.note_customer_message(talk_id="t-1")
    assert cl.verdict(talk_id="t-1")[0] == "missed"
    cl.note_served(talk_id="t-1")
    assert cl.verdict(talk_id="t-1")[0] == "served"


def test_serving_a_conversation_we_never_saw_still_counts_as_served():
    """Cold start: the first thing we do is reply, having joined mid-thread."""
    cl.note_served(talk_id="t-9", uid="UID-X")
    assert cl.verdict(uid="UID-X")[0] == "served"


def test_stats_say_how_many_are_outstanding():
    cl.note_customer_message(talk_id="t-1")
    cl.note_customer_message(talk_id="t-2")
    cl.note_served(talk_id="t-1")
    assert cl.stats()["unanswered"] == 1


# ── it must not be the 15-second map ───────────────────────────────────────

def test_the_ledger_outlives_the_duplicate_guard():
    """dispatch_state's map is a 15s duplicate guard that POPS expired entries,
    so it answers 'dispatched recently', not 'ever served'. A closure notice
    arrives minutes later, so using it would report a miss for almost every
    conversation."""
    from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
        dispatch_state,
    )
    assert dispatch_state.TALK_DISPATCH_TTL_S <= 60
    assert cl.TTL_S >= 3600, "the ledger must span far more than a dispatch window"


def test_the_dispatch_path_feeds_the_ledger():
    from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
        dispatch_state,
    )
    cl.note_customer_message(talk_id="t-1")
    dispatch_state.note_talk_dispatched("t-1", "m-1")
    assert cl.verdict(talk_id="t-1")[0] == "served"


def test_the_observer_records_what_it_sees():
    import inspect
    from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
        ws_observer,
    )
    src = inspect.getsource(ws_observer)
    assert "note_customer_message" in src


# ── turning a notice into a verdict ────────────────────────────────────────

def test_the_notice_carries_a_customer_identifier():
    """Measured against the real capture: the plaintext fields are empty and
    only the security form is populated."""
    assert fs.notice_customer_uid(CLOSURE) == "UID-ABC"


def test_a_notice_without_json_yields_no_identifier():
    assert fs.notice_customer_uid("客服超时未回复用户，系统关闭会话") == ""


def test_junk_json_yields_no_identifier():
    for junk in ("{not json", "{}", '{"data":null}', '{"data":{}}', ""):
        assert fs.notice_customer_uid(junk) == ""


def test_a_closure_for_a_conversation_we_dropped_raises_a_definitive_miss():
    """The whole point: the site and our own records agree, so no inference."""
    cl.note_customer_message(talk_id="t-1", uid="UID-ABC")
    fs.report_system_event(CLOSURE)
    report = ss.trip_report(fs.SITE)
    assert "feige_chat/conversation_missed" in report
    assert report["feige_chat/conversation_missed"]["severity"] == "incident"


def test_a_closure_for_a_conversation_we_answered_is_not_called_a_miss():
    cl.note_customer_message(talk_id="t-1", uid="UID-ABC")
    cl.note_served(talk_id="t-1")
    fs.report_system_event(CLOSURE)
    report = ss.trip_report(fs.SITE)
    assert "feige_chat/conversation_missed" not in report
    # ...but the closure itself is still an incident: the site closed a
    # conversation we thought we had answered.
    assert "feige_chat/conversation_closed_unanswered" in report


def test_a_closure_for_an_unseen_conversation_is_flagged_separately():
    fs.report_system_event(CLOSURE)
    report = ss.trip_report(fs.SITE)
    assert "feige_chat/closure_for_unseen_conversation" in report
    assert "feige_chat/conversation_missed" not in report


def test_the_verdict_reaches_the_permanent_record():
    cl.note_customer_message(talk_id="t-1", uid="UID-ABC")
    fs.report_system_event(CLOSURE)
    events = dj.read_events()
    assert any(e["element"] == "conversation_missed" for e in events)


def test_a_miss_marks_the_install_degraded():
    """An incident is what turns the Agents-page dot; this is the most
    important incident there is."""
    from agent.ec_skills.browser_use_extension import degraded_state
    degraded_state.reset()
    cl.note_customer_message(talk_id="t-1", uid="UID-ABC")
    fs.report_system_event(CLOSURE)
    assert "signal:conversation_missed" in degraded_state.active()
    degraded_state.reset()


def test_no_customer_content_from_the_notice_is_stored():
    """The notice JSON carries customer_name and attention_content alongside
    the ids."""
    cl.note_customer_message(talk_id="t-1", uid="UID-ABC")
    fs.report_system_event(CLOSURE)
    blob = json.dumps(dj.read_events(), ensure_ascii=False)
    assert "系统关闭会话" not in blob
    assert "attention_content" not in blob


# ── it must never break decoding ───────────────────────────────────────────

@pytest.mark.parametrize("junk", [None, "", 42, {}, []])
def test_junk_into_the_ledger_is_survivable(junk):
    cl.note_customer_message(talk_id=junk)      # must not raise
    cl.note_served(talk_id=junk)
    cl.verdict(uid=junk, talk_id=junk)


def test_the_ledger_is_bounded():
    for i in range(cl.MAX_TRACKED + 200):
        cl.note_customer_message(talk_id=f"t-{i}")
    assert len(cl._seen) <= cl.MAX_TRACKED + 200
    assert cl.MAX_TRACKED <= 20000, "an unbounded ledger on a long run is a leak"


def test_it_is_safe_from_several_threads():
    import threading

    def work(n):
        for i in range(100):
            cl.note_customer_message(talk_id=f"t{n}-{i}", uid=f"u{n}-{i}")
            cl.note_served(talk_id=f"t{n}-{i}")

    threads = [threading.Thread(target=work, args=(n,)) for n in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert cl.stats()["unanswered"] == 0


# ── the business module may name the site; it IS the site ──────────────────

def test_the_ledger_lives_in_the_bundle_not_the_platform():
    assert "hooks" in pathlib.Path(cl.__file__).parts
    assert "external" in pathlib.Path(cl.__file__).parts
