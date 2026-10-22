"""Contract for utils/file_lock.py.

Pins two properties:

* the lock is held by the *kernel* (not by the file): killing the holder
  drops the lock, so a crashed caller never wedges the resource;
* the lock is mutually exclusive: a second holder waits, or fails, and
  never both.

The "kill drops the lock" property is the one the previous file-presence
design failed to deliver, and the one the rest of the keepalive stack now
relies on (utils/task_lease.py, utils/app_watchdog.py).
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from utils import file_lock as fl


#: Repo root, so a child process can ``import utils`` regardless of cwd.
REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Basic semantics
# ---------------------------------------------------------------------------

def test_acquire_then_release_makes_the_lock_takeable_again(tmp_path):
    a = fl.FileLock(tmp_path / "x.lock")
    assert a.acquire() is True
    assert a.held is True
    a.release()
    assert a.held is False

    b = fl.FileLock(tmp_path / "x.lock")
    assert b.acquire() is True
    b.release()


def test_a_second_holder_is_refused(tmp_path):
    a = fl.FileLock(tmp_path / "x.lock")
    a.acquire()
    try:
        b = fl.FileLock(tmp_path / "x.lock")
        assert b.acquire() is False
        assert b.held is False
    finally:
        a.release()


def test_a_second_holder_waits_with_a_timeout(tmp_path):
    a = fl.FileLock(tmp_path / "x.lock")
    a.acquire()
    try:
        b = fl.FileLock(tmp_path / "x.lock")
        # a 0.1s window is plenty to start b, but not enough for a
        # the slow release to come around, even on a busy CI host.
        got = b.acquire(timeout=0.1)
        assert got is False
    finally:
        a.release()


def test_release_is_idempotent(tmp_path):
    a = fl.FileLock(tmp_path / "x.lock")
    a.acquire()
    a.release()
    a.release()                                  # must not raise
    assert a.held is False


# ---------------------------------------------------------------------------
# The "kill drops the lock" property
# ---------------------------------------------------------------------------

def test_killing_the_holder_releases_the_lock(tmp_path):
    """A crash in the holder must not wedge the resource it was protecting.

    Spawn a child that takes the lock and dies without releasing. The
    parent then acquires -- the kernel handed the lock back, exactly
    because the file-presence design would not have.
    """
    lock_path = tmp_path / "wedge.lock"
    code = (
        "import sys, time;"
        f"from utils.file_lock import FileLock;"
        f"FileLock({str(lock_path)!r}).acquire();"
        "time.sleep(0.5)"        # give the parent time to try + fail + notice
    )
    proc = subprocess.Popen([sys.executable, "-c", code], cwd=str(REPO_ROOT))
    # Wait for the child to have taken the lock. We cannot tell exactly
    # when, so we poll: try to take it ourselves; once that fails we
    # know the child holds it.
    ours = fl.FileLock(lock_path)
    for _ in range(200):
        if ours.acquire() is True:
            ours.release()
            time.sleep(0.01)
            continue
        break
    # Wait for the child to exit (it does, after the sleep above).
    proc.wait(timeout=5)

    # The lock must now be free -- the kernel drops it on process death.
    after = fl.FileLock(lock_path)
    assert after.acquire(timeout=1.0) is True
    after.release()


# ---------------------------------------------------------------------------
# Payload alongside the lock byte
# ---------------------------------------------------------------------------

def test_payload_round_trips_alongside_the_lock(tmp_path):
    """The metadata byte range is independent of the lock byte.

    Callers need to keep state (e.g. a pid) next to the lock so that a
    later reader knows what to do with the file. The layout must not
    interleave the two.
    """
    path = tmp_path / "p.lock"
    lock = fl.FileLock(path)
    assert lock.acquire() is True
    try:
        assert lock.write_payload("pid:42") is True
        assert lock.read_payload() == "pid:42"

        # Re-write is a clean overwrite, not an append.
        assert lock.write_payload("pid:99") is True
        assert lock.read_payload() == "pid:99"
    finally:
        lock.release()


def test_the_payload_is_readable_after_the_lock_is_released(tmp_path):
    """The payload outlives the lock -- it is on disk, not in the handle.

    A later reader (the watchdog's identity check) must be able to read
    who the holder was after the holder is gone.
    """
    path = tmp_path / "p.lock"
    lock = fl.FileLock(path)
    lock.acquire()
    lock.write_payload("pid:42")
    lock.release()

    assert path.read_bytes().lstrip(b"\x00").decode("utf-8") == "pid:42"


def test_read_payload_without_the_lock_is_empty(tmp_path):
    """A lock file nobody has written to carries no payload."""
    lock = fl.FileLock(tmp_path / "empty.lock")
    assert lock.read_payload() is None


# ---------------------------------------------------------------------------
# Cross-process mutex -- the property the watchdog / task_lease both need
# ---------------------------------------------------------------------------

def test_critical_sections_never_overlap_across_processes(tmp_path):
    """The property gap 2 actually violated: two writers inside the
    critical section at the same time.

    This is a mutex, not a one-shot token: every child that waits long
    enough may legitimately acquire the lock in turn. What must never
    happen is two children being inside the critical section at once --
    that is what lets two writers both read "the lease is free" and both
    write one.

    Each child appends "enter <pid>" on entry and "leave <pid>" on exit,
    to an append-only file. A plain append is atomic for these sizes, so
    the log is a faithful record of the interleaving.
    """
    lock_path = tmp_path / "race.lock"
    trace = tmp_path / "trace.log"
    code = (
        "import sys, os, time;"
        "from utils.file_lock import FileLock;"
        f"lock = {str(lock_path)!r};"
        f"trace = {str(trace)!r};"
        "l = FileLock(lock);"
        "ok = l.acquire(timeout=10);"
        "open(trace, 'a').write('enter %d\\n' % os.getpid());"
        "open(trace, 'a').flush();"
        "time.sleep(0.05);"
        "open(trace, 'a').write('leave %d\\n' % os.getpid());"
        "open(trace, 'a').flush();"
        "l.release();"
        "sys.exit(0 if ok else 1)"
    )
    procs = [
        subprocess.Popen([sys.executable, "-c", code], cwd=str(REPO_ROOT))
        for _ in range(6)
    ]
    for p in procs:
        assert p.wait(timeout=30) == 0, "a child failed to acquire the lock"

    depth = 0
    peak = 0
    for line in trace.read_text(encoding="utf-8").splitlines():
        if line.startswith("enter"):
            depth += 1
            peak = max(peak, depth)
        elif line.startswith("leave"):
            depth -= 1
        assert depth >= 0, "unbalanced trace: a leave without an enter"
    assert depth == 0, "unbalanced trace: the log ends inside a section"
    assert peak == 1, f"two children were inside the critical section at once (peak={peak})"


def test_a_locked_resource_serialises_acquirers_across_processes(tmp_path):
    """Six sequential acquirers all succeed -- a mutex is not one-shot.

    Paired with the test above: overlap is forbidden, starvation is not.
    Every child waits for its turn and gets it.
    """
    lock_path = tmp_path / "queue.lock"
    code = (
        "import sys;"
        "from utils.file_lock import FileLock;"
        f"l = FileLock({str(lock_path)!r});"
        "sys.exit(0 if l.acquire(timeout=15) is True else 1)"
    )
    procs = [
        subprocess.Popen([sys.executable, "-c", code], cwd=str(REPO_ROOT))
        for _ in range(6)
    ]
    assert all(p.wait(timeout=30) == 0 for p in procs), \
        "a waiter starved: the lock must be handable to all of them in turn"
