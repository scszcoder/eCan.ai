"""Worker boot identity: which process is the current eCan run?

A boot id is the smallest signal that says "the work I am about to do
belongs to **this** process". Used as the namespace for leases: any lease
written by another boot id is automatically orphaned, even if its pid
happens to match a recycled OS pid.

Why a bare pid is not enough
----------------------------
The first version of this module compared ``pid`` only. That is wrong: the
OS reuses pids, and on a busy desktop it reuses them fast. A worker that
crashed an hour ago left ``boot_id.json`` behind; by the time the next
launch happens the OS may well have handed that pid back, and ``claim_boot``
would happily hand the *dead* generation's identity to the *live* process —
silently erasing the one distinction boot_id exists to make.

The fix is the fingerprint ``crash_boundary.py`` already uses: pair the pid
with ``process_create_time`` (when the OS started that exact process). Pid
plus create-time is unique for as long as the process lives; a recycled pid
comes with a different create-time.

Failures we deliberately guard against:

* never leave a half-written file for another worker to read (atomic
  rename);
* oversized / corrupt / partial files are treated as *no* marker;
* ``release_boot`` will not delete a marker it cannot prove it owns — an
  unreadable file is somebody else's evidence, not garbage to clean up;
* ``claim_boot`` never raises and never returns an empty id — a worker must
  keep running when appdata is unwritable, and an empty id written into
  every lease would be worse than a non-durable one. Durability is
  observable separately, through ``boot_is_durable()``.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Optional

from utils.logger_helper import logger_helper as logger

BOOT_ID_NAME = "boot_id.json"
#: Refuse to read anything larger than this — a corrupt/hostile file must
#: not be loaded into memory just to make a sticky decision.
MAX_BOOT_BYTES = 4096

#: How far apart two create-times may be and still count as the same
#: process. Mirrors utils/crash_boundary.py — comfortably wider than the
#: clock's resolution, far narrower than any real process lifetime.
CREATE_TIME_TOLERANCE_S = 2.0


class _Unset:
    """Sentinel so "not yet computed" differs from "computed as None"."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<unset>"


_UNSET = _Unset()

#: This process's create-time, computed once. ``None`` means psutil was
#: unavailable, in which case identity falls back to pid-only and every
#: claim is treated as a new generation (the safe direction).
_PROCESS_CREATE_TIME = _UNSET

#: Boot ids already handed out by *this* process, keyed by marker path.
#: Process-local, so idempotence does not depend on the file being
#: readable, and two installs with different log_dirs stay independent.
_PROCESS_BOOT_IDS: dict[str, str] = {}


def current_create_time() -> Optional[float]:
    """Public alias for :func:`_current_create_time`."""
    return _current_create_time()


def _current_create_time() -> Optional[float]:
    """When this exact process started, per the OS. None when unknown."""
    global _PROCESS_CREATE_TIME
    if isinstance(_PROCESS_CREATE_TIME, _Unset):
        try:
            import psutil
            _PROCESS_CREATE_TIME = float(psutil.Process(os.getpid()).create_time())
        except Exception:
            _PROCESS_CREATE_TIME = None
    return _PROCESS_CREATE_TIME


def process_alive(pid, create_time: Optional[float] = None) -> Optional[bool]:
    """Is *pid* still running, optionally checking it is the same process?

    Returns True / False, or None when the question cannot be answered
    (no psutil, or the OS refuses to say). Callers must treat None as
    "unknown" and fall back to a time-based decision — never as "alive",
    and never as "dead".
    """
    try:
        pid = int(pid)
    except Exception:
        return False
    if pid <= 0:
        return False

    mine = _current_create_time()
    if pid == os.getpid():
        if create_time is None or mine is None:
            return True
        try:
            return abs(mine - float(create_time)) <= CREATE_TIME_TOLERANCE_S
        except Exception:
            return True

    try:
        import psutil
    except Exception:
        return None
    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        return None
    except Exception:
        return None

    try:
        if create_time is not None:
            try:
                if abs(float(proc.create_time()) - float(create_time)) > CREATE_TIME_TOLERANCE_S:
                    return False
            except psutil.NoSuchProcess:
                return False
            except Exception:
                pass                       # cannot read it; fall through
        return bool(proc.is_running())
    except Exception:
        return None


def _runlogs_dir(log_dir: Optional[str] = None) -> Path:
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
        logger.debug(f"[WorkerBoot] cannot create runlogs dir: {exc}")
    return path


def boot_id_path(log_dir: Optional[str] = None) -> Path:
    """Path to the singleton boot-id marker for this process."""
    return _runlogs_dir(log_dir) / BOOT_ID_NAME


def _cache_key(log_dir: Optional[str] = None) -> str:
    try:
        return str(boot_id_path(log_dir).resolve())
    except Exception:
        try:
            return str(boot_id_path(log_dir))
        except Exception:
            return f"<unresolvable:{os.getpid()}>"


def _read(log_dir: Optional[str] = None) -> Optional[dict]:
    """Return the boot-id payload, or None when there is nothing trustworthy.

    Permissive on ``process_create_time`` so markers written by an older
    build still parse — the strictness lives in ``_is_this_process``,
    which is the only place that decides ownership.
    """
    try:
        path = boot_id_path(log_dir)
        try:
            if path.stat().st_size > MAX_BOOT_BYTES:
                return None
        except Exception:
            return None
        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            return None
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        if not isinstance(data.get("boot_id"), str) or not data["boot_id"]:
            return None
        if not isinstance(data.get("pid"), int) or isinstance(data.get("pid"), bool):
            return None
        return data
    except Exception:
        return None


def _is_this_process(record: dict) -> bool:
    """True only when *record* provably belongs to the process asking.

    A matching pid is necessary but not sufficient — that is the whole
    point of the create-time fingerprint. When either side's create-time is
    unknown we refuse, because "probably ours" is exactly the judgement
    that leaked a dead generation's identity in the first place.
    """
    try:
        if int(record.get("pid") or -1) != os.getpid():
            return False
    except Exception:
        return False
    stored = record.get("process_create_time")
    mine = _current_create_time()
    if stored is None or mine is None:
        return False
    try:
        return abs(float(stored) - float(mine)) <= CREATE_TIME_TOLERANCE_S
    except Exception:
        return False


def read_boot(log_dir: Optional[str] = None) -> Optional[dict]:
    """Public accessor: return the current boot record, or None."""
    return _read(log_dir)


def read_current_pid(log_dir: Optional[str] = None) -> Optional[int]:
    """The pid recorded in the marker, if any."""
    data = _read(log_dir)
    return int(data["pid"]) if data else None


def claim_boot(log_dir: Optional[str] = None) -> str:
    """Claim a boot id for *this* process.

    Returns a boot id (a UUID4 hex). Never raises and never returns an
    empty string: a worker must keep running even when appdata is not
    writable, and an empty id would be worse than a non-durable one — it
    would be written into every lease, making them indistinguishable.

    What *is* observable is durability: when the marker could not be
    persisted, :func:`boot_is_durable` reports False, so a caller that
    cares can tell that nobody will later be able to prove this process
    owns the marker.

    Calling it twice from the same process returns the same id. A marker
    belonging to a *previous* generation is never adopted, even when the OS
    has recycled its pid onto us.
    """
    key = _cache_key(log_dir)
    already = _PROCESS_BOOT_IDS.get(key)
    if already:
        return already

    existing = _read(log_dir)
    if existing and _is_this_process(existing):
        _PROCESS_BOOT_IDS[key] = str(existing["boot_id"])
        return _PROCESS_BOOT_IDS[key]

    boot_id = uuid.uuid4().hex
    if not _write(boot_id, log_dir):
        # The id is still unique and usable, but it left no trace on disk:
        # nobody can later prove this process owns it. Loud, because a
        # silently non-durable identity looks like a working one.
        logger.warning(
            "[WorkerBoot] boot id could not be persisted; the marker is "
            "not durable (appdata unwritable?)"
        )
    _PROCESS_BOOT_IDS[key] = boot_id
    return boot_id


def boot_is_durable(log_dir: Optional[str] = None) -> bool:
    """True when this process's marker is on disk and provably ours.

    False when the marker was never written, was written by somebody else,
    or cannot be read back. A caller that needs a durable identity (rather
    than merely a unique one) must check this.
    """
    existing = _read(log_dir)
    return bool(existing and _is_this_process(existing))


def refresh_boot(log_dir: Optional[str] = None) -> Optional[str]:
    """Re-stamp the marker to advertise liveness without changing identity.

    Returns the existing id on success, or None when this process does not
    own the marker (no marker, or somebody else's).
    """
    existing = _read(log_dir)
    if not existing or not _is_this_process(existing):
        return None
    if not _write(existing["boot_id"], log_dir):
        return None
    return str(existing["boot_id"])


def release_boot(log_dir: Optional[str] = None) -> None:
    """Drop the marker. Used by a worker on a clean stop.

    Deletes only what this process can prove it wrote. A marker we cannot
    parse is *not* ours to delete: it is the forensic record of whichever
    generation crashed, and that record is exactly what recovery reads
    later.
    """
    key = _cache_key(log_dir)
    try:
        path = boot_id_path(log_dir)
        if not path.exists():
            _PROCESS_BOOT_IDS.pop(key, None)
            return
        existing = _read(log_dir)
        if existing is None:
            logger.debug("[WorkerBoot] marker unreadable; leaving it in place")
            return
        if not _is_this_process(existing):
            logger.debug(
                "[WorkerBoot] refusing to delete a marker this process does "
                f"not own (our pid={os.getpid()}, marker pid={existing.get('pid')})"
            )
            return
        path.unlink()
        _PROCESS_BOOT_IDS.pop(key, None)
    except Exception as exc:
        logger.debug(f"[WorkerBoot] could not release marker: {exc}")


def _write(boot_id: str, log_dir: Optional[str] = None) -> bool:
    """Atomic write of the boot record. Best-effort: returns False on error."""
    try:
        path = boot_id_path(log_dir)
        payload = {
            "boot_id": str(boot_id),
            "pid": int(os.getpid()),
            "process_create_time": _current_create_time(),
            "stamp": time.time(),
        }
        tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
        return True
    except Exception as exc:
        logger.debug(f"[WorkerBoot] could not write boot record: {exc}")
        return False