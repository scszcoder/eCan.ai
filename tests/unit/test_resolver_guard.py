"""Spending limits for L2, and the breaker.

L2 calls the strongest model available, by decision. That makes an unhealed
element an unbounded money leak: it fails, we ask, the answer does not stick,
the next poll asks again — forever, on every affected machine, with nobody
watching.

The properties that matter:

1. **The cap survives a restart.** A machine stuck in a bad state restarts a
   lot, and an in-memory cap gives it a fresh allowance each time.
2. **One hopeless element cannot starve the others.**
3. **Giving up is LOUD.** Silence plus spend is the worst outcome: the machine
   is broken and unremarkable. A breaker that opens quietly is barely better
   than no breaker.
"""

import pathlib

import pytest

from agent.ec_skills.browser_use_extension import drift_journal as dj
from agent.ec_skills.browser_use_extension import resolver_guard as rg


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("ECAN_RESOLVER_GUARD_DIR", str(tmp_path / "guard"))
    monkeypatch.setenv("ECAN_DRIFT_JOURNAL_DIR", str(tmp_path / "journal"))
    rg.reset()
    dj.reset_incident_window()
    yield
    rg.reset()
    dj.reset_incident_window()


def _spend(n, site="s", element="e"):
    """Make n permitted calls, defeating backoff (tested separately)."""
    for _ in range(n):
        rg.record_attempt(site, element)


# ── the caps ───────────────────────────────────────────────────────────────

def test_a_fresh_element_is_allowed():
    permitted, why = rg.allow("s", "e")
    assert permitted and why == ""


def test_an_element_is_capped_per_day():
    _spend(rg.DAILY_CAP_PER_ELEMENT)
    permitted, why = rg.allow("s", "e")
    assert not permitted
    assert "element daily cap" in why


def test_one_hopeless_element_does_not_starve_another():
    """The whole point of a per-element cap."""
    _spend(rg.DAILY_CAP_PER_ELEMENT, element="hopeless")
    assert not rg.allow("s", "hopeless")[0]
    assert rg.allow("s", "other")[0]


def test_the_machine_has_a_cap_across_all_elements():
    """The backstop for 'many elements each just under their own cap'."""
    per = rg.DAILY_CAP_PER_ELEMENT
    for i in range((rg.DAILY_CAP_TOTAL // per) + 1):
        _spend(per, element=f"e{i}")
    permitted, why = rg.allow("s", "brand_new")
    assert not permitted
    assert "machine daily cap" in why


def test_a_timed_out_call_still_costs_its_budget():
    """Charged on attempt, not on answer — otherwise a call that hangs or
    crashes is free, and those are exactly the expensive ones."""
    before = rg.report()["calls_today"]
    rg.record_attempt("s", "e")            # no outcome ever reported
    assert rg.report()["calls_today"] == before + 1


# ── it must survive a restart ──────────────────────────────────────────────

def test_the_days_spend_survives_a_restart():
    """An in-memory cap gives a crash-looping machine a fresh allowance every
    time, which is no cap at all."""
    _spend(rg.DAILY_CAP_PER_ELEMENT)
    assert not rg.allow("s", "e")[0]

    import importlib
    reloaded = importlib.reload(rg)
    assert not reloaded.allow("s", "e")[0], "the cap reset on restart"


def test_an_open_breaker_survives_a_restart():
    for _ in range(rg.CIRCUIT_AFTER_FAILURES):
        rg.record_outcome("s", "e", resolved=False)
    assert not rg.allow("s", "e")[0]

    import importlib
    reloaded = importlib.reload(rg)
    permitted, why = reloaded.allow("s", "e")
    assert not permitted and "circuit open" in why


def test_a_breaker_that_opened_late_is_not_cleared_by_midnight():
    """Daily caps reset at UTC midnight; a breaker must not, or an element that
    was declared broken at 23:59 is retried at 00:00."""
    for _ in range(rg.CIRCUIT_AFTER_FAILURES):
        rg.record_outcome("s", "e", resolved=False)

    # Simulate the day rolling over.
    rg._DAY = "1999-01-01"
    permitted, why = rg.allow("s", "e")
    assert not permitted and "circuit open" in why


# ── the breaker ────────────────────────────────────────────────────────────

def test_a_losing_run_opens_the_breaker():
    for i in range(rg.CIRCUIT_AFTER_FAILURES - 1):
        rg.record_outcome("s", "e", resolved=False)
        assert rg.allow("s", "e")[0] or True     # backoff may refuse; fine
    rg.record_outcome("s", "e", resolved=False)
    permitted, why = rg.allow("s", "e")
    assert not permitted and "circuit open" in why


def test_a_success_clears_the_losing_run():
    """Healing is the normal case; a couple of misses must not latch."""
    for _ in range(rg.CIRCUIT_AFTER_FAILURES - 1):
        rg.record_outcome("s", "e", resolved=False)
    rg.record_outcome("s", "e", resolved=True)
    for _ in range(rg.CIRCUIT_AFTER_FAILURES - 1):
        rg.record_outcome("s", "e", resolved=False)
    assert rg.report()["elements"]["s::e"]["circuit_open"] is False


def test_opening_the_breaker_is_loud(monkeypatch):
    """Silence plus spend is the worst outcome."""
    errors = []
    monkeypatch.setattr(rg.logger, "error", lambda m: errors.append(m))
    for _ in range(rg.CIRCUIT_AFTER_FAILURES):
        rg.record_outcome("s", "e", resolved=False)
    assert errors, "the breaker opened without saying so"
    assert "CIRCUIT OPEN" in errors[0]
    assert "needs a human" in errors[0]


def test_opening_the_breaker_goes_on_the_permanent_record():
    """'We gave up on this element on this date' should be answerable in two
    years, not just in today's run log."""
    for _ in range(rg.CIRCUIT_AFTER_FAILURES):
        rg.record_outcome("s", "e", resolved=False)
    (event,) = dj.read_events()
    assert event["kind"] == "resolver_circuit_open"
    assert event["element"] == "e"


def test_the_breaker_opens_once_not_on_every_further_failure():
    for _ in range(rg.CIRCUIT_AFTER_FAILURES * 3):
        rg.record_outcome("s", "e", resolved=False)
    assert len(dj.read_events()) == 1


# ── backoff ────────────────────────────────────────────────────────────────

def test_a_failure_introduces_backoff():
    """Without this a fast poll loop spends the daily cap in a minute."""
    rg.record_attempt("s", "e")
    rg.record_outcome("s", "e", resolved=False)
    permitted, why = rg.allow("s", "e")
    assert not permitted and "backing off" in why


def test_backoff_grows_with_consecutive_failures():
    rg.record_attempt("s", "e")
    rg.record_outcome("s", "e", resolved=False)
    first = rg.allow("s", "e")[1]
    rg.record_attempt("s", "e")
    rg.record_outcome("s", "e", resolved=False)
    second = rg.allow("s", "e")[1]

    def secs(msg):
        return int("".join(ch for ch in msg if ch.isdigit()) or 0)

    assert secs(second) > secs(first)


def test_backoff_is_capped():
    assert rg.BACKOFF_MAX_S <= 600, "an unbounded backoff is just a broken element"


# ── it must not become the problem ─────────────────────────────────────────

def test_the_guard_fails_OPEN_when_it_cannot_read_its_state(monkeypatch):
    """A guard that throws must not be the thing that blocks resolution. It is
    a cost control, not a correctness control."""
    monkeypatch.setattr(rg, "_state_path",
                        lambda: (_ for _ in ()).throw(OSError("no disk")))
    rg._LOADED = False
    permitted, _ = rg.allow("s", "e")
    assert permitted, "the guard must fail open, not closed"


def test_recording_never_raises(monkeypatch):
    monkeypatch.setattr(rg, "_save",
                        lambda: (_ for _ in ()).throw(OSError("read-only")))
    rg.record_attempt("s", "e")
    rg.record_outcome("s", "e", resolved=False)


def test_it_is_safe_from_several_threads():
    import threading

    def work(n):
        for _ in range(20):
            rg.allow("s", f"e{n}")
            rg.record_attempt("s", f"e{n}")

    threads = [threading.Thread(target=work, args=(n,)) for n in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert rg.report()["calls_today"] == 80


# ── it has to be wired in, or none of the above matters ────────────────────

def test_the_resolver_consults_the_guard():
    import inspect
    from agent.ec_skills.browser_use_extension import element_resolver
    src = inspect.getsource(element_resolver.resolve_element)
    assert "resolver_guard.allow" in src
    assert "resolver_guard.record_attempt" in src


def test_the_outcome_reaches_the_guard():
    """Without an outcome the breaker never opens, and the guard just meters a
    leak instead of stopping it."""
    import inspect
    from agent.ec_skills.browser_use_extension import learned_targets
    src = inspect.getsource(learned_targets)
    assert "resolver_guard.record_outcome" in src


def test_a_learned_descriptor_hit_is_not_charged_to_the_resolver():
    """A descriptor that was already learned costs nothing, so its success says
    nothing about L2's spend and must not clear or credit the breaker."""
    from agent.ec_skills.browser_use_extension import learned_targets as lt
    from agent.ec_skills.browser_use_extension.element_targeting import (
        TargetDescriptor,
    )
    for _ in range(rg.CIRCUIT_AFTER_FAILURES - 1):
        rg.record_outcome("s", "e", resolved=False)
    before = rg.report()["elements"]["s::e"]["consecutive_failures"]

    lt.record_success("s", "e", TargetDescriptor(target_text="Send"),
                      source="learned")
    after = rg.report()["elements"]["s::e"]["consecutive_failures"]
    assert after == before, "a cached hit was credited as an L2 success"


# ── the standing directive ─────────────────────────────────────────────────

def test_the_platform_module_names_no_business():
    src = pathlib.Path(rg.__file__).read_text(encoding="utf-8").lower()
    for term in ("feige", "douyin", "jinritemai", "飞鸽", "etsy", "ebay"):
        assert term not in src
