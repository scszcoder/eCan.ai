"""The persisted crash-loop breaker: it must bound a build that cannot stay up.

Every test here is about a number that is finite. The failure being defended
against is a build with a bug that kills it seconds after launch, which the
in-memory restart budget turned into ~144 launches a day, forever, because the
budget refilled itself and was forgotten every time the watchdog restarted.
"""
import json

import pytest

from utils import watchdog_breaker as wb

NOW = 1_800_000_000.0


def _fail_n(state, n, start=NOW, reason="crashed"):
    """Apply *n* consecutive failures, honouring each wait in between."""
    now = start
    for _ in range(n):
        state = wb.note_failure(state, now, reason)
        now = state["next_attempt_at"] or now
    return state, now


# --------------------------------------------------------------------------
# Closed: nothing changes until something actually fails
# --------------------------------------------------------------------------

def test_a_fresh_breaker_allows_every_launch():
    st = wb.new_state()
    assert wb.allow_launch(st, NOW) == (True, 0.0)
    assert wb.needs_reset(st) is False
    assert wb.summary(st)["tripped"] is False
    assert wb.summary(st)["gave_up"] is False


# --------------------------------------------------------------------------
# The backoff ladder
# --------------------------------------------------------------------------

def test_failures_back_off_geometrically_and_then_hold():
    """30, 60, 120, 240, 480, then 900 s -- never more than MAX_BACKOFF_SEC."""
    st = wb.new_state()
    now = NOW
    waits = []
    for _ in range(5):
        st = wb.note_failure(st, now, "crashed")
        allowed, wait = wb.allow_launch(st, now)
        assert allowed is False
        waits.append(wait)
        now = st["next_attempt_at"]
    assert waits == [30.0, 60.0, 120.0, 240.0, 480.0]
    # The sixth failure is the storm threshold, so it opens the breaker instead
    # of setting another, longer ladder delay.
    st = wb.note_failure(st, now, "crashed")
    assert st["consecutive_failures"] == wb.STORM_THRESHOLD
    assert st["opened_at"] > 0
    assert st["cooldown_sec"] > wb.MAX_BACKOFF_SEC


def test_the_backoff_never_exceeds_its_ceiling():
    st = wb.new_state()
    now = NOW
    for _ in range(5):
        st = wb.note_failure(st, now, "crashed")
        now = st["next_attempt_at"]
    # Punish the same state far beyond the threshold: everything stays capped.
    st["consecutive_failures"] = wb.STORM_THRESHOLD - 1
    st["opened_at"] = 0.0
    for _ in range(10):
        st = wb.note_failure(st, now, "crashed")
        now = st["next_attempt_at"]
        assert st["cooldown_sec"] <= wb.MAX_COOLDOWN_SEC
        assert st["next_attempt_at"] - now <= wb.MAX_COOLDOWN_SEC


# --------------------------------------------------------------------------
# Open -> half open -> given up
# --------------------------------------------------------------------------

def test_a_storm_trips_the_breaker_and_the_wait_jumps_to_the_first_cooldown():
    st, now = _fail_n(wb.new_state(), wb.STORM_THRESHOLD)
    assert st["opened_at"] > 0
    assert st["consecutive_failures"] == wb.STORM_THRESHOLD
    allowed, wait = wb.allow_launch(st, st["opened_at"])
    assert allowed is False
    assert wait == pytest.approx(wb.OPEN_COOLDOWN_SEC)
    assert wb.summary(st)["tripped"] is True


def test_each_failed_probe_doubles_the_cooldown_and_then_it_gives_up():
    st, now = _fail_n(wb.new_state(), wb.STORM_THRESHOLD)
    seen = []
    for _ in range(wb.GIVE_UP_AFTER_PROBES):
        assert wb.allow_launch(st, st["opened_at"])[0] is False
        st = wb.note_failure(st, st["opened_at"], "crashed")
        seen.append(st["cooldown_sec"])
    assert seen == [3600.0, 7200.0, 14400.0, 21600.0, 21600.0]
    assert st["gave_up"] is True
    # The caller must be able to tell "wait" from "stop asking" without a clock.
    assert wb.allow_launch(st, NOW + 10 ** 9) == (False, float("inf"))
    assert wb.summary(st)["gave_up"] is True


def test_the_total_number_of_attempts_in_a_storm_is_bounded():
    """The whole point: a finite number of launches, whatever the clock does."""
    st = wb.new_state()
    now = NOW
    launches = 0
    for _ in range(400):                     # far more polls than a day has
        allowed, wait = wb.allow_launch(st, now)
        if not allowed:
            if wait == float("inf"):
                break
            now += wait
            continue
        launches += 1
        st = wb.note_launch(st, now)
        st = wb.note_failure(st, now, "crashed")
        now = max(now, st["next_attempt_at"])
    assert st["gave_up"] is True
    # The ladder (STORM_THRESHOLD attempts) plus one launch per failed probe.
    assert launches == wb.STORM_THRESHOLD + wb.GIVE_UP_AFTER_PROBES
    assert len(st["history"]) <= wb.MAX_HISTORY


def test_a_broken_installation_trips_it_sooner():
    """``launch_failed`` cannot be fixed by retrying: 3 strikes, not 6."""
    st, _ = _fail_n(wb.new_state(), wb.LAUNCH_FAILURE_THRESHOLD, reason="launch_failed")
    assert st["opened_at"] > 0
    st2, _ = _fail_n(wb.new_state(), wb.LAUNCH_FAILURE_THRESHOLD - 1, reason="launch_failed")
    assert st2["opened_at"] == 0.0


def test_a_probe_that_died_unnoticed_still_costs_the_full_cooldown():
    """``note_launch`` reserves the slot, so a probe killed by us (a hang) or by
    a machine going to sleep cannot buy a burst of extra attempts."""
    st, _ = _fail_n(wb.new_state(), wb.STORM_THRESHOLD)
    st = wb.note_launch(st, st["opened_at"] + wb.OPEN_COOLDOWN_SEC)
    allowed, wait = wb.allow_launch(st, st["opened_at"] + wb.OPEN_COOLDOWN_SEC)
    assert allowed is False and wait > 0


# --------------------------------------------------------------------------
# Recovery has to be automatic, or an unattended machine stays down
# --------------------------------------------------------------------------

def test_a_healthy_instance_closes_it_even_after_giving_up():
    st, _ = _fail_n(wb.new_state(), 40)
    assert st["gave_up"] is True
    assert wb.needs_reset(st) is True
    st = wb.note_healthy(st, NOW)
    assert st["gave_up"] is False and st["opened_at"] == 0.0
    assert st["consecutive_failures"] == 0 and st["probes"] == 0
    assert wb.allow_launch(st, NOW) == (True, 0.0)
    assert wb.needs_reset(st) is False


def test_reset_forgets_the_storm():
    path = None
    st, _ = _fail_n(wb.new_state(), 40)
    st2 = wb.reset("/dev/null")                     # a path that cannot be written
    assert st2["gave_up"] is False and wb.allow_launch(st2, NOW) == (True, 0.0)


# --------------------------------------------------------------------------
# Persistence: the state has to survive the watchdog itself
# --------------------------------------------------------------------------

def test_the_state_survives_a_watchdog_restart(tmp_path):
    path = tmp_path / "watchdog_breaker.json"
    st, _ = _fail_n(wb.new_state(), wb.STORM_THRESHOLD)
    assert wb.save(path, st) is True
    assert not list(tmp_path.glob("*.tmp"))         # atomic: no leftovers

    again = wb.load(path)
    assert again["consecutive_failures"] == st["consecutive_failures"]
    assert again["opened_at"] == st["opened_at"]
    assert wb.allow_launch(again, st["opened_at"])[0] is False


def test_a_missing_or_corrupt_file_is_a_closed_breaker_not_a_crash(tmp_path):
    path = tmp_path / "watchdog_breaker.json"
    assert wb.load(path)["gave_up"] is False        # missing
    path.write_text("{ this is not json", encoding="utf-8")
    assert wb.allow_launch(wb.load(path), NOW) == (True, 0.0)
    path.write_text("[1, 2, 3]", encoding="utf-8")   # valid JSON, wrong shape
    assert wb.allow_launch(wb.load(path), NOW) == (True, 0.0)


def test_a_hand_edited_file_cannot_make_the_breaker_raise(tmp_path):
    path = tmp_path / "watchdog_breaker.json"
    path.write_text(json.dumps({
        "consecutive_failures": "lots", "total_failures": -5, "probes": None,
        "opened_at": "yesterday", "next_attempt_at": float("inf"),
        "gave_up": 1, "last_reason": "x" * 500, "history": "not a list",
        "last_failure_at": float("nan"),
    }), encoding="utf-8")
    st = wb.load(path)
    assert st["consecutive_failures"] == 0 and st["total_failures"] == 0
    assert st["opened_at"] == 0.0 and st["next_attempt_at"] == 0.0
    assert st["gave_up"] is True                     # it *was* truthy; honour it
    assert st["last_reason"].startswith("x") and len(st["last_reason"]) <= 200
    assert st["history"] == []
    assert isinstance(wb.summary(st)["last_failure_iso"], str)


def test_history_is_bounded(tmp_path):
    path = tmp_path / "watchdog_breaker.json"
    st = wb.new_state()
    now = NOW
    for i in range(wb.MAX_HISTORY * 3):
        st = wb.note_failure(st, now, "crashed", uptime_s=i)
        now += 1
    assert len(st["history"]) == wb.MAX_HISTORY
    assert wb.save(path, st) is True
    assert len(wb.load(path)["history"]) == wb.MAX_HISTORY


# --------------------------------------------------------------------------
# Clocks
# --------------------------------------------------------------------------

def test_a_clock_change_cannot_park_the_breaker_in_the_future():
    """The state outlives processes, so it outlives a clock change. A stamp two
    days ahead must not mean two days of silence -- or, because the comparison
    moves with the clock, permanent silence."""
    st = wb.new_state()
    st["opened_at"] = NOW
    st["next_attempt_at"] = NOW + 2 * 86400
    assert wb.allow_launch(st, NOW) == (True, 0.0)

    # ... and the rule must never cut a *legitimate* cooldown short.
    legit = wb.new_state()
    legit["opened_at"] = NOW
    legit["cooldown_sec"] = wb.MAX_COOLDOWN_SEC
    legit["next_attempt_at"] = NOW + wb.MAX_COOLDOWN_SEC
    assert wb.allow_launch(legit, NOW)[0] is False
    assert wb.allow_launch(legit, NOW + wb.MAX_COOLDOWN_SEC - 60)[0] is False
    assert wb.allow_launch(legit, NOW + wb.MAX_COOLDOWN_SEC + 1)[0] is True


def test_a_stamp_in_the_past_does_not_block_anything():
    st = wb.new_state()
    st["next_attempt_at"] = NOW - 10_000
    assert wb.allow_launch(st, NOW) == (True, 0.0)


# --------------------------------------------------------------------------
# The supervisor's own loop: the layer above the app crash loop
# --------------------------------------------------------------------------

def test_a_supervisor_that_cannot_poll_is_counted_and_cleared():
    st = wb.new_state()
    assert st["loop_error_streak"] == 0
    assert wb.summary(st)["loop_error_streak"] == 0
    for i in range(3):
        st = wb.note_loop_error(st)
        assert st["loop_error_streak"] == i + 1
    # Reaching the loop again means the last exit was not "this build cannot
    # supervise at all": the streak is forgotten, or an intermittent bug would
    # accumulate against a limit meant for a permanently broken build.
    st = wb.note_loop_ok(st)
    assert st["loop_error_streak"] == 0
    assert wb.summary(st)["loop_error_streak"] == 0


def test_the_loop_error_count_survives_a_watchdog_restart(tmp_path):
    path = tmp_path / "watchdog_breaker.json"
    st = wb.new_state()
    wb.save(path, wb.note_loop_error(st))
    wb.save(path, wb.note_loop_error(wb.load(path)))
    # The platform restarts the watchdog after a crash, and the count has to
    # come from disk: an in-memory counter is exactly what the old budget got
    # wrong (a restart refilled it).
    assert wb.load(path)["loop_error_streak"] == 2


def test_a_hand_edited_loop_error_streak_cannot_raise(tmp_path):
    path = tmp_path / "watchdog_breaker.json"
    path.write_text(json.dumps({"loop_error_streak": "many"}), encoding="utf-8")
    st = wb.load(path)
    assert st["loop_error_streak"] == 0
    assert wb.note_loop_error(st)["loop_error_streak"] == 1
