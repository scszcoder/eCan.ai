"""Keep eCan running on an unattended PC: start it, and relaunch it when it
crashes or hangs.

Runs as its own small process (``eCan.exe --watchdog``, or
``python main.py --watchdog`` in dev), started by the "unattended" logon task
(utils/unattended.py) and by eCan itself when unattended mode is on. It reads
the heartbeat eCan writes every 5 s (utils/crash_boundary.py,
runlogs/process_heartbeat.json):

- process gone and no clean exit recorded  -> crashed: relaunch
- process alive but heartbeat not updated for HEARTBEAT_STALE_SEC -> frozen:
  kill, relaunch
- main event loop silent for LOOP_STALE_SEC after startup finished -> hung:
  kill, relaunch
- clean exit recorded (the user quit)      -> quiet for QUIT_HOLD_SEC, then start it
                                             again (unattended mode must not be
                                             disarmed by one deliberate quit)

Within one watchdog lifetime, at most MAX_RESTARTS relaunches per
RESTART_WINDOW_SEC. Across lifetimes -- and this is the part that actually
stops a crash loop -- the persistent circuit breaker in
utils/watchdog_breaker.py keeps the score on disk: escalating backoff while
the app keeps failing, then no relaunches at all (with a CRITICAL log line and
a status the Settings UI shows) once the build has proved it cannot stay up.
Logs to runlogs/watchdog.log (never eCan.log, which the app rotates).

Everything here is platform-neutral -- psutil for process identity, an
advisory file lock (utils/file_lock.py) for the singleton, and per-platform
detach flags in _launch() -- because the app ships for Windows, macOS and
Linux and the watchdog is started by whatever autostart mechanism that
platform has (utils/unattended.py).
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from utils import watchdog_breaker
from utils.exit_intent import lease_is_active, read_exit_lease

POLL_SEC = 15
HEARTBEAT_STALE_SEC = 120
LOOP_STALE_SEC = 600
MIN_UPTIME_FOR_HANG_SEC = 900
MAX_RESTARTS = 3
RESTART_WINDOW_SEC = 1800
LAUNCH_GRACE_SEC = 120
#: How long a freshly launched eCan may take to write its *own* heartbeat
#: before the launch is counted as a failure. Must cover the whole startup
#: path -- report_previous_process_boundary() runs two PowerShell queries and
#: a WER scan before start_crash_boundary_heartbeat() is even reached -- which
#: on a busy kiosk is tens of seconds.
STARTUP_TIMEOUT_SEC = 300
#: How far apart two create-times may be and still count as the same
#: process. Mirrors utils/worker_boot.py and utils/crash_boundary.py --
#: comfortably wider than the clock's resolution, far narrower than any
#: real process lifetime.
CREATE_TIME_TOLERANCE_S = 2.0
#: A wall-clock jump larger than this, measured against the monotonic clock,
#: means the machine slept or the clock was changed between two polls. No
#: verdict may be drawn from a heartbeat that "aged" while the machine was
#: suspended: eCan was asleep too, not frozen.
CLOCK_JUMP_TOLERANCE_S = 30.0
#: How many polls a stale heartbeat may be excused while the process is
#: demonstrably burning CPU. A frozen app burns nothing; a healthy app whose
#: heartbeat file is temporarily unwritable (a Windows sharing violation
#: against the reader) does. Bounded, so a real hang is still killed.
FROZEN_DEFER_MAX = 8
#: CPU-seconds that count as "making progress" between two polls.
CPU_PROGRESS_MIN_SEC = 0.2
#: Backoff floor after a launch that could not even be started (missing exe,
#: no permission), so a broken installation does not retry every POLL_SEC. The
#: breaker's own backoff takes over immediately after: a permanent launch
#: failure must not become an every-minute retry for the rest of the day.
LAUNCH_RETRY_BACKOFF_SEC = 60
#: How many consecutive errors the poll loop itself may throw before the
#: watchdog stops. A watchdog that dies from an unexpected exception leaves the
#: machine unwatched, so a single bad poll is logged and retried; only a
#: genuinely broken loop (20 polls in a row failing) exits -- with a distinct
#: code, so a restart policy can tell it from the "user quit" exit.
MAX_LOOP_ERRORS = 20
LOOP_ERROR_BACKOFF_SEC = 30
#: How many such exits in a row are allowed before the watchdog stops even
#: trying to be a supervisor. Every restart policy we install (launchd
#: KeepAlive, systemd ``Restart=on-failure``, Task Scheduler
#: RestartOnFailure) would otherwise restart a *buggy watchdog* every five
#: minutes for ever. Three attempts is enough for a transient cause (a disk
#: that came back, a psutil import race) and short enough that a broken build
#: stops within ~15 min -- and it stops by exiting 0, which every policy reads
#: as success.
MAX_LOOP_ERROR_EXITS = 3
#: Minimum spacing between repeated "the breaker is holding us back" log lines,
#: so a 6 h cooldown writes a handful of lines instead of 1440.
HOLD_LOG_INTERVAL_SEC = 300
#: How long the watchdog stays quiet after eCan was shut down *on purpose*
#: (a clean exit, or a shutdown lease that expired with the process gone).
#:
#: It used to exit at that point, and the exit itself was the bug: a clean
#: exit is not always the human in front of the screen. An updater, antivirus,
#: or a scripted ``taskkill`` without ``/F`` all end the app cleanly with a
#: lease, and one such event silently ended unattended mode for the rest of
#: the session -- nothing on the machine would ever start eCan again until the
#: next logon, and the only trace was one line in watchdog.log. The trade is
#: the other way round now: respect the quit (no relaunch for this long, so a
#: human closing the window is never fought), then resume supervising. Turning
#: the Settings switch off still stops the watchdog for good, and an uninstall
#: is a permanent lease that still wins.
QUIT_HOLD_SEC = 1800

_log = logging.getLogger("ecan.watchdog")


def runlogs_dir() -> Path:
    try:
        from config.app_info import app_info
        p = Path(app_info.appdata_path) / "runlogs"
    except Exception:
        p = Path.cwd() / "runlogs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def app_command() -> list:
    """How to start eCan itself, on every platform this app ships for.

    * frozen, launched from an AppImage: ``sys.executable`` points *inside*
      the mounted squashfs image, and that mount is gone the moment the app
      exits -- relaunching that path fails every single time, silently, which
      is the worst possible failure for a watchdog. ``$APPIMAGE`` is the
      stable path to the file the user actually has.
    * frozen, otherwise (Windows exe, macOS bundle): ``sys.executable`` is the
      bundled executable and stays valid.
    * source tree: the interpreter plus main.py.
    """
    if getattr(sys, "frozen", False):
        appimage = os.environ.get("APPIMAGE")
        if appimage and os.path.exists(appimage):
            return [appimage]
        return [sys.executable]
    return [sys.executable, str(Path(__file__).resolve().parent.parent / "main.py")]


def read_heartbeat(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def process_alive(hb: dict) -> bool:
    import psutil
    try:
        p = psutil.Process(int(hb.get("pid") or 0))
        ct = float(hb.get("process_create_time") or 0)
        return p.is_running() and (not ct or abs(p.create_time() - ct) < 2)
    except Exception:
        return False


def should_honour_lease(hb: Optional[dict], now: float,
                        lease: Optional[dict] = None) -> bool:
    """Whether *lease* describes the process this watchdog is watching.

    A lease only means something for the process that wrote it. Two guards
    keep a leftover lease from silencing the watchdog:

    * the lease's ``pid`` must match the heartbeat's ``pid`` — otherwise it
      belongs to a different (already dead) process;
    * the heartbeat must be recent — a stale heartbeat means the app was not
      running a moment ago, so the lease cannot be about it.

    Without this, the lease left in the appdata folder by the previous
    session would keep the watchdog from starting the app at logon.
    """
    if not lease:
        return False
    if not hb:
        # No heartbeat: there is no process we could be watching, so a normal
        # lease tells us nothing. A permanent lease is handled separately
        # (it is the uninstall marker, which must always win).
        return False
    lease_pid = int(lease.get("pid") or 0)
    if lease_pid:
        hb_pid = int(hb.get("pid") or 0)
        if hb_pid and hb_pid != lease_pid:
            return False
    updated_at = float(hb.get("updated_at") or 0)
    if updated_at and now - updated_at > HEARTBEAT_STALE_SEC:
        return False
    return True


def is_permanent_lease(lease: Optional[dict]) -> bool:
    """True for a lease that never expires (the uninstall marker)."""
    if not lease:
        return False
    try:
        return float(lease.get("grace_s")) == float("inf")
    except Exception:
        return False


def assess(hb: Optional[dict], now: float, alive: bool, exiting: bool = False) -> str:
    """'ok' | 'not_running' | 'crashed' | 'quit' | 'exiting' | 'frozen' | 'hung'.

    ``exiting`` means the app took a shutdown lease (utils/exit_intent.py):
    it is on its way out on purpose. While the lease is active we must neither
    relaunch the app nor kill it as hung, not even while its event loop is
    already winding down.

    A recorded *clean exit* still wins: that means the shutdown already
    finished, so the watchdog should stand down for good rather than keep
    watching.
    """
    if not hb:
        return "exiting" if exiting else "not_running"
    if not alive:
        if hb.get("clean_exit"):
            return "quit"
        return "exiting" if exiting else "crashed"
    if exiting:
        return "exiting"
    if now - float(hb.get("updated_at") or 0) > HEARTBEAT_STALE_SEC:
        return "frozen"
    tick = hb.get("main_loop_tick")
    phase = str(hb.get("phase") or "")
    # "not startup" rather than "startswith(main_loop)": any other component
    # can own the phase at the moment of the hang (utils/memory_monitor.py
    # writes "memory:*" for the rest of the session), and a phase that has
    # moved on must not switch the hang detector off for good.
    if (tick and not phase.startswith("startup")
            and now - float(hb.get("started_at") or now) > MIN_UPTIME_FOR_HANG_SEC
            and now - float(tick) > LOOP_STALE_SEC):
        return "hung"
    return "ok"


def _kill(pid: int) -> None:
    """Kill *pid* and its descendants -- but never this watchdog itself.

    eCan normally starts the watchdog (utils/unattended.py::
    ensure_watchdog_running), which makes the watchdog a *child* of eCan. The
    obvious ``for c in p.children(recursive=True): c.kill()`` therefore finds
    the caller in the list and kills it first: the watchdog dies mid-kill,
    ``p.kill()`` never runs, and the frozen app stays frozen forever with
    nobody left to restart it. Excluding our own pid (and refusing to kill
    ourselves outright) is what makes the rest of this file mean anything.
    """
    import psutil
    me = os.getpid()
    try:
        target = int(pid or 0)
    except Exception:
        target = 0
    if target <= 0 or target == me:
        _log.warning(f"refusing to kill pid {pid} (that is this watchdog)")
        return
    try:
        p = psutil.Process(target)
    except Exception as e:
        _log.warning(f"could not kill pid {pid}: {e}")
        return
    children = []
    try:
        children = [c for c in p.children(recursive=True) if c.pid != me]
    except Exception:
        pass
    for c in children:
        try:
            c.kill()
        except Exception:
            pass
    try:
        p.kill()
    except Exception as e:
        _log.warning(f"could not kill pid {pid}: {e}")


def _launch():
    """Start eCan and return its ``Popen``.

    The handle matters: without it the loop cannot tell "the instance I
    started 15 s ago is still booting" from "the app crashed again", and it
    spends a whole crash budget relaunching an app that is already starting.
    """
    env = dict(os.environ)
    env["ECAN_LAUNCHED_BY_WATCHDOG"] = "1"
    kwargs = {"env": env, "close_fds": True, "stdout": subprocess.DEVNULL,
              "stderr": subprocess.DEVNULL, "stdin": subprocess.DEVNULL}
    if sys.platform == "win32":
        # A new process group plus DETACHED_PROCESS: closing the console the
        # watchdog was started from (or a Ctrl-Break aimed at it) must not
        # take eCan down with it.
        kwargs["creationflags"] = (subprocess.CREATE_NEW_PROCESS_GROUP
                                   | getattr(subprocess, "DETACHED_PROCESS", 0x8))
    else:
        # POSIX equivalent: a new session, so SIGHUP/SIGINT sent to the
        # watchdog's process group (a logout, a closed terminal) does not
        # propagate to the app we just started.
        kwargs["start_new_session"] = True
    return subprocess.Popen(app_command(), **kwargs)


#: The watchdog's singleton lock, kept alive for the whole process
#: lifetime. An advisory OS lock is held by the *open file handle*, so
#: releasing it (or letting the object be collected) would drop the
#: lock and let a second watchdog start. Module-level on purpose.
_WATCHDOG_LOCK = None


def _current_create_time():
    """When this exact process started, per the OS. None when unknown."""
    try:
        import psutil
        return float(psutil.Process(os.getpid()).create_time())
    except Exception:
        return None


def _lock_identity(pid: int) -> dict:
    """The identity stored next to the watchdog lock.

    A pid alone is not an identity: the OS recycles pids, and on a busy
    desktop it recycles them fast. A lock file left behind by a crashed
    watchdog whose pid has since been handed to some unrelated process
    would make the next watchdog believe "another watchdog is running"
    and exit -- leaving the machine unwatched. The create-time
    fingerprint is what tells the two apart, and it is the same pairing
    the rest of the keepalive stack already uses
    (utils/worker_boot.py, utils/crash_boundary.py).
    """
    create_time = None
    try:
        import psutil
        create_time = float(psutil.Process(int(pid)).create_time())
    except Exception:
        create_time = None
    return {"pid": int(pid), "create_time": create_time}


def _read_lock_identity(lock: Path) -> tuple:
    """Read ``(pid, create_time)`` from the lock file.

    Returns ``(0, None)`` when the file is missing or unreadable. A
    legacy lock file (a bare pid, written by an older build) is read as
    ``(pid, None)`` -- pid known, fingerprint unknown.

    The file may carry a leading lock byte (see utils/file_lock.py), so
    the byte is stripped before parsing.
    """
    try:
        raw = lock.read_bytes()
    except Exception:
        return 0, None
    text = raw.lstrip(b"\x00").decode("utf-8", errors="replace").strip()
    if not text:
        return 0, None
    try:
        data = json.loads(text)
    except Exception:
        data = None
    if isinstance(data, dict):
        try:
            pid = int(data.get("pid") or 0)
        except Exception:
            return 0, None
        ct = data.get("create_time")
        try:
            ct = float(ct) if ct is not None else None
        except Exception:
            ct = None
        return pid, ct
    # Legacy format: the file held a bare pid.
    try:
        return int(text), None
    except Exception:
        return 0, None


def _is_same_process(pid: int, create_time) -> bool:
    """Is the process recorded in the lock file still that same process?

    True when the pid matches *and* the create-time matches. False when
    the pid is dead, and false when the fingerprint proves it is a
    *different* generation that merely inherited the pid.

    When the fingerprint is unknown on either side the answer is None:
    the caller cannot tell, and must not guess. None is returned rather
    than True/False so that "cannot tell" stays distinct from "dead" --
    the same distinction utils/worker_boot.py draws.

    Note that a pid match on its own proves nothing, *including* a match
    against our own pid: the OS can hand our pid to a dead generation
    while we are running, and the file we are reading may have been
    written by that generation. The fingerprint is what separates them,
    so it is compared even when the pid is our own.
    """
    try:
        pid = int(pid)
    except Exception:
        return False
    if pid <= 0:
        return False
    try:
        import psutil
    except Exception:
        return None
    try:
        if pid == os.getpid():
            mine = _current_create_time()
        else:
            mine = float(psutil.Process(pid).create_time())
    except psutil.NoSuchProcess:
        return False
    except Exception:
        return None
    if mine is None:
        return None
    if create_time is None:
        return None            # no fingerprint to compare against
    try:
        return abs(float(mine) - float(create_time)) <= CREATE_TIME_TOLERANCE_S
    except Exception:
        return None


def _acquire_singleton(lock: Path) -> bool:
    """Become the one watchdog, or report that another one already is.

    Two layers, in order of authority:

    1. **An advisory OS lock.** This is the real guarantee. It is held
       by the kernel, so it is released automatically when the holder
       dies -- a crashed watchdog can never wedge the machine, and two
       watchdogs starting at the same instant cannot both win.
    2. **The identity in the file.** Informational, and the fallback when
       the filesystem cannot lock at all. It records ``(pid,
       create_time)`` so a recycled pid is not mistaken for a live
       watchdog.

    The lock handle is stored module-level: an advisory lock lives on the
    open file handle, so the handle must stay open for as long as the
    watchdog runs.
    """
    global _WATCHDOG_LOCK

    from utils import file_lock as fl

    handle = fl.FileLock(lock)
    got = handle.acquire(timeout=1.0)
    if got is True:
        # We hold the OS lock: nobody else can. Record who we are.
        handle.write_payload(json.dumps(_lock_identity(os.getpid())))
        _WATCHDOG_LOCK = handle      # keep it open for the process lifetime
        return True

    if got is None:
        # Advisory locking is unavailable here (an exotic filesystem, a
        # network share). Fall back to the identity check, which is what
        # this code always did -- and is better than it was, because it
        # now compares the create-time and not just the pid.
        pid, create_time = _read_lock_identity(lock)
        if pid and pid != os.getpid():
            same = _is_same_process(pid, create_time)
            if same is True:
                return False
            if same is None and _pid_alive(pid):
                # Cannot prove it is a different process, and the pid is
                # in use: assume the worst (two watchdogs) and stand down.
                return False
        try:
            lock.write_text(json.dumps(_lock_identity(os.getpid())),
                            encoding="utf-8")
        except Exception:
            pass
        return True

    # The OS says somebody else holds the lock: a watchdog is running.
    return False


def _pid_alive(pid: int) -> bool:
    """Is *pid* in use by any process? Used only where the fingerprint
    could not be established."""
    try:
        import psutil
        return bool(psutil.pid_exists(int(pid)))
    except Exception:
        return False


def _release_singleton() -> None:
    """Drop the watchdog's singleton lock.

    Not needed in production -- the kernel drops the lock when the
    process exits. It exists so a test can hand the lock back.
    """
    global _WATCHDOG_LOCK
    handle, _WATCHDOG_LOCK = _WATCHDOG_LOCK, None
    if handle is not None:
        handle.release()


def _clock_jumped(prev_wall, prev_mono, wall, mono) -> bool:
    """Did the wall clock move differently from the monotonic clock?

    Heartbeat ages are wall-clock (that is what the file stores), but a PC
    that slept two hours also ages the heartbeat by two hours -- eCan was
    suspended with the machine, not frozen. Comparing the two clocks tells
    "two hours passed" from "two hours were skipped"; without it, waking
    from sleep makes this loop kill a perfectly healthy app.
    """
    if prev_wall is None or prev_mono is None:
        return False
    try:
        return abs((float(wall) - prev_wall) - (float(mono) - prev_mono)) > CLOCK_JUMP_TOLERANCE_S
    except Exception:
        return False


def _cpu_seconds(pid: int):
    """Total CPU seconds *pid* has burned so far, or None when unreadable."""
    try:
        import psutil
        t = psutil.Process(int(pid)).cpu_times()
        return float(t.user) + float(t.system)
    except Exception:
        return None

def _launch_matches() -> dict:
    """What identifies "an eCan started from this installation".

    Split out so the test suite (and a future packaging variant) can reason
    about the match without spawning anything. In dev the interpreter name is
    useless -- every other Python process on the box would match -- so the
    script path is the identity; in a frozen build the executable's own name
    is.
    """
    cmd = app_command()
    script = str((Path(__file__).resolve().parent.parent / "main.py").resolve())
    return {"exe": Path(str(cmd[0])).name.lower(),
            "script": script if not getattr(sys, "frozen", False) else "",
            "frozen": bool(getattr(sys, "frozen", False))}


def _other_instance_running() -> Optional[int]:
    """pid of an eCan that is already up and not this watchdog, else None.

    The heartbeat is the watchdog's only view of the app, and it can be
    missing while the app is very much alive: the file was deleted, the
    directory was moved, eCan was started by hand from a shell that never
    wrote one, or an *earlier* launch is still initialising. Launching into
    that state puts a second window (and a second login) on the machine, or
    makes two instances fight over the same ports and lock files -- a failure
    mode that looks like "the watchdog keeps restarting eCan" from the
    outside. One process scan per launch decision is cheap; the launch itself
    is not.
    """
    try:
        import psutil
    except Exception:
        return None
    match = _launch_matches()
    me = os.getpid()
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            info = proc.info or {}
            pid = int(info.get("pid") or 0)
            if pid <= 0 or pid == me:
                continue
            cmdline = " ".join(info.get("cmdline") or [])
            if "--watchdog" in cmdline:
                continue                      # another watchdog, not the app
            if match["frozen"]:
                if (info.get("name") or "").lower() == match["exe"]:
                    return pid
            elif match["script"] and match["script"] in cmdline.replace("\\", "/"):
                return pid
        except Exception:
            continue
    return None

def _heartbeat_is_from(hb: Optional[dict], pid: int, now: float) -> bool:
    """Is *hb* a fresh heartbeat written by *pid*?"""
    if not hb:
        return False
    try:
        return (int(hb.get("pid") or 0) == int(pid)
                and now - float(hb.get("updated_at") or 0) <= HEARTBEAT_STALE_SEC)
    except Exception:
        return False


def _log_breaker(breaker) -> None:
    """Say out loud what the persisted breaker state means for this run.

    A watchdog that starts with the circuit already open must not look like a
    healthy one in the log: the operator's first question after a bad night is
    "did it try to recover eCan, and why did it stop?".
    """
    info = watchdog_breaker.summary(breaker)
    if info["gave_up"]:
        _log.critical(f"crash-loop breaker gave up at {info['gave_up_iso']} after "
                      f"{info['consecutive_failures']} failures in a row "
                      f"(last: {info['last_reason']}); watching eCan but not relaunching it")
    elif info["tripped"]:
        _log.warning(f"crash-loop breaker is open: {info['consecutive_failures']} failures in a "
                     f"row, cooldown {int(info['cooldown_sec'] // 60)} min, "
                     f"last: {info['last_reason']}")
    elif info["total_failures"]:
        _log.info(f"crash-loop breaker closed; {info['total_failures']} failure(s) on record")


def _bill_failure(billed, breaker, path, now, pid, reason, uptime=0.0, detail=""):
    """Charge one death against the breaker -- once per process.

    ``billed`` is the list of pids this session has already charged. Without it
    the same death counts twice, once when the launch we started exits and once
    when the next poll calls the (stale) heartbeat a crash, and the breaker
    would give up on a build that only died three times.
    """
    try:
        pid = int(pid or 0)
    except Exception:
        pid = 0
    if pid and pid in billed:
        return breaker
    if pid:
        billed.append(pid)
        del billed[:-32]
    state = watchdog_breaker.note_failure(breaker, now, reason, uptime_s=uptime, detail=detail)
    watchdog_breaker.save(path, state)
    return state


def _prove_healthy(breaker, path, hb, now):
    """Close the breaker once an instance has demonstrably stayed up.

    The proof is uptime, not "it is running": a build that dies in 3 s is also
    "running" on the poll right after its launch. HEALTHY_UPTIME_SEC of fresh
    heartbeats is the smallest window that distinguishes the two.
    """
    if not watchdog_breaker.needs_reset(breaker):
        return breaker
    try:
        uptime = now - float(hb.get("started_at") or now)
    except Exception:
        return breaker
    if uptime < watchdog_breaker.HEALTHY_UPTIME_SEC:
        return breaker
    state = watchdog_breaker.note_healthy(breaker, now)
    watchdog_breaker.save(path, state)
    _log.info(f"eCan has been up {int(uptime)}s; the crash-loop history is cleared")
    return state


def _hold_after_quit(quiet_until: float, mono: float, reason: str) -> float:
    """Track the quiet hold that follows a deliberate shutdown.

    Returns the deadline to carry into the next poll: ``mono + QUIT_HOLD_SEC``
    when the hold starts, the unchanged deadline while it lasts, and ``0.0``
    once it is over -- the caller must then resume normal supervision (start
    the app again) instead of exiting.

    Both entry points share it -- a finished clean exit, and a shutdown lease
    that expired with its process gone -- so watchdog.log says the same thing
    either way, and neither of them can quietly disarm unattended mode.
    """
    if quiet_until <= 0:
        _log.info(f"eCan was shut down on purpose ({reason}); not relaunching it for "
                  f"{int(QUIT_HOLD_SEC // 60)} min, then resuming unattended mode "
                  f"(turn the switch off in Settings to stop the watchdog entirely)")
        return mono + QUIT_HOLD_SEC
    if mono < quiet_until:
        return quiet_until
    _log.warning(f"unattended mode resumes: eCan has been closed for "
                 f"{int(QUIT_HOLD_SEC // 60)} min ({reason}); starting it again")
    return 0.0


def run() -> int:
    logs = runlogs_dir()
    from utils.log_redact import scrub  # secrets masked; the watchdog stays light

    class _Redacting(logging.Formatter):
        def format(self, record):
            return scrub(super().format(record))

    # Idempotent on purpose: run() can be entered twice in one process (the test
    # suite does exactly that), and a second RotatingFileHandler would not only
    # print every line twice -- it would hold a second handle on watchdog.log,
    # and then neither handler could roll the file over.
    if not any(getattr(h, "_ecan_watchdog_sink", False) for h in _log.handlers):
        handler = logging.handlers.RotatingFileHandler(
            logs / "watchdog.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8")
        handler.setFormatter(_Redacting("%(asctime)s %(levelname)s %(message)s"))
        handler._ecan_watchdog_sink = True     # marker: never add a second one
        _log.addHandler(handler)
    _log.setLevel(logging.INFO)
    if not _acquire_singleton(logs / "watchdog.lock"):
        _log.info("another watchdog is running; exiting")
        return 0
    hb_path = logs / "process_heartbeat.json"
    breaker_path = logs / "watchdog_breaker.json"
    breaker = watchdog_breaker.load(breaker_path)
    # A watchdog that keeps failing as a *supervisor* must stop being restarted
    # by the platform (see MAX_LOOP_ERROR_EXITS). Checked before anything else,
    # because a build that cannot supervise is what the restart policy is
    # about to relaunch.
    if int(breaker.get("loop_error_streak") or 0) >= MAX_LOOP_ERROR_EXITS:
        _log.critical(
            f"this watchdog failed to poll {breaker.get('loop_error_streak')} times in a "
            f"row; standing down for good instead of letting the restart policy relaunch "
            f"it forever. Unattended mode stays off until the build is fixed and the "
            f"switch is turned off and on again (utils.unattended.reset_watchdog_breaker).")
        return 0
    billed: list = []           # pids whose death is already charged to the breaker
    restarts: list = []         # monotonic stamps of the relaunches in this window
    launched_at = 0.0           # monotonic: a wall-clock jump must not extend it
    child = None                # the eCan process this watchdog started, if any
    child_started_at = 0.0
    last_cpu = None
    frozen_defers = 0
    prev_wall = prev_mono = None
    loop_errors = 0
    hold_logged_at = 0.0
    # monotonic: quiet after a deliberate shutdown (see _hold_after_quit), and
    # the relaunch pause after MAX_RESTARTS in a window. Both are *state* the
    # loop re-checks every POLL_SEC, never a blocking sleep -- a sleeping
    # watchdog is not watching (a quit, an uninstall, or eCan coming back on
    # its own would all wait for the sleep to end).
    quiet_until = 0.0
    pause_until = 0.0
    gave_up_logged = bool(breaker.get("gave_up"))
    _log.info(f"watchdog started (pid {os.getpid()}), watching {hb_path}")
    _log_breaker(breaker)
    first = True
    while True:
        try:
            now = time.time()
            mono = time.monotonic()

            if not gave_up_logged and breaker.get("gave_up"):
                gave_up_logged = True
                _log.critical(
                    f"eCan crashed {breaker.get('consecutive_failures')} times in a row "
                    f"(last: {breaker.get('last_reason')}); the watchdog has stopped relaunching "
                    f"it and will only watch from now on. Fix the build, or reset unattended "
                    f"mode in Settings to give it another chance.")

            jumped = _clock_jumped(prev_wall, prev_mono, now, mono)
            prev_wall, prev_mono = now, mono
            if jumped:
                _log.warning("the wall clock jumped (the machine slept, or the time was "
                             "changed); not judging eCan on this poll")
            hb = read_heartbeat(hb_path)
            alive = bool(hb) and process_alive(hb)
            cpu = _cpu_seconds(int(hb.get("pid") or 0)) if (alive and hb) else None
            progressed = (cpu is not None and last_cpu is not None
                          and cpu - last_cpu >= CPU_PROGRESS_MIN_SEC)
            if cpu is not None:
                last_cpu = cpu

            # A shutdown lease (utils/exit_intent.py) means the app is quitting on
            # purpose. Honour it before anything else, otherwise a teardown that
            # takes longer than POLL_SEC would be misread as a crash and the
            # watchdog would relaunch an app the user just closed.
            lease = read_exit_lease(log_dir=str(logs))
            permanent = is_permanent_lease(lease)
            active = permanent or lease_is_active(lease, now)
            applies = bool(lease) and (permanent or should_honour_lease(hb, now, lease))
            exiting = applies and active
            state = assess(hb, now, alive, exiting=exiting)

            if applies and not active:
                # The lease ran out while still describing the process we watch:
                # the shutdown really was deliberate after all (see the module
                # docstring of utils/exit_intent.py). A lease that is merely *old*
                # cannot get here -- should_honour_lease() requires a fresh
                # heartbeat, so a marker from the previous session is ignored and
                # logon still starts eCan.
                if not alive:
                    # The shutdown was deliberate and it is over. This used to
                    # `return 0` -- "watchdog exiting" -- which is the same
                    # silent disarmament as a clean quit (see QUIT_HOLD_SEC):
                    # one slow teardown that ended here and unattended mode was
                    # over for the session. Hold quiet instead, then resume.
                    if launched_at and mono - launched_at < STARTUP_TIMEOUT_SEC:
                        # We already relaunched the app this lease was about, and
                        # it clears the marker itself on startup
                        # (utils/exit_intent.py::on_startup). Re-reading a lease
                        # we have already acted on must not re-arm the hold, or
                        # the relaunch we just made would be suppressed for
                        # another QUIT_HOLD_SEC and then made a second time.
                        time.sleep(POLL_SEC)
                        continue
                    quiet_until = _hold_after_quit(quiet_until, mono, "exit lease expired")
                    if quiet_until:
                        time.sleep(POLL_SEC)
                        continue
                    # Hold over: fall through to the launch logic below and start
                    # eCan, exactly like the clean-exit path does.
                    state = "not_running"
                else:
                    # Still alive: a *slow* shutdown, not a finished one. Standing
                    # by forever used to be the whole rule here, which left a
                    # half-dead app holding ports and locks with nobody watching.
                    # It is not needed: a teardown that is really wedged stops
                    # writing its heartbeat, and the ordinary "frozen" rule below
                    # then kills and restarts it.
                    _log.info("eCan is still shutting down past its lease; standing by")
                    time.sleep(POLL_SEC)
                    continue

            # Retire the launch this watchdog started last round. Only a launch
            # that is *confirmed* to have failed costs a restart: a fresh instance
            # needs tens of seconds before it writes its first heartbeat, and the
            # old heartbeat still describes the dead process it replaced.
            starting = False
            if child is not None:
                started_pid = child.pid
                if _heartbeat_is_from(hb, started_pid, now):
                    child = None                      # it is running: normal rules apply
                elif child.poll() is not None:
                    child = None
                    if not alive:
                        restarts.append(mono)
                        _log.warning("the eCan instance we started exited before writing a heartbeat")
                        breaker = _bill_failure(billed, breaker, breaker_path, now, started_pid,
                                                "exited_early", uptime=mono - child_started_at,
                                                detail=f"pid {started_pid}")
                elif mono - child_started_at > STARTUP_TIMEOUT_SEC:
                    _log.warning(f"eCan (pid {started_pid}) never wrote a heartbeat in "
                                 f"{int(mono - child_started_at)}s; killing it")
                    _kill(started_pid)
                    child = None
                    restarts.append(mono)
                    breaker = _bill_failure(billed, breaker, breaker_path, now, started_pid,
                                            "no_heartbeat", uptime=mono - child_started_at,
                                            detail=f"pid {started_pid}")
                else:
                    starting = True

            if first:
                first = False
                if not alive and not exiting:
                    # Started at logon (or after eCan was closed): the last heartbeat
                    # may say "clean exit" from the previous shutdown -- start eCan.
                    state = "not_running"
            if state == "quit" and launched_at and mono - launched_at < LAUNCH_GRACE_SEC:
                state = "ok"          # the old heartbeat of a process we just replaced
            if state == "exiting":
                if permanent:
                    # An uninstall marker never expires: the app is gone for good.
                    _log.info("eCan was uninstalled (permanent exit lease); watchdog exiting")
                    return 0
                # Stand by: do not relaunch and do not kill, but keep watching.
                # The lease expires by itself; once it does, the normal clean_exit
                # / crashed logic takes over again.
                _log.info("eCan is shutting down (exit lease); watchdog standing down")
                time.sleep(POLL_SEC)
                continue
            if state == "quit":
                # The app said goodbye properly. Honour that for QUIT_HOLD_SEC
                # (a human closing the window must not be fought), then start
                # it again: exiting here would end unattended mode for the rest
                # of the session, and the quit is not always a human's -- see
                # the QUIT_HOLD_SEC comment.
                quiet_until = _hold_after_quit(quiet_until, mono, "clean exit")
                if quiet_until:
                    time.sleep(POLL_SEC)
                    continue
                state = "not_running"     # the app is gone: relaunch it now
            if state in ("not_running", "crashed", "frozen", "hung"):
                if starting:
                    # We started it ourselves and it is still booting.
                    time.sleep(POLL_SEC)
                    continue
                if jumped:
                    # The heartbeat "aged" while the machine was asleep: that is
                    # not evidence of a freeze. Look again on the next poll.
                    time.sleep(POLL_SEC)
                    continue
                if state == "not_running" and launched_at and mono - launched_at < LAUNCH_GRACE_SEC:
                    time.sleep(POLL_SEC)
                    continue      # still starting up, no heartbeat yet
                if state == "not_running":
                    # The heartbeat says nothing is running -- but the heartbeat is
                    # not the only evidence. Launching a second eCan next to one
                    # that never wrote a heartbeat (a deleted file, a hand-started
                    # instance, an instance still initialising) is how a watchdog
                    # ends up with two windows fighting over the same ports.
                    other = _other_instance_running()
                    if other:
                        _log.warning(f"eCan looks down, but pid {other} is already running from "
                                     f"this installation; not launching a second one")
                        time.sleep(POLL_SEC)
                        continue
                restarts = [t for t in restarts if mono - t < RESTART_WINDOW_SEC]
                if len(restarts) >= MAX_RESTARTS and not pause_until:
                    # A pause, but not a sleep. `time.sleep(RESTART_WINDOW_SEC)`
                    # used to park the supervisor for 30 min: no heartbeat read,
                    # no lease read, no uninstall check, no clock-jump guard --
                    # half an hour in which eCan could come back and die again,
                    # or be uninstalled, with nobody watching. The loop keeps
                    # polling; only the launch is suppressed.
                    pause_until = mono + RESTART_WINDOW_SEC
                    _log.warning(f"{len(restarts)} relaunches in "
                                 f"{RESTART_WINDOW_SEC // 60} min; pausing launches for "
                                 f"{RESTART_WINDOW_SEC // 60} min (still watching)")
                if pause_until:
                    if mono < pause_until:
                        time.sleep(POLL_SEC)
                        continue
                    pause_until = 0.0
                    _log.info("relaunch pause is over")
                # The breaker has the last word: it remembers every failure across
                # watchdog restarts, so the budget the line above just refilled is
                # not a fresh supply of relaunches for a build that cannot start.
                allowed, wait_s = watchdog_breaker.allow_launch(breaker, now)
                if not allowed:
                    if now - hold_logged_at >= HOLD_LOG_INTERVAL_SEC:
                        hold_logged_at = now
                        if wait_s == float("inf"):
                            _log.critical("eCan keeps crashing; the watchdog has given up "
                                          "relaunching it (see watchdog_breaker.json)")
                        else:
                            _log.warning(f"crash loop: not relaunching eCan for another "
                                         f"{int(wait_s // 60) + 1} min "
                                         f"({breaker.get('consecutive_failures')} failures in a row)")
                    time.sleep(POLL_SEC)
                    continue
                if state in ("frozen", "hung") and hb:
                    if progressed and frozen_defers < FROZEN_DEFER_MAX:
                        # A frozen app burns no CPU. One that is still burning CPU
                        # while its heartbeat went stale is not frozen -- most
                        # likely the heartbeat file is momentarily unwritable
                        # (a Windows sharing violation against this very reader).
                        # Killing it would be the outage, not the cure.
                        frozen_defers += 1
                        _log.warning(f"eCan {state} but the process is still working "
                                     f"({cpu:.1f}s cpu); not killing it yet "
                                     f"(defer {frozen_defers}/{FROZEN_DEFER_MAX})")
                        time.sleep(POLL_SEC)
                        continue
                    frozen_defers = 0
                    _log.warning(f"eCan {state} (pid {hb.get('pid')}, phase {hb.get('phase')}); "
                                 f"killing it")
                    _kill(int(hb.get("pid") or 0))
                    breaker = _bill_failure(billed, breaker, breaker_path, now, hb.get("pid"),
                                            state, uptime=now - float(hb.get("started_at") or now),
                                            detail=f"phase {hb.get('phase')}")
                elif state == "crashed":
                    _log.warning(f"eCan died without a clean exit (pid {hb.get('pid')}, phase "
                                 f"{hb.get('phase')}, last seen {hb.get('updated_at_iso')})")
                    breaker = _bill_failure(billed, breaker, breaker_path, now, hb.get("pid"),
                                            "crashed", uptime=now - float(hb.get("started_at") or now),
                                            detail=f"phase {hb.get('phase')}")
                _log.info(f"starting eCan ({state})")
                try:
                    new_child = _launch()
                except Exception as e:
                    # A launch that cannot even start is a broken installation, not
                    # a crash: charge it to the breaker (which trips faster for this
                    # reason) instead of retrying every minute for the rest of the day.
                    _log.error(f"could not start eCan: {e}")
                    breaker = _bill_failure(billed, breaker, breaker_path, now, 0,
                                            "launch_failed", detail=str(e))
                    time.sleep(max(LAUNCH_RETRY_BACKOFF_SEC, 1))
                    continue
                launched_at = mono
                last_cpu = None
                breaker = watchdog_breaker.note_launch(breaker, now)
                watchdog_breaker.save(breaker_path, breaker)
                if new_child is None:
                    # No handle to follow (an older call site, or a test double):
                    # fall back to charging the launch itself against the budget.
                    if state != "not_running":
                        restarts.append(launched_at)
                    child, child_started_at = None, 0.0
                else:
                    child, child_started_at = new_child, mono
            elif state == "ok":
                frozen_defers = 0
                # A running app proves both waits were about the past: someone
                # started eCan during the post-quit hold (so the next quit gets
                # a full hold again) or during a relaunch pause (so the pause
                # must not suppress the next real relaunch).
                quiet_until = 0.0
                pause_until = 0.0
                breaker = _prove_healthy(breaker, breaker_path, hb, now)
            # Reaching the end of a round is the only proof this build can poll.
            # Both counters are cleared *here*, not at the top of the round: a
            # top-of-round reset let a build that raises later in the round
            # (deciding to kill, launching, walking psutil) clear its own count
            # every time, so neither MAX_LOOP_ERRORS nor MAX_LOOP_ERROR_EXITS
            # could ever fire and the platform's restart policy would relaunch
            # this watchdog forever.
            loop_errors = 0
            if breaker.get("loop_error_streak"):
                breaker = watchdog_breaker.note_loop_ok(breaker)
                watchdog_breaker.save(breaker_path, breaker)
        except Exception as exc:
            # One bad poll must not end unattended mode. Anything unexpected --
            # psutil refusing a process, a lease file that is not JSON, a disk
            # that went away -- is logged and retried; only a loop that cannot
            # poll at all any more gives up, and it says so with a distinct exit
            # code so a restart policy can tell it from the "user quit" exit.
            loop_errors += 1
            _log.exception(f"poll failed ({loop_errors}/{MAX_LOOP_ERRORS}): {exc}")
            if loop_errors >= MAX_LOOP_ERRORS:
                _log.critical("the watchdog can no longer poll reliably; exiting with code 3")
                # Count the exit *before* leaving, so the restart policy that
                # is about to fire can be told to stop (MAX_LOOP_ERROR_EXITS).
                try:
                    watchdog_breaker.save(breaker_path,
                                          watchdog_breaker.note_loop_error(breaker))
                except Exception:
                    pass                    # the exit matters more than the note
                return 3
            time.sleep(LOOP_ERROR_BACKOFF_SEC)
            continue
        time.sleep(POLL_SEC)
