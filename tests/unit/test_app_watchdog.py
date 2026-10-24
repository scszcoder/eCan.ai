"""Unattended mode: the watchdog starts eCan, relaunches it after a crash or a
hang, leaves it alone when the user quit, and cannot restart-loop; the switch
creates/removes the logon task without a console window."""
import json
import time

import pytest

from utils import app_watchdog as wd

NOW = 1_800_000_000.0


def hb(**kw):
    base = {"pid": 1, "updated_at": NOW - 5, "started_at": NOW - 3600, "phase": "main_loop:running",
            "main_loop_tick": NOW - 5, "clean_exit": False}
    base.update(kw)
    return base


@pytest.mark.parametrize("beat, alive, want", [
    (None, False, "not_running"),
    (hb(), True, "ok"),
    (hb(), False, "crashed"),
    (hb(clean_exit=True), False, "quit"),
    (hb(updated_at=NOW - 300), True, "frozen"),                          # whole process stuck
    (hb(main_loop_tick=NOW - 700), True, "hung"),                        # main loop stuck
    (hb(main_loop_tick=NOW - 700, phase="startup:webgui"), True, "ok"),  # never during startup
    (hb(main_loop_tick=NOW - 700, started_at=NOW - 600), True, "ok"),    # not right after start
    (hb(main_loop_tick=None), True, "ok"),                               # older build: no tick
])
def test_assess(beat, alive, want):
    assert wd.assess(beat, NOW, alive) == want


def _drive(monkeypatch, tmp_path, beats, alive_seq):
    """Run the real loop over a scripted sequence of heartbeats."""
    monkeypatch.setattr(wd, "runlogs_dir", lambda: tmp_path)
    events = []
    it = iter(zip(beats, alive_seq))
    state = {}

    def fake_read(_p):
        try:
            state["cur"] = next(it)
        except StopIteration:
            raise SystemExit
        return state["cur"][0]

    monkeypatch.setattr(wd, "read_heartbeat", fake_read)
    monkeypatch.setattr(wd, "process_alive", lambda h: state["cur"][1])
    monkeypatch.setattr(wd, "_launch", lambda: events.append("launch"))
    monkeypatch.setattr(wd, "_kill", lambda pid: events.append(f"kill {pid}"))
    # Never scan the real process table here: a developer with eCan open would
    # otherwise make every launch decision in this file depend on their desktop.
    monkeypatch.setattr(wd, "_other_instance_running", lambda: None)
    monkeypatch.setattr(wd.time, "sleep", lambda s: None)
    monkeypatch.setattr(wd.time, "time", lambda: NOW)
    try:
        rc = wd.run()
    except SystemExit:
        rc = None
    return events, rc


def test_logon_start_launches_even_after_a_previous_clean_exit(monkeypatch, tmp_path):
    events, _ = _drive(monkeypatch, tmp_path, [hb(clean_exit=True)], [False])
    assert events == ["launch"]


def test_hung_app_is_killed_and_relaunched(monkeypatch, tmp_path):
    events, _ = _drive(monkeypatch, tmp_path, [hb(), hb(pid=7, main_loop_tick=NOW - 700)], [True, True])
    assert events == ["kill 7", "launch"]


def test_a_user_quit_no_longer_disarms_unattended_mode(monkeypatch, tmp_path):
    """The old contract -- a clean exit ends the watchdog -- was the R2 bug.

    One deliberate quit (a human at the window, yes, but also an updater, an
    antivirus, a scripted ``taskkill`` without ``/F``) ended unattended mode
    for the rest of the session: the watchdog exited 0, no restart policy
    fires on success, and nothing started eCan again until the next logon.
    It goes quiet instead, and relaunches once the hold has passed --
    ``test_watchdog_quit_and_pause.py`` drives that part.
    """
    events, rc = _drive(monkeypatch, tmp_path, [hb(), hb(clean_exit=True)], [True, False])
    assert events == [] and rc is None


def test_a_crash_loop_cannot_run_for_a_day(monkeypatch, tmp_path):
    """A build that dies right after every launch, watched for 24 h.

    This is the failure the breaker exists for. The in-memory budget alone
    allowed MAX_RESTARTS relaunches per window and then a pause that refilled
    the budget: 144 launches a day, forever, with each crash report overwriting
    the interesting first one. The persisted breaker has to end it -- a bounded
    ladder of attempts, then one probe per cooldown, then silence.

    The clocks advance here (sleeps move them) because the breaker decides
    *when* the next launch may happen from wall-clock stamps; a frozen clock
    would read as "no time has passed yet", which is the state backoff exists
    to wait out.
    """
    monkeypatch.setattr(wd, "runlogs_dir", lambda: tmp_path)
    monkeypatch.setattr(wd, "_other_instance_running", lambda: None)
    monkeypatch.setattr(wd, "_cpu_seconds", lambda pid: None)
    clock = {"wall": NOW, "mono": 1_000.0}
    stop_at = NOW + 24 * 3600
    launches = []
    pids = iter(range(5_000, 6_000))

    class DeadOnArrival:
        """The instance we started is gone before it writes a heartbeat."""

        def __init__(self):
            self.pid = next(pids)

        def poll(self):
            return 0

    def fake_sleep(sec):
        clock["wall"] += sec
        clock["mono"] += sec

    def fake_read(_p):
        if clock["wall"] >= stop_at:
            raise SystemExit        # the day is over
        return None

    def fake_launch():
        launches.append(clock["wall"])
        return DeadOnArrival()

    monkeypatch.setattr(wd, "read_heartbeat", fake_read)
    monkeypatch.setattr(wd, "process_alive", lambda h: False)
    monkeypatch.setattr(wd, "_launch", fake_launch)
    monkeypatch.setattr(wd.time, "sleep", fake_sleep)
    monkeypatch.setattr(wd.time, "time", lambda: clock["wall"])
    monkeypatch.setattr(wd.time, "monotonic", lambda: clock["mono"])
    try:
        wd.run()
    except SystemExit:
        pass

    state = json.loads((tmp_path / "watchdog_breaker.json").read_text(encoding="utf-8"))
    assert state["gave_up"] is True
    assert len(launches) <= 12, launches
    # It gave up long before the day ended: that silence is the whole point.
    assert launches[-1] < stop_at - 3600


def test_switch_creates_and_removes_the_logon_task_without_a_window(monkeypatch, tmp_path):
    from utils import unattended as ua
    calls = []
    monkeypatch.setattr(ua, "_marker", lambda: tmp_path / "unattended.json")
    monkeypatch.setattr(ua, "ensure_watchdog_running", lambda: calls.append("ensure"))
    monkeypatch.setattr(ua, "_stop_watchdog", lambda: calls.append("stop"))

    class R:
        returncode = 0
        stdout = stderr = ""

    def fake_run(cmd, **kw):
        calls.append((cmd[1], kw.get("creationflags")))
        return R()

    monkeypatch.setattr(ua.subprocess, "run", fake_run)
    monkeypatch.setattr(ua.sys, "platform", "win32")
    on = ua.set_enabled(True)
    assert on["enabled"] and on["logon_task"] and ua.is_enabled()
    assert ("/Create", ua._NO_WINDOW) in calls and "ensure" in calls
    ua.set_enabled(False)
    assert not ua.is_enabled() and ("/Delete", ua._NO_WINDOW) in calls and "stop" in calls


# --------------------------------------------------------------------------
# P1-3: the hang detector must not switch itself off when another component
# owns the phase (utils/memory_monitor.py writes "memory:*" for the rest of
# the session).
# --------------------------------------------------------------------------

def test_a_phase_owned_by_another_component_still_hangs():
    beat = hb(main_loop_tick=NOW - 700, phase="memory:protect_rss_3000mb")
    assert wd.assess(beat, NOW, alive=True) == "hung"


def test_detail_is_reported_without_moving_the_phase():
    from utils import crash_boundary as cb
    cb.set_crash_boundary_phase("main_loop:running")
    cb.set_crash_boundary_detail("memory:protect_rss_3000mb")
    assert cb.get_crash_boundary_phase() == "main_loop:running"
    assert cb.get_crash_boundary_detail() == "memory:protect_rss_3000mb"


# --------------------------------------------------------------------------
# P0-1: eCan starts the watchdog, so the watchdog is in eCan's child list.
# Killing "the children of eCan" must never include the killer itself.
# --------------------------------------------------------------------------

def test_kill_refuses_to_kill_itself():
    import os
    wd._kill(os.getpid())          # must return without raising ...
    assert os.getpid() > 0         # ... and without taking us down
    wd._kill(0)                    # and a nonsense pid is a no-op


def test_kill_skips_its_own_pid_in_the_child_list(monkeypatch):
    import os
    import psutil
    killed = []

    class Fake:
        def __init__(self, pid, children=()):
            self.pid = pid
            self._children = list(children)

        def children(self, recursive=False):
            return self._children

        def kill(self):
            killed.append(self.pid)

    me = Fake(os.getpid())
    other = Fake(999_999)
    parent = Fake(4242, [me, other])
    monkeypatch.setattr(psutil, "Process", lambda pid: parent)
    wd._kill(4242)
    # Children first, then the target itself -- and never our own pid, which
    # is the entry that used to take the watchdog down mid-kill.
    assert killed == [999_999, 4242]


# --------------------------------------------------------------------------
# P0-3: a launch is not a restart. A fresh instance needs tens of seconds
# before it writes its first heartbeat, and the old heartbeat still describes
# the process it replaced -- charging that against the crash budget spent it
# on four launches of an app that was starting correctly, and then went blind
# for the whole RESTART_WINDOW_SEC pause.
# --------------------------------------------------------------------------

class _Child:
    """Stand-in for the Popen of an eCan instance the watchdog started."""

    def __init__(self, pid: int, exit_after=None):
        self.pid = pid
        self._exit_after = exit_after
        self._polls = 0

    def poll(self):
        self._polls += 1
        if self._exit_after is not None and self._polls >= self._exit_after:
            return 0
        return None


def _drive_child(monkeypatch, tmp_path, steps):
    """Run the real loop with ``_launch`` returning a live Popen handle.

    ``steps`` holds one ``(beat, alive, wall, mono)`` per poll. The clocks are
    looked up by *poll index* rather than popped off a queue: the module under
    test imports the very same ``time`` module object, so every log record
    (and anything else in-process) would otherwise eat the scripted values.
    """
    monkeypatch.setattr(wd, "runlogs_dir", lambda: tmp_path)
    events = []
    idx = {"i": 0}
    child = _Child(4242)

    def at(i):
        return steps[min(max(i, 0), len(steps) - 1)]

    def fake_read(_p):
        if idx["i"] >= len(steps):
            raise SystemExit
        beat = steps[idx["i"]][0]
        idx["i"] += 1
        return beat

    def fake_launch():
        events.append("launch")
        return child

    monkeypatch.setattr(wd, "read_heartbeat", fake_read)
    monkeypatch.setattr(wd, "process_alive", lambda h: at(idx["i"] - 1)[1])
    monkeypatch.setattr(wd, "_launch", fake_launch)
    monkeypatch.setattr(wd, "_kill", lambda pid: events.append(f"kill {pid}"))
    # Same reason as _drive(): never look at the real process table.
    monkeypatch.setattr(wd, "_other_instance_running", lambda: None)
    monkeypatch.setattr(wd, "_cpu_seconds", lambda pid: 0.0)
    monkeypatch.setattr(wd.time, "sleep", lambda s: None)
    # time.time() is read at the top of the poll, before read_heartbeat(), so
    # it still sees the poll that is about to be read; monotonic moves in
    # lockstep unless a test wants a gap between the two clocks.
    monkeypatch.setattr(wd.time, "time", lambda: at(idx["i"])[2])
    monkeypatch.setattr(wd.time, "monotonic", lambda: at(idx["i"])[3])
    try:
        rc = wd.run()
    except SystemExit:
        rc = None
    return events, rc


def test_a_booting_instance_is_not_launched_again(monkeypatch, tmp_path):
    """Many polls with no heartbeat yet: exactly one launch."""
    steps = [(None, False, NOW + 15 * i, 15.0 * i) for i in range(6)]
    events, _ = _drive_child(monkeypatch, tmp_path, steps)
    assert events == ["launch"]


def test_a_child_that_never_writes_a_heartbeat_is_killed_and_counted(monkeypatch, tmp_path):
    """The startup budget runs out in STARTUP_TIMEOUT_SEC instead of leaving
    the watchdog blind for as long as the heartbeat stays missing."""
    late = wd.STARTUP_TIMEOUT_SEC + 100
    steps = [(None, False, NOW, 0.0), (None, False, NOW + late, late)]
    events, _ = _drive_child(monkeypatch, tmp_path, steps)
    assert events[:2] == ["launch", "kill 4242"]


def test_a_started_instance_that_reports_in_keeps_its_place(monkeypatch, tmp_path):
    """Once the new instance writes its own heartbeat, normal rules apply."""
    steps = [(None, False, NOW, 0.0),
             (hb(pid=4242), True, NOW + 15, 15.0),
             (hb(pid=4242), True, NOW + 30, 30.0)]
    events, _ = _drive_child(monkeypatch, tmp_path, steps)
    assert events == ["launch"]


# --------------------------------------------------------------------------
# P1-1: waking from sleep ages the heartbeat by hours. That is not a freeze.
# --------------------------------------------------------------------------

def test_a_wall_clock_jump_does_not_kill_the_app(monkeypatch, tmp_path):
    steps = [(hb(), True, NOW, 100.0), (hb(), True, NOW + 7200, 115.0)]
    events, _ = _drive_child(monkeypatch, tmp_path, steps)
    assert events == []


def test_a_stale_heartbeat_without_a_clock_jump_is_still_killed(monkeypatch, tmp_path):
    steps = [(hb(), True, NOW, 100.0), (hb(), True, NOW + 200, 300.0)]
    events, _ = _drive_child(monkeypatch, tmp_path, steps)
    assert "kill 1" in events


# --------------------------------------------------------------------------
# P1-4: an expired lease is a statement about a *shutdown that finished*.
# --------------------------------------------------------------------------

def _expired_lease(tmp_path, pid=1):
    (tmp_path / "exit_intent.json").write_text(json.dumps({
        "reason": "user_exit", "at": NOW - 1000, "grace_s": 120, "pid": pid,
    }), encoding="utf-8")


def test_an_expired_lease_with_a_dead_process_does_not_end_unattended_mode(monkeypatch, tmp_path):
    """A finished deliberate shutdown used to `return 0` here as well.

    Same disarmament as the clean exit above, reached by a slower route: a
    teardown that outlived its lease, then this branch, then nothing watching
    for the rest of the session. It holds off instead.
    """
    _expired_lease(tmp_path)
    events, rc = _drive_child(monkeypatch, tmp_path, [(hb(), False, NOW, 0.0)])
    assert events == [] and rc is None


def test_an_expired_lease_with_a_live_process_keeps_watching(monkeypatch, tmp_path):
    """A slow shutdown must not end unattended mode for the session: the app
    is still there, so the watchdog keeps watching instead of exiting."""
    _expired_lease(tmp_path)
    steps = [(hb(), True, NOW, 0.0), (hb(), True, NOW + 15, 15.0)]
    events, rc = _drive_child(monkeypatch, tmp_path, steps)
    assert events == [] and rc is None


# --------------------------------------------------------------------------
# The logon task name is per build, and a recycled pid is not a watchdog.
# --------------------------------------------------------------------------

def test_logon_task_name_follows_the_app_name():
    from utils import unattended as ua
    from config.constants import APP_NAME
    assert ua.task_name() == f"{APP_NAME} Unattended"


def test_cleanup_also_removes_the_legacy_logon_task(monkeypatch):
    from utils import unattended as ua
    deleted = []
    monkeypatch.setattr(ua, "_schtasks", lambda args: deleted.append(args[2]))
    ua._delete_logon_task()
    assert ua.LEGACY_TASK_NAME in deleted


def test_a_recycled_pid_is_not_a_running_watchdog(monkeypatch, tmp_path):
    import psutil
    from utils import unattended as ua

    class Proc:
        def create_time(self):
            return 5_000.0

        def cmdline(self):
            return ["python", "main.py", "--watchdog"]

    monkeypatch.setattr(wd, "runlogs_dir", lambda: tmp_path)
    monkeypatch.setattr(psutil, "pid_exists", lambda pid: True)
    monkeypatch.setattr(psutil, "Process", lambda pid: Proc())

    # Same pid, different process: the lock file's fingerprint is what tells
    # them apart. Reporting a watchdog here would stop ensure_watchdog_running
    # from ever starting one.
    monkeypatch.setattr(wd, "_read_lock_identity", lambda _p: (1234, 1_000.0))
    assert ua._watchdog_pid() is None

    monkeypatch.setattr(wd, "_read_lock_identity", lambda _p: (1234, 5_000.0))
    assert ua._watchdog_pid() == 1234


def _seed_loop_errors(tmp_path, n):
    from utils import watchdog_breaker as wb
    st = wb.new_state()
    for _ in range(n):
        st = wb.note_loop_error(st)
    (tmp_path / "watchdog_breaker.json").write_text(json.dumps(st), encoding="utf-8")


def test_a_watchdog_that_cannot_supervise_stands_down_for_good(monkeypatch, tmp_path):
    """Every restart policy we write is rate-limited but not counted.

    A watchdog with a bug that always dies inside a minute would therefore be
    relaunched by launchd / systemd / Task Scheduler every five minutes, for
    ever -- the same failure one level down. After MAX_LOOP_ERROR_EXITS it has
    to exit cleanly instead: exit 0 is "success" for every one of those
    policies, which ends the loop without needing them to be smarter.
    """
    from utils import watchdog_breaker as wb
    _seed_loop_errors(tmp_path, wd.MAX_LOOP_ERROR_EXITS)
    monkeypatch.setattr(wd, "runlogs_dir", lambda: tmp_path)
    monkeypatch.setattr(wd, "_launch", lambda: pytest.fail("relaunched eCan anyway"))
    assert wd.run() == 0
    # The count stays where it was: standing down is not another failure, and a
    # human re-arming the switch (which resets the breaker) is what clears it.
    streak = wb.load(tmp_path / "watchdog_breaker.json")["loop_error_streak"]
    assert streak == wd.MAX_LOOP_ERROR_EXITS


def test_a_loop_that_cannot_poll_exits_with_a_restartable_code(monkeypatch, tmp_path):
    from utils import watchdog_breaker as wb

    def unreadable(_path):
        raise RuntimeError("the log directory went away")

    monkeypatch.setattr(wd, "runlogs_dir", lambda: tmp_path)
    monkeypatch.setattr(wd, "read_heartbeat", unreadable)
    monkeypatch.setattr(wd.time, "sleep", lambda _s: None)
    # 3 is distinguishable from 0 on purpose: a restart policy may relaunch a
    # watchdog that failed, and must not relaunch one that stood down.
    assert wd.run() == 3
    assert wb.load(tmp_path / "watchdog_breaker.json")["loop_error_streak"] == 1


def _broken_run(monkeypatch, tmp_path, where):
    """Make one poll raise *after* the round has started polling."""
    monkeypatch.setattr(wd, "runlogs_dir", lambda: tmp_path)
    monkeypatch.setattr(wd, "_acquire_singleton", lambda _p: True)
    monkeypatch.setattr(wd, "read_heartbeat", lambda _p: None)
    monkeypatch.setattr(wd, "_other_instance_running", where)
    monkeypatch.setattr(wd.time, "sleep", lambda _s: None)


def _boom(*_a, **_kw):
    raise RuntimeError("psutil is unhappy")


def test_a_failure_late_in_the_round_still_reaches_the_loop_cap(monkeypatch, tmp_path):
    """Regression: both loop-error counters used to be cleared at the *top* of
    a round. A build that raises after that point -- deciding whether to kill,
    launching, walking psutil -- cleared its own count every time, so the
    20-error exit never happened and the watchdog span at full speed for ever.
    """
    from utils import watchdog_breaker as wb
    _broken_run(monkeypatch, tmp_path, _boom)
    assert wd.run() == 3
    assert wb.load(tmp_path / "watchdog_breaker.json")["loop_error_streak"] == 1


def test_three_failing_runs_end_unattended_mode_for_good(monkeypatch, tmp_path):
    """The platform's restart policy is rate-limited but not counted, so the
    only way out of "restart me, I crash on start" is for the watchdog to stop
    asking: the third such run exits 0, which every policy reads as success.
    """
    from utils import watchdog_breaker as wb
    _broken_run(monkeypatch, tmp_path, _boom)
    for n in range(1, wd.MAX_LOOP_ERROR_EXITS + 1):
        assert wd.run() == 3, "run %d should still ask to be restarted" % n
        assert wb.load(tmp_path / "watchdog_breaker.json")["loop_error_streak"] == n
    # Restarted once more by launchd / systemd / Task Scheduler: it declines.
    assert wd.run() == 0
