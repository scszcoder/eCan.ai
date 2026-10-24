import atexit
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import psutil

from utils.logger_helper import logger_helper as logger

_HEARTBEAT_NAME = "process_heartbeat.json"
_REPORT_NAME = "previous_process_report.json"
_PHASE_LOCK = threading.Lock()
_CURRENT_PHASE = "startup"
_CURRENT_DETAIL = ""
_MONITOR = None
_CLEAN_EXIT_MARKED = False
_MAIN_LOOP_TICK: dict = {}


def attach_main_loop(loop) -> None:
    """Record a tick from *loop* every 5 s into the heartbeat (main_loop_tick)."""
    async def _tick():
        import asyncio
        while True:
            _MAIN_LOOP_TICK["t"] = time.time()
            await asyncio.sleep(5)
    try:
        loop.create_task(_tick())
    except Exception as exc:
        logger.debug(f"[CrashBoundary] main-loop tick not attached: {exc}")


def _utc_iso(ts: float | None = None) -> str:
    return datetime.fromtimestamp(time.time() if ts is None else ts, timezone.utc).isoformat()


def _runlogs_dir(log_dir: str | None = None) -> Path:
    if log_dir:
        path = Path(log_dir)
    else:
        try:
            from config.app_info import app_info
            path = Path(app_info.appdata_path) / "runlogs"
        except Exception:
            path = Path.cwd() / "runlogs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def heartbeat_path(log_dir: str | None = None) -> Path:
    return _runlogs_dir(log_dir) / _HEARTBEAT_NAME


def report_path(log_dir: str | None = None) -> Path:
    return _runlogs_dir(log_dir) / _REPORT_NAME


def _atomic_write_json(path: Path, data: dict[str, Any], attempts: int = 5) -> None:
    """Write *data* so a reader never sees half a file, retrying a sharing hit.

    On Windows the final rename cannot replace a file another process holds
    open without FILE_SHARE_DELETE -- and the watchdog reads this very file
    every 15 s. A dropped write is not cosmetic: "the heartbeat stopped" is
    exactly the evidence the watchdog kills a frozen app on. So a transient
    collision is retried here instead of being reported once and forgotten.
    """
    payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    last: Exception | None = None
    for attempt in range(max(1, int(attempts))):
        try:
            tmp.write_text(payload, encoding="utf-8")
            os.replace(tmp, path)
            return
        except Exception as exc:
            last = exc
            time.sleep(0.02 * (attempt + 1))
    raise last if last is not None else RuntimeError("heartbeat write failed")


def set_crash_boundary_phase(phase: str) -> None:
    global _CURRENT_PHASE
    with _PHASE_LOCK:
        _CURRENT_PHASE = str(phase or "unknown")


def get_crash_boundary_phase() -> str:
    with _PHASE_LOCK:
        return _CURRENT_PHASE


def set_crash_boundary_detail(detail: str) -> None:
    """Record *what* is happening without moving the phase.

    The phase answers "may the watchdog judge this process yet" — it is
    "startup" until startup finishes and ``main_loop:*`` afterwards. A
    component that wants to describe its own activity (utils/memory_monitor.py
    reports memory-protection events) must not overwrite it: doing so used to
    leave the heartbeat stuck on ``memory:*`` for the rest of the session,
    which silently switched the hang detector off.
    """
    global _CURRENT_DETAIL
    with _PHASE_LOCK:
        _CURRENT_DETAIL = str(detail or "")


def get_crash_boundary_detail() -> str:
    with _PHASE_LOCK:
        return _CURRENT_DETAIL


def _process_alive(pid: int, create_time: float | None = None) -> bool:
    if pid <= 0:
        return False
    try:
        proc = psutil.Process(pid)
        if create_time is not None and abs(float(proc.create_time()) - float(create_time)) > 2.0:
            return False
        return proc.is_running()
    except Exception:
        return False


def _powershell_json(command: str, timeout_s: float = 5.0) -> Any:
    if os.name != "nt":
        return None
    startupinfo = None
    creationflags = 0
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creationflags = subprocess.CREATE_NO_WINDOW
    except Exception:
        startupinfo = None
        creationflags = 0
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return {"returncode": proc.returncode, "stderr": proc.stderr.strip()[:2000]}
        return json.loads(proc.stdout)
    except Exception as exc:
        return {"error": str(exc)}


def _collect_wer_reports(since_ts: float) -> list[dict[str, Any]]:
    if os.name != "nt":
        return []
    roots = []
    for env_name in ("LOCALAPPDATA", "PROGRAMDATA"):
        root = os.environ.get(env_name)
        if root:
            roots.append(Path(root) / "Microsoft" / "Windows" / "WER" / "ReportArchive")
            roots.append(Path(root) / "Microsoft" / "Windows" / "WER" / "ReportQueue")
    rows: list[dict[str, Any]] = []
    cutoff = max(0.0, since_ts - 3600.0)
    for root in roots:
        try:
            if not root.exists():
                continue
            for item in root.iterdir():
                try:
                    stat = item.stat()
                    if stat.st_mtime < cutoff:
                        continue
                    name = item.name.lower()
                    if not any(token in name for token in ("ecan", "python", "qt", "chrome", "chromium", "msedgewebview")):
                        continue
                    rows.append({
                        "path": str(item),
                        "name": item.name,
                        "mtime": stat.st_mtime,
                        "mtime_iso": _utc_iso(stat.st_mtime),
                    })
                except Exception:
                    continue
        except Exception:
            continue
    rows.sort(key=lambda r: float(r.get("mtime") or 0.0), reverse=True)
    return rows[:20]


def collect_windows_termination_evidence(previous: dict[str, Any]) -> dict[str, Any]:
    if os.name != "nt":
        return {}
    updated_at = float(previous.get("updated_at") or time.time())
    lookback_minutes = int(max(10, min(240, (time.time() - updated_at) / 60.0 + 30)))
    app_command = (
        f"$start=(Get-Date).AddMinutes(-{lookback_minutes});"
        "$ids=1000,1001,1002;"
        "Get-WinEvent -FilterHashtable @{LogName='Application'; StartTime=$start} -ErrorAction SilentlyContinue | "
        "Where-Object { $ids -contains $_.Id -or $_.ProviderName -match 'Windows Error Reporting|Application Error' } | "
        "Select-Object -First 30 TimeCreated,Id,ProviderName,LevelDisplayName,Message | ConvertTo-Json -Depth 4 -Compress"
    )
    system_command = (
        f"$start=(Get-Date).AddMinutes(-{lookback_minutes});"
        "Get-WinEvent -FilterHashtable @{LogName='System'; Id=2004; StartTime=$start} -ErrorAction SilentlyContinue | "
        "Select-Object -First 20 TimeCreated,Id,ProviderName,LevelDisplayName,Message | ConvertTo-Json -Depth 4 -Compress"
    )
    return {
        "lookback_minutes": lookback_minutes,
        "application_events": _powershell_json(app_command),
        "resource_exhaustion_events": _powershell_json(system_command),
        "wer_reports": _collect_wer_reports(updated_at),
    }


def report_previous_process_boundary(log_dir: str | None = None) -> dict[str, Any]:
    path = heartbeat_path(log_dir)
    if not path.exists():
        return {"unexpected": False, "reason": "no_previous_heartbeat"}
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"unexpected": False, "reason": f"unreadable_previous_heartbeat:{exc}"}
    pid = int(previous.get("pid") or 0)
    create_time = previous.get("process_create_time")
    clean_exit = bool(previous.get("clean_exit")) or str(previous.get("status") or "") == "clean_exit"
    still_alive = _process_alive(pid, create_time)
    unexpected = bool(pid and not clean_exit and not still_alive)
    report = {
        "unexpected": unexpected,
        "reason": "previous_process_died_unexpectedly" if unexpected else "previous_process_clean_or_alive",
        "detected_at": time.time(),
        "detected_at_iso": _utc_iso(),
        "previous": previous,
    }
    if unexpected:
        report["windows_evidence"] = collect_windows_termination_evidence(previous)
        try:
            _atomic_write_json(report_path(log_dir), report)
        except Exception:
            pass
        logger.warning(
            f"[CrashBoundary] Previous process died unexpectedly: "
            f"pid={pid} phase={previous.get('phase')} "
            f"last_seen={previous.get('updated_at_iso')} rss={previous.get('rss_mb')}MB"
        )
    return report


class CrashBoundaryHeartbeat:
    def __init__(self, log_dir: str | None = None, interval_s: float = 5.0):
        self.log_dir = log_dir
        self.interval_s = max(1.0, float(interval_s or 5.0))
        self.path = heartbeat_path(log_dir)
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.process = psutil.Process(os.getpid())
        self.started_at = time.time()
        self.process_create_time = self.process.create_time()

    def snapshot(self, *, clean_exit: bool = False, status: str = "running", reason: str = "") -> dict[str, Any]:
        try:
            mem = self.process.memory_info()
            rss_mb = round(mem.rss / (1024 * 1024), 1)
            vms_mb = round(mem.vms / (1024 * 1024), 1)
        except Exception:
            rss_mb = 0.0
            vms_mb = 0.0
        try:
            threads = int(self.process.num_threads())
        except Exception:
            threads = threading.active_count()
        now = time.time()
        return {
            "pid": os.getpid(),
            "process_create_time": self.process_create_time,
            "started_at": self.started_at,
            "started_at_iso": _utc_iso(self.started_at),
            "updated_at": now,
            "updated_at_iso": _utc_iso(now),
            "rss_mb": rss_mb,
            "vms_mb": vms_mb,
            "threads": threads,
            "phase": get_crash_boundary_phase(),
            "detail": get_crash_boundary_detail(),
            "status": status,
            "clean_exit": clean_exit,
            "reason": reason,
            # Last tick of the main event loop (utils/app_watchdog.py: a loop
            # frozen for minutes is a hang even while this thread still writes).
            "main_loop_tick": _MAIN_LOOP_TICK.get("t"),
            "argv": sys.argv[:],
        }

    def write(self, *, clean_exit: bool = False, status: str = "running", reason: str = "") -> None:
        _atomic_write_json(self.path, self.snapshot(clean_exit=clean_exit, status=status, reason=reason))

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.write()
        self.thread = threading.Thread(target=self._run, name="CrashBoundaryHeartbeat", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        failures = 0
        while not self.stop_event.wait(self.interval_s):
            try:
                self.write()
                if failures:
                    logger.info(f"[CrashBoundary] heartbeat recovered after {failures} failure(s)")
                failures = 0
            except Exception as exc:
                failures += 1
                # Loud once it is no longer a blip: the watchdog reads a stale
                # heartbeat as "frozen" and will kill a healthy app on it.
                log = logger.warning if failures >= 3 else logger.debug
                log(f"[CrashBoundary] heartbeat write failed ({failures}x): {exc}")

    def stop(self, reason: str = "clean_exit") -> bool:
        """Record the clean exit; True when the file really says so.

        The clean exit is the only thing that stops the watchdog from
        relaunching an app the user just closed, so a single dropped write
        would resurrect the app. Retry it.
        """
        self.stop_event.set()
        last: Exception | None = None
        for _ in range(3):
            try:
                self.write(clean_exit=True, status="clean_exit", reason=reason)
                return True
            except Exception as exc:
                last = exc
                time.sleep(0.05)
        logger.warning(f"[CrashBoundary] could not record the clean exit: {last}")
        return False


def start_crash_boundary_heartbeat(log_dir: str | None = None, interval_s: float | None = None) -> CrashBoundaryHeartbeat:
    global _MONITOR
    if _MONITOR is None:
        interval = interval_s if interval_s is not None else float(os.getenv("ECAN_CRASH_HEARTBEAT_INTERVAL_S", "5.0"))
        _MONITOR = CrashBoundaryHeartbeat(log_dir=log_dir, interval_s=interval)
        _MONITOR.start()
        atexit.register(mark_clean_exit, "atexit")
    return _MONITOR


def mark_clean_exit(reason: str = "clean_exit") -> None:
    global _CLEAN_EXIT_MARKED
    _CLEAN_EXIT_MARKED = True
    mon = _MONITOR
    if mon is not None:
        mon.stop(reason=reason)
    else:
        try:
            path = heartbeat_path()
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
            else:
                data = {}
            data.update({"clean_exit": True, "status": "clean_exit", "reason": reason, "updated_at": time.time(), "updated_at_iso": _utc_iso()})
            _atomic_write_json(path, data)
        except Exception:
            pass
