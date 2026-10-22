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
- clean exit recorded (the user quit)      -> the watchdog exits too

At most MAX_RESTARTS within RESTART_WINDOW_SEC, then it pauses for
RESTART_WINDOW_SEC so a crash-at-startup cannot loop forever. Logs to
runlogs/watchdog.log (never eCan.log, which the app rotates).
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

from utils.exit_intent import lease_is_active, read_exit_lease

POLL_SEC = 15
HEARTBEAT_STALE_SEC = 120
LOOP_STALE_SEC = 600
MIN_UPTIME_FOR_HANG_SEC = 900
MAX_RESTARTS = 3
RESTART_WINDOW_SEC = 1800
LAUNCH_GRACE_SEC = 120
#: How far apart two create-times may be and still count as the same
#: process. Mirrors utils/worker_boot.py and utils/crash_boundary.py --
#: comfortably wider than the clock's resolution, far narrower than any
#: real process lifetime.
CREATE_TIME_TOLERANCE_S = 2.0

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
    """How to start eCan itself (frozen exe, or main.py in dev)."""
    if getattr(sys, "frozen", False):
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
    if (tick and phase.startswith("main_loop")
            and now - float(hb.get("started_at") or now) > MIN_UPTIME_FOR_HANG_SEC
            and now - float(tick) > LOOP_STALE_SEC):
        return "hung"
    return "ok"


def _kill(pid: int) -> None:
    import psutil
    try:
        p = psutil.Process(pid)
        for c in p.children(recursive=True):
            try:
                c.kill()
            except Exception:
                pass
        p.kill()
    except Exception as e:
        _log.warning(f"could not kill pid {pid}: {e}")


def _launch() -> None:
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0x8)
    env = dict(os.environ)
    env["ECAN_LAUNCHED_BY_WATCHDOG"] = "1"
    subprocess.Popen(app_command(), creationflags=flags, env=env, close_fds=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)


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


def run() -> int:
    logs = runlogs_dir()
    handler = logging.handlers.RotatingFileHandler(logs / "watchdog.log", maxBytes=2_000_000,
                                                   backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    _log.addHandler(handler)
    _log.setLevel(logging.INFO)
    if not _acquire_singleton(logs / "watchdog.lock"):
        _log.info("another watchdog is running; exiting")
        return 0
    hb_path = logs / "process_heartbeat.json"
    restarts: list = []
    launched_at = 0.0
    _log.info(f"watchdog started (pid {os.getpid()}), watching {hb_path}")
    first = True
    while True:
        now = time.time()
        hb = read_heartbeat(hb_path)
        alive = bool(hb) and process_alive(hb)
        # A shutdown lease (utils/exit_intent.py) means the app is quitting on
        # purpose. Honour it before anything else, otherwise a teardown that
        # takes longer than POLL_SEC would be misread as a crash and the
        # watchdog would relaunch an app the user just closed.
        lease = read_exit_lease(log_dir=str(logs))
        permanent = is_permanent_lease(lease)
        exiting = (permanent or should_honour_lease(hb, now, lease)) and lease_is_active(lease, now)
        state = assess(hb, now, alive, exiting=exiting)
        if first:
            first = False
            if not alive and not exiting:
                # Started at logon (or after eCan was closed): the last heartbeat
                # may say "clean exit" from the previous shutdown -- start eCan.
                state = "not_running"
        if state == "quit" and launched_at and now - launched_at < LAUNCH_GRACE_SEC:
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
            _log.info("eCan exited cleanly (user quit); watchdog exiting")
            return 0
        if state in ("not_running", "crashed", "frozen", "hung"):
            if state == "not_running" and launched_at and now - launched_at < LAUNCH_GRACE_SEC:
                time.sleep(POLL_SEC)
                continue      # still starting up, no heartbeat yet
            restarts = [t for t in restarts if now - t < RESTART_WINDOW_SEC]
            if len(restarts) >= MAX_RESTARTS:
                _log.warning(f"{len(restarts)} restarts in {RESTART_WINDOW_SEC // 60} min; pausing")
                time.sleep(RESTART_WINDOW_SEC)
                continue
            if state in ("frozen", "hung") and hb:
                _log.warning(f"eCan {state} (pid {hb.get('pid')}, phase {hb.get('phase')}); killing it")
                _kill(int(hb.get("pid") or 0))
            elif state == "crashed":
                _log.warning(f"eCan died without a clean exit (pid {hb.get('pid')}, phase {hb.get('phase')}, "
                             f"last seen {hb.get('updated_at_iso')})")
            _log.info(f"starting eCan ({state})")
            try:
                _launch()
                launched_at = time.time()
                if state != "not_running":
                    restarts.append(launched_at)
            except Exception as e:
                _log.error(f"could not start eCan: {e}")
        time.sleep(POLL_SEC)
