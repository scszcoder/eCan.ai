"""Task lease: a worker declares "I am running task X" before it starts work,
and the zombie recovery walks the lease list at startup to find orphaned
tasks. See utils/task_lease.py for the design; this file pins the contract.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from utils import task_lease as tl


#: A pid that is definitely running, so "the holder is still alive" can be
#: tested without depending on whatever the OS happens to have allocated.
_LIVE_PID = None


def _live_other_pid() -> int:
    """The pid of a live process that is definitely not us."""
    global _LIVE_PID
    if _LIVE_PID is None:
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"])
        _LIVE_PID = proc.pid
    return _LIVE_PID


# --------------------------------------------------------------------------
# acquire / read / renew / release
# --------------------------------------------------------------------------

def test_acquire_writes_a_lease(tmp_path):
    ok = tl.acquire(task_id="t1", boot_id="boot-1", worker_pid=os.getpid(),
                    ttl_s=60, log_dir=str(tmp_path))
    assert ok is True
    lease = tl.read_lease("t1", log_dir=str(tmp_path))
    assert lease["task_id"] == "t1"
    assert lease["boot_id"] == "boot-1"
    assert lease["worker_pid"] == os.getpid()
    assert lease["ttl_s"] == 60


def test_acquire_by_same_pid_is_idempotent(tmp_path):
    """A worker re-acquiring during a long task must not reject itself."""
    tl.acquire(task_id="t1", boot_id="boot-1", worker_pid=os.getpid(),
               ttl_s=60, log_dir=str(tmp_path))
    again = tl.acquire(task_id="t1", boot_id="boot-1", worker_pid=os.getpid(),
                       ttl_s=60, log_dir=str(tmp_path))
    assert again is True
    assert tl.read_lease("t1", log_dir=str(tmp_path))["boot_id"] == "boot-1"


def test_acquire_is_refused_when_held_by_a_different_pid(tmp_path):
    """A live worker holding the lease means the task may be running right
    now -- taking it over would run it twice.

    The holder must be a *live* process: a dead holder is released early
    (see test_lease_hardening.py), which is the whole point of consulting
    liveness. A long-running helper process stands in for a live worker.
    """
    tl.acquire(task_id="t1", boot_id="boot-1", worker_pid=_live_other_pid(),
               ttl_s=60, log_dir=str(tmp_path))
    ok = tl.acquire(task_id="t1", boot_id="boot-2", worker_pid=os.getpid(),
                    ttl_s=60, log_dir=str(tmp_path))
    assert ok is False


def test_acquire_overwrites_an_expired_lease(tmp_path):
    """A lease whose TTL has elapsed is fair game."""
    tl.acquire(task_id="t1", boot_id="old-boot", worker_pid=99999,
               ttl_s=10, log_dir=str(tmp_path))
    later = time.time() + 120    # well past TTL
    ok = tl.acquire(task_id="t1", boot_id="new-boot", worker_pid=os.getpid(),
                    ttl_s=60, log_dir=str(tmp_path), now=later)
    assert ok is True
    lease = tl.read_lease("t1", log_dir=str(tmp_path))
    assert lease["boot_id"] == "new-boot"


def test_renew_extends_expiry_for_owner(tmp_path):
    tl.acquire(task_id="t1", boot_id="b", worker_pid=os.getpid(),
               ttl_s=10, log_dir=str(tmp_path))
    ok = tl.renew(task_id="t1", boot_id="b", worker_pid=os.getpid(),
                  ttl_s=30, log_dir=str(tmp_path))
    assert ok is True
    assert tl.read_lease("t1", log_dir=str(tmp_path))["ttl_s"] == 30


def test_renew_by_a_non_owner_is_refused(tmp_path):
    tl.acquire(task_id="t1", boot_id="b", worker_pid=99999,
               ttl_s=10, log_dir=str(tmp_path))
    ok = tl.renew(task_id="t1", boot_id="b", worker_pid=os.getpid(),
                  ttl_s=30, log_dir=str(tmp_path))
    assert ok is False


def test_renew_for_a_missing_lease_is_false(tmp_path):
    ok = tl.renew(task_id="never-existed", boot_id="b",
                  worker_pid=os.getpid(), log_dir=str(tmp_path))
    assert ok is False


def test_release_drops_a_lease_owned_by_the_caller(tmp_path):
    tl.acquire(task_id="t1", boot_id="b", worker_pid=os.getpid(),
               ttl_s=60, log_dir=str(tmp_path))
    tl.release(task_id="t1", boot_id="b", worker_pid=os.getpid(),
               log_dir=str(tmp_path))
    assert tl.read_lease("t1", log_dir=str(tmp_path)) is None


def test_release_by_a_non_owner_is_a_noop(tmp_path):
    tl.acquire(task_id="t1", boot_id="b", worker_pid=99999,
               ttl_s=60, log_dir=str(tmp_path))
    tl.release(task_id="t1", boot_id="b", worker_pid=os.getpid(),
               log_dir=str(tmp_path))
    assert tl.read_lease("t1", log_dir=str(tmp_path)) is not None


def test_release_for_a_missing_task_is_a_noop(tmp_path):
    tl.release(task_id="never-existed", boot_id="b",
               worker_pid=os.getpid(), log_dir=str(tmp_path))


# --------------------------------------------------------------------------
# is_active: TTL semantics
# --------------------------------------------------------------------------

def test_lease_is_active_within_ttl(tmp_path):
    tl.acquire(task_id="t1", boot_id="b", worker_pid=os.getpid(),
               ttl_s=10, log_dir=str(tmp_path))
    assert tl.is_active("t1", log_dir=str(tmp_path)) is True


def test_lease_is_inactive_after_ttl(tmp_path):
    tl.acquire(task_id="t1", boot_id="b", worker_pid=os.getpid(),
               ttl_s=10, log_dir=str(tmp_path))
    assert tl.is_active("t1", log_dir=str(tmp_path),
                        now=time.time() + 11) is False


def test_is_active_handles_clock_rewind_safely(tmp_path):
    """``now < started_at`` is treated as "still inside TTL" -- a clock that
    jumps backwards must not make a live lease look orphaned."""
    tl.acquire(task_id="t1", boot_id="b", worker_pid=os.getpid(),
               ttl_s=60, log_dir=str(tmp_path))
    assert tl.is_active("t1", log_dir=str(tmp_path),
                        now=time.time() - 600) is True


# --------------------------------------------------------------------------
# Defensive read
# --------------------------------------------------------------------------

def test_lease_treats_invalid_json_as_no_lease(tmp_path):
    path = tl.lease_path("t1", str(tmp_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not json", encoding="utf-8")
    assert tl.read_lease("t1", log_dir=str(tmp_path)) is None


def test_lease_treats_oversized_file_as_no_lease(tmp_path):
    path = tl.lease_path("t1", str(tmp_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x" * (tl.MAX_LEASE_BYTES + 1), encoding="utf-8")
    assert tl.read_lease("t1", log_dir=str(tmp_path)) is None


def test_atomic_write_leaves_no_orphans(tmp_path):
    tl.acquire(task_id="t1", boot_id="b", worker_pid=os.getpid(),
               ttl_s=60, log_dir=str(tmp_path))
    leftovers = [p.name for p in Path(str(tmp_path)).rglob("*.tmp.*")]
    assert leftovers == []


def test_lease_path_is_per_task(tmp_path):
    a = tl.lease_path("alpha", str(tmp_path))
    b = tl.lease_path("beta", str(tmp_path))
    assert a != b


def test_lease_path_sanitises_task_ids(tmp_path):
    """A task id with path separators or NULs cannot escape the leases dir."""
    a = tl.lease_path("../../etc/passwd", str(tmp_path))
    root = tl._leases_root(str(tmp_path))
    assert str(root.resolve()) in a.resolve().__str__()


# --------------------------------------------------------------------------
# reclaim_expired
# --------------------------------------------------------------------------

def test_reclaim_drops_expired_leases(tmp_path):
    tl.acquire(task_id="t-old", boot_id="b", worker_pid=99999,
               ttl_s=10, log_dir=str(tmp_path))
    later = time.time() + 60
    reclaimed = tl.reclaim_expired(log_dir=str(tmp_path), now=later)
    assert reclaimed == ["t-old"]
    assert tl.read_lease("t-old", log_dir=str(tmp_path)) is None


def test_reclaim_keeps_active_leases(tmp_path):
    tl.acquire(task_id="t-live", boot_id="b", worker_pid=os.getpid(),
               ttl_s=600, log_dir=str(tmp_path))
    reclaimed = tl.reclaim_expired(log_dir=str(tmp_path))
    assert reclaimed == []


def test_reclaim_ignores_non_lease_files(tmp_path):
    """Extra files in the leases dir (editor backups, etc.) must not crash
    the reclaimer."""
    root = tl._leases_root(str(tmp_path))
    (root / "random_garbage.txt").write_text("hi", encoding="utf-8")
    assert tl.reclaim_expired(log_dir=str(tmp_path)) == []


def test_reclaim_sorts_reclaimed_ids(tmp_path):
    for tid in ["c", "a", "b"]:
        tl.acquire(task_id=tid, boot_id="old", worker_pid=99999,
                   ttl_s=10, log_dir=str(tmp_path))
    reclaimed = tl.reclaim_expired(log_dir=str(tmp_path), now=time.time() + 60)
    assert reclaimed == sorted(reclaimed)
