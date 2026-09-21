"""The site tells us when we have failed a customer. These keep us listening.

Feige emits explicit notices over the websocket — "用户已等待超30秒" and, worse,
"客服超时未回复用户，系统关闭会话" (the conversation CLOSED because we never
replied). `ws_reader` discarded that whole channel for the life of the project.

It is the only source of *labelled failures* we have in production: every other
detector infers that something changed, while this one is the site stating
outright that we lost a customer. So the tests here are less about parsing and
more about not losing the channel again.
"""

import base64
import json
import pathlib

import pytest

from agent.ec_skills.browser_use_extension import drift_journal as dj
from agent.ec_skills.browser_use_extension import site_signals as ss
from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    signals as fs,
    ws_reader,
)


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    monkeypatch.setenv("ECAN_DRIFT_JOURNAL_DIR", str(tmp_path / "journal"))
    dj.reset_incident_window()
    ss.reset()
    fs.register()
    yield
    ss.reset()
    dj.reset_incident_window()


# ── every declared signal must be trippable ────────────────────────────────

PHRASE_MATCHED = [s for s in fs.SIGNALS
                  if any(name == s.name for name, _ in fs._PATTERNS)]


@pytest.mark.parametrize("signal", PHRASE_MATCHED, ids=lambda s: s.name)
def test_every_phrase_signal_trips_on_its_own_example(signal):
    """A signal nobody can trip on demand is a signal nobody should trust.
    The `example` field is the promise; this is the proof."""
    assert signal.example, f"{signal.name} declares no example"
    assert fs.match_system_event(signal.example) == signal.name


def test_every_signal_is_either_phrase_matched_or_raised_by_a_verdict():
    """The same guarantee for the rest: an `invariant` signal is not a phrase,
    it is a disagreement between two records, so its proof is a test that
    trips it through the real path (below) rather than an example string."""
    by_name = {s.name: s for s in fs.SIGNALS}
    phrase_names = {name for name, _ in fs._PATTERNS}
    for name, signal in by_name.items():
        if name in phrase_names:
            continue
        assert signal.kind == "invariant", (
            f"{name} is neither phrase-matched nor an invariant; nothing can "
            f"trip it, so nothing should trust it")


def test_all_signals_are_registered_with_the_platform():
    assert set(ss.declared(fs.SITE)) == {s.name for s in fs.SIGNALS}


def test_the_closure_notice_is_an_incident_and_waiting_is_not():
    """A closed conversation is a lost customer; a waiting one is still
    recoverable. Flattening them would make the alarm useless."""
    by_name = {s.name: s for s in fs.SIGNALS}
    assert by_name["conversation_closed_unanswered"].severity == "incident"
    assert by_name["customer_waiting"].severity == "warning"


# ── the ordering that matters ──────────────────────────────────────────────

def test_a_closure_notice_is_never_downgraded_to_merely_waiting():
    """The closure text also reads like a lateness complaint. Matching in the
    wrong order would report a lost customer as one still waiting."""
    assert fs.match_system_event(
        "客服超时未回复用户，系统关闭会话") == "conversation_closed_unanswered"


@pytest.mark.parametrize("text", [
    "用户已等待超30秒，请尽快回复",
    "用户已等待超5分钟，请尽快回复",
    "客户等待超2小时",
])
def test_the_wait_threshold_is_not_hard_coded(text):
    """The site varies the interval; the words around it are what is stable."""
    assert fs.match_system_event(text) == "customer_waiting"


@pytest.mark.parametrize("text", ["", None, "订单什么时候发货？", "你好",
                                  "这个商品有优惠吗"])
def test_ordinary_customer_text_trips_nothing(text):
    """A false incident on every customer question would be worse than none."""
    assert fs.match_system_event(text) == ""


# ── the channel must stay connected ────────────────────────────────────────

def test_the_decoder_no_longer_discards_the_system_event_channel():
    src = pathlib.Path(ws_reader.__file__).read_text(encoding="utf-8")
    assert "def report_system_events" in src
    assert "def system_event_strings" in src


def test_the_observer_reads_system_events_before_parsing_messages():
    """A frame carrying ONLY a closure notice has no customer message in it.
    Reading events after a message-parse guard would drop exactly the frames
    that matter most."""
    from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
        ws_observer,
    )
    src = pathlib.Path(ws_observer.__file__).read_text(encoding="utf-8")
    assert "report_system_events" in src
    assert src.index("report_system_events") < src.index(
        "for m in ws_reader.customer_messages(raw)")


def test_strings_are_walked_at_any_depth_not_just_field_8():
    """The file's own docstring said these arrive "as JSON at frame .8".
    Against a real capture that finds NOTHING — they sit at varying depths.
    A fixed-path reader would silently catch none of them."""
    src = pathlib.Path(ws_reader.__file__).read_text(encoding="utf-8")
    assert "_walk_strings" in src
    assert "NOT reliably at .8" in src, "the corrected docstring was lost"


def test_a_junk_frame_cannot_break_decoding():
    for junk in (b"", b"\x00\x01\x02", b"not a protobuf frame at all"):
        assert ws_reader.report_system_events(junk) == []


def test_the_walk_is_bounded():
    """Frames come from a backend we do not control."""
    assert ws_reader._MAX_SIGNAL_STRINGS <= 1000
    assert ws_reader._MAX_SIGNAL_DEPTH <= 20


# ── regression against the real capture ────────────────────────────────────

_CAPTURE = (pathlib.Path(__file__).resolve().parents[2]
            / "customer_logs" / "eCan_feigecap.jsonl")


@pytest.mark.skipif(not _CAPTURE.exists(),
                    reason="capture is git-ignored; present only on a dev box")
def test_it_fires_on_the_real_capture():
    """The counts that started this: one ordinary session, 535 decoded frames,
    four conversations closed because we never replied."""
    frames = 0
    with _CAPTURE.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("k") != "ws" or rec.get("dir") != "recv":
                continue
            try:
                raw = base64.b64decode(rec["payload_b64"])
            except Exception:
                continue
            frames += 1
            ws_reader.report_system_events(raw)

    assert frames > 100, "capture did not decode"
    report = ss.trip_report(fs.SITE)
    assert report["feige_chat/conversation_closed_unanswered"]["count"] == 4
    assert report["feige_chat/customer_waiting"]["count"] == 8


@pytest.mark.skipif(not _CAPTURE.exists(), reason="capture is git-ignored")
def test_no_customer_text_reaches_the_permanent_record():
    """These notices arrive wrapped in JSON that also carries customer fields."""
    ws_reader.report_system_events(b"")
    fs.report_system_event("客服超时未回复用户，系统关闭会话", talk_id="t-99")
    blob = json.dumps(dj.read_events(), ensure_ascii=False)
    assert "t-99" in blob                      # the opaque id is useful
    assert "系统关闭会话" not in blob           # the wrapped payload is not
