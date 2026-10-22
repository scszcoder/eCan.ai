"""Task lease: a worker declares "I am running task X" before it starts work,
and the zombie recovery walks the lease list at startup to find orphaned
tasks.

Without a lease, a worker that dies mid-task leaves no trace the supervisor
can use to roll back the DB row. The lease is the smallest possible signal
that fits that need:

* written to a file before any DB write begins (covering the in-between
  window);
* ``task_id``, ``boot_id``, ``worker_pid``, ``worker_create_time``,
  ``started_at``, ``ttl_s``;
* expired leases are reclaimed by the supervisor at startup;
* defensive read: oversized, corrupt, or partial files are all "no lease",
  so a crash mid-write never blocks the next run.

The lease is a contract about lifecycle. It is *not* the task's work
slot: any number of workers may inspect an expired lease and decide the
task is fair game.

What it *does* guarantee is that the lease itself is not handed to two
workers at once. Deciding who owns a task and recording that decision
is a read-decide-write, and read-decide-write is not atomic across
processes -- without an exclusivity primitive, two workers can both
read "no lease" and both write one, each then believing it holds the
task exclusively. The mutation therefore runs under a per-task advisory
lock (utils/file_lock.py). Note the distinction: the *lock* serialises
the bookkeeping, while the *lease* decides who may take the task over
when its holder dies.

Two rules make it trustworthy
-----------------------------
**Liveness beats the clock.** The TTL says "this lease is good for a while",
but a worker that was SIGKILLed will never renew it — waiting out the TTL
just leaves the user's task visibly stuck. So a lease whose worker is
provably gone is treated as *already* invalid, and orphan detection reports
it immediately. A worker that is merely slow keeps its lease until the TTL
lapses, as the contract has always said: long tasks must ``renew``.

**A pid alone is not an identity.** The OS recycles pids, so the lease
records the worker's ``process_create_time`` next to its pid. Pairing the
two is what makes "is this the same worker?" answerable across a reboot or
a busy desktop. Same reasoning as ``utils/worker_boot.py`` and
``utils/crash_boundary.py``.

Wall-clock time is still what drives the TTL — a monotonic clock cannot be
persisted across a reboot, and leases must survive one. The clock is only
ever consulted when liveness is unknown, and a *negative* age (clock jumped
backwards) is treated as "still inside the TTL", the safe direction: it
delays a takeover rather than handing a live task to a second worker.
"""
from __future__ import annotations

import json
import os
import contextlib
import hashlib
import time
import urllib.parse
from pathlib import Path
from typing import Optional

from utils import file_lock as fl
from utils import worker_boot as wb
from utils.logger_helper import logger_helper as logger

LEASE_DIR_NAME = "task_leases"
LEASE_NAME = "lease.json"
#: Suffix of the per-task advisory lock. It sits next to the lease file so
#: that the lock and the data it protects share a parent directory.
LOCK_SUFFIX = ".lck"
#: Refuse to read anything larger than this — a corrupt/hostile file must
#: not be loaded into memory just to make a sticky decision.
MAX_LEASE_BYTES = 4096
#: How long a mutating call waits for a peer to finish its own lease
#: write before giving up. A lease write is a single small file rename, so
#: this only ever elapses when a peer is wedged -- and a wedged peer must
#: not be able to block this task forever.
LOCK_TIMEOUT_S = 2.0


def _leases_root(log_dir: Optional[str] = None) -> Path:
    if log_dir:
        path = Path(log_dir)
    else:
        try:
            from config.app_info import app_info
            path = Path(app_info.appdata_path) / "runlogs"
        except Exception:
            path = Path.cwd() / "runlogs"
    root = path / LEASE_DIR_NAME
    try:
        root.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.debug(f"[TaskLease] cannot create leases dir: {exc}")
    return root


def lease_path(task_id: str, log_dir: Optional[str] = None) -> Path:
    """Path to *task_id*'s lease file."""
    return _leases_root(log_dir) / _safe_name(task_id)


def lock_path(task_id: str, log_dir: Optional[str] = None) -> Path:
    """Path to *task_id*'s advisory lock file."""
    return _leases_root(log_dir) / (_safe_name(task_id) + LOCK_SUFFIX)


@contextlib.contextmanager
def _locked(task_id: str, log_dir: Optional[str] = None,
            timeout: float = LOCK_TIMEOUT_S):
    """Serialise a lease mutation across processes.

    Yields True when the caller may proceed with its mutation. It yields
    False when a peer still holds the lock past *timeout*: the caller
    must then **refuse**, not proceed anyway. Writing while a peer sits
    inside its own read-decide-write is exactly the double-grant this
    lock exists to prevent, so a busy lock is treated as "not acquired"
    rather than as "acquire anyway".

    Locking that is unsupported on this platform (``acquire`` returns
    None) yields True, so a filesystem without advisory locks degrades to
    the previous behaviour instead of refusing every lease.

    The lock is advisory and kernel-held: a peer that dies mid-write drops
    it, so a crashed worker can never wedge a task.
    """
    lock = fl.FileLock(lock_path(task_id, log_dir))
    try:
        yield lock.acquire(timeout=timeout) is not False
    finally:
        lock.release()


#: Most filesystems cap a single filename at 255 bytes. Percent-encoding
#: expands a character to up to three bytes, so a long task id can blow
#: past that; those fall back to a digest.
MAX_FILENAME_BYTES = 200


def _safe_name(task_id: str) -> str:
    """Map a task id onto exactly one filename.

    A task id may contain anything, so the name is percent-encoded: that
    keeps path separators and NULs out of the filename *and* keeps the
    mapping injective, so two different task ids can never share one lease
    file. (A plain "replace every unsafe character with _" mapping is not
    injective: "a/b" and "a_b" would collide.)

    Percent-encoding is injective because ``%`` itself is escaped. It is
    also expandable, though: a 100-character id made of separators becomes
    300 bytes, which no filesystem will accept. Such ids fall back to a
    SHA-256 digest, which is collision-free in practice. The lease payload
    always carries the real task id, so a reader never has to reverse this
    mapping.
    """
    raw = str(task_id)
    encoded = urllib.parse.quote(raw, safe="")
    if len(f"{encoded}.{LEASE_NAME}".encode("utf-8")) <= MAX_FILENAME_BYTES:
        return f"{encoded}.{LEASE_NAME}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"h-{digest}.{LEASE_NAME}"


def _read_path(path: Path) -> Optional[dict]:
    """Return the lease payload at *path*, or None when it is untrustworthy.

    Reading by path (rather than by task id) is what lets the recovery
    walk read the real task id out of the payload instead of having to
    reverse-engineer it from the filename.
    """
    try:
        try:
            if path.stat().st_size > MAX_LEASE_BYTES:
                return None
        except Exception:
            return None
        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            return None
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        if not isinstance(data.get("task_id"), str) or not data["task_id"]:
            return None
        if not isinstance(data.get("worker_pid"), int) or isinstance(data.get("worker_pid"), bool):
            return None
        if not isinstance(data.get("ttl_s"), (int, float)) or isinstance(data.get("ttl_s"), bool):
            return None
        if not isinstance(data.get("started_at"), (int, float)) or isinstance(data.get("started_at"), bool):
            return None
        return data
    except Exception:
        return None


def _read(task_id: str, log_dir: Optional[str] = None) -> Optional[dict]:
    """Return the lease payload for *task_id*, or None when untrustworthy."""
    try:
        return _read_path(lease_path(task_id, log_dir))
    except Exception:
        return None


def read_lease(task_id: str, log_dir: Optional[str] = None) -> Optional[dict]:
    """Public accessor: return the lease for *task_id*, or None."""
    return _read(task_id, log_dir)


def _within_ttl(lease: dict, now: Optional[float] = None) -> bool:
    """True while the lease's TTL has not elapsed.

    A negative age (the wall clock jumped backwards) counts as "inside the
    TTL": the consequence of being wrong here is a delayed takeover, while
    the other direction would run a live task twice.
    """
    try:
        ttl = float(lease["ttl_s"])
        started = float(lease["started_at"])
    except Exception:
        return False
    if ttl <= 0:
        return False
    current = time.time() if now is None else float(now)
    return (current - started) < ttl


def _holder_alive(lease: dict) -> Optional[bool]:
    """Is the worker that wrote this lease still running?

    True / False, or None when the OS cannot tell us (no psutil, or the
    process is not inspectable). None means "unknown" and the caller must
    fall back to the TTL.
    """
    try:
        pid = int(lease.get("worker_pid") or -1)
    except Exception:
        return False
    if pid <= 0:
        return False
    create_time = lease.get("worker_create_time")
    if create_time is not None:
        try:
            create_time = float(create_time)
        except Exception:
            create_time = None
    try:
        return wb.process_alive(pid, create_time)
    except Exception:
        return None


def is_active(task_id: str, log_dir: Optional[str] = None,
              now: Optional[float] = None) -> bool:
    """True while the lease is still in force.

    A lease is in force while its TTL has not elapsed *and* its worker is
    not provably gone. The second half is what keeps a SIGKILLed worker's
    task from looking stuck for the rest of the TTL.
    """
    lease = _read(task_id, log_dir)
    if not lease:
        return False
    if not _within_ttl(lease, now):
        return False
    if _holder_alive(lease) is False:
        return False
    return True


def _owned_by(lease: Optional[dict], boot_id: str, worker_pid: int) -> bool:
    """True when *lease* belongs to the (boot_id, worker_pid) pair asking.

    Both halves are required, and the ``boot_id`` half used to be missing
    entirely: a worker that had been fenced out could still ``renew`` and
    ``release`` the lease it no longer held, because only the pid was ever
    compared. Pids get recycled and a worker keeps its pid for its whole
    life, so pid-only ownership is not an identity -- see
    ``test_renew_by_a_different_boot_is_refused``.
    """
    if not lease:
        return False
    try:
        if int(lease.get("worker_pid") or -1) != int(worker_pid):
            return False
    except Exception:
        return False
    recorded = lease.get("boot_id")
    if recorded is None:
        # A lease written before boot ids existed (or by a build that
        # could not claim one) cannot be fenced. Refusing is the safe
        # direction: a takeover attempt is retried, a wrong release is
        # not recoverable.
        return False
    return str(recorded) == str(boot_id)


def acquire(task_id: str, boot_id: str, worker_pid: int,
            ttl_s: float = 60.0, log_dir: Optional[str] = None,
            now: Optional[float] = None) -> bool:
    """Take a lease for *task_id*. Returns True on success.

    A lease inside its TTL blocks a takeover — unless the worker holding it
    is provably gone. A SIGKILLed worker never releases or renews, so
    refusing to take over would leave the task stuck for the rest of the
    TTL. Once the TTL has elapsed the lease is fair game regardless of the
    holder: a worker that wants to keep a long task must ``renew``.

    The whole read-decide-write runs under *task_id*'s advisory lock.
    That is what makes "inside its TTL blocks a takeover" true across
    processes: without it, two workers can both read "no lease" in the
    same window and both write one, and each then believes it holds the
    task exclusively.
    """
    current = time.time() if now is None else float(now)
    with _locked(task_id, log_dir) as may_write:
        if not may_write:
            # A peer is mid-write for this task right now. Refusing is the
            # only safe answer: writing anyway could hand one task to two
            # workers, which is the defect this lock exists to prevent.
            return False
        existing = _read(task_id, log_dir)
        if existing:
            try:
                ttl = float(existing["ttl_s"])
                started = float(existing["started_at"])
                holder_pid = int(existing["worker_pid"])
            except Exception:
                holder_pid, ttl, started = -1, 0.0, 0.0
            if holder_pid == int(worker_pid) and (current - started) < ttl:
                # We already own it — re-stamp. Match the recorded boot id
                # so a re-acquire cannot silently adopt a lease that
                # belongs to a different generation of this pid.
                if str(existing.get("boot_id") or "") == str(boot_id):
                    return _write(task_id, boot_id, worker_pid, ttl_s,
                                  current, log_dir)
                # Same pid, different boot id: the lease is not ours to
                # extend. Fall through to the TTL / liveness rules below,
                # which decide it on evidence rather than on pid alone.
            if (current - started) < ttl:
                # Someone else owns it for now. Only a provably dead holder
                # releases it early.
                if _holder_alive(existing) is not False:
                    return False
        return _write(task_id, boot_id, worker_pid, ttl_s, current, log_dir)


def renew(task_id: str, boot_id: str, worker_pid: int,
          ttl_s: float = 60.0, log_dir: Optional[str] = None,
          now: Optional[float] = None) -> bool:
    """Extend an existing lease we own. Refuses if the lease is held by
    a different (boot_id, worker_pid) pair or does not exist."""
    current = time.time() if now is None else float(now)
    with _locked(task_id, log_dir) as may_write:
        if not may_write:
            return False
        existing = _read(task_id, log_dir)
        if not existing:
            return False
        if not _owned_by(existing, boot_id, worker_pid):
            return False
        return _write(task_id, boot_id, worker_pid, ttl_s, current, log_dir)


def release(task_id: str, boot_id: str, worker_pid: int,
            log_dir: Optional[str] = None) -> None:
    """Drop the lease *only if* it still belongs to *worker_pid*.

    A different pid's lease is left alone — the corresponding task may
    already be picked up by another worker. The same holds for a lease
    owned by a different ``boot_id``: a fenced-out worker must not be
    able to delete the new owner's lease on its way out.
    """
    try:
        with _locked(task_id, log_dir) as may_write:
            if not may_write:
                # A peer is writing this lease. Leaving the file alone is
                # the safe answer: deleting it now could drop the lease of
                # a worker that just took ownership.
                return
            existing = _read(task_id, log_dir)
            if not existing:
                return
            if not _owned_by(existing, boot_id, worker_pid):
                return
            path = lease_path(task_id, log_dir)
            if path.exists():
                path.unlink()
    except Exception as exc:
        logger.debug(f"[TaskLease] could not release: {exc}")


def reclaim_expired(log_dir: Optional[str] = None,
                    now: Optional[float] = None) -> list[str]:
    """Walk all lease files; drop the expired ones; return their task ids.

    A lease is reclaimed when its TTL has elapsed, or when its worker is
    provably gone — a SIGKILLed worker will never renew, and leaving its
    file behind only delays the next attempt to run the task.
    """
    current = time.time() if now is None else float(now)
    reclaimed: list[tuple[float, str]] = []     # (started_at, task_id) for stable ordering
    root = _leases_root(log_dir)
    try:
        candidates = list(root.iterdir())
    except Exception:
        return []
    for path in candidates:
        # Exact suffix, not a substring: the lock sidecar is named
        # "<task>.lease.json.lck", so a substring test would sweep it in
        # here as if it were a lease.
        if not path.is_file() or not path.name.endswith("." + LEASE_NAME):
            continue
        try:
            if path.stat().st_size > MAX_LEASE_BYTES:
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        try:
            ttl = float(data.get("ttl_s"))
            started = float(data.get("started_at"))
            task_id = str(data.get("task_id") or "")
        except Exception:
            continue
        if not task_id:
            continue
        expired = (current - started) >= ttl
        dead_holder = _holder_alive(data) is False
        if expired or dead_holder:
            try:
                path.unlink()
                reclaimed.append((started, task_id))
            except Exception:
                pass
    reclaimed.sort(key=lambda x: x[1])
    return [tid for _started, tid in reclaimed]


def _write(task_id: str, boot_id: str, worker_pid: int,
           ttl_s: float, started_at: float,
           log_dir: Optional[str] = None) -> bool:
    """Atomic write of the lease. Best-effort: returns False on error."""
    try:
        path = lease_path(task_id, log_dir)
        payload = {
            "task_id": str(task_id),
            "boot_id": str(boot_id),
            "worker_pid": int(worker_pid),
            "worker_create_time": _create_time_for(worker_pid),
            "started_at": float(started_at),
            "ttl_s": float(ttl_s),
        }
        tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
        return True
    except Exception as exc:
        logger.debug(f"[TaskLease] could not write lease: {exc}")
        return False


def _create_time_for(worker_pid: int) -> Optional[float]:
    """The create-time of *worker_pid*, when we are the one writing it.

    Only meaningful for our own process: a lease we write always belongs
    to the process writing it.
    """
    try:
        if int(worker_pid) != os.getpid():
            return None
    except Exception:
        return None
    return wb._current_create_time()
