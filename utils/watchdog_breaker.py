"""A persistent circuit breaker for the crash/hang watchdog (utils/app_watchdog.py).

The problem it solves
---------------------
The watchdog has an *in-memory* restart budget: at most ``MAX_RESTARTS``
relaunches per ``RESTART_WINDOW_SEC``, then a pause. That bounds the rate but
never stops the loop, and it forgets everything when the watchdog itself
restarts (logon, logout/login, the user toggling the switch, a crash of the
watchdog). Measured against the failure it is meant to survive -- a build with
a bug that kills it a few seconds after launch -- the old loop launched eCan 3
times, slept 30 minutes, forgot the budget had ever been spent, and repeated.
A full day of that is 144 launches of a build that cannot work, no escalation,
no signal, and crash reports overwritten so many times that the first
(interesting) one is gone.

The state machine
-----------------
``closed``      -> normal operation; the watchdog relaunches on a crash.
``open``        -> too many failures in a row: the watchdog *stops launching*
                   and only watches, so the machine stops thrashing and the
                   crash evidence stays on disk.
``half open``   -> one probe launch per (geometrically growing) cooldown. If
                   the probe survives long enough to prove itself healthy the
                   breaker closes; if it dies, the cooldown doubles.
``given up``    -> after ``GIVE_UP_AFTER_PROBES`` failed probes the watchdog
                   stops launching altogether and says so (CRITICAL in
                   watchdog.log, plus ``summary()`` for the Settings UI) until
                   a human fixes the build, resets it, or starts eCan by hand
                   and it stays up.

Why this cannot loop forever
----------------------------
Every path out of a failure is bounded:

* the first failures are spaced by ``BASE_BACKOFF_SEC`` doubling up to
  ``MAX_BACKOFF_SEC``;
* after that each attempt costs one cooldown, and the cooldown doubles from
  ``OPEN_COOLDOWN_SEC`` up to ``MAX_COOLDOWN_SEC``;
* ``GIVE_UP_AFTER_PROBES`` failed probes end it for good.

Measured against the failure it was written for -- a build that dies within one
poll of every launch, simulated over 24 h (and over 72 h) -- it is exactly 11
launches, the last of them at +14.4 h, and then nothing for the rest of the
day. A finite, testable number instead of "every 30 minutes forever".

What still recovers by itself
-----------------------------
A transient cause (OOM, a locked database, a network share that came back)
must not need a human. ``note_healthy()`` clears everything -- including
``given up`` -- as soon as eCan runs for ``HEALTHY_UPTIME_SEC`` with a fresh
heartbeat, whether the watchdog launched it or the user did.

All times are wall-clock seconds (``time.time()``) because the state has to
survive across processes. ``_clamp()`` keeps a clock that moved backwards from
parking the breaker in the far future.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

#: How long to wait after the first failure, doubling per consecutive failure.
BASE_BACKOFF_SEC = 30.0
#: Ceiling for the above, so a flapping app is still retried within minutes.
MAX_BACKOFF_SEC = 900.0
#: Consecutive failures that trip the breaker. Low enough to stop a startup
#: crash loop inside the first minute of thrashing, high enough that a couple
#: of unlucky restarts (a laptop lid, a killed process) do not.
STORM_THRESHOLD = 6
#: A failure that proves the installation itself is broken (the executable
#: could not even be started) trips it sooner: retrying cannot fix a missing
#: file, and every attempt costs a startup timeout of the operator's time.
LAUNCH_FAILURE_THRESHOLD = 3
#: First cooldown once the breaker opens; doubles per failed probe.
OPEN_COOLDOWN_SEC = 1800.0
#: Ceiling for the cooldown. Six hours means at most four probes a day at
#: saturation -- visible in the log, harmless to the machine.
MAX_COOLDOWN_SEC = 21600.0
#: Failed half-open probes tolerated before the breaker gives up for good.
GIVE_UP_AFTER_PROBES = 5
#: Uptime (seconds of fresh heartbeats) that proves an instance is not part of
#: a crash loop. A build that dies at start never reaches it; a build that
#: runs for ten minutes and then crashes once did.
HEALTHY_UPTIME_SEC = 600.0
#: Failures kept for diagnosis. Bounded so the file cannot grow without limit.
MAX_HISTORY = 20
#: Bumped when the on-disk shape changes in a way older readers cannot parse.
VERSION = 1


def new_state() -> dict:
    """A fresh, never-failed breaker."""
    return {
        "version": VERSION,
        "consecutive_failures": 0,
        "total_failures": 0,
        "opened_at": 0.0,
        "cooldown_sec": 0.0,
        "next_attempt_at": 0.0,
        "probes": 0,
        "gave_up": False,
        "gave_up_at": 0.0,
        "first_failure_at": 0.0,
        "last_failure_at": 0.0,
        "last_healthy_at": 0.0,
        "last_reason": "",
        "last_uptime_s": 0.0,
        # How many times this watchdog has exited *as a supervisor* because its
        # own polling loop failed (app_watchdog.MAX_LOOP_ERRORS). Persisted so
        # a restart policy (launchd KeepAlive, systemd Restart, Task Scheduler
        # RestartOnFailure) cannot turn "the watchdog is buggy" into an endless
        # restart loop: see note_loop_error().
        "loop_error_streak": 0,
        "history": [],
    }


def _num(value, default: float = 0.0) -> float:
    try:
        out = float(value)
    except Exception:
        return default
    if out != out or out in (float("inf"), float("-inf")):    # NaN / inf
        return default
    return out


def _now_iso(ts) -> str:
    """ISO-8601 (local time) for a wall-clock stamp, or "" when it is nonsense.

    Only ever used for the human-readable copy of a failure (history, summary).
    A state file written by a machine with a broken clock must not make the
    watchdog raise while it is trying to record *why* eCan died -- that would
    turn a logging detail into the failure the watchdog was there to survive.
    """
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def normalize(state) -> dict:
    """Coerce whatever was on disk into a complete, sane state dict.

    The file is written by an older or newer build in the middle of a crash
    storm -- exactly when it is most likely to be half-written, truncated or
    hand-edited. Every field is therefore defaulted and re-typed here rather
    than trusted: a breaker that raises on a bad file would take the watchdog
    down with it, which is the one thing this module must never do.
    """
    base = new_state()
    if not isinstance(state, dict):
        return base
    for key in ("consecutive_failures", "total_failures", "probes", "loop_error_streak"):
        try:
            base[key] = max(0, int(state.get(key) or 0))
        except Exception:
            base[key] = 0
    for key in ("opened_at", "cooldown_sec", "next_attempt_at", "gave_up_at",
                "first_failure_at", "last_failure_at", "last_healthy_at", "last_uptime_s"):
        base[key] = max(0.0, _num(state.get(key)))
    base["gave_up"] = bool(state.get("gave_up"))
    base["last_reason"] = str(state.get("last_reason") or "")[:200]
    history = state.get("history")
    if isinstance(history, list):
        base["history"] = [h for h in history if isinstance(h, dict)][-MAX_HISTORY:]
    return base

# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def load(path) -> dict:
    """Read the breaker state, or a fresh one when there is nothing usable.

    Never raises and never deletes: a corrupt file is reported by the caller's
    summary (it looks like "closed") rather than fixed here, because a broken
    file must not be the reason a kiosk stops being protected.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return new_state()
    return normalize(data)


def save(path, state) -> bool:
    """Persist *state* atomically. Returns whether it landed.

    ``os.replace`` after a temporary write: the watchdog may be killed at any
    point (that is its whole job), and a half-written breaker file would be
    read as "closed" and hand the app a fresh crash budget it did not earn.
    A failure to save is reported, not raised: the in-memory state still
    bounds this session.
    """
    st = normalize(state)
    target = Path(path)
    tmp = target.with_suffix(target.suffix + ".tmp")
    payload = json.dumps(st, ensure_ascii=False, indent=2, sort_keys=True)
    for attempt in range(3):
        try:
            tmp.write_text(payload, encoding="utf-8")
            os.replace(tmp, target)
            return True
        except Exception:
            time.sleep(0.02 * (attempt + 1))
    try:
        target.write_text(payload, encoding="utf-8")
        return True
    except Exception:
        return False


def _clamp_deadline(value, now: float) -> float:
    """Discard a "do not launch before" stamp that cannot be genuine.

    The state survives across processes, so it survives a clock change too. A
    machine whose clock was set two days back would otherwise be left waiting
    two days before relaunching an app that merely crashed -- and because the
    comparison is always against the *current* time, that wait never ends: the
    app would stay down for good. That is the opposite of the failure this
    module exists to prevent.

    No legitimate cooldown lies further out than ``MAX_COOLDOWN_SEC`` from the
    moment it was stored -- and as time passes the remaining wait only shrinks.
    So a stamp beyond that horizon cannot be real, and is treated as expired.
    A genuine six-hour cooldown is never cut short by this rule.
    """
    v = _num(value)
    if v <= 0:
        return 0.0
    if v - float(now) > MAX_COOLDOWN_SEC:
        return 0.0
    return v


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------


def allow_launch(state, now: float) -> tuple:
    """May the watchdog launch eCan right now?

    Returns ``(allowed, wait_seconds)``. ``wait_seconds`` is the time left on
    the current backoff/cooldown when the answer is False, and ``math.inf``
    when the breaker has given up (the caller must then stop launching and
    keep watching instead of asking again in a loop).
    """
    st = normalize(state)
    if st["gave_up"]:
        return False, float("inf")
    deadline = _clamp_deadline(st["next_attempt_at"], now)
    if float(now) < deadline:
        return False, deadline - float(now)
    return True, 0.0


def note_launch(state, now: float) -> dict:
    """Record that a launch attempt has been made.

    While the breaker is open this reserves the next slot immediately, so a
    probe that dies *without* the watchdog noticing a failure (a kill we did
    ourselves, a machine that went to sleep mid-probe) still costs the full
    cooldown instead of buying a burst of attempts.
    """
    st = normalize(state)
    if st["opened_at"]:
        st["next_attempt_at"] = float(now) + max(st["cooldown_sec"], BASE_BACKOFF_SEC)
    return st


def note_failure(state, now: float, reason: str = "", uptime_s: float = 0.0,
                 detail: str = "") -> dict:
    """Record one failed attempt and compute when the next one may happen.

    ``uptime_s`` is how long the attempt lived. It is kept in the history
    because "died after 3 s" and "died after 4 h" are different bugs, and the
    log line the operator reads first should not lose that difference.
    """
    st = normalize(state)
    now = float(now)
    st["consecutive_failures"] += 1
    st["total_failures"] += 1
    st["last_reason"] = str(reason or "")[:200]
    st["last_failure_at"] = now
    st["last_uptime_s"] = max(0.0, _num(uptime_s))
    if not st["first_failure_at"]:
        st["first_failure_at"] = now
    entry = {"at": round(now, 3), "iso": _now_iso(now), "reason": st["last_reason"],
             "uptime_s": round(st["last_uptime_s"], 1), "detail": str(detail or "")[:200]}
    st["history"] = (st["history"] + [entry])[-MAX_HISTORY:]

    threshold = LAUNCH_FAILURE_THRESHOLD if reason == "launch_failed" else STORM_THRESHOLD
    if st["consecutive_failures"] >= threshold:
        # Open (or extend) the circuit. ``probes`` counts failed half-open
        # attempts, so the cooldown doubles on each of them.
        if st["opened_at"]:
            st["probes"] += 1
        else:
            st["probes"] = 0
        st["opened_at"] = now
        st["cooldown_sec"] = min(MAX_COOLDOWN_SEC, OPEN_COOLDOWN_SEC * (2 ** min(st["probes"], 6)))
        st["next_attempt_at"] = now + st["cooldown_sec"]
        if st["probes"] >= GIVE_UP_AFTER_PROBES:
            st["gave_up"] = True
            st["gave_up_at"] = now
    else:
        delay = min(MAX_BACKOFF_SEC, BASE_BACKOFF_SEC * (2 ** (st["consecutive_failures"] - 1)))
        st["next_attempt_at"] = now + delay
    return st


def note_healthy(state, now: float = 0.0) -> dict:
    """The app proved itself: close the breaker and forget every failure.

    Called only after HEALTHY_UPTIME_SEC of fresh heartbeats, so it cannot be
    satisfied by a build that merely takes a moment to die. ``gave_up`` is
    cleared here too, which is what makes recovery from a *fixed* build
    automatic: either the probe finally stays up, or the user starts eCan by
    hand and this notices.
    """
    st = normalize(state)
    st.update({"consecutive_failures": 0, "opened_at": 0.0, "cooldown_sec": 0.0,
               "next_attempt_at": 0.0, "probes": 0, "gave_up": False,
               "gave_up_at": 0.0, "first_failure_at": 0.0,
               "last_healthy_at": max(0.0, _num(now))})
    return st



def note_loop_error(state) -> dict:
    """Record that the watchdog failed as a *supervisor* (it exited with 3).

    The last line of defence against a crash loop that the breaker above
    cannot see. Every platform we install an autostart entry for also restarts
    the watchdog itself -- launchd ``KeepAlive``, systemd ``Restart=``, Task
    Scheduler ``RestartOnFailure`` -- and those policies are rate-limited but
    *not counted*: a watchdog with a bug that always dies inside a minute would
    otherwise be restarted every five minutes, for ever, on a machine nobody is
    watching. That is the same failure mode as the app crash loop, one level
    down.

    So each such exit is counted here, and after ``MAX_LOOP_ERROR_EXITS`` in a
    row the watchdog stands down *cleanly* instead of failing again: exit 0 is
    "success" for every restart policy we write, which ends the loop without
    needing the supervisor to be smarter than it is.
    """
    st = normalize(state)
    st["loop_error_streak"] = int(st["loop_error_streak"]) + 1
    return st


def note_loop_ok(state) -> dict:
    """The polling loop completed a round, so the supervisor is not buggy.

    Clears the streak: an intermittent bug that only bites once a day must not
    accumulate against a limit meant for "this build cannot supervise at all".
    """
    st = normalize(state)
    st["loop_error_streak"] = 0
    return st


def needs_reset(state) -> bool:
    """True when ``note_healthy()`` would actually change something.

    Used to avoid rewriting the file every 15 s for a healthy app.
    """
    st = normalize(state)
    return bool(st["consecutive_failures"] or st["opened_at"] or st["probes"]
                or st["gave_up"] or st["next_attempt_at"])


def summary(state) -> dict:
    """What the Settings UI and the log need to say about the breaker."""
    st = normalize(state)
    return {
        "tripped": bool(st["opened_at"]) and not st["gave_up"],
        "gave_up": bool(st["gave_up"]),
        "consecutive_failures": st["consecutive_failures"],
        "total_failures": st["total_failures"],
        "probes": st["probes"],
        "cooldown_sec": st["cooldown_sec"],
        "last_reason": st["last_reason"],
        "last_uptime_s": st["last_uptime_s"],
        "loop_error_streak": st["loop_error_streak"],
        "last_failure_iso": _now_iso(st["last_failure_at"]) if st["last_failure_at"] else "",
        "gave_up_iso": _now_iso(st["gave_up_at"]) if st["gave_up_at"] else "",
    }


def reset(path) -> dict:
    """Forget the storm: the operator said "try again" (Settings, or a new
    install). Leaves ``total_failures`` history out on purpose -- the reset is
    about what happens next, and the old count is only useful in the log."""
    st = new_state()
    st["last_healthy_at"] = time.time()
    save(path, st)
    return st
