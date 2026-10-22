"""Worker boot identity: which process is the current eCan run?

A boot id is the smallest signal that says "the work I am about to do
belongs to **this** process". Used as the namespace for leases: any lease
written by another boot id is automatically orphaned, even if its pid
happens to match a recycled OS pid.

Failure modes we deliberately guard against (see tests for the contract):

* never leave a half-written file for another worker to read (atomic
  rename);
* oversized / corrupt / partial files are treated as *no* marker, so a
  crash mid-write never blocks the next run;
* one marker per process: a second process clobbering the file must NOT
  erase the previous generation's identity (it is the previous one that
  becomes orphaned).
"""

import json
import os
import time

import pytest

from utils import worker_boot as wb


def _read(log_dir):
    path = wb.boot_id_path(log_dir)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def test_claim_boot_writes_a_uuid_hex(tmp_path):
    boot = wb.claim_boot(log_dir=str(tmp_path))
    assert isinstance(boot, str) and len(boot) >= 16
    data = _read(tmp_path)
    assert data["boot_id"] == boot
    assert data["pid"] == os.getpid()


def test_claim_boot_is_idempotent_within_one_process(tmp_path):
    """The same process claiming twice is the *same* generation; the boot id
    must not change out from under it."""
    first = wb.claim_boot(log_dir=str(tmp_path))
    second = wb.claim_boot(log_dir=str(tmp_path))
    assert first == second


def test_write_is_atomic_via_rename(tmp_path):
    wb.claim_boot(log_dir=str(tmp_path))
    leftovers = [p.name for p in tmp_path.iterdir() if ".tmp" in p.name]
    assert leftovers == []


def test_release_clears_our_own_marker(tmp_path):
    wb.claim_boot(log_dir=str(tmp_path))
    wb.release_boot(log_dir=str(tmp_path))
    assert not wb.boot_id_path(tmp_path).exists()


def test_release_is_safe_when_no_marker_exists(tmp_path):
    wb.release_boot(log_dir=str(tmp_path))   # must not raise


def test_release_does_not_clobber_another_pids_marker(tmp_path):
    """If a marker exists for a *different* pid, release must NOT clobber it
    -- the new worker is the second generation, the old one becomes the
    orphan."""
    path = wb.boot_id_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"boot_id": "old-boot", "pid": 99999, "stamp": 0.0}),
                    encoding="utf-8")
    wb.release_boot(log_dir=str(tmp_path))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["boot_id"] == "old-boot"


def test_oversized_marker_is_treated_as_missing(tmp_path):
    path = wb.boot_id_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x" * (wb.MAX_BOOT_BYTES + 1), encoding="utf-8")
    assert wb.read_boot(log_dir=str(tmp_path)) is None


def test_corrupt_marker_is_treated_as_missing(tmp_path):
    path = wb.boot_id_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert wb.read_boot(log_dir=str(tmp_path)) is None


def test_read_boot_returns_none_when_no_marker(tmp_path):
    assert wb.read_boot(log_dir=str(tmp_path)) is None


def test_marker_contains_stamp_for_zombie_detection(tmp_path):
    wb.claim_boot(log_dir=str(tmp_path))
    data = _read(tmp_path)
    assert isinstance(data["stamp"], (int, float))
    assert data["stamp"] <= time.time() + 1


def test_refresh_keeps_the_same_boot_id(tmp_path):
    """A still-running worker re-stamps to advertise liveness, but keeps its
    identity across refreshes."""
    first = wb.claim_boot(log_dir=str(tmp_path))
    refreshed = wb.refresh_boot(log_dir=str(tmp_path))
    assert refreshed == first


def test_refresh_is_noop_when_no_marker_exists(tmp_path):
    assert wb.refresh_boot(log_dir=str(tmp_path)) is None


def test_refresh_is_noop_for_a_different_pids_marker(tmp_path):
    path = wb.boot_id_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"boot_id": "old-boot", "pid": 99999, "stamp": 1.0}),
                    encoding="utf-8")
    assert wb.refresh_boot(log_dir=str(tmp_path)) is None
