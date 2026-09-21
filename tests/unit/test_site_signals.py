"""Declared health signals — the platform half.

The contract these protect:

1. **The registry is the truth.** A signal that fires without being declared is
   reported as a gap, not silently invented. Otherwise "what do we depend on
   about this site?" has no answer, which is the state that made ws193 take
   days.
2. **Severity decides what happens.** An incident must not be logged at the
   same level as ordinary traffic, and ordinary traffic must not fill the
   permanent record.
3. **A signal cannot break the path that noticed it.**
"""

import pathlib

import pytest

from agent.ec_skills.browser_use_extension import drift_journal as dj
from agent.ec_skills.browser_use_extension import site_signals as ss


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    monkeypatch.setenv("ECAN_DRIFT_JOURNAL_DIR", str(tmp_path / "journal"))
    dj.reset_incident_window()
    ss.reset()
    yield
    ss.reset()
    dj.reset_incident_window()


def _declare(severity="warning", kind="distress"):
    ss.register("s", [ss.SiteSignal(name="sig", kind=kind, severity=severity,
                                    means="something happened", example="boom")])


# ── the vocabulary ─────────────────────────────────────────────────────────

def test_a_signal_must_use_a_known_kind():
    with pytest.raises(ValueError):
        ss.SiteSignal(name="x", kind="vibes", severity="warning", means="m")


def test_a_signal_must_use_a_known_severity():
    with pytest.raises(ValueError):
        ss.SiteSignal(name="x", kind="distress", severity="catastrophic", means="m")


def test_the_four_kinds_are_the_declared_ones():
    """Each covers a failure the others miss; adding one is a design decision."""
    assert set(ss.KINDS) == {"distress", "anchor", "invariant", "liveness"}


# ── the registry is the truth ──────────────────────────────────────────────

def test_declared_signals_are_enumerable():
    _declare()
    assert "sig" in ss.declared("s")
    assert ss.declared("s")["sig"].means


def test_an_undeclared_signal_is_reported_as_a_gap_not_invented(monkeypatch):
    warnings = []
    monkeypatch.setattr(ss.logger, "warning", lambda m: warnings.append(m))
    assert ss.trip("s", "never_declared") is False
    assert warnings and "not declared" in warnings[0]
    assert ss.trip_report() == {}


def test_registering_again_replaces_rather_than_accumulates():
    _declare()
    ss.register("s", [ss.SiteSignal(name="other", kind="anchor",
                                    severity="info", means="m")])
    assert set(ss.declared("s")) == {"other"}


# ── severity decides what happens ──────────────────────────────────────────

@pytest.mark.parametrize("severity,method", [("incident", "error"),
                                             ("warning", "warning"),
                                             ("info", "info")])
def test_severity_picks_the_log_level(severity, method, monkeypatch):
    seen = []
    for name in ("error", "warning", "info"):
        monkeypatch.setattr(ss.logger, name,
                            lambda m, _n=name: seen.append((_n, m)))
    _declare(severity=severity)
    ss.trip("s", "sig")
    assert seen and seen[0][0] == method


def test_faults_go_on_the_permanent_record():
    _declare(severity="incident")
    ss.trip("s", "sig", detail="talk=t-1")
    (event,) = dj.read_events()
    assert event["kind"] == "site_signal"
    assert event["element"] == "sig"
    assert "incident" in event["summary"]


def test_ordinary_traffic_does_not_fill_the_permanent_record():
    """An `info` signal is expected traffic. Journalling it would bury the
    ones that matter under three years of noise."""
    _declare(severity="info")
    ss.trip("s", "sig")
    assert dj.read_events() == []
    assert ss.trip_report()["s/sig"]["count"] == 1    # still counted


def test_repeats_are_counted_not_re_journalled():
    _declare(severity="warning")
    for _ in range(50):
        ss.trip("s", "sig")
    assert ss.trip_report()["s/sig"]["count"] == 50
    assert len(dj.read_events()) == 1


# ── it must not break the path that noticed it ─────────────────────────────

def test_tripping_never_raises_even_when_the_journal_explodes(monkeypatch):
    monkeypatch.setattr(dj, "record_event",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    _declare(severity="incident")
    ss.trip("s", "sig")                     # must not raise


def test_tripping_never_raises_when_logging_explodes(monkeypatch):
    monkeypatch.setattr(ss.logger, "warning",
                        lambda m: (_ for _ in ()).throw(RuntimeError("sink died")))
    _declare(severity="warning")
    ss.trip("s", "sig")


def test_it_is_safe_from_several_threads():
    import threading
    _declare()

    def work():
        for _ in range(200):
            ss.trip("s", "sig")

    threads = [threading.Thread(target=work) for _ in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert ss.trip_report()["s/sig"]["count"] == 800


# ── reporting ──────────────────────────────────────────────────────────────

def test_the_report_leads_with_incidents(monkeypatch):
    ss.register("s", [
        ss.SiteSignal(name="minor", kind="liveness", severity="info", means="m"),
        ss.SiteSignal(name="bad", kind="distress", severity="incident", means="m"),
    ])
    ss.trip("s", "minor")
    ss.trip("s", "bad")
    lines = []
    monkeypatch.setattr(ss.logger, "info", lambda m: lines.append(m))
    ss.log_trip_report()
    body = [l for l in lines if "s/" in l]
    assert "bad" in body[0], "an incident must not be reported below info traffic"


# ── the standing directive ─────────────────────────────────────────────────

def test_the_platform_module_names_no_business():
    src = pathlib.Path(ss.__file__).read_text(encoding="utf-8").lower()
    for term in ("feige", "douyin", "jinritemai", "飞鸽", "etsy", "ebay"):
        assert term not in src, (
            f"platform module site_signals.py mentions '{term}'; the phrases "
            f"and thresholds belong in hooks/external/<site>/signals.py"
        )
