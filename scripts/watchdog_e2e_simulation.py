#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end simulation of the unattended watchdog -- real loop, real processes.

Why this exists
===============
The unit tests (tests/unit/test_watchdog_quit_and_pause.py) prove the *logic*
with a fake clock. They cannot prove the thing that actually broke in the
field: that ``utils.app_watchdog.run()`` -- the real loop, with real psutil
process checks, real heartbeat files, real shutdown leases and real
``subprocess.Popen`` children -- keeps watching when eCan quits on purpose
(R2) or when it has exhausted its relaunch budget (R6).

This script runs that exact loop, unmodified, against a *fake eCan* process
that writes a real heartbeat and can quit / crash / claim a shutdown lease on
command. Nothing inside utils.app_watchdog is replaced; only the constants are
scaled down (30 min -> a few seconds) and ``app_command()`` points at the fake
app instead of main.py.

Scenarios
=========
  quit    R2  the app exits cleanly (writes clean_exit) -> the watchdog must
              NOT exit. It holds quiet, then starts the app again.
  lease   R2  the app took a shutdown lease and then died mid-teardown -> when
              the lease expires the watchdog must hold, not exit.
  pause   R6  the app dies MAX_RESTARTS times -> the relaunch pause must be a
              *pause*: a permanent (uninstall) lease written while it lasts is
              honoured within one poll instead of after half an hour.
  adopt   R2  the app comes back on its own during the hold -> the hold is
              reset and the watchdog does not launch a second instance.

Every scenario also asserts that no single ``time.sleep`` in the loop is
longer than POLL_SEC -- the property that makes the two waits observable.

Usage
=====
  python3 scripts/watchdog_e2e_simulation.py              # all scenarios
  python3 scripts/watchdog_e2e_simulation.py -s quit      # just one
  python3 scripts/watchdog_e2e_simulation.py --keep       # keep the temp dirs
  python3 scripts/watchdog_e2e_simulation.py --real-time  # unscaled constants

Exit code 0 = every assertion held.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# The watchdog process must never touch the app's log files; same gate the
# real ``main.py --watchdog`` path uses (see utils/logger_helper.py).
os.environ.setdefault("ECAN_NO_FILE_LOGGING", "1")

_G, _R, _Y, _B, _DIM = "\033[92m", "\033[91m", "\033[93m", "\033[94m", "\033[2m"
_RESET = "\033[0m"
if os.environ.get("TERM") == "dumb" or not sys.stdout.isatty():
    _G = _R = _Y = _B = _DIM = _RESET = ""


def ok(msg):
    print(f"  {_G}✓{_RESET}  {msg}")


def bad(msg):
    print(f"  {_R}✗{_RESET}  {msg}")


def info(msg):
    print(f"  {_B}·{_RESET}  {msg}")


def warn(msg):
    print(f"  {_Y}!{_RESET}  {msg}")


def head(title):
    print(f"\n{_DIM}{'─' * 70}{_RESET}\n{title}\n{_DIM}{'─' * 70}{_RESET}")


# ──────────────────────────────────────────────────────────────────────────────
# The fake eCan: a real process that speaks the real file protocol
# ──────────────────────────────────────────────────────────────────────────────
FAKE_APP = '''
import json, os, sys, time
from pathlib import Path

def _arg(name, default=None):
    if name in sys.argv:
        return sys.argv[sys.argv.index(name) + 1]
    return default

logdir = Path(_arg("--dir", "."))
logdir.mkdir(parents=True, exist_ok=True)
try:
    control = json.loads((logdir / "sim_mode.json").read_text(encoding="utf-8"))
except Exception:
    control = {}
mode = _arg("--mode") or control.get("mode", "stay")
ticks = int(control.get("ticks", 8))
interval = float(control.get("interval", 0.5))
grace = float(control.get("grace", 6.0))

started = time.time()
try:
    import psutil
    create_time = psutil.Process().create_time()
except Exception:
    create_time = started

# _launch() marks its children with ECAN_LAUNCHED_BY_WATCHDOG=1. Counting the
# launches that carry it is how the simulation tells "the watchdog started it"
# from "a human/scheduler started it".
if os.environ.get("ECAN_LAUNCHED_BY_WATCHDOG") == "1":
    with open(logdir / "launches.txt", "a", encoding="utf-8") as fh:
        fh.write("%d %.3f %s\\n" % (os.getpid(), started, mode))

def beat(clean=False):
    now = time.time()
    payload = {
        "pid": os.getpid(),
        "process_create_time": create_time,
        "updated_at": now,
        "updated_at_iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now)),
        "started_at": started,
        "main_loop_tick": now,
        "phase": "main_loop",
        "clean_exit": bool(clean),
    }
    tmp = logdir / ("process_heartbeat.json.tmp.%d" % os.getpid())
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, logdir / "process_heartbeat.json")

if mode.startswith("lease"):
    lease = {"reason": "user_exit", "at": time.time(), "grace_s": grace,
             "pid": os.getpid(), "process_create_time": create_time}
    (logdir / "exit_intent.json").write_text(json.dumps(lease), encoding="utf-8")

if mode.endswith("crash"):
    for _ in range(max(0, ticks)):      # ticks=0: die before writing anything
        beat()
        time.sleep(interval)
    os._exit(3)                 # died mid-teardown: no clean exit, no goodbye

if mode == "stay":
    while True:
        beat()
        time.sleep(interval)

for _ in range(max(1, ticks)):
    beat()
    time.sleep(interval)
beat(clean=True)                # "the user quit"
sys.exit(0)
'''


_ORIGINAL: dict = {}


def _remember(w) -> None:
    """Keep the first-seen versions: every scenario re-patches the module."""
    for name in ("read_heartbeat", "runlogs_dir", "app_command", "_other_instance_running"):
        _ORIGINAL.setdefault(name, getattr(w, name))


class _Clock:
    """Delegates to time but records every sleep the watchdog asks for."""

    def __init__(self):
        self.sleeps: list[float] = []

    def sleep(self, seconds):
        self.sleeps.append(float(seconds))
        time.sleep(seconds)

    def __getattr__(self, name):
        return getattr(time, name)


class Harness:
    """Runs the real ``app_watchdog.run()`` against a fake eCan in a temp dir."""

    def __init__(self, name: str, scaled: bool = True):
        self.name = name
        self.dir = Path(tempfile.mkdtemp(prefix=f"wd-sim-{name}-"))
        self.runlogs = self.dir / "runlogs"
        self.runlogs.mkdir(parents=True)
        self.app = self.dir / "fake_ecan.py"
        self.app.write_text(FAKE_APP, encoding="utf-8")
        self.clock = _Clock()
        self.rc = None
        self.started_at = 0.0
        self._stop = threading.Event()
        self._thread = None
        self._scaled = scaled
        self.set_mode("stay")

    # ── wiring ──────────────────────────────────────────────────────────────
    def set_mode(self, mode: str, **kw):
        payload = {"mode": mode, "interval": 0.5, "ticks": 8, "grace": 6.0}
        payload.update(kw)
        (self.runlogs / "sim_mode.json").write_text(json.dumps(payload), encoding="utf-8")

    def start_app(self, mode: str = "stay"):
        """Start the fake app the way a *human* would (no watchdog marker)."""
        import subprocess
        env = {k: v for k, v in os.environ.items() if k != "ECAN_LAUNCHED_BY_WATCHDOG"}
        return subprocess.Popen([sys.executable, str(self.app), "--dir", str(self.runlogs),
                                 "--mode", mode], env=env, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, start_new_session=True)

    def _patch(self):
        import utils.app_watchdog as w
        from utils import watchdog_breaker

        # A fresh "process": drop the previous scenario's log sink and the
        # module-level singleton lock handle.
        for h in list(w._log.handlers):
            if getattr(h, "_ecan_watchdog_sink", False):
                w._log.removeHandler(h)
                try:
                    h.close()
                except Exception:
                    pass
        w._WATCHDOG_LOCK = None

        _remember(w)
        w.runlogs_dir = lambda: self.runlogs
        w.app_command = lambda: [sys.executable, str(self.app), "--dir", str(self.runlogs)]
        w._other_instance_running = lambda: None   # not what these scenarios test
        # The loop reads time through the module, so this records every wait
        # without faking anything else.
        w.time = self.clock

        if self._scaled:
            w.POLL_SEC = 1
            w.HEARTBEAT_STALE_SEC = 6
            w.QUIT_HOLD_SEC = 8            # "30 min"
            w.RESTART_WINDOW_SEC = 12      # "30 min"
            w.MAX_RESTARTS = 2
            w.LAUNCH_GRACE_SEC = 2
            w.STARTUP_TIMEOUT_SEC = 4
            w.MIN_UPTIME_FOR_HANG_SEC = 3600   # the hang detector is not on trial
            w.LOOP_STALE_SEC = 3600
            w.LOOP_ERROR_BACKOFF_SEC = 1
            w.LAUNCH_RETRY_BACKOFF_SEC = 1
            # The persistent breaker is a different subject (test_watchdog_breaker.py);
            # scaled out of the way so the crash budget is what we observe here.
            watchdog_breaker.BASE_BACKOFF_SEC = 1
            watchdog_breaker.OPEN_COOLDOWN_SEC = 2
            watchdog_breaker.STORM_THRESHOLD = 99
            watchdog_breaker.LAUNCH_FAILURE_THRESHOLD = 99
            watchdog_breaker.GIVE_UP_AFTER_PROBES = 99
            watchdog_breaker.HEALTHY_UPTIME_SEC = 10 ** 6
        self.w = w

    # ── lifecycle ───────────────────────────────────────────────────────────
    def start(self):
        self._patch()
        w = self.w
        real_read = _ORIGINAL["read_heartbeat"]

        def read(path):
            if self._stop.is_set():
                # BaseException on purpose: run()'s ``except Exception`` must
                # not swallow it, so the loop really unwinds.
                raise SystemExit(0)
            return real_read(path)

        w.read_heartbeat = read
        self.started_at = time.time()
        self._thread = threading.Thread(target=self._body, name=f"watchdog-{self.name}",
                                        daemon=True)
        self._thread.start()

    def _body(self):
        try:
            self.rc = self.w.run()
        except SystemExit:
            self.rc = None
        except BaseException as exc:                    # pragma: no cover
            self.rc = f"crash: {exc!r}"

    def stop(self, timeout: float = 30.0) -> bool:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            alive = self._thread.is_alive()
            if alive:
                warn("the watchdog thread did not unwind")
            return not alive
        return True

    def cleanup(self, keep: bool = False):
        self._kill_children()
        if not keep:
            shutil.rmtree(self.dir, ignore_errors=True)

    def _kill_children(self):
        try:
            import psutil
        except Exception:
            return
        needle = str(self.dir)
        for proc in psutil.process_iter(["cmdline"]):
            try:
                if needle in " ".join(proc.info.get("cmdline") or []):
                    proc.kill()
            except Exception:
                pass

    # ── observations ────────────────────────────────────────────────────────
    def launches(self) -> list[dict]:
        path = self.runlogs / "launches.txt"
        out = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                pid, ts, mode = line.split()
                out.append({"pid": int(pid), "at": float(ts), "mode": mode})
        except Exception:
            pass
        return out

    def log(self) -> str:
        try:
            return (self.runlogs / "watchdog.log").read_text(encoding="utf-8")
        except Exception:
            return ""

    def log_lines(self, needle: str) -> list[str]:
        return [ln for ln in self.log().splitlines() if needle in ln]

    def elapsed(self) -> float:
        return time.time() - self.started_at

    def tail(self, limit: int = 14):
        lines = self.log().splitlines()
        for ln in lines[-limit:]:
            print(f"    {_DIM}{ln}{_RESET}")
        if not lines:
            print(f"    {_DIM}(no watchdog.log yet){_RESET}")


def wait_until(predicate, timeout: float, interval: float = 0.25) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


# ──────────────────────────────────────────────────────────────────────────────
# Scenarios
# ──────────────────────────────────────────────────────────────────────────────
def _common(h: Harness, results: list, max_sleep_ok: float) -> None:
    longest = max(h.clock.sleeps) if h.clock.sleeps else 0.0
    if longest <= max_sleep_ok:
        ok(f"no wait longer than POLL_SEC ({longest:.1f}s <= {max_sleep_ok:.0f}s)")
        results.append(True)
    else:
        bad(f"a single wait of {longest:.1f}s exceeds POLL_SEC ({max_sleep_ok:.0f}s)")
        results.append(False)


def scenario_quit(h: Harness, results: list):
    """R2: a clean exit is a pause, not a disarmament."""
    head("scenario quit — the app exits cleanly; the watchdog must survive it")
    h.set_mode("quit", ticks=8)          # ~4 s of life, then clean_exit
    h.start()

    relaunched = wait_until(lambda: len(h.launches()) >= 2, timeout=h.elapsed_timeout(45))
    first = h.launches()[0]["at"] if h.launches() else 0.0
    second = h.launches()[1]["at"] if len(h.launches()) > 1 else 0.0
    stopped = h.stop()

    if h.rc is None:
        ok("run() never returned 0 -- unattended mode is still armed")
        results.append(True)
    else:
        bad(f"run() returned {h.rc!r}: the watchdog disarmed itself on a clean quit")
        results.append(False)

    if relaunched:
        gap = second - first
        ok(f"eCan was started again {gap:.0f}s after the quit (QUIT_HOLD_SEC={h.w.QUIT_HOLD_SEC}s)")
        results.append(True)
    else:
        bad("eCan was never started again after the clean exit")
        results.append(False)

    holds = h.log_lines("not relaunching it for")
    if holds:
        ok(f"the log explains the wait once per hold ({len(holds)} line(s))")
        results.append(True)
    else:
        bad("no 'not relaunching it for' line in watchdog.log")
        results.append(False)

    if stopped:
        results.append(True)
    _common(h, results, h.w.POLL_SEC)
    h.tail()


def scenario_lease(h: Harness, results: list):
    """R2: a shutdown lease that expired with the process gone must not exit."""
    head("scenario lease — the app claimed a lease, died mid-teardown, lease expired")
    h.set_mode("lease-crash", ticks=8, grace=6.0)   # beats 4 s, dies, lease ends at 6 s
    h.start()

    relaunched = wait_until(lambda: len(h.launches()) >= 2, timeout=h.elapsed_timeout(60))
    h.stop()

    if h.rc is None:
        ok("run() never returned 0 on the expired-lease path")
        results.append(True)
    else:
        bad(f"run() returned {h.rc!r}: an expired lease disarmed the watchdog")
        results.append(False)

    if relaunched:
        ok("eCan was started again after the hold")
        results.append(True)
    else:
        bad("eCan was never started again after the expired lease")
        results.append(False)

    # The second launch must not clear the lease the watchdog itself already
    # acted on -- it must be the same hold, not a second one stacked on top.
    stacks = h.log_lines("not relaunching it for")
    if len(stacks) <= 2:
        ok(f"no hold was re-armed on top of another ({len(stacks)} line(s))")
        results.append(True)
    else:
        bad(f"the hold was armed {len(stacks)} times: the loop is re-arming itself")
        results.append(False)

    _common(h, results, h.w.POLL_SEC)
    h.tail()


def scenario_pause(h: Harness, results: list):
    """R6: the relaunch pause must not blind the loop."""
    head("scenario pause — crash budget exhausted; an uninstall must still be seen")
    h.set_mode("crash", ticks=0)         # dies before writing anything: a launch that did not take
    h.start()

    paused = wait_until(lambda: bool(h.log_lines("pausing launches")), timeout=h.elapsed_timeout(60))
    if paused:
        ok("the relaunch budget was exhausted and the pause started")
        results.append(True)
    else:
        bad("the pause never started (launches: %d)" % len(h.launches()))
        results.append(False)
        h.stop()
        _common(h, results, h.w.POLL_SEC)
        h.tail()
        return

    # The whole point: while paused, the loop is still polling. Drop the
    # uninstall marker (a permanent lease) and measure how long it takes for
    # the watchdog to honour it.
    marker_at = time.time()
    lease = {"reason": "uninstall", "at": marker_at, "grace_s": float("inf"), "pid": 0}
    (h.runlogs / "exit_intent.json").write_text(json.dumps(lease), encoding="utf-8")

    returned = wait_until(lambda: h.rc is not None, timeout=h.elapsed_timeout(20))
    reaction = time.time() - marker_at
    h.stop()

    if returned and h.rc == 0:
        ok(f"the watchdog honoured the uninstall {reaction:.1f}s after it was written")
        results.append(True)
    else:
        bad(f"the uninstall was not honoured while paused (rc={h.rc!r}, {reaction:.1f}s)")
        results.append(False)

    limit = max(3.0, h.w.POLL_SEC * 3)
    if reaction <= limit:
        ok(f"reaction time {reaction:.1f}s <= {limit:.0f}s: the loop was watching during the pause")
        results.append(True)
    else:
        bad(f"reaction time {reaction:.1f}s: the loop was asleep, not watching")
        results.append(False)

    _common(h, results, h.w.POLL_SEC)
    h.tail()


def scenario_adopt(h: Harness, results: list):
    """R2: an app that comes back on its own resets the hold."""
    head("scenario adopt — eCan is started by hand during the hold")
    h.set_mode("quit", ticks=8)
    h.start()

    holding = wait_until(lambda: bool(h.log_lines("not relaunching it for")),
                         timeout=h.elapsed_timeout(30))
    if not holding:
        bad("the hold never started")
        results.append(False)
        h.stop()
        _common(h, results, h.w.POLL_SEC)
        h.tail()
        return
    ok("the watchdog is holding after the clean exit")
    results.append(True)

    proc = h.start_app("stay")           # a human opens eCan during the hold
    try:
        seen_ok = wait_until(lambda: bool(h.log_lines("clean exit")) and
                             len(h.launches()) == 1, timeout=h.elapsed_timeout(20))
        time.sleep(h.w.QUIT_HOLD_SEC + 4)   # long enough for the old hold to expire
        launches = h.launches()
        resumed = h.log_lines("unattended mode resumes")
        if len(launches) == 1 and not resumed:
            ok("the hold was reset: no second instance was launched")
            results.append(True)
        else:
            bad(f"the watchdog launched anyway ({len(launches)} launches, "
                f"{len(resumed)} 'resumes' lines)")
            results.append(False)
        if seen_ok:
            results.append(True)
    finally:
        proc.kill()
        h.stop()
    _common(h, results, h.w.POLL_SEC)
    h.tail()


SCENARIOS = {
    "quit": (scenario_quit, 40),
    "lease": (scenario_lease, 50),
    "pause": (scenario_pause, 50),
    "adopt": (scenario_adopt, 45),
}

Harness.elapsed_timeout = lambda self, cap: cap   # the scaled runs finish in seconds


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-s", "--scenario", action="append", choices=sorted(SCENARIOS),
                    help="run only this scenario (repeatable); default: all")
    ap.add_argument("--keep", action="store_true", help="keep the temp directories")
    ap.add_argument("--real-time", action="store_true",
                    help="use the shipping constants (QUIT_HOLD_SEC=1800s): ~1 h per scenario")
    args = ap.parse_args(argv)

    names = args.scenario or ["quit", "lease", "pause", "adopt"]
    print(f"\n{_B}watchdog end-to-end simulation{_RESET}  "
          f"({'real-time constants' if args.real_time else 'scaled constants'})")
    print(f"{_DIM}real app_watchdog.run(), real processes, real heartbeat/lease files{_RESET}")

    summary = {}
    for name in names:
        fn, _cap = SCENARIOS[name]
        h = Harness(name, scaled=not args.real_time)
        results: list = []
        try:
            fn(h, results)
        except Exception as exc:
            bad(f"scenario {name} raised: {exc!r}")
            results.append(False)
        finally:
            if args.keep:
                info(f"kept {h.dir}")
            h.cleanup(keep=args.keep)
        summary[name] = all(results) and bool(results)

    head("summary")
    failed = 0
    for name, passed in summary.items():
        if passed:
            ok(f"{name}")
        else:
            bad(f"{name}")
            failed += 1
    print()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
