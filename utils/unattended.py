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
    from utils.app_watchdog import runlogs_dir
    try:
        pid = int((runlogs_dir() / "watchdog.lock").read_text().strip() or 0)
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


def ensure_watchdog_running() -> None:
    """When unattended mode is on and no watchdog is up, start one."""
    if not is_enabled() or _watchdog_pid() is not None:
        return
    flags = _NO_WINDOW
    if sys.platform == "win32":
        flags |= subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0x8)
    subprocess.Popen(watchdog_command(), creationflags=flags, close_fds=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    logger.info("[Unattended] crash/hang watchdog started")
