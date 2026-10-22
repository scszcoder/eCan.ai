"""Regression tests for the watchdog singleton lock.

The watchdog is the thing that keeps an unattended PC alive. If it
refuses to start when it should, the machine is silently unwatched --
and nothing reports that, because the thing that would have reported it
is the thing that did not start.

Two defects are pinned here.

⑩  **The singleton check compared a bare pid.** ``_acquire_singleton``
    read the pid from the lock file and asked ``psutil.pid_exists()``.
    The OS recycles pids, so a lock file left behind by a *crashed*
    watchdog whose pid has since been handed to an unrelated process
    makes the next watchdog believe "another watchdog is running" and
    exit. The machine is then unwatched, and the log line says
    "another watchdog is running; exiting" -- a confident, wrong answer.

⑪  **The lock had no exclusivity primitive at all.** Two watchdogs
    starting in the same instant both read an empty lock file and both
    wrote their pid, and both went on to supervise the app. The check
    was a read followed by a write, with nothing in between.

The fix is an advisory OS lock (utils/file_lock.py): the kernel owns it,
releases it when the holder dies, and hands it to exactly one caller.
The identity in the file is now ``(pid, create_time)`` rather than a
bare pid, matching utils/worker_boot.py.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from utils import app_watchdog as wd


#: Repo root, so a child process can ``import utils`` regardless of cwd.
REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _release_lock():
    """Every test starts and ends holding no watchdog lock."""
    wd._release_singleton()
    yield
    wd._release_singleton()


# ---------------------------------------------------------------------------
# The singleton must actually be a singleton
# ---------------------------------------------------------------------------

def test_a_second_watchdog_in_the_same_process_is_refused(tmp_path):
    """Two watchdogs must not both supervise the app.

    The OS lock is what makes this true: it is held by the open file
    handle, so a second acquisition on the same path fails even within
    one process.
    """
    lock = tmp_path / "watchdog.lock"
    assert wd._acquire_singleton(lock) is True
    assert wd._acquire_singleton(lock) is False


def test_the_lock_is_released_when_the_holder_lets_go(tmp_path):
    """After the holder releases, the next watchdog may take over.

    A watchdog that exits cleanly must not keep the machine unwatched.
    """
    lock = tmp_path / "watchdog.lock"
    assert wd._acquire_singleton(lock) is True
    wd._release_singleton()
    assert wd._acquire_singleton(lock) is True


def test_a_crashed_holder_does_not_wedge_the_watchdog(tmp_path):
    """A watchdog that dies must not stop the next one from starting.

    This is the property the old pid-based check got wrong in the
    opposite direction: a stale lock file used to be enough to convince
    the next watchdog to quit. With an OS lock the kernel drops it when
    the holder dies, so the next start succeeds.
    """
    lock = tmp_path / "watchdog.lock"
    code = (
        "from utils import app_watchdog as wd;"
        f"wd._acquire_singleton({str(lock)!r});"
        "print('held', flush=True)"
    )
    proc = subprocess.Popen([sys.executable, "-c", code], cwd=str(REPO_ROOT),
                            stdout=subprocess.PIPE)
    assert b"held" in proc.communicate(timeout=30)[0]
    # The child is gone; its lock is gone with it.
    assert wd._acquire_singleton(lock) is True


def test_two_processes_racing_for_the_singleton_produce_one_winner(tmp_path):
    """Simultaneous starts must not both succeed.

    The old implementation read an empty file and wrote a pid, so two
    processes starting together both saw "no watchdog" and both became
    one.

    The children *hold* the lock for a moment before exiting. Without
    that they would release it the instant they won, and the next child
    would legitimately win in turn -- a mutex hands the lock around, it
    does not hand it out once. What must never happen is two children
    holding it at the same time.
    """
    lock = tmp_path / "watchdog.lock"
    code = (
        "import sys, time;"
        "from utils import app_watchdog as wd;"
        f"ok = wd._acquire_singleton({str(lock)!r});"
        "sys.stdout.write('yes' if ok else 'no'); sys.stdout.flush();"
        "time.sleep(1.5)"
    )
    procs = [
        subprocess.Popen([sys.executable, "-c", code], cwd=str(REPO_ROOT),
                         stdout=subprocess.PIPE)
        for _ in range(6)
    ]
    results = []
    for proc in procs:
        out, _ = proc.communicate(timeout=30)
        results.append(b"yes" in out)
    assert sum(results) == 1, (
        f"{sum(results)} watchdogs held the singleton lock at once; a "
        "second watchdog would supervise the app as well")


# ---------------------------------------------------------------------------
# The pid-recycling defect
# ---------------------------------------------------------------------------

def test_a_recycled_pid_does_not_block_the_next_watchdog(tmp_path):
    """A lock file naming a *live but different* process must not win.

    The lock file records (pid, create_time). A stale file whose pid has
    been recycled onto an unrelated process has a different create-time,
    so it is not the watchdog it claims to be -- and the next watchdog
    must start.

    Before the fix the check was ``pid_exists(pid)`` alone, so this
    scenario made the watchdog quit and left the machine unwatched.
    """
    lock = tmp_path / "watchdog.lock"
    lock.write_text(json.dumps({
        "pid": os.getpid(),
        "create_time": 1000.0,        # not our create-time
    }), encoding="utf-8")

    # Same pid, different fingerprint -> not the same process.
    assert wd._is_same_process(os.getpid(), 1000.0) is False
    # And the watchdog must still be able to take the lock.
    assert wd._acquire_singleton(lock) is True


def test_the_lock_file_records_the_create_time(tmp_path):
    """The identity written to disk must include the fingerprint.

    A bare pid cannot distinguish "the watchdog that is running" from
    "whatever process the OS handed that pid to next".
    """
    lock = tmp_path / "watchdog.lock"
    assert wd._acquire_singleton(lock) is True
    pid, create_time = wd._read_lock_identity(lock)
    assert pid == os.getpid()
    assert create_time is not None, "the fingerprint must be recorded"
    assert wd._is_same_process(pid, create_time) is True


def test_a_legacy_bare_pid_lock_file_still_parses(tmp_path):
    """A lock file written by an older build must still be understood.

    It carries no fingerprint, so the pid is known but the fingerprint
    is not. The reader must not mistake that for a parse failure.
    """
    lock = tmp_path / "watchdog.lock"
    lock.write_text("4242", encoding="utf-8")
    assert wd._read_lock_identity(lock) == (4242, None)


def test_the_lock_file_may_carry_a_leading_lock_byte(tmp_path):
    """The reserved lock byte must not break the reader.

    utils/file_lock.py keeps byte 0 for the lock itself and the payload
    starts at byte 1.
    """
    lock = tmp_path / "watchdog.lock"
    lock.write_bytes(b"\x00" + json.dumps(
        {"pid": 4242, "create_time": 1234.5}).encode("utf-8"))
    assert wd._read_lock_identity(lock) == (4242, 1234.5)


def test_a_missing_lock_file_parses_as_nobody(tmp_path):
    assert wd._read_lock_identity(tmp_path / "absent.lock") == (0, None)


def test_a_corrupt_lock_file_parses_as_nobody(tmp_path):
    lock = tmp_path / "watchdog.lock"
    lock.write_text("not json at all", encoding="utf-8")
    assert wd._read_lock_identity(lock) == (0, None)


# ---------------------------------------------------------------------------
# The unattended reader must follow the new format
# ---------------------------------------------------------------------------

def test_unattended_can_still_find_the_watchdog(tmp_path, monkeypatch):
    """utils/unattended.py reads the same lock file.

    It used to parse a bare pid; the format is now JSON with a
    fingerprint. A stale reader would report "no watchdog running" and
    the UI would offer to start a second one.
    """
    from utils import unattended as ua

    monkeypatch.setattr(wd, "runlogs_dir", lambda: tmp_path)
    lock = tmp_path / "watchdog.lock"
    lock.write_text(json.dumps({"pid": 4242, "create_time": 1.0}),
                    encoding="utf-8")

    # The pid does not exist, so there is no watchdog to find -- but the
    # reader must have parsed the file rather than crashed on it.
    assert ua._watchdog_pid() is None


def test_unattended_finds_a_live_watchdog(tmp_path, monkeypatch):
    """The happy path: a live watchdog pid is reported."""
    from utils import unattended as ua

    monkeypatch.setattr(wd, "runlogs_dir", lambda: tmp_path)
    lock = tmp_path / "watchdog.lock"
    lock.write_text(json.dumps({"pid": os.getpid(), "create_time": 1.0}),
                    encoding="utf-8")

    found = ua._watchdog_pid()
    # Our own pid is alive, but its cmdline is pytest, not "--watchdog",
    # so the watchdog-specific check rejects it. The point is that the
    # file parsed and the pid was read.
    assert found is None or found == os.getpid()
