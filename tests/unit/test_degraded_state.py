"""Can the person running this tell that it is broken?

Every detector so far writes to a log or to the permanent journal. Neither is
visible to the person whose shop is not getting replies — they find out when a
customer complains, which is the situation this whole effort exists to leave.

So the three things that know something is wrong feed a readiness level that
shows up as a dot on the Agents page. The properties under test:

1. It goes red for real problems and stays quiet for transient ones.
2. Recovery clears it — a latched red dot is as useless as no dot.
3. The things that know feed it, and the UI reads it.
"""

import pathlib

import pytest

from agent.ec_skills.browser_use_extension import degraded_state as ds


@pytest.fixture(autouse=True)
def clean():
    ds.reset()
    yield
    ds.reset()


def _age(source, seconds):
    """Backdate a degradation, as if it had been going on that long."""
    import time
    ds._ACTIVE[source].since = time.time() - seconds


# ── the level ──────────────────────────────────────────────────────────────

def test_a_healthy_install_reports_ok():
    assert ds.state() == ("ok", "")


def test_a_fresh_problem_is_watched_not_red():
    """Pages render late and scans catch frames mid-rebuild. Going red on the
    first miss makes the dot meaningless within a day."""
    ds.mark_degraded("parser_collapse", "stopped resolving", site="s", element="e")
    level, detail = ds.state()
    assert level == "watching"
    assert "parser_collapse" in detail


def test_a_persistent_problem_goes_red():
    ds.mark_degraded("parser_collapse", site="s", element="e")
    _age("parser_collapse", ds.DEGRADED_AFTER_S + 1)
    assert ds.state()[0] == "degraded"


def test_the_age_is_how_long_it_has_been_happening():
    """Not how recently it was last mentioned — these conditions recur every
    scan, so a restarted clock would never reach the threshold."""
    ds.mark_degraded("parser_collapse", "first")
    _age("parser_collapse", ds.DEGRADED_AFTER_S + 1)
    ds.mark_degraded("parser_collapse", "still happening")
    assert ds.state()[0] == "degraded"
    assert "still happening" in ds.state()[1]


def test_recovery_clears_it():
    ds.mark_degraded("resolver_circuit", site="s", element="e")
    _age("resolver_circuit", ds.DEGRADED_AFTER_S + 1)
    assert ds.state()[0] == "degraded"
    ds.mark_recovered("resolver_circuit")
    assert ds.state() == ("ok", "")


def test_recovering_one_source_leaves_the_others():
    ds.mark_degraded("a", "one")
    ds.mark_degraded("b", "two")
    ds.mark_recovered("a")
    level, detail = ds.state()
    assert level == "watching"
    assert "b" in detail and "a@" not in detail


def test_recovering_something_that_was_never_wrong_is_harmless():
    ds.mark_recovered("never_marked")
    assert ds.state() == ("ok", "")


def test_the_worst_problem_sets_the_level():
    """One long-running problem makes the install degraded even if a second
    one only just appeared."""
    ds.mark_degraded("old", "a")
    _age("old", ds.DEGRADED_AFTER_S + 1)
    ds.mark_degraded("new", "b")
    assert ds.state()[0] == "degraded"


def test_the_detail_names_what_is_wrong_and_where():
    ds.mark_degraded("resolver_circuit", "gave up", site="feige_chat",
                     element="sidebar_row_name")
    detail = ds.state()[1]
    assert "resolver_circuit" in detail
    assert "feige_chat/sidebar_row_name" in detail
    assert "gave up" in detail


def test_active_lists_what_is_wrong():
    ds.mark_degraded("a", "detail", site="s", element="e")
    rows = ds.active()
    assert rows["a"]["site"] == "s" and rows["a"]["element"] == "e"
    assert isinstance(rows["a"]["age_s"], int)


# ── it reaches the readiness ledger ────────────────────────────────────────

def test_marking_reports_to_the_readiness_ledger(monkeypatch):
    """The dot is the whole point; a level nobody can see is not a fix."""
    from utils import agent_status
    seen = []
    monkeypatch.setattr(agent_status, "report",
                        lambda **kw: seen.append(kw) or {})
    ds.mark_degraded("parser_collapse", "stopped", site="s", element="e")
    assert seen, "nothing reached agent_status"
    assert seen[-1]["targeting"] == "watching"
    assert "parser_collapse" in seen[-1]["targeting_detail"]


def test_recovery_reports_ok(monkeypatch):
    from utils import agent_status
    seen = []
    monkeypatch.setattr(agent_status, "report",
                        lambda **kw: seen.append(kw) or {})
    ds.mark_degraded("a")
    ds.mark_recovered("a")
    assert seen[-1]["targeting"] == "ok"


def test_refresh_promotes_watching_to_degraded(monkeypatch):
    """`watching` becomes `degraded` through time passing, and nothing here
    runs on a timer — so a periodic caller has to re-evaluate."""
    from utils import agent_status
    seen = []
    monkeypatch.setattr(agent_status, "report",
                        lambda **kw: seen.append(kw) or {})
    ds.mark_degraded("a")
    _age("a", ds.DEGRADED_AFTER_S + 1)
    ds.refresh()
    assert seen[-1]["targeting"] == "degraded"


def test_a_broken_ledger_cannot_break_the_caller(monkeypatch):
    from utils import agent_status
    monkeypatch.setattr(agent_status, "report",
                        lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    ds.mark_degraded("a")               # must not raise
    ds.mark_recovered("a")


def test_it_is_safe_from_several_threads():
    import threading

    def work(n):
        for _ in range(50):
            ds.mark_degraded(f"s{n}")
            ds.mark_recovered(f"s{n}")

    threads = [threading.Thread(target=work, args=(n,)) for n in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert ds.state() == ("ok", "")


# ── the sources actually feed it ───────────────────────────────────────────

def test_an_open_breaker_marks_the_install_degraded(tmp_path, monkeypatch):
    monkeypatch.setenv("ECAN_RESOLVER_GUARD_DIR", str(tmp_path / "guard"))
    monkeypatch.setenv("ECAN_DRIFT_JOURNAL_DIR", str(tmp_path / "journal"))
    from agent.ec_skills.browser_use_extension import resolver_guard as rg
    rg.reset()
    for _ in range(rg.CIRCUIT_AFTER_FAILURES):
        rg.record_outcome("s", "e", resolved=False)
    assert "resolver_circuit" in ds.active()
    rg.reset()


def test_a_successful_resolution_clears_the_breaker_degradation(tmp_path,
                                                                monkeypatch):
    monkeypatch.setenv("ECAN_RESOLVER_GUARD_DIR", str(tmp_path / "guard"))
    monkeypatch.setenv("ECAN_DRIFT_JOURNAL_DIR", str(tmp_path / "journal"))
    from agent.ec_skills.browser_use_extension import resolver_guard as rg
    rg.reset()
    for _ in range(rg.CIRCUIT_AFTER_FAILURES):
        rg.record_outcome("s", "e", resolved=False)
    rg.record_outcome("s", "e", resolved=True)
    assert "resolver_circuit" not in ds.active()
    rg.reset()


def test_a_parser_collapse_marks_the_install_degraded(tmp_path, monkeypatch):
    monkeypatch.setenv("ECAN_DRIFT_JOURNAL_DIR", str(tmp_path / "journal"))
    from agent.ec_skills.browser_use_extension import element_targeting as et
    et.reset()
    for _ in range(95):
        et.record_resolution("s", "row", "data_qa_id")
    for _ in range(5):
        et.record_resolution("s", "row", "titled_scan")
    baseline = et.resolution_report()
    et.reset()
    for _ in range(30):
        et.record_resolution("s", "row", "titled_scan")
    et.log_drift(baseline)
    assert "parser_collapse" in ds.active()
    et.reset()


def test_an_incident_signal_marks_the_install_degraded(tmp_path, monkeypatch):
    monkeypatch.setenv("ECAN_DRIFT_JOURNAL_DIR", str(tmp_path / "journal"))
    from agent.ec_skills.browser_use_extension import site_signals as ss
    ss.reset()
    ss.register("s", [ss.SiteSignal(name="lost", kind="distress",
                                    severity="incident",
                                    means="the customer is gone")])
    ss.trip("s", "lost")
    assert "signal:lost" in ds.active(), (
        "an incident did not reach the readiness dots — check that trip() "
        "passes only parameters it actually has")


def test_a_warning_signal_does_not_turn_the_dot(tmp_path, monkeypatch):
    """Warnings are worth knowing about; incidents are worth someone looking.
    Turning the dot for both makes it meaningless."""
    monkeypatch.setenv("ECAN_DRIFT_JOURNAL_DIR", str(tmp_path / "journal"))
    from agent.ec_skills.browser_use_extension import site_signals as ss
    ss.reset()
    ss.register("s", [ss.SiteSignal(name="late", kind="distress",
                                    severity="warning", means="we are late")])
    ss.trip("s", "late")
    assert ds.active() == {}


# ── the UI reads it ────────────────────────────────────────────────────────

STRIP = (pathlib.Path(__file__).resolve().parents[2] / "gui_v2" / "src"
         / "pages" / "Agents" / "components" / "ReadinessStrip.tsx")


def test_the_agents_page_shows_a_targeting_dot():
    src = STRIP.read_text(encoding="utf-8")
    assert "targetingLevel" in src
    assert "'targeting'" in src


def test_watching_is_amber_and_degraded_is_red():
    src = STRIP.read_text(encoding="utf-8")
    block = src[src.index("function targetingLevel"):]
    block = block[:block.index("}\n")]
    assert "'degraded'" in block and "'bad'" in block
    assert "'watching'" in block and "'warn'" in block


@pytest.mark.parametrize("locale", ["en-US", "zh-CN"])
def test_the_dot_is_labelled_in_both_locales(locale):
    import json
    path = (pathlib.Path(__file__).resolve().parents[2] / "gui_v2" / "src"
            / "i18n" / "locales" / f"{locale}.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["pages"]["agents"].get("readiness_targeting")


# ── the standing directive ─────────────────────────────────────────────────

def test_the_platform_module_names_no_business():
    src = pathlib.Path(ds.__file__).read_text(encoding="utf-8").lower()
    for term in ("feige", "douyin", "jinritemai", "飞鸽", "etsy", "ebay"):
        assert term not in src
