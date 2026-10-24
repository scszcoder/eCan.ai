"""Unattended mode: start eCan at Windows logon and restart it when it crashes
or hangs (utils/app_watchdog.py). Off by default; switched in Settings.

On: a marker file (``unattended.json`` in the app data folder) plus a Windows
logon task "eCan Unattended" that runs ``eCan --watchdog``; the watchdog
starts eCan and keeps it up. While on, eCan also makes sure a watchdog is
running when it starts by hand, so a crash is covered either way.
Off: both removed. Every command runs without a console window.

The marker carries two independent switches: ``enabled`` (keep eCan alive on
this PC) and ``allow_in_dev`` (also run a watchdog against the source tree).
The second exists because a developer iterating on a crashing build does not
want an automatic relaunch, while a developer *deliberately* reproducing a
crash-loop does. Both default to off.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from utils.logger_helper import logger_helper as logger

#: The logon task name every build used before it was derived from the app
#: name. Still deleted on cleanup so an upgraded install does not leave a
#: second task behind (see task_name()).
LEGACY_TASK_NAME = "eCan Unattended"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def task_name() -> str:
    """The Windows logon task name, e.g. ``"eCan Unattended"``.

    Derived from the app name instead of hard-coded. The name used to be the
    constant ``"eCan Unattended"``, so every build variant (eCan.cn,
    eCan.intl) shared one task: installing the second variant overwrote the
    first one's logon task, and the two builds then fought over the same
    watchdog singleton. Result: a logon that started only one of them, or
    neither, with no error anywhere.
    """
    try:
        from config.constants import APP_NAME
        name = str(APP_NAME or "").strip()
    except Exception:
        name = ""
    return f"{name or 'eCan'} Unattended"


def _task_names() -> list:
    """The current logon task name plus the legacy one, deduplicated."""
    current = task_name()
    return [current] if current == LEGACY_TASK_NAME else [current, LEGACY_TASK_NAME]


def _delete_logon_task() -> None:
    """Remove every logon task this app may have created. Never raises."""
    for name in _task_names():
        try:
            _schtasks(["/Delete", "/TN", name, "/F"])
        except Exception as exc:
            logger.debug(f"[Unattended] could not remove logon task {name!r}: {exc}")


def _marker() -> Path:
    from config.app_info import app_info
    return Path(app_info.appdata_path) / "unattended.json"


def _read_marker() -> dict:
    """The marker file's contents, or {} when absent/unreadable."""
    try:
        data = json.loads(_marker().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def is_enabled() -> bool:
    return bool(_read_marker().get("enabled"))


def allows_dev_watchdog() -> bool:
    """Whether the user also wants a watchdog while running from source.

    A separate flag from ``is_enabled()`` on purpose. ``enabled`` means "keep
    eCan alive on this PC"; in dev the user is iterating, not running a kiosk,
    so it must not imply "relaunch my crashed build". An older marker (or a
    stale copy from a QA run) has no ``allow_in_dev``, and therefore keeps the
    dev skip -- so the flag cannot be switched on by accident, which is the
    property the environment variable used to provide.
    """
    return bool(_read_marker().get("allow_in_dev"))


def _write_marker(enabled: bool, allow_in_dev: bool) -> None:
    _marker().write_text(json.dumps({"enabled": bool(enabled),
                                     "allow_in_dev": bool(allow_in_dev)}),
                         encoding="utf-8")


def watchdog_command() -> list:
    from utils.app_watchdog import app_command
    return app_command() + ["--watchdog"]


def _schtasks(args: list) -> subprocess.CompletedProcess:
    return subprocess.run(["schtasks"] + args, capture_output=True, text=True,
                          creationflags=_NO_WINDOW, timeout=30)


def _task_command_line() -> str:
    return " ".join(f'"{a}"' if " " in a or not a else a for a in watchdog_command())


def set_enabled(enabled: bool, allow_in_dev: bool | None = None) -> dict:
    """Turn unattended mode on/off.

    ``allow_in_dev`` is the separate opt-in for running a watchdog against
    the source tree. ``None`` (the default) leaves the stored value alone, so
    toggling unattended mode never silently flips the dev behaviour; pass it
    explicitly to change it.

    Returns ``{enabled, allow_in_dev, logon_task, watchdog_available, error?}``.
    ``watchdog_available`` is reported because ``enabled`` alone does not
    mean the feature is live: the marker records the user's choice, while
    ``should_skip_watchdog()`` decides whether a watchdog can actually be
    started in the current environment. See ``status()``.
    """
    current = _read_marker()
    dev_flag = current.get("allow_in_dev", False) if allow_in_dev is None else bool(allow_in_dev)
    # Answered against dev_flag, not the stored marker: the value being
    # written is not readable yet.
    result = {"enabled": bool(enabled), "allow_in_dev": bool(dev_flag), "logon_task": False,
              "watchdog_available": not should_skip_watchdog(allow_in_dev=dev_flag)}
    _write_marker(enabled=bool(enabled), allow_in_dev=bool(dev_flag))
    if sys.platform != "win32":
        return result
    try:
        if enabled:
            name = task_name()
            # An older build registered the task under the legacy name; leaving
            # it in place would start a second watchdog at every logon.
            _delete_logon_task()
            r = _schtasks(["/Create", "/TN", name, "/TR", _task_command_line(),
                           "/SC", "ONLOGON", "/RL", "LIMITED", "/F"])
            result["logon_task"] = r.returncode == 0
            if r.returncode != 0:
                result["error"] = (r.stderr or r.stdout or "").strip()[:300]
            ensure_watchdog_running()
        else:
            _delete_logon_task()
            _stop_watchdog()
    except Exception as e:
        result["error"] = str(e)
    logger.info(f"[Unattended] set {'on' if enabled else 'off'}: {result}")
    return result


def status() -> dict:
    """What Settings renders: the switch states plus what is really running.

    ``enabled`` is the user's choice for this PC (the marker file).
    ``allow_in_dev`` is their separate opt-in for a source-tree run.
    ``watchdog_available`` is whether a watchdog can run at all here. The
    three differ in dev/CI -- ``should_skip_watchdog()`` returns True and no
    watchdog is ever started -- so showing only ``enabled`` would report
    "on" for a feature that is demonstrably doing nothing.
    """
    allow_dev = allows_dev_watchdog()
    out = {"enabled": is_enabled(), "allow_in_dev": allow_dev, "logon_task": False,
           "watchdog_running": _watchdog_pid() is not None,
           # The UI offers the dev opt-in only in a source-tree run, so it
           # needs to know which one this is -- it cannot infer it from
           # watchdog_available, which is also false under CI.
           "dev_mode": _is_dev_mode(),
           "watchdog_available": not should_skip_watchdog(allow_in_dev=allow_dev)}
    if sys.platform == "win32":
        try:
            out["logon_task"] = _schtasks(["/Query", "/TN", task_name()]).returncode == 0
        except Exception:
            pass
    return out


def _watchdog_pid():
    import psutil
    from utils.app_watchdog import runlogs_dir, _read_lock_identity
    try:
        # The lock file carries (pid, create_time) as JSON -- a bare pid
        # is not an identity, because the OS recycles pids. A legacy
        # bare-pid file still parses.
        pid, create_time = _read_lock_identity(runlogs_dir() / "watchdog.lock")
        if not pid or not psutil.pid_exists(pid):
            return None
        proc = psutil.Process(pid)
        # The fingerprint is what makes the pid an identity. Without this
        # check a recycled pid makes the caller believe a watchdog is
        # running: ensure_watchdog_running() then returns early and the PC
        # is left with no crash cover at all, silently.
        if create_time:
            from utils.app_watchdog import CREATE_TIME_TOLERANCE_S
            if abs(proc.create_time() - float(create_time)) > CREATE_TIME_TOLERANCE_S:
                return None
        if "--watchdog" in " ".join(proc.cmdline()):
            return pid
    except Exception:
        pass
    return None


#: How long to wait for a terminated watchdog to actually die before
#: escalating to SIGKILL. The watchdog has no signal handler, so it dies
#: immediately on SIGTERM (measured: ~2 ms); the wait is for the OS to
#: reap it. The budget is generous because it is only spent when
#: something is actually wrong.
WATCHDOG_STOP_TIMEOUT_S = 5.0
#: How long to wait after SIGKILL before giving up and returning anyway.
#: A logout must not be held hostage by a wedged watchdog.
WATCHDOG_KILL_TIMEOUT_S = 2.0


def _stop_watchdog() -> None:
    """Terminate the watchdog and wait until it is really gone.

    ``psutil.Process.terminate()`` sends SIGTERM and returns immediately —
    it does not wait for the process to die. That is not good enough here:
    the start path decides whether a watchdog is already running by asking
    ``_watchdog_pid()``, which only checks that the pid is alive and its
    cmdline contains ``--watchdog``. A watchdog that has been *sent* SIGTERM
    but has not died yet still satisfies both checks.

    So without the wait, "log out, then log back in" can lose the
    watchdog entirely: the stop sends SIGTERM and returns, the start sees
    the dying watchdog and skips starting a replacement, and then the
    watchdog dies. Unattended mode is silently dead for the rest of the
    session — a crash of eCan is no longer covered, and nothing reports
    it, because the thing that would have reported it is the thing that
    did not start.

    Escalate to SIGKILL if the process does not go away, and give up
    after that rather than block the logout forever.
    """
    import psutil
    pid = _watchdog_pid()
    if not pid:
        return
    try:
        proc = psutil.Process(pid)
    except Exception:
        return
    try:
        proc.terminate()
    except Exception:
        return

    try:
        proc.wait(timeout=WATCHDOG_STOP_TIMEOUT_S)
        return
    except Exception:
        pass

    # Still alive after SIGTERM. Escalate.
    try:
        proc.kill()
    except Exception:
        pass
    try:
        proc.wait(timeout=WATCHDOG_KILL_TIMEOUT_S)
    except Exception:
        logger.debug("[Unattended] watchdog did not die after SIGKILL")


def stop_watchdog() -> None:
    """Stop the crash/hang watchdog, if one is running.

    The counterpart of ``ensure_watchdog_running``.  Called when the user
    logs out: unattended mode exists to keep a *signed-in* eCan alive, so
    once nobody is signed in there is nothing to keep alive — and a
    watchdog that relaunches the app would just bring back a login screen
    the user deliberately walked away from.
    """
    try:
        _stop_watchdog()
    except Exception as exc:
        logger.debug(f"[Unattended] could not stop watchdog: {exc}")


def _truthy_env(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in ("1", "true", "yes", "on")


def _is_dev_mode() -> bool:
    """True when eCan runs from the source tree instead of a packaged build."""
    try:
        from config.app_settings import app_settings
        return bool(app_settings.is_dev_mode)
    except Exception:
        return False


def should_skip_watchdog(allow_in_dev: bool | None = None) -> bool:
    """Whether the crash/hang watchdog must not be started here.

    The watchdog relaunches eCan when it dies — right for a production kiosk,
    wrong while a developer iterates: a crash while debugging would spawn a
    replacement instance under the developer's feet. (A *clean* exit is safe:
    the app records ``clean_exit`` and the watchdog stands down, so closing
    the window does not bounce.)

    Skip when:
      * ``ECAN_NO_WATCHDOG`` is set to a truthy value (explicit opt-out for
        CI, installer tests, performance runs);
      * the app runs in dev mode and neither ``ECAN_DEV_WATCHDOG`` nor the
        marker's ``allow_in_dev`` is set;
      * we are inside a pytest run.

    Two opt-ins, deliberately equivalent in effect but different in scope:

    * ``ECAN_DEV_WATCHDOG`` — scoped to one shell, for a developer who wants
      it *for this run*.
    * ``allow_in_dev`` in ``unattended.json`` — persisted, so the Settings UI
      can drive it. It defaults to off and lives beside ``enabled`` rather
      than replacing it, which is what keeps the property the env var was
      chosen for: a stale or hand-edited marker cannot silently arm a
      watchdog. Both must be *explicitly* set.

    The explicit opt-out still wins over both, so an exported opt-in in a
    developer's shell profile cannot make CI spawn watchdogs. The pytest
    guard is absolute for the same reason: a test run must never spawn one,
    whatever the marker says.
    """
    if _truthy_env("ECAN_NO_WATCHDOG"):
        return True
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    if _is_dev_mode() and not (_truthy_env("ECAN_DEV_WATCHDOG") or _dev_opt_in(allow_in_dev)):
        return True
    return False


def _dev_opt_in(allow_in_dev: bool | None) -> bool:
    """The effective dev opt-in: an explicit argument wins over the marker."""
    if allow_in_dev is not None:
        return bool(allow_in_dev)
    return allows_dev_watchdog()


def ensure_watchdog_running() -> None:
    """When unattended mode is on and no watchdog is up, start one."""
    if not is_enabled() or _watchdog_pid() is not None:
        return
    if should_skip_watchdog():
        logger.info("[Unattended] watchdog not started (dev mode without allow_in_dev, "
                    "or CI/opt-out/test environment)")
        return
    flags = _NO_WINDOW
    if sys.platform == "win32":
        flags |= subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0x8)
    subprocess.Popen(watchdog_command(), creationflags=flags, close_fds=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    logger.info("[Unattended] crash/hang watchdog started")


def disable_for_uninstall(log_dir: str | None = None) -> None:
    """Stop unattended mode for good: the user is removing the app.

    Removes the marker (so a later reinstall does not immediately re-arm the
    watchdog), stops a running watchdog, removes the Windows logon task and
    writes a permanent shutdown lease so the watchdog does not relaunch an
    executable that no longer exists.

    Never raises — an uninstall must not fail because of cleanup.
    """
    try:
        # The marker lives in the app data folder, not in runlogs -- so a
        # caller that passes the runlogs directory (the natural reading of
        # ``log_dir``, and what exit_intent uses) needs the parent. Both
        # spellings are cleared: looking only inside runlogs meant the
        # uninstall never found the marker, so a reinstall came up with
        # unattended mode silently re-armed.
        if log_dir:
            base = Path(log_dir)
            candidates = [base / "unattended.json", base.parent / "unattended.json"]
        else:
            candidates = [_marker()]
        for marker in candidates:
            if marker.exists():
                marker.unlink()
    except Exception as exc:
        logger.debug(f"[Unattended] could not remove marker: {exc}")
    try:
        _stop_watchdog()
    except Exception as exc:
        logger.debug(f"[Unattended] could not stop watchdog: {exc}")
    if sys.platform == "win32":
        _delete_logon_task()
    try:
        from utils.exit_intent import claim_shutdown_lease
        claim_shutdown_lease(reason="uninstall", log_dir=log_dir)
    except Exception as exc:
        logger.debug(f"[Unattended] could not write uninstall lease: {exc}")
    logger.info("[Unattended] unattended mode disabled for uninstall")
