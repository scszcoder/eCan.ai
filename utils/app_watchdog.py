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

POLL_SEC = 15
HEARTBEAT_STALE_SEC = 120
LOOP_STALE_SEC = 600
MIN_UPTIME_FOR_HANG_SEC = 900
MAX_RESTARTS = 3
RESTART_WINDOW_SEC = 1800
LAUNCH_GRACE_SEC = 120

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


def assess(hb: Optional[dict], now: float, alive: bool) -> str:
    """'ok' | 'not_running' | 'crashed' | 'quit' | 'frozen' | 'hung'."""
    if not hb:
        return "not_running"
    if not alive:
        return "quit" if hb.get("clean_exit") else "crashed"
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


def _acquire_singleton(lock: Path) -> bool:
    import psutil
    try:
        other = int(lock.read_text().strip() or 0)
        if other and other != os.getpid() and psutil.pid_exists(other):
            return False
    except Exception:
        pass
    lock.write_text(str(os.getpid()))
    return True


def run() -> int:
    logs = runlogs_dir()
    handler = logging.handlers.RotatingFileHandler(logs / "watchdog.log", maxBytes=2_000_000,
                                                   backupCount=2, encoding="utf-8")
    from utils.log_redact import scrub  # secrets masked; the watchdog stays light

    class _Redacting(logging.Formatter):
        def format(self, record):
            return scrub(super().format(record))
    handler.setFormatter(_Redacting("%(asctime)s %(levelname)s %(message)s"))
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
        state = assess(hb, now, alive)
        if first:
            first = False
            if not alive:
                # Started at logon (or after eCan was closed): the last heartbeat
                # may say "clean exit" from the previous shutdown -- start eCan.
                state = "not_running"
        if state == "quit" and launched_at and now - launched_at < LAUNCH_GRACE_SEC:
            state = "ok"          # the old heartbeat of a process we just replaced
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
