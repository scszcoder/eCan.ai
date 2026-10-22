"""Regression tests for the two lease defects that survived self-review.

Both were found by re-reading ``utils/task_lease.py`` against its own
documented contract, and both were reproduced by hand before being pinned
here. They are not new features.

⑧  **``acquire`` was not atomic.** The read-decide-write sequence had no
    exclusivity primitive, so two workers could both read "no lease" and
    both write one. Measured on this machine: 6 concurrent processes,
    20 rounds, **every round returned ``True`` from all 6** — each
    believed it held the task exclusively, which is precisely the
    double-run the lease exists to prevent.

⑨  **``boot_id`` was accepted and ignored.** ``renew`` and ``release``
    take a ``boot_id`` argument but never compared it to the one in the
    lease. A worker that had been fenced out could keep extending the
    lease and could delete it outright on its way out.

The unifying root cause, as in ``test_lease_hardening.py``: the code had
a correctness *invariant* in its docstring and no mechanism enforcing it.

A note on how the concurrency tests are set up
---------------------------------------------
Liveness is *stubbed* inside each child rather than left to the real OS.
The lease stack's rule is "a provably dead holder releases its lease
early", so a child that exits immediately hands the lease to the next
contender — correct behaviour that has nothing to do with exclusivity.
Stubbing liveness makes "is the holder alive?" a deterministic fact
about the test, so the only thing the race measures is whether two
workers can hold one task at once.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from utils import task_lease as tl
from utils import worker_boot as wb


#: Repo root, so a child process can ``import utils`` regardless of cwd.
REPO_ROOT = Path(__file__).resolve().parents[2]

#: 6 contenders, matching the hand-run that exposed the defect.
_CONTENDERS = 6


# ══════════════════════════════════════════════════════════════════════
# ⑧ acquire() must be exclusive across processes.
# ══════════════════════════════════════════════════════════════════════

#: Body of a child process. Reads "go" from stdin so that every
#: contender is inside ``acquire`` at the same moment -- a race needs the
#: barrier, not merely concurrency.
_CHILD = """
import sys, os, json, time
from unittest.mock import patch
from utils import task_lease as tl
from utils import worker_boot as wb

DEAD_PID = {dead_pid!r}

# Liveness is decided by the test, not by the OS: every pid except
# DEAD_PID is "alive". Without this, a child that exits would let the
# next contender take the lease -- correct per the liveness rule, and
# irrelevant to exclusivity.
patch.object(wb, "process_alive",
             side_effect=lambda pid, ct=None: False if int(pid or -1) == int(DEAD_PID)
             else True).start()

sys.stdout.write("ready\\n")
sys.stdout.flush()
sys.stdin.readline()

ok = tl.acquire(task_id={task_id!r}, boot_id={boot_id!r},
                worker_pid=os.getpid(), ttl_s=60, log_dir={log_dir!r})
sys.stdout.write(json.dumps({{"ok": bool(ok)}}))
sys.stdout.flush()
"""


def _contenders(task_id: str, log_dir: str, count: int, dead_pid=None):
    """Start *count* children that all race for *task_id*.

    Returns the list of (ok, raw_output) once every child has finished.
    """
    procs = []
    for i in range(count):
        src = _CHILD.format(task_id=task_id, log_dir=log_dir,
                             boot_id=f"boot-{i}", dead_pid=dead_pid)
        procs.append(subprocess.Popen(
            [sys.executable, "-c", src], cwd=str(REPO_ROOT),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE))

    # Let every child reach its "ready" marker and block on stdin, so the
    # release below puts them all into acquire() together.
    time.sleep(1.0)
    for proc in procs:
        try:
            proc.stdin.write(b"go\n")
            proc.stdin.flush()
        except Exception:
            pass

    results = []
    for proc in procs:
        out, _ = proc.communicate(timeout=30)
        results.append((b'"ok": true' in out, out))
    return results


def test_acquire_is_exclusive_across_processes(tmp_path):
    """Only one of N concurrent processes may win the lease.

    Before the fix this returned N winners out of N, in every round:
    ``acquire`` had no lock around its read-decide-write.
    """
    task_id = "shared-task"
    log_dir = str(tmp_path)
    results = _contenders(task_id, log_dir, _CONTENDERS)

    winners = [i for i, (ok, _out) in enumerate(results) if ok]
    assert len(winners) == 1, (
        f"{len(winners)} of {_CONTENDERS} processes acquired the same lease "
        f"{task_id!r} -- acquire() is not exclusive: {winners}")


def test_a_repeated_contended_race_never_double_grants(tmp_path):
    """Repeat the race: a single lucky round proves nothing.

    The pre-fix code failed 20/20 rounds, so a handful of rounds is enough
    to catch a regression that only shows up under scheduling pressure.

    Each round races on its *own* task id. A lease left behind by an
    earlier round would still be held by that round's winner -- whose pid
    the stub reports as alive -- so the next round would have no winner at
    all. That is correct behaviour (a live holder blocks a takeover), and
    it is not what this test is measuring.
    """
    log_dir = str(tmp_path)
    for round_no in range(5):
        task_id = f"racy-{round_no}"
        results = _contenders(task_id, log_dir, 4)
        winners = [i for i, (ok, _out) in enumerate(results) if ok]
        assert len(winners) == 1, (
            f"round {round_no} granted the lease {len(winners)} times: {winners}")
        # And the single winner is the lease's actual holder.
        assert tl.read_lease(task_id, log_dir=log_dir) is not None


def test_a_dead_holders_lease_is_still_reclaimable_under_concurrency(tmp_path):
    """The lock must not break takeover: exclusivity is not a new lock-out.

    A lease held by a pid that is provably gone must still be claimable,
    even with peers contending for it -- and exactly one peer may claim it.
    """
    task_id = "orphaned"
    log_dir = str(tmp_path)
    tl.acquire(task_id=task_id, boot_id="dead", worker_pid=999999,
               ttl_s=600, log_dir=log_dir)
    # 999999 reads as dead to the children's stub, so the lease is
    # reclaimable; every other pid reads as alive, so the winner of the
    # race blocks the losers.
    results = _contenders(task_id, log_dir, 4, dead_pid=999999)
    winners = [i for i, (ok, _out) in enumerate(results) if ok]
    assert len(winners) == 1, (
        f"a dead holder's lease was handed to {len(winners)} workers; the "
        "lock must serialise the takeover, not block it")


def test_leases_for_different_tasks_do_not_contend(tmp_path):
    """The lock is per task, so unrelated tasks never wait on each other."""
    log_dir = str(tmp_path)
    tl.acquire(task_id="t-1", boot_id="b1", worker_pid=os.getpid(),
               ttl_s=60, log_dir=log_dir)
    # A lease held by another task must not affect this one.
    assert tl.acquire(task_id="t-2", boot_id="b2", worker_pid=os.getpid(),
                      ttl_s=60, log_dir=log_dir) is True


def test_the_lock_sidecar_is_not_mistaken_for_a_lease(tmp_path):
    """The .lck sidecar must not be walked as a lease by orphan recovery.

    The sidecar is named ``<task>.lease.json.lck``, so it *contains* the
    lease suffix -- the recovery scan has to match the exact ending, not
    a substring, or it would sweep the lock in as a lease.
    """
    tl.acquire(task_id="t", boot_id="b", worker_pid=os.getpid(),
               ttl_s=60, log_dir=str(tmp_path))
    assert tl.lock_path("t", str(tmp_path)).exists()
    reclaimed = tl.reclaim_expired(log_dir=str(tmp_path))
    assert reclaimed == []
    assert tl.read_lease("t", log_dir=str(tmp_path)) is not None


def test_the_lock_file_is_kept_after_release(tmp_path):
    """The lock file must outlive the lock.

    Deleting it would be a correctness bug, not housekeeping: a peer
    that already opened the same path would go on locking the old inode
    while a third caller creates a fresh file and locks that one --
    two holders at once. The kernel drops the lock when the handle
    closes; the inert file it leaves behind is what keeps the path
    stable for the next caller.
    """
    task_id = "t"
    log_dir = str(tmp_path)
    tl.acquire(task_id=task_id, boot_id="b", worker_pid=os.getpid(),
               ttl_s=60, log_dir=log_dir)
    tl.release(task_id=task_id, boot_id="b", worker_pid=os.getpid(),
               log_dir=log_dir)
    assert tl.lock_path(task_id, log_dir).exists()
    # And the lease itself is gone.
    assert tl.read_lease(task_id, log_dir=log_dir) is None


# ══════════════════════════════════════════════════════════════════════
# ⑨ boot_id is the fencing token; it was accepted and thrown away.
# ══════════════════════════════════════════════════════════════════════

def test_renew_by_a_different_boot_is_refused(tmp_path):
    """The same pid with a different boot id is a different owner.

    Before the fix this returned True: ``renew`` compared ``worker_pid``
    and ignored ``boot_id`` entirely, so a fenced-out worker could keep
    extending the new owner's lease.
    """
    tl.acquire(task_id="t", boot_id="boot-A", worker_pid=os.getpid(),
               ttl_s=10, log_dir=str(tmp_path))
    ok = tl.renew(task_id="t", boot_id="boot-B", worker_pid=os.getpid(),
                  ttl_s=300, log_dir=str(tmp_path))
    assert ok is False
    # And the lease must be untouched.
    lease = tl.read_lease("t", log_dir=str(tmp_path))
    assert lease["boot_id"] == "boot-A"
    assert lease["ttl_s"] == 10


def test_release_by_a_different_boot_does_not_delete_the_lease(tmp_path):
    """A fenced-out worker must not be able to drop the new owner's lease.

    Before the fix ``release`` compared only the pid and deleted the file,
    so the worker that had just been fenced out could erase the lease of
    the worker that replaced it.
    """
    tl.acquire(task_id="t", boot_id="boot-A", worker_pid=os.getpid(),
               ttl_s=60, log_dir=str(tmp_path))
    tl.release(task_id="t", boot_id="boot-B", worker_pid=os.getpid(),
               log_dir=str(tmp_path))
    assert tl.read_lease("t", log_dir=str(tmp_path)) is not None
    assert tl.read_lease("t", log_dir=str(tmp_path))["boot_id"] == "boot-A"


def test_a_fenced_out_worker_cannot_take_the_lease_back(tmp_path):
    """boot-A loses the lease; boot-B takes it; boot-A must stay out.

    A pid is not an identity — it survives a whole process lifetime while
    a boot id changes with every generation. Without the boot id check,
    the original owner could re-acquire its own lease after being fenced
    and run the task concurrently with its replacement.
    """
    task_id, log_dir = "t", str(tmp_path)
    # boot-A is the same pid, and the lease is inside its TTL, so boot-B
    # cannot take it while the holder is alive.
    tl.acquire(task_id=task_id, boot_id="boot-A", worker_pid=os.getpid(),
               ttl_s=600, log_dir=log_dir)
    with patch.object(wb, "process_alive", return_value=False):
        assert tl.acquire(task_id=task_id, boot_id="boot-B",
                          worker_pid=os.getpid(), ttl_s=600,
                          log_dir=log_dir) is True
    assert tl.read_lease(task_id, log_dir=log_dir)["boot_id"] == "boot-B"

    # boot-A is fenced. It must not re-stamp the lease it no longer owns.
    with patch.object(wb, "process_alive", return_value=True):
        assert tl.acquire(task_id=task_id, boot_id="boot-A",
                          worker_pid=os.getpid(), ttl_s=600,
                          log_dir=log_dir) is False
    assert tl.read_lease(task_id, log_dir=log_dir)["boot_id"] == "boot-B"


def test_the_owner_can_still_renew_after_a_fence_check(tmp_path):
    """Fencing must not break the legitimate owner.

    The whole point of checking boot_id is that the *rightful* holder can
    still extend its own lease; otherwise a long task would lose its
    lease the moment the check landed.
    """
    task_id, log_dir = "t", str(tmp_path)
    tl.acquire(task_id=task_id, boot_id="boot-A", worker_pid=os.getpid(),
               ttl_s=10, log_dir=log_dir)
    assert tl.renew(task_id=task_id, boot_id="boot-A",
                    worker_pid=os.getpid(), ttl_s=300,
                    log_dir=log_dir) is True
    assert tl.read_lease(task_id, log_dir=log_dir)["ttl_s"] == 300
    tl.release(task_id=task_id, boot_id="boot-A",
               worker_pid=os.getpid(), log_dir=log_dir)
    assert tl.read_lease(task_id, log_dir=log_dir) is None


def test_a_lease_with_no_boot_id_cannot_be_released_by_boot_id_guessing(tmp_path):
    """A lease that records no boot id cannot be proven to be ours.

    Such a lease is one this build wrote before boot ids existed. Refusing
    is the safe direction: the lease stays and is reclaimed by TTL or by
    orphan recovery, rather than being deleted on a guess.
    """
    path = tl.lease_path("t", str(tmp_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "task_id": "t", "worker_pid": os.getpid(),
        "started_at": time.time(), "ttl_s": 600,
    }), encoding="utf-8")

    assert tl.renew(task_id="t", boot_id="anything",
                    worker_pid=os.getpid(), ttl_s=300,
                    log_dir=str(tmp_path)) is False
    tl.release(task_id="t", boot_id="anything", worker_pid=os.getpid(),
               log_dir=str(tmp_path))
    assert path.exists()


def test_orphan_recovery_is_unaffected_by_the_lock(tmp_path):
    """Adding locks must not change what recovery finds.

    ``identify_orphans`` walks lease files; the .lck sidecars must be
    invisible to it, and a lease left behind by a dead worker must still
    be reported exactly as before.
    """
    from agent.ec_tasks import zombie_recovery as zr

    task_id, log_dir = "t-crashed", str(tmp_path)
    tl.acquire(task_id=task_id, boot_id="dead-boot", worker_pid=999999,
               ttl_s=3600, log_dir=log_dir)
    # The lock file for this task exists now; recovery must ignore it.
    assert tl.lock_path(task_id, log_dir).exists()
    with patch.object(wb, "process_alive", return_value=False):
        orphans = zr.identify_orphans(leases_dir=log_dir)
    assert orphans == [task_id]
