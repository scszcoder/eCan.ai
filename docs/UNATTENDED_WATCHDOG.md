# Unattended Mode: the watchdog, the three platforms, and why it cannot loop

**Status:** implemented on `feat/watchdog-dev-optin`
**Scope:** `utils/app_watchdog.py`, `utils/watchdog_breaker.py`,
`utils/unattended.py`, `utils/exit_intent.py`, `utils/crash_boundary.py`,
`main.py`, `gui/LoginoutGUI.py`, `build_system/ecan_build.py`.

## What runs

| File (`<appdata>/runlogs/`) | Written by | Read by |
|---|---|---|
| `process_heartbeat.json` | the app (`utils/crash_boundary.py`) | the watchdog |
| `exit_intent.json` | the app on shutdown (`utils/exit_intent.py`), the uninstaller | the watchdog |
| `watchdog_breaker.json` | the watchdog (`utils/watchdog_breaker.py`) | the watchdog, the Settings UI |
| `watchdog.log` | the watchdog (`RotatingFileHandler`, 2 MB × 3) | humans |
| `watchdog.lock` | the watchdog (`utils/file_lock.py`) | the next watchdog |

The watchdog is the same executable as the app, started as
`<app> --watchdog`. `main.py:631` handles that flag **before** PySide6 is
imported, so the supervisor needs no display and no GUI stack: it is the same
code path on a Windows kiosk, a desktop Mac and a headless Linux box.

The supervisor writes **only** `watchdog.log`. It is the same binary as the
app, so importing it also runs `utils/logger_helper.py`'s module-level
singleton, which opens `eCan.log` (10 MB x 5) and `eCan.wscap.log` (20 MB x 5)
in a second process that never writes to either. On Windows that second handle
blocks the app's own `doRollover()`: `eCan.log` then stops rotating and grows
without a bound for as long as unattended mode runs. `main.py` therefore sets
`ECAN_NO_FILE_LOGGING=1` before any app import when it sees `--watchdog`, and
`LoggerHelper.setup()` honours it (console only, `log=console-only` in the
SESSION line). Pinned by `tests/unit/test_watchdog_log_isolation.py`.

## How it is armed

`utils/unattended.py::set_enabled(True)` installs one autostart entry per
platform and starts a watchdog right away; `set_enabled(False)` removes the
entry and stops the watchdog. `status()` reports
`{enabled, allow_in_dev, logon_task, autostart, autostart_kind, breaker}`.

| Platform | Entry | How the *watchdog* is restarted if it dies | Why this spelling |
|---|---|---|---|
| Windows | Scheduled task `<slug>` registered from XML (`schtasks /Create /XML`) | `RestartOnFailure` `PT5M` × 999 | The command-line form (`/SC ONLOGON`) cannot express a restart policy and defaults `ExecutionTimeLimit` to **72 h**, which silently kills the supervisor on day four |
| macOS | `~/Library/LaunchAgents/com.ecan.unattended.plist` | `KeepAlive {"SuccessfulExit": false}` + `ThrottleInterval 300` | Restarts a watchdog that *failed*, never one that deliberately stood down (exit 0) |
| Linux | `$XDG_CONFIG_HOME/autostart/<slug>.desktop` (primary) plus `systemd --user/<slug>.service` (best effort) | `Restart=on-failure`, `RestartSec=300`, `StartLimitBurst=6` per hour | Same split as macOS; `Restart=always` would reopen the loop, because exit 0 *means* "I stood down" |

Windows specifics worth knowing:

* the task XML is written as UTF-16 **with a BOM** and declares the same
  encoding — `schtasks` believes the declaration and reports only "The task XML
  is malformed" otherwise;
* the principal is `InteractiveToken` + `LeastPrivilege` + the current user
  (`<UserId>DOMAIN\user</UserId>`): the watchdog must not hold a privilege the
  GUI it restarts does not have, and Task Scheduler wants a principal user;
* if `schtasks` rejects the XML anyway, `_install_autostart()` falls back to
  `/SC ONLOGON` and logs a warning — a task with a 72 h limit beats no autostart
  entry at all.

The app itself is launched detached (`DETACHED_PROCESS |
CREATE_NEW_PROCESS_GROUP` on Windows, `start_new_session=True` on POSIX), so a
logout, a closed console or a Ctrl-Break aimed at the watchdog cannot take the
GUI down with it.

## Exit codes, and what each platform does with them

| Code | Meaning | launchd / systemd / Task Scheduler |
|---|---|---|
| `0` | deliberate: the user quit, the app was uninstalled, another watchdog already holds the lock, or this one has given up | "success" → **no restart** |
| `3` | the poll loop itself is unusable | relaunch (rate-limited by the platform) |

That single distinction is what lets the supervisor be supervised without
turning a broken build into an infinite restart chain.

## Why it cannot loop forever

Four independent ceilings, each of which ends the loop on its own:

1. **Burst window (in memory).** At most `MAX_RESTARTS = 3` relaunches per
   `RESTART_WINDOW_SEC = 1800`, then a pause. Bounds the rate, nothing else.
2. **Persistent breaker** (`watchdog_breaker.json`, survives watchdog
   restarts — which is the point: the old in-memory budget was forgotten on
   every logon, logout, toggle or crash):
   * failures are spaced by `BASE_BACKOFF_SEC = 30` doubling to
     `MAX_BACKOFF_SEC = 900`;
   * after `STORM_THRESHOLD = 6` consecutive failures the gate *opens*: no more
     launches, only watching, so the crash evidence stays on disk;
   * then one probe per cooldown, doubling `OPEN_COOLDOWN_SEC = 1800` →
     `MAX_COOLDOWN_SEC = 21600`;
   * after `GIVE_UP_AFTER_PROBES = 5` failed probes: `gave_up`, CRITICAL in
     `watchdog.log`, nothing launched until a human acts — or until eCan runs
     `HEALTHY_UPTIME_SEC = 600` on its own (`note_healthy()` clears even
     `gave_up`, so a transient cause still heals without a human).
   * a death is charged **once per pid** (`_bill_failure`), so one crash cannot
     be counted twice.
3. **The supervisor's own failure.** `MAX_LOOP_ERRORS = 20` consecutive failed
   polls → exit 3. `MAX_LOOP_ERROR_EXITS = 3` such exits in a row → exit 0 and
   stay down. Both counters are cleared only at the **end of a complete round**:
   clearing them at the top (where the heartbeat read can raise) let a build
   that dies mid-round wipe its own evidence every time, and the platform
   restarted it forever.
4. **The platform's own rate limit.** launchd `ThrottleInterval 300`;
   systemd `RestartSec=300` + `StartLimitBurst=6/3600 s`; Task Scheduler
   `PT5M` × 999. Ceiling 3 is what makes 999 finite.

Measured, not asserted: a build that exits 15 s after every launch, simulated
over **72 h** (`tests/unit/test_watchdog_breaker.py` pins the same ladder) is
**11 launches**, the last at **+14.36 h**, then `gave_up` (5 probes, 6 h
cooldown) and **silence for the remaining 57.6 h**. The old code produced
144 launches in 24 h, forever.

Two smaller holes closed on the same path:

* a clock that jumped (sleep/hibernate, NTP step) is not evidence of a freeze —
  wall and monotonic are compared (`CLOCK_JUMP_TOLERANCE_S = 30`), and the
  verdict is skipped for that poll;
* a heartbeat that is momentarily unwritable (Windows sharing violation) is
  not a freeze either, as long as the process is still burning CPU
  (`CPU_PROGRESS_MIN_SEC`, excused for at most `FROZEN_DEFER_MAX = 8` polls).

## What it deliberately does not do

* **No separate watchdog entry point.** A dedicated `--watchdog`-only binary
  was considered and rejected: a frozen build must go through the PyInstaller
  bootstrap anyway, and the dev-mode cold start of `main.py --watchdog` is
  ~0.09 s.
* **The breaker never kills a live app.** When it refuses to relaunch, it
  watches only; killing the running instance would leave ports and locks held
  by nobody.
* **It does not repair its own autostart entry.** `ensure_watchdog_running()`
  starts a process; re-installing the launchd plist / task / unit behind the
  user's back is not something a supervisor should do.

## Operating it

* `unattended.status()` → includes `breaker` (`state`, `consecutive_failures`,
  `next_attempt_in`, `loop_error_streak`, `gave_up`, `last_reason`, history).
* Turning unattended mode off and on again is the human's "try once more": it
  resets the breaker (still bounded by ceiling 2).
* IPC `unattended.reset_breaker` does the same without toggling.
* `watchdog.log` says which ceiling stopped it, in one line, with the numbers.

## Tests

`tests/unit/` — `test_app_watchdog.py`, `test_watchdog_breaker.py`,
`test_unattended_autostart.py`, `test_unattended_dev_skip.py`,
`test_unattended_dev_opt_in.py`, `test_unattended_status_honesty.py`,
`test_unattended_stop_race.py`, `test_watchdog_singleton.py`,
`test_installer_lease_contract.py`, `test_platform_signals.py` — **219 tests**.
They cover the 24 h crash-loop bound with a fake clock, the breaker ladder
(`30/60/120/240/480 → open → 1800/3600/7200/14400/21600 → gave_up`), the
platform artifacts (task XML parsed with `ElementTree`, plist parsed with
`plistlib`, systemd unit content), and the exit-code contract each restart
policy depends on.
