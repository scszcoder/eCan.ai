"""R2 and R6: a deliberate quit and the relaunch pause are *waits*, not exits.

Both rules used to end unattended mode quietly, and both looked reasonable in
isolation:

* R2 -- a clean exit (``state == "quit"``, or a shutdown lease that expired
  with its process gone) made the watchdog ``return 0``. The exit code reads
  as success, so no restart policy fires, and one such event ended the session:
  an updater, an antivirus, or a scripted ``taskkill`` without ``/F`` produces
  a clean exit too, and the only trace was one line in watchdog.log.
* R6 -- ``time.sleep(RESTART_WINDOW_SEC)`` after MAX_RESTARTS parked the loop
  for 30 min. A sleeping watchdog is not watching: an uninstall, a quit, a
  clock jump, or eCan coming back on its own all went unseen.

These tests drive the real ``run()`` loop with a clock that only moves when the
loop sleeps, so "did it actually wait?" and "did it stop watching?" are both
observable instead of being argued about.
"""
import json

from utils import app_watchdog as wd

NOW = 1_800_000_000.0


def hb(**kw):
    base = {"pid": 1, "updated_at": NOW - 5, "started_at": NOW - 3600, "phase": "main_loop:running",
            "main_loop_tick": NOW - 5, "clean_exit": False}
    base.update(kw)
    return base


def fresh(clock, **kw):
    """A heartbeat that is 5 s old *relative to the driven clock*.

    The loop judges a re-read lease and a stale heartbeat against
    ``time.time()``, so a heartbeat frozen at NOW would age out of the
    lease-honouring window after two minutes and the hold would be escaped by
    accident instead of by design.
    """
    return hb(updated_at=clock.wall - 5, main_loop_tick=clock.wall - 5,
              started_at=clock.wall - 3600, **kw)


class _Clock:
    """A clock the loop cannot outrun: only ``sleep()`` moves it forward.

    A frozen clock cannot tell "waited 30 min" from "did not wait at all", and
    a free-running one would race the loop, so the sleeps are the time source.
    """

    def __init__(self, mono=1_000.0):
        self.wall = NOW
        self.mono = mono
        self.start = mono
        self.sleeps = []

    def sleep(self, sec):
        assert sec > 0, sec
        self.sleeps.append(sec)
        self.wall += sec
        self.mono += sec


def _drive(monkeypatch, tmp_path, poll, launch=None, max_polls=5_000):
    """Run the real loop; ``poll(clock, launches)`` returns ``(beat, alive)``.

    Raising ``SystemExit`` from ``poll`` ends the run the same way the end of a
    scripted heartbeat file does in test_app_watchdog.py, without being caught
    by the loop's own error accounting.
    """
    clock = _Clock()
    seen = {"beat": None, "alive": False, "polls": 0}
    launches = []

    monkeypatch.setattr(wd, "runlogs_dir", lambda: tmp_path)
    monkeypatch.setattr(wd, "_other_instance_running", lambda: None)
    monkeypatch.setattr(wd, "_cpu_seconds", lambda pid: None)

    def fake_read(_p):
        seen["polls"] += 1
        if seen["polls"] > max_polls:
            raise SystemExit(f"the loop polled {max_polls} times without ending")
        seen["beat"], seen["alive"] = poll(clock, launches)
        return seen["beat"]

    def fake_launch():
        launches.append(clock.mono)
        return launch(clock) if launch else None

    monkeypatch.setattr(wd, "read_heartbeat", fake_read)
    monkeypatch.setattr(wd, "process_alive", lambda h: seen["alive"])
    monkeypatch.setattr(wd, "_launch", fake_launch)
    monkeypatch.setattr(wd, "_kill", lambda pid: None)
    monkeypatch.setattr(wd.time, "sleep", clock.sleep)
    monkeypatch.setattr(wd.time, "time", lambda: clock.wall)
    monkeypatch.setattr(wd.time, "monotonic", lambda: clock.mono)
    try:
        rc = wd.run()
    except SystemExit:
        rc = None
    return {"clock": clock, "launches": launches, "rc": rc, "polls": seen["polls"]}


# --------------------------------------------------------------------------
# R2: a clean exit is a request for quiet, not a request to stop supervising.
# --------------------------------------------------------------------------

def test_a_deliberate_quit_is_respected_and_then_supervision_resumes(monkeypatch, tmp_path):
    """The quit holds the relaunch for QUIT_HOLD_SEC -- and then it relaunches.

    Before: watchdog.log said "eCan exited cleanly (user quit); watchdog
    exiting", and it was over for the session. Now the same event buys a
    bounded silence, and unattended mode comes back on its own.
    """
    quit_at = {}

    def poll(clock, launches):
        if clock.mono < clock.start + 2 * wd.POLL_SEC:
            return fresh(clock), True                # eCan is running normally
        if not launches:
            quit_at.setdefault("mono", clock.mono)
            return fresh(clock, clean_exit=True), False   # the user quit
        raise SystemExit                         # the relaunch is what we assert on

    out = _drive(monkeypatch, tmp_path, poll)
    assert len(out["launches"]) == 1, out
    held = out["launches"][0] - quit_at["mono"]
    assert held >= wd.QUIT_HOLD_SEC - wd.POLL_SEC, f"relaunched after only {held}s"
    assert held <= wd.QUIT_HOLD_SEC + 2 * wd.POLL_SEC, f"relaunched {held}s later, too late"
    # And it waited by polling, not by parking the loop.
    assert max(out["clock"].sleeps) <= wd.POLL_SEC


def test_an_expired_lease_after_a_slow_shutdown_only_pauses(monkeypatch, tmp_path):
    """The second route into the same disarmament: a teardown outlived its lease.

    Same hold, same conclusion -- the app is gone, so it is started again.
    """
    (tmp_path / "exit_intent.json").write_text(json.dumps({
        "reason": "user_exit", "at": NOW - 1000, "grace_s": 120, "pid": 1,
    }), encoding="utf-8")
    seen_at = {}

    def poll(clock, launches):
        if launches:
            raise SystemExit
        seen_at.setdefault("mono", clock.mono)
        return fresh(clock), False

    out = _drive(monkeypatch, tmp_path, poll)
    assert len(out["launches"]) == 1, out
    held = out["launches"][0] - seen_at["mono"]
    assert wd.QUIT_HOLD_SEC - wd.POLL_SEC <= held <= wd.QUIT_HOLD_SEC + 2 * wd.POLL_SEC, held


def test_the_lease_we_already_acted_on_does_not_re_arm_the_hold(monkeypatch, tmp_path, caplog):
    """A relaunch caused by the marker must not be undone by re-reading the marker.

    The lease stays on disk until the new instance clears it on startup
    (utils/exit_intent.py::on_startup), so the very next poll still sees an
    expired lease and a dead process. Without the guard in that branch the
    hold would start over -- suppressing the relaunch we just made for another
    30 min, and then making a second one.
    """
    (tmp_path / "exit_intent.json").write_text(json.dumps({
        "reason": "user_exit", "at": NOW - 1000, "grace_s": 120, "pid": 1,
    }), encoding="utf-8")

    def poll(clock, launches):
        if launches and clock.mono > launches[-1] + wd.STARTUP_TIMEOUT_SEC - 2 * wd.POLL_SEC:
            raise SystemExit
        return fresh(clock), False

    with caplog.at_level("INFO", logger="ecan.watchdog"):
        out = _drive(monkeypatch, tmp_path, poll)
    assert len(out["launches"]) == 1, out["launches"]
    # Announced once, for the hold before the relaunch -- not again after it.
    holds = [r.getMessage() for r in caplog.records if "not relaunching it for" in r.getMessage()]
    assert len(holds) == 1, holds

def test_an_app_that_comes_back_by_itself_restarts_the_full_hold(monkeypatch, tmp_path):
    """If eCan is running again (someone started it), the next quit gets a full hold.

    Otherwise a stale deadline from the first quit would relaunch straight away
    the second time the user closed the window.
    """
    def poll(clock, launches):
        if clock.mono < clock.start + 2 * wd.POLL_SEC:
            return fresh(clock), True
        if clock.mono < clock.start + wd.QUIT_HOLD_SEC:
            return fresh(clock), True                # back up during the hold
        raise SystemExit

    out = _drive(monkeypatch, tmp_path, poll)
    assert out["launches"] == [] and out["rc"] is None


# --------------------------------------------------------------------------
# R6: the relaunch pause suppresses launches, never observation.
# --------------------------------------------------------------------------

class _DeadOnArrival:
    """The instance we started is gone before it writes a heartbeat."""

    def __init__(self, pid):
        self.pid = pid

    def poll(self):
        return 0


def test_the_relaunch_pause_does_not_stop_watching(monkeypatch, tmp_path):
    """MAX_RESTARTS used to buy a 30 min sleep; an uninstall during it was missed.

    Here the pause is entered for real (three relaunches inside the window),
    and an uninstall marker is planted while it runs. The watchdog has to act
    on it within a poll -- i.e. the pause is a suppressed launch, not a nap.
    """
    pids = iter(range(7_000, 8_000))
    planted = {}

    def poll(clock, launches):
        # Plant only once the budget is spent *and* the grace has passed, so
        # the poll that sets pause_until has already happened.
        if (len(launches) >= wd.MAX_RESTARTS and "mono" not in planted
                and clock.mono >= launches[-1] + wd.LAUNCH_GRACE_SEC + 2 * wd.POLL_SEC):
            planted["mono"] = clock.mono
            (tmp_path / "exit_intent.json").write_text(json.dumps({
                "reason": "uninstall", "at": clock.wall, "grace_s": "inf", "pid": 1,
            }), encoding="utf-8")
        return None, False

    out = _drive(monkeypatch, tmp_path, poll, launch=lambda clock: _DeadOnArrival(next(pids)))
    assert out["rc"] == 0, out                # an uninstall still ends it
    assert "mono" in planted, "the relaunch budget was never spent; test precondition broken"
    assert len(out["launches"]) == wd.MAX_RESTARTS, out["launches"]
    # The unattended run ended inside the pause window, one poll after the
    # marker appeared -- with a 30 min sleep it would have waited out the nap.
    assert out["clock"].mono - planted["mono"] < 2 * wd.POLL_SEC
    assert out["clock"].mono - planted["mono"] < wd.RESTART_WINDOW_SEC
    # No single sleep in the whole run was longer than a poll.
    assert max(out["clock"].sleeps) <= wd.POLL_SEC, max(out["clock"].sleeps)
