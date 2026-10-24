"""Regression tests for six defects found in self-review of the lease stack.

These are not new features. Each one is a bug that shipped in
``utils/worker_boot.py`` / ``utils/task_lease.py`` /
``agent/ec_tasks/zombie_recovery.py`` and was reproduced by hand before
being pinned here. Read the module docstring of each test for the exact
failure.

The unifying root cause: identity was expressed as a bare ``pid``, and
liveness was expressed as a wall-clock difference. Both are wrong on their
own -- the OS recycles pids, and wall clocks jump. ``crash_boundary.py``
already solved the pid half with ``process_create_time``; the lease stack
just never adopted it.
"""

import json
import os
import subprocess
import sys
import time
from unittest.mock import patch

import pytest

from utils import task_lease as tl
from utils import worker_boot as wb


#: A pid that is definitely running, so "the holder is alive" can be tested
#: without depending on whatever the OS happens to have allocated.
_LIVE_PID = None


def _live_other_pid() -> int:
    """The pid of a live process that is definitely not us."""
    global _LIVE_PID
    if _LIVE_PID is None:
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"])
        _LIVE_PID = proc.pid
    return _LIVE_PID


# ══════════════════════════════════════════════════════════════════════
# ① claim_boot adopted a stale marker's identity when the OS recycled its
#    pid. That erases the one distinction boot_id exists to make.
# ══════════════════════════════════════════════════════════════════════

def test_claim_boot_does_not_adopt_a_stale_marker_with_our_pid(tmp_path):
    """A marker left by a crashed generation must never be inherited, even
    when the OS has handed its pid back to us.

    Before the fix: claim_boot() returned the *previous* generation's
    boot_id, so every lease written afterwards was indistinguishable from
    the dead run's work.
    """
    path = wb.boot_id_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "boot_id": "OLD-GENERATION",
        "pid": os.getpid(),          # <- same pid, recycled
        "stamp": time.time() - 99999,
    }), encoding="utf-8")

    got = wb.claim_boot(log_dir=str(tmp_path))
    assert got != "OLD-GENERATION"


def test_claim_boot_reuses_our_own_fresh_marker(tmp_path):
    """The idempotence guarantee must survive the fix: two claims in one
    live process are the same generation."""
    first = wb.claim_boot(log_dir=str(tmp_path))
    second = wb.claim_boot(log_dir=str(tmp_path))
    assert first == second


def test_boot_record_carries_process_create_time(tmp_path):
    """The marker must record create_time so a later reader can tell a
    recycled pid from the original owner."""
    wb.claim_boot(log_dir=str(tmp_path))
    data = json.loads(wb.boot_id_path(tmp_path).read_text(encoding="utf-8"))
    assert "process_create_time" in data


def test_same_pid_different_create_time_is_not_the_same_generation(tmp_path):
    """The create_time fingerprint is what actually disambiguates; assert it
    is compared, not just stored."""
    path = wb.boot_id_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "boot_id": "OLD-GENERATION",
        "pid": os.getpid(),
        "process_create_time": 1000.0,      # <- not our create_time
        "stamp": time.time(),
    }), encoding="utf-8")

    got = wb.claim_boot(log_dir=str(tmp_path))
    assert got != "OLD-GENERATION"


# ══════════════════════════════════════════════════════════════════════
# ② release_boot deleted a marker it could not parse, destroying exactly
#    the forensic evidence it claims to preserve.
# ══════════════════════════════════════════════════════════════════════

def test_release_boot_keeps_a_marker_it_could_not_parse(tmp_path):
    """Unreadable marker => we cannot prove ownership => we must not delete.

    Before the fix: _read() returned None for corrupt input, the
    ownership guard short-circuited on `existing and ...`, and the
    unlink ran anyway.
    """
    path = wb.boot_id_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("garbage-from-another-process", encoding="utf-8")

    wb.release_boot(log_dir=str(tmp_path))
    assert path.exists()


def test_release_boot_keeps_an_oversized_marker(tmp_path):
    path = wb.boot_id_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x" * (wb.MAX_BOOT_BYTES + 1), encoding="utf-8")

    wb.release_boot(log_dir=str(tmp_path))
    assert path.exists()


def test_release_boot_still_removes_our_own_marker(tmp_path):
    wb.claim_boot(log_dir=str(tmp_path))
    wb.release_boot(log_dir=str(tmp_path))
    assert not wb.boot_id_path(tmp_path).exists()


# ══════════════════════════════════════════════════════════════════════
# ③ claim_boot reported success even when nothing was persisted, so
#    callers believed they had a durable identity in an unwritable appdata.
# ══════════════════════════════════════════════════════════════════════

def test_claim_boot_reports_that_nothing_was_persisted(tmp_path):
    """A silent 'here is your boot id' on a failed write is a lie the
    caller cannot detect. Durability must be observable."""
    with patch.object(wb, "_write", return_value=False):
        got = wb.claim_boot(log_dir=str(tmp_path))
    assert got                       # a usable id is still handed out
    assert wb.boot_is_durable(log_dir=str(tmp_path)) is False


def test_claim_boot_returns_the_id_on_success(tmp_path):
    got = wb.claim_boot(log_dir=str(tmp_path))
    assert got
    assert json.loads(wb.boot_id_path(tmp_path).read_text(
        encoding="utf-8"))["boot_id"] == got
    assert wb.boot_is_durable(log_dir=str(tmp_path)) is True


def test_claim_boot_on_unwritable_dir_does_not_raise(tmp_path):
    """The worker must keep running when appdata is unwritable, and the
    returned id must still be unique — an empty id would be written into
    every lease and make them indistinguishable."""
    if os.name == "nt":
        # Windows ignores the POSIX permission bits: chmod 0o500 on a
        # directory does not stop the owner from creating files in it, so
        # the premise of this test ("the directory cannot be written")
        # cannot be set up here. The unwritable path is covered by
        # test_claim_boot_reports_that_nothing_was_persisted.
        pytest.skip("POSIX permission bits are not enforced on Windows")
    os.chmod(tmp_path, 0o500)               # read+exec, cannot create
    try:
        got = wb.claim_boot(log_dir=str(tmp_path))
        assert got and len(got) >= 16
        assert wb.boot_is_durable(log_dir=str(tmp_path)) is False
    finally:
        os.chmod(tmp_path, 0o700)


def test_claim_boot_never_returns_an_empty_id(tmp_path):
    """An empty boot id would be stamped onto every lease, making leases
    from different runs indistinguishable."""
    with patch.object(wb, "_write", return_value=False):
        got = wb.claim_boot(log_dir=str(tmp_path))
    assert got != ""


# ══════════════════════════════════════════════════════════════════════
# ④ Liveness was never consulted. A SIGKILLed worker's task stayed
#    "held" for the whole TTL, which is the exact case recovery exists for.
# ══════════════════════════════════════════════════════════════════════

def test_is_active_is_false_when_the_holder_is_dead(tmp_path):
    tl.acquire(task_id="t", boot_id="b", worker_pid=999999, ttl_s=600,
               log_dir=str(tmp_path))
    with patch.object(wb, "process_alive", return_value=False):
        assert tl.is_active("t", log_dir=str(tmp_path)) is False


def test_acquire_reclaims_a_dead_holders_lease_before_its_ttl(tmp_path):
    """SIGKILL must not cost the user a full TTL of a stuck task."""
    tl.acquire(task_id="t", boot_id="old", worker_pid=999999,
               ttl_s=600, log_dir=str(tmp_path))
    with patch.object(wb, "process_alive", return_value=False):
        ok = tl.acquire(task_id="t", boot_id="new", worker_pid=os.getpid(),
                        ttl_s=600, log_dir=str(tmp_path))
    assert ok is True
    assert tl.read_lease("t", log_dir=str(tmp_path))["boot_id"] == "new"


def test_acquire_refuses_takeover_while_the_holder_is_alive_inside_the_ttl(tmp_path):
    """A live worker holding the lease means the task may be running right
    now — taking it over would run it twice."""
    tl.acquire(task_id="t", boot_id="old", worker_pid=_live_other_pid(),
               ttl_s=600, log_dir=str(tmp_path))
    with patch.object(wb, "process_alive", return_value=True):
        ok = tl.acquire(task_id="t", boot_id="new", worker_pid=os.getpid(),
                        ttl_s=600, log_dir=str(tmp_path))
    assert ok is False
    assert tl.read_lease("t", log_dir=str(tmp_path))["boot_id"] == "old"


def test_acquire_takes_over_once_the_ttl_has_lapsed(tmp_path):
    """The long-standing contract: an elapsed TTL makes the lease fair game.
    A worker that wants to keep a long task must renew it."""
    tl.acquire(task_id="t", boot_id="old", worker_pid=_live_other_pid(),
               ttl_s=1, log_dir=str(tmp_path))
    later = time.time() + 9999
    with patch.object(wb, "process_alive", return_value=True):
        ok = tl.acquire(task_id="t", boot_id="new", worker_pid=os.getpid(),
                        ttl_s=600, log_dir=str(tmp_path), now=later)
    assert ok is True
    assert tl.read_lease("t", log_dir=str(tmp_path))["boot_id"] == "new"


def test_acquire_refuses_takeover_when_liveness_is_unknown(tmp_path):
    """When the OS cannot tell us whether the holder is alive, we must not
    guess: refusing costs a delayed retry, guessing costs a double run."""
    tl.acquire(task_id="t", boot_id="old", worker_pid=999999,
               ttl_s=600, log_dir=str(tmp_path))
    with patch.object(wb, "process_alive", return_value=None):
        ok = tl.acquire(task_id="t", boot_id="new", worker_pid=os.getpid(),
                        ttl_s=600, log_dir=str(tmp_path))
    assert ok is False


def test_identify_orphans_reports_a_killed_worker_before_ttl(tmp_path):
    """End-to-end: the task a SIGKILLed worker was running must show up as
    an orphan on the next startup, not after the lease TTL."""
    from agent.ec_tasks import zombie_recovery as zr

    tl.acquire(task_id="t-killed", boot_id="old", worker_pid=999999,
               ttl_s=3600, log_dir=str(tmp_path))
    with patch.object(wb, "process_alive", return_value=False):
        orphans = zr.identify_orphans(leases_dir=str(tmp_path))
    assert "t-killed" in orphans


# ══════════════════════════════════════════════════════════════════════
# ⑤ Wall-clock TTLs. A backwards clock jump made a lease immortal, and
#    the original test suite *codified that as correct behaviour*.
# ══════════════════════════════════════════════════════════════════════

def test_dead_holders_lease_is_reclaimed_after_a_backward_clock_jump(tmp_path):
    tl.acquire(task_id="t", boot_id="old", worker_pid=999999,
               ttl_s=600, log_dir=str(tmp_path))
    with patch.object(wb, "process_alive", return_value=False):
        assert tl.is_active("t", log_dir=str(tmp_path),
                            now=time.time() - 86400) is False


def test_live_holders_lease_survives_a_backward_clock_jump(tmp_path):
    """When liveness is knowable it wins over the clock in both directions."""
    tl.acquire(task_id="t", boot_id="b", worker_pid=os.getpid(),
               ttl_s=600, log_dir=str(tmp_path))
    with patch.object(wb, "process_alive", return_value=True):
        assert tl.is_active("t", log_dir=str(tmp_path),
                            now=time.time() - 86400) is True


def test_unknown_liveness_falls_back_to_ttl_and_keeps_negative_age(tmp_path):
    """With no psutil we cannot tell; a negative age must not be read as
    'expired', or a clock jump hands the task to a second worker."""
    tl.acquire(task_id="t", boot_id="b", worker_pid=999999,
               ttl_s=600, log_dir=str(tmp_path))
    with patch.object(wb, "process_alive", return_value=None):
        assert tl.is_active("t", log_dir=str(tmp_path),
                            now=time.time() - 86400) is True


# ══════════════════════════════════════════════════════════════════════
# ⑥ task_id sanitisation collided, so two distinct tasks could share one
#    lease file.
# ══════════════════════════════════════════════════════════════════════

def test_distinct_task_ids_never_share_a_lease_file(tmp_path):
    a = tl.lease_path("a/b", str(tmp_path))
    b = tl.lease_path("a_b", str(tmp_path))
    assert a != b


def test_lease_path_stays_inside_the_leases_dir(tmp_path):
    root = tl._leases_root(str(tmp_path)).resolve()
    for evil in ("../../etc/passwd", "..\\..\\windows\\system32", "a/../../b"):
        assert root in tl.lease_path(evil, str(tmp_path)).resolve().parents or \
               str(root) in str(tl.lease_path(evil, str(tmp_path)).resolve())


def test_long_task_ids_still_yield_a_usable_filename(tmp_path):
    """Percent-encoding expands a character up to three bytes, so a long id
    could exceed the filesystem's 255-byte filename limit. Those ids must
    fall back to a digest rather than fail to write at all."""
    long_id = "/" * 300
    path = tl.lease_path(long_id, str(tmp_path))
    assert len(path.name.encode("utf-8")) <= 255
    # And the lease must still round-trip.
    assert tl.acquire(task_id=long_id, boot_id="b", worker_pid=os.getpid(),
                      ttl_s=60, log_dir=str(tmp_path)) is True
    assert tl.read_lease(long_id, log_dir=str(tmp_path)) is not None


def test_orphan_detection_reads_the_task_id_from_the_payload(tmp_path):
    """The filename is not reversible (long ids use a digest), so recovery
    must take the task id from the lease payload."""
    from agent.ec_tasks import zombie_recovery as zr

    long_id = "/" * 300
    tl.acquire(task_id=long_id, boot_id="old", worker_pid=999999,
               ttl_s=10, log_dir=str(tmp_path), now=time.time() - 3600)
    with patch.object(wb, "process_alive", return_value=False):
        orphans = zr.identify_orphans(leases_dir=str(tmp_path))
    assert long_id in orphans


# ══════════════════════════════════════════════════════════════════════
# ⑦ The same recycled-pid defect exists in the Step 0 shutdown lease.
#    A finite lease whose pid the OS has recycled would be mistaken for
#    "our own lease" and kept — hiding a crash of the app running now.
# ══════════════════════════════════════════════════════════════════════

def test_startup_drops_a_stale_shutdown_lease_with_a_recycled_pid(tmp_path):
    from utils import exit_intent as ei

    ei.mark_exiting(reason="user_exit", grace_s=600, log_dir=str(tmp_path))
    # Rewrite the fingerprint to a different process that happens to have
    # the same pid -- the OS handed our pid back to a dead generation.
    path = ei.exit_intent_path(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["pid"] = os.getpid()
    data["process_create_time"] = 1000.0     # not ours
    path.write_text(json.dumps(data), encoding="utf-8")

    ei.on_startup(log_dir=str(tmp_path))
    assert ei.read_exit_lease(log_dir=str(tmp_path)) is None


def test_startup_keeps_the_permanent_uninstall_lease(tmp_path):
    """The uninstall marker is written by the Inno Setup installer, which
    cannot call Python: it carries no pid fingerprint at all. It must
    survive startup, or the watchdog relaunches an app the user deleted."""
    from utils import exit_intent as ei

    path = ei.exit_intent_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "reason": "uninstall", "at": time.time(),
        "grace_s": "inf", "pid": 0,
    }), encoding="utf-8")

    ei.on_startup(log_dir=str(tmp_path))
    assert ei.read_exit_lease(log_dir=str(tmp_path)) is not None
    assert ei.is_permanent_lease(ei.read_exit_lease(log_dir=str(tmp_path))) is True


def test_startup_keeps_a_lease_this_process_actually_wrote(tmp_path):
    """A lease written by *this* process is ours, fingerprint and all."""
    from utils import exit_intent as ei

    ei.mark_exiting(reason="ota_update", grace_s=600, log_dir=str(tmp_path))
    ei.on_startup(log_dir=str(tmp_path))
    assert ei.read_exit_lease(log_dir=str(tmp_path)) is not None