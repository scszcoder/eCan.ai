# Shutdown Lease & Dev Watchdog Skip

**Status:** implemented
**Scope:** L0 of the process/state keep-alive design (see "Out of scope" below).

## The problem

eCan already records a *clean exit* flag in the heartbeat
(`utils/crash_boundary.py` → `runlogs/process_heartbeat.json`) and the
watchdog honours it (`utils/app_watchdog.py::assess`). A user who closes the
app is therefore not restarted.

The gap is the window **before** that flag is written. In
`gui/WebGUI.py::closeEvent` the user presses *Yes* and the app then spends up
to ~8 seconds tearing down — live-chat drain, lightrag stop, MCP cleanup,
port release — before reaching `os._exit(0)` at the end. If the process dies
*inside* that window (power loss, `taskkill /F`, the OOM killer), no clean-exit
flag was ever written, the watchdog sees "process gone, no clean exit", and
it relaunches an app the user deliberately closed.

A second, quieter problem: the watchdog is started whenever unattended mode
is on, and unattended mode is stored in a file (`unattended.json`). A stale
marker left behind by a QA run makes a developer's local `python main.py`
restart itself after every window close.

## The design: a lease, not a flag

The marker is a **lease**: "I am on my way out — leave me alone for the next
N seconds". It is written at the *start* of the shutdown, not at the end,
and it expires by itself.

```
runlogs/exit_intent.json
{
  "reason": "user_exit" | "ota_update" | "uninstall" | "signal_sigterm" | ...,
  "at": 1763712345.123,     // UTC epoch seconds
  "grace_s": 120.0,         // 120 = quit, 600 = OTA, "inf" = uninstall
  "pid": 12345,             // the process that wrote it
  "process_create_time": 1763712300.5   // when that exact process started
}
```

The watchdog's decision order becomes:

```
clean_exit flag   ->  "quit"     the app finished shutting down; stand down
lease active      ->  "exiting"  the app is on its way out; do not relaunch
neither           ->  "crashed"  relaunch
```

### A lease belongs to a process

A lease only means something for the process that wrote it. Two guards stop
a leftover lease from silencing the watchdog:

* the lease's `pid` must match the heartbeat's `pid`;
* the heartbeat must be recent (`HEARTBEAT_STALE_SEC`).

Without them, the lease left in the appdata folder by the previous session
would keep the watchdog from starting the app at Windows logon.

A pid alone is not enough, though: **the OS recycles pids**. A lease left
behind by a crashed generation would be attributed to a later, unrelated
process that happens to have inherited its pid — and for a permanent lease
that would silence the watchdog *forever*. So a lease written by Python also
records `process_create_time` (the OS's start time for that exact process),
and ownership is only claimed when **both** the pid and the create-time
match. The Inno Setup uninstaller cannot call Python and writes neither, so
it writes `pid: 0` and no fingerprint; that lease is recognised as
*permanent* and is never dropped at startup.

A **permanent** lease (`grace_s = "inf"`, the uninstall marker) is the one
exception: it always wins, and the watchdog exits.

## Where the lease is claimed

| Where | Reason | Grace | Why here |
|---|---|---|---|
| `gui/WebGUI.py` `closeEvent` (user branch) | `user_exit` | 120s | Before the ~8s teardown starts |
| `gui/WebGUI.py` `closeEvent` (OTA branch) | `ota_update` | 600s | The installer replaces the exe |
| `ota/core/installer.py` `_terminate_current_process` | `ota_update` | 600s | Before the process is hard-killed |
| `utils/platform_signals.py` (SIGTERM/SIGINT/SIGBREAK) | `signal_*` | 120s | The default disposition kills the process |
| `build_system/ecan_build.py` (Inno Setup) | `uninstall` | ∞ | The app is removed for good |
| `utils/unattended.py` `disable_for_uninstall` | `uninstall` | ∞ | Python-side uninstall path |

On startup (`utils/exit_intent.py::on_startup`, called from `main.py`) a
lease written by a *previous* process is dropped — otherwise a crash of the
app that is running now would go unnoticed for the whole grace window.

## Dev / CI / test environments

`utils/unattended.py::should_skip_watchdog` skips the watchdog when:

* `ECAN_NO_WATCHDOG` is set to a truthy value (`1`/`true`/`yes`/`on`);
* the app runs in dev mode (`config.app_settings.app_settings.is_dev_mode`)
  **and** `ECAN_DEV_WATCHDOG` is not set to a truthy value;
* we are inside a pytest run (`PYTEST_CURRENT_TEST` is set).

### Running the watchdog while developing

Dev mode skips the watchdog by default — a stale `unattended.json` left by a
QA run would otherwise restart every `python main.py` the developer launches.
To work on the watchdog itself, or to reproduce a crash-loop against the
source tree, set the opt-in for that shell:

```
ECAN_DEV_WATCHDOG=1 python main.py          # or export it in your shell
```

This only lifts the *dev-mode* skip. `ECAN_NO_WATCHDOG` still wins, and the
pytest guard still applies — a value exported in a shell profile can never
make CI spawn watchdogs. The opt-in is an environment variable rather than a
setting because `unattended.json` is exactly the file a stale copy can
silently re-enable.

The watchdog itself (`main.py --watchdog`) has no dev gate and can always be
run directly.

`utils/platform_signals.py` additionally skips installing real signal
handlers under pytest, so Ctrl+C still works for the test runner.

## Cross-platform notes

| | Linux | macOS | Windows |
|---|---|---|---|
| SIGTERM | ✅ | ✅ | ❌ does not exist (`ValueError`) |
| SIGINT | ✅ | ✅ | console mode only |
| SIGBREAK | ❌ | ❌ | ✅ |
| `atexit` | ✅ | ✅ | ✅ (but `os._exit` skips it) |

Every signal is probed individually; a platform that refuses one handler
never prevents the others. On Windows the user-quit path is covered by the
Qt `closeEvent`, which every Windows user actually goes through.

The Inno Setup uninstaller cannot call Python, so it writes the lease file
itself. The format is a contract pinned by
`tests/unit/test_installer_lease_contract.py` — keep both sides in sync.

## Tests

```
tests/unit/test_exit_intent.py            31   file format, expiry, clock skew
tests/unit/test_shutdown_lease.py           8   grace windows per reason
tests/unit/test_exit_intent_startup.py      6   stale-lease cleanup
tests/unit/test_platform_signals.py        10   per-platform signal install
tests/unit/test_unattended_dev_skip.py     18   dev / CI / test skip rules
tests/unit/test_uninstall_ota_lease.py      9   lease format vs the installer
tests/unit/test_ota_lease.py                4   OTA installer claims the lease
tests/unit/test_installer_lease_contract.py 9   Inno Setup path contract
tests/unit/test_watchdog_lease_scope.py     8   lease scope, permanent lease
```

## Out of scope

* **Worker subprocesses** — the watchdog only monitors the main process's
  heartbeat pid. Worker leases belong to the task-lease work (L3).
* **`main.py` `sys.exit` paths** — those are startup failures, where the
  watchdog *should* retry.
* **macOS/Linux uninstallers** — no equivalent hook exists in this repo.

## Related

* `utils/app_watchdog.py` — the watchdog itself.
* `utils/crash_boundary.py` — the heartbeat and the legacy clean-exit flag.
* `utils/unattended.py` — the unattended switch and the Windows logon task.
