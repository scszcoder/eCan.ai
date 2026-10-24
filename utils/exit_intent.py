"""Exit-intent lease: "I am shutting down on purpose — do not relaunch me".

Why this exists
---------------
eCan already records a *clean exit* flag in the heartbeat
(utils/crash_boundary.py -> runlogs/process_heartbeat.json) and the watchdog
honours it (utils/app_watchdog.py::assess). That covers the happy path.

The gap: between "the user pressed the close button" and "atexit ran" there is
a real window of seconds-to-minutes where eCan is tearing down (Qt teardown,
worker drain, proxy shutdown, session flush). If the process dies *inside*
that window — power loss, taskkill /F, OOM killer — no clean-exit flag was
ever written, so the watchdog sees "process gone, no clean exit" and relaunches
an app the user deliberately closed.

So the marker is a *lease*, not a flag. It has two phases:

* **active** (within ``grace_s``) — the app is on its way out. The watchdog
  must neither relaunch it nor kill it as hung.
* **expired** (past ``grace_s``) — the shutdown window is over. What that
  means depends on the process, not on the clock alone:

  - process gone → the shutdown was real; the watchdog stands down for good
    (``quit``).
  - process still alive → the teardown is merely slow. The watchdog keeps
    standing by. That is enough: a teardown that is really wedged stops
    writing its heartbeat, and the ordinary "frozen" rule kills and restarts
    it.

  The clock alone used to be the whole rule ("expired ⇒ exit forever"), which
  meant one slow shutdown silently ended unattended mode for the session --
  and, worse, "expired" was consulted even when the app was demonstrably
  still running.

The lease is written at the *start* of the shutdown, not at the end, and it
expires by itself.

Design constraints (see tests/unit/test_exit_intent.py for the spec):

* Written with a temp file + ``os.replace`` so a reader never sees a
  half-written file, even if the process is killed mid-write.
* Every failure is swallowed: a broken marker must never stop the app from
  shutting down.
* Reading is defensive: oversized, empty, corrupt or partial files are all
  treated as "no lease" (fail open towards *not* suppressing a relaunch).
* Timestamps are plain UTC epoch floats — no timezones, no local time.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

from utils.logger_helper import logger_helper as logger

EXIT_INTENT_NAME = "exit_intent.json"
#: Refuse to read anything larger than this — a corrupt/hostile file must not
#: be loaded into memory just to decide "is the app quitting".
MAX_INTENT_BYTES = 4096
#: Default lease length. Must comfortably exceed a full Qt teardown + worker
#: drain, but stay short enough that a user who closed the app does not see it
#: come back minutes later.
DEFAULT_GRACE_S = 120.0


def _runlogs_dir(log_dir: str | None = None) -> Path:
    if log_dir:
        path = Path(log_dir)
    else:
        try:
            from config.app_info import app_info
            path = Path(app_info.appdata_path) / "runlogs"
        except Exception:
            path = Path.cwd() / "runlogs"
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.debug(f"[ExitIntent] cannot create runlogs dir {path}: {exc}")
    return path


def exit_intent_path(log_dir: str | None = None) -> Path:
    return _runlogs_dir(log_dir) / EXIT_INTENT_NAME


def mark_exiting(reason: str = "", grace_s: float = DEFAULT_GRACE_S,
                 log_dir: str | None = None) -> bool:
    """Claim a lease: "I am on my way out, do not relaunch me for *grace_s*".

    Returns True when the lease was written, False when it could not be
    written (the caller must not treat that as a fatal error).
    """
    try:
        path = exit_intent_path(log_dir)
        payload = {
            "reason": str(reason or "unknown"),
            "at": time.time(),
            "grace_s": float(grace_s),
            "pid": os.getpid(),
            # Fingerprint of *this* process. The OS reuses pids, so a pid
            # alone cannot tell "the lease I wrote" from "a lease a dead
            # generation left behind whose pid the OS has since handed to
            # us". Pairing the pid with the create-time does.
            "process_create_time": _current_create_time(),
        }
        tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
        logger.debug(f"[ExitIntent] lease acquired (reason={payload['reason']!r}, "
                     f"grace_s={payload['grace_s']})")
        return True
    except Exception as exc:
        logger.debug(f"[ExitIntent] could not write lease: {exc}")
        return False


def _current_create_time() -> Optional[float]:
    """When this exact process started, per the OS. None when unknown."""
    try:
        from utils.worker_boot import current_create_time
        return current_create_time()
    except Exception:
        return None


def _belongs_to_this_process(lease: dict) -> bool:
    """True only when *lease* provably belongs to the process asking.

    The pid must match *and* the create-time fingerprint must match. A pid
    match on its own is not enough: the OS recycles pids, and a lease left
    behind by a crashed generation whose pid has since been reused would
    otherwise be mistaken for our own — which, for a permanent
    ("inf") lease, would silence the watchdog forever.
    """
    try:
        if int(lease.get("pid") or 0) != os.getpid():
            return False
    except Exception:
        return False
    stored = lease.get("process_create_time")
    mine = _current_create_time()
    if stored is None or mine is None:
        # A lease without a fingerprint (e.g. one written by the Inno Setup
        # uninstaller, which cannot call Python) cannot be attributed to
        # this process. Treat it as not ours.
        return False
    try:
        return abs(float(stored) - float(mine)) <= 2.0
    except Exception:
        return False


def _coerce_grace(value) -> Optional[float]:
    """Accept the grace value in the shapes the Inno Setup uninstaller writes.

    The uninstaller cannot call Python, so it writes the lease file itself as
    plain JSON. It writes ``"inf"`` for a permanent lease and plain decimal
    strings for a finite one.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if not text:
            return None
        if text in ("inf", "+inf", "infinity", "+infinity"):
            return float("inf")
        try:
            return float(text)
        except ValueError:
            return None
    return None


def read_exit_lease(log_dir: str | None = None) -> Optional[dict]:
    """Return the lease payload, or None when there is nothing trustworthy."""
    try:
        path = exit_intent_path(log_dir)
        try:
            if path.stat().st_size > MAX_INTENT_BYTES:
                return None
        except Exception:
            return None
        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            return None
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        if _coerce_grace(data.get("grace_s")) is None:
            return None
        at = data.get("at")
        if isinstance(at, bool) or not isinstance(at, (int, float, str)):
            return None
        if isinstance(at, str):
            try:
                at = float(at.strip())
            except ValueError:
                return None
        data["at"] = float(at)
        data["grace_s"] = _coerce_grace(data.get("grace_s"))
        return data
    except Exception:
        return None


def is_permanent_lease(lease: Optional[dict]) -> bool:
    """True for a lease that never expires (the uninstall marker).

    Duplicated from utils/app_watchdog.py on purpose: the watchdog imports
    this module, so importing back from it would be circular.
    """
    if not lease:
        return False
    try:
        return float(lease.get("grace_s")) == float("inf")
    except Exception:
        return False


def lease_is_active(lease: Optional[dict], now: float | None = None) -> bool:
    """True while *lease* is still within its grace window.

    The lease is expired when ``now - at >= grace_s``. A clock that jumps
    backwards yields a negative age, which is treated as "still inside the
    lease" — the safe direction, because the worst outcome is a delayed
    relaunch rather than a lost session.
    """
    if not lease:
        return False
    try:
        grace = float(lease["grace_s"])
        at = float(lease["at"])
    except Exception:
        return False
    if grace <= 0:
        return False
    current = time.time() if now is None else float(now)
    return (current - at) < grace


def is_exiting(log_dir: str | None = None, now: float | None = None) -> bool:
    """True while a shutdown lease is still valid."""
    return lease_is_active(read_exit_lease(log_dir), now=now)


def clear_exit_intent(log_dir: str | None = None) -> None:
    """Drop the lease. Used when a new session starts and the old lease is
    known to be stale (e.g. the previous process already exited long ago)."""
    try:
        path = exit_intent_path(log_dir)
        if path.exists():
            path.unlink()
    except Exception as exc:
        logger.debug(f"[ExitIntent] could not clear lease: {exc}")


#: Grace windows per shutdown kind. A plain quit must outlast the full
#: teardown (live-chat drain + lightrag + MCP cleanup + port release, ~8s
#: worst case) with a wide margin. An OTA replacement runs an installer that
#: needs considerably longer. An uninstall must never be relaunched.
GRACE_BY_REASON = {
    "user_exit": 120.0,
    "ota_update": 600.0,
    "uninstall": float("inf"),
}
DEFAULT_REASON_GRACE_S = 120.0


def claim_shutdown_lease(reason: str = "user_exit", grace_s: float | None = None,
                         log_dir: str | None = None) -> bool:
    """Take the shutdown lease for *reason*.

    Call this at the *start* of a teardown, not at the end: the point is to
    cover the window in which the app is still running but no longer intends
    to be running. Never raises — a failed lease must not stop the app from
    closing.
    """
    key = str(reason or "user_exit")
    if grace_s is None:
        grace_s = GRACE_BY_REASON.get(key, DEFAULT_REASON_GRACE_S)
    try:
        return mark_exiting(reason=key, grace_s=float(grace_s), log_dir=log_dir)
    except Exception as exc:
        logger.debug(f"[ExitIntent] could not claim shutdown lease: {exc}")
        return False


def _install_handlers() -> None:
    """Record the shutdown intent when the platform sends an exit signal."""
    from utils.platform_signals import install_exit_handlers

    def _mark(name: str) -> None:
        mark_exiting(reason=f"signal_{name.lower()}")

    install_exit_handlers(_mark)


def on_startup(log_dir: str | None = None) -> None:
    """Prepare the exit-intent machinery for a fresh process.

    * Drops a lease left behind by a *previous* process. A stale lease would
      make the watchdog stand down for its whole grace window, hiding a crash
      of the app that is running now. A lease written by *this* process (an
      OTA-triggered restart, for instance) is kept.
    * Installs the exit-signal handlers.

    Never raises: startup must not fail because of this.
    """
    try:
        lease = read_exit_lease(log_dir)
        if lease and not _belongs_to_this_process(lease):
            if is_permanent_lease(lease):
                # The uninstall marker (written by the Inno Setup installer,
                # which cannot call Python and therefore carries no pid
                # fingerprint). It must survive: clearing it would let the
                # watchdog relaunch an app the user just deleted.
                logger.debug("[ExitIntent] keeping the permanent uninstall lease")
            else:
                clear_exit_intent(log_dir)
                logger.debug("[ExitIntent] cleared a stale shutdown lease")
    except Exception as exc:
        logger.debug(f"[ExitIntent] could not clear stale lease: {exc}")
    try:
        _install_handlers()
    except Exception as exc:
        logger.debug(f"[ExitIntent] could not install exit handlers: {exc}")
