"""Unattended mode: start eCan at Windows logon and restart it when it crashes
or hangs (utils/app_watchdog.py). Off by default; switched in Settings.

On: a marker file (``unattended.json`` in the app data folder) plus a Windows
logon task "eCan Unattended" that runs ``eCan --watchdog``; the watchdog
starts eCan and keeps it up. While on, eCan also makes sure a watchdog is
running when it starts by hand, so a crash is covered either way.
Off: both removed. Every command runs without a console window.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from utils.logger_helper import logger_helper as logger

TASK_NAME = "eCan Unattended"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _marker() -> Path:
    from config.app_info import app_info
    return Path(app_info.appdata_path) / "unattended.json"


def is_enabled() -> bool:
    try:
        return bool(json.loads(_marker().read_text(encoding="utf-8")).get("enabled"))
    except Exception:
        return False


def watchdog_command() -> list:
    from utils.app_watchdog import app_command
    return app_command() + ["--watchdog"]


def _schtasks(args: list) -> subprocess.CompletedProcess:
    return subprocess.run(["schtasks"] + args, capture_output=True, text=True,
                          creationflags=_NO_WINDOW, timeout=30)


def _task_command_line() -> str:
    return " ".join(f'"{a}"' if " " in a or not a else a for a in watchdog_command())


def set_enabled(enabled: bool) -> dict:
    """Turn unattended mode on/off. Returns {enabled, logon_task, error?}."""
    result = {"enabled": bool(enabled), "logon_task": False}
    _marker().write_text(json.dumps({"enabled": bool(enabled)}), encoding="utf-8")
    if sys.platform != "win32":
        return result
    try:
        if enabled:
            r = _schtasks(["/Create", "/TN", TASK_NAME, "/TR", _task_command_line(),
                           "/SC", "ONLOGON", "/RL", "LIMITED", "/F"])
            result["logon_task"] = r.returncode == 0
            if r.returncode != 0:
                result["error"] = (r.stderr or r.stdout or "").strip()[:300]
            ensure_watchdog_running()
        else:
            _schtasks(["/Delete", "/TN", TASK_NAME, "/F"])
            _stop_watchdog()
    except Exception as e:
        result["error"] = str(e)
    logger.info(f"[Unattended] set {'on' if enabled else 'off'}: {result}")
    return result


def status() -> dict:
    out = {"enabled": is_enabled(), "logon_task": False, "watchdog_running": _watchdog_pid() is not None}
    if sys.platform == "win32":
        try:
            out["logon_task"] = _schtasks(["/Query", "/TN", TASK_NAME]).returncode == 0
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
        pid, _create_time = _read_lock_identity(runlogs_dir() / "watchdog.lock")
        if pid and psutil.pid_exists(pid) and "--watchdog" in " ".join(psutil.Process(pid).cmdline()):
            return pid
    except Exception:
        pass
    return None


def _stop_watchdog() -> None:
    import psutil
    pid = _watchdog_pid()
    if pid:
        try:
            psutil.Process(pid).terminate()
        except Exception:
            pass


def _truthy_env(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in ("1", "true", "yes", "on")


def _is_dev_mode() -> bool:
    """True when eCan runs from the source tree instead of a packaged build."""
    try:
        from config.app_settings import app_settings
        return bool(app_settings.is_dev_mode)
    except Exception:
        return False


def should_skip_watchdog() -> bool:
    """Whether the crash/hang watchdog must not be started here.

    The watchdog relaunches eCan when it dies — right for a production kiosk,
    wrong while a developer iterates: a stale ``unattended.json`` left behind
    by a QA run would restart every ``python main.py`` after the developer
    closed the window.

    Skip when:
      * ``ECAN_NO_WATCHDOG`` is set to a truthy value (explicit opt-out for
        CI, installer tests, performance runs);
      * the app runs in dev mode and ``ECAN_DEV_WATCHDOG`` is not set;
      * we are inside a pytest run.

    ``ECAN_DEV_WATCHDOG`` is the dev-mode opt-in: it exists so a developer
    working on the watchdog itself, or reproducing a crash-loop, can run it
    against the source tree. It is an environment variable rather than a
    setting because ``unattended.json`` is exactly the file a stale copy can
    silently re-enable; an env var is scoped to the shell that sets it. The
    explicit opt-out still wins, so a developer's exported variable cannot
    make CI spawn watchdogs.
    """
    if _truthy_env("ECAN_NO_WATCHDOG"):
        return True
    if _is_dev_mode() and not _truthy_env("ECAN_DEV_WATCHDOG"):
        return True
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    return False


def ensure_watchdog_running() -> None:
    """When unattended mode is on and no watchdog is up, start one."""
    if not is_enabled() or _watchdog_pid() is not None:
        return
    if should_skip_watchdog():
        logger.info("[Unattended] watchdog not started (dev/CI/test environment)")
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
        marker = Path(log_dir) / "unattended.json" if log_dir else _marker()
        if marker.exists():
            marker.unlink()
    except Exception as exc:
        logger.debug(f"[Unattended] could not remove marker: {exc}")
    try:
        _stop_watchdog()
    except Exception as exc:
        logger.debug(f"[Unattended] could not stop watchdog: {exc}")
    if sys.platform == "win32":
        try:
            _schtasks(["/Delete", "/TN", TASK_NAME, "/F"])
        except Exception as exc:
            logger.debug(f"[Unattended] could not remove logon task: {exc}")
    try:
        from utils.exit_intent import claim_shutdown_lease
        claim_shutdown_lease(reason="uninstall", log_dir=log_dir)
    except Exception as exc:
        logger.debug(f"[Unattended] could not write uninstall lease: {exc}")
    logger.info("[Unattended] unattended mode disabled for uninstall")
