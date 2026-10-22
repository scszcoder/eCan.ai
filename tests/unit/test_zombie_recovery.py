"""On startup, find tasks that the previous process started and never finished.

Every task a worker takes moves through three states: ``running`` (set when
the task is claimed), ``completed`` / ``failed`` (set when it ends, success
or failure). A *crash* leaves it stuck at ``running`` -- the worker is
gone, no happy/sad ending was ever written.

The runner does not currently walk that orphan list. ``recover_orphans``
is the missing piece, called once at startup, with two guards:

* the lease has expired (no one owns it now);
* the lease's ``boot_id`` belongs to a worker that no longer exists
  (``pid`` either disappeared or points to a different process -- a reused
  OS pid).

A recovered task is not retried automatically; ``utils.task_lease`` already
returned its id, the runner decides what to do with it (mark failed, queue
retry, ignore). This module only collects them.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from utils import task_lease as tl
from agent.ec_tasks import zombie_recovery as zr


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


def _boot_dir(log_dir, key):
    return Path(log_dir) / "workers"


def _seed_worker(log_dir, key, pid, boot_id="seed-boot"):
    """Pretend a worker lived and wrote a boot id."""
    d = _boot_dir(log_dir, key)
    d.mkdir(parents=True, exist_ok=True)
    (d / "boot_id.json").write_text(json.dumps({
        "key": key, "pid": pid, "boot_id": boot_id,
        "stamp": time.time() - 1000,   # ancient
    }), encoding="utf-8")


def test_recover_returns_expired_leases_owned_by_dead_workers(tmp_path):
    far_past = time.time() - 3600
    tl.acquire(task_id="t-stuck", boot_id="old-boot", worker_pid=99999,
               ttl_s=10, log_dir=str(tmp_path), now=far_past)
    log_dir = str(tmp_path / "runlogs")
    os.makedirs(log_dir, exist_ok=True)
    orphan = zr.identify_orphans(leases_dir=str(tmp_path), log_dir=log_dir)
    assert "t-stuck" in orphan


def test_recover_keeps_leases_for_a_live_worker_pid(tmp_path):
    """A lease inside its TTL must NOT be reclaimed as orphan -- the worker
    may still be alive."""
    tl.acquire(task_id="t-live", boot_id="b", worker_pid=os.getpid(),
               ttl_s=600, log_dir=str(tmp_path))
    log_dir = str(tmp_path / "runlogs")
    os.makedirs(log_dir, exist_ok=True)
    orphan = zr.identify_orphans(leases_dir=str(tmp_path), log_dir=log_dir)
    assert "t-live" not in orphan


def test_recover_skips_leases_within_ttl(tmp_path):
    """A fresh lease may belong to a worker that has not yet booted into our
    process listing; do not snap-reclaim just because the pid is unknown.

    The holder here must be *alive*: a lease whose worker is provably dead
    is orphaned immediately, without waiting for the TTL (that is the
    point of consulting liveness).
    """
    tl.acquire(task_id="t-fresh", boot_id="b", worker_pid=_live_other_pid(),
               ttl_s=10**6, log_dir=str(tmp_path))     # far future
    log_dir = str(tmp_path / "runlogs")
    os.makedirs(log_dir, exist_ok=True)
    orphan = zr.identify_orphans(leases_dir=str(tmp_path), log_dir=log_dir)
    assert "t-fresh" not in orphan


def test_recover_returns_task_ids_in_deterministic_order(tmp_path):
    for tid in ["c", "a", "b"]:
        tl.acquire(task_id=tid, boot_id="old", worker_pid=99999,
                   ttl_s=10, log_dir=str(tmp_path))
    log_dir = str(tmp_path / "runlogs")
    os.makedirs(log_dir, exist_ok=True)
    orphan = zr.identify_orphans(leases_dir=str(tmp_path), log_dir=log_dir)
    # Sorting is irrelevant for correctness, but callers that emit user-visible
    # messages benefit from stable output.
    assert orphan == sorted(orphan)


def test_recover_handles_a_missing_log_dir_gracefully(tmp_path):
    far_past = time.time() - 3600
    tl.acquire(task_id="t-x", boot_id="old", worker_pid=99999,
               ttl_s=10, log_dir=str(tmp_path), now=far_past)
    # log_dir is intentionally NOT created.
    orphan = zr.identify_orphans(leases_dir=str(tmp_path),
                                  log_dir=str(tmp_path / "nope"))
    # No live pids can be enumerated -> all leases fall into orphan. Acceptable.
    assert "t-x" in orphan


def test_recover_is_safe_when_no_leases_exist(tmp_path):
    log_dir = str(tmp_path / "runlogs")
    os.makedirs(log_dir, exist_ok=True)
    assert zr.identify_orphans(leases_dir=str(tmp_path), log_dir=log_dir) == []


def test_mark_orphan_drops_the_lease(tmp_path):
    """The runner's recovery path drops the lease once it has decided what to
    do with the task, so the next startup does not see the same orphan."""
    from utils import task_lease as tls
    tls.acquire(task_id="t-gone", boot_id="old", worker_pid=99999,
                ttl_s=10, log_dir=str(tmp_path))
    zr.mark_orphan_resolved(task_id="t-gone", leases_dir=str(tmp_path))
    assert tls.read_lease("t-gone", log_dir=str(tmp_path)) is None


def test_startup_recovery_handles_each_orphan_once(tmp_path):
    """run_startup_recovery must invoke the handler exactly once per orphan
    and drop the corresponding lease after a clean return."""
    far_past = time.time() - 3600
    for tid in ("t-a", "t-b"):
        tl.acquire(task_id=tid, boot_id="old", worker_pid=99999,
                   ttl_s=10, log_dir=str(tmp_path), now=far_past)
    log_dir = str(tmp_path / "runlogs")
    os.makedirs(log_dir, exist_ok=True)
    seen: list[str] = []

    def handler(tid: str) -> None:
        seen.append(tid)

    handled = zr.run_startup_recovery(
        leases_dir=str(tmp_path), log_dir=log_dir, on_orphan=handler
    )
    assert handled == sorted(seen)
    # Leases for the handled ids are gone.
    for tid in seen:
        assert tl.read_lease(tid, log_dir=str(tmp_path)) is None


def test_startup_recovery_keeps_a_lease_when_handler_fails(tmp_path):
    """If the handler raises, the lease stays — the next startup gets
    another chance. Silence here would lose the orphan forever."""
    far_past = time.time() - 3600
    tl.acquire(task_id="t-stuck", boot_id="old", worker_pid=99999,
               ttl_s=10, log_dir=str(tmp_path), now=far_past)
    log_dir = str(tmp_path / "runlogs")
    os.makedirs(log_dir, exist_ok=True)
    calls = {"n": 0}

    def handler(tid: str) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated DB hiccup")

    handled = zr.run_startup_recovery(
        leases_dir=str(tmp_path), log_dir=log_dir, on_orphan=handler
    )
    assert handled == []   # this round failed
    # Lease is preserved for the next startup to retry.
    assert tl.read_lease("t-stuck", log_dir=str(tmp_path)) is not None

    # Second pass succeeds and clears the lease.
    handled = zr.run_startup_recovery(
        leases_dir=str(tmp_path), log_dir=log_dir, on_orphan=handler
    )
    assert handled == ["t-stuck"]
    assert tl.read_lease("t-stuck", log_dir=str(tmp_path)) is None


def test_startup_recovery_uses_default_handler_when_none_given(tmp_path):
    far_past = time.time() - 3600
    tl.acquire(task_id="t-x", boot_id="old", worker_pid=99999,
               ttl_s=10, log_dir=str(tmp_path), now=far_past)
    log_dir = str(tmp_path / "runlogs")
    os.makedirs(log_dir, exist_ok=True)
    handled = zr.run_startup_recovery(leases_dir=str(tmp_path), log_dir=log_dir)
    assert handled == ["t-x"]
    assert tl.read_lease("t-x", log_dir=str(tmp_path)) is None
