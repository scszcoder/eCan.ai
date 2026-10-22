"""Wiring contract: a worker subprocess claims a boot id at start and
releases it on a clean stop.

The two hooks in ``agent.ec_tasks.worker_entry`` are tested by exercising
the underlying helpers directly (the module's ``main()`` path also calls
``argparse`` and is covered by the supervisor's existing subprocess tests).
This file pins the part of the contract that is unique to the boot id --
namely, that the released marker belongs to the releasing process.
"""

import json
import os
from unittest.mock import patch

import pytest

from utils import worker_boot as wb


def test_claim_boot_at_worker_start_writes_a_marker(tmp_path):
    boot = wb.claim_boot(log_dir=str(tmp_path))
    assert boot
    data = json.loads(wb.boot_id_path(tmp_path).read_text(encoding="utf-8"))
    assert data["pid"] == os.getpid()
    assert data["boot_id"] == boot
    # Tidy up so other tests do not see the global marker.
    wb.release_boot(log_dir=str(tmp_path))


def test_release_at_worker_drain_clears_our_marker(tmp_path):
    wb.claim_boot(log_dir=str(tmp_path))
    wb.release_boot(log_dir=str(tmp_path))
    assert not wb.boot_id_path(tmp_path).exists()


def test_release_does_not_clobber_a_different_pids_marker(tmp_path):
    """The drain path must not erase a marker left by a previous generation
    -- a reused OS pid must never silently absorb a different boot's id."""
    marker = wb.boot_id_path(str(tmp_path))
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"boot_id": "old-boot", "pid": 99999, "stamp": 0.0}),
                      encoding="utf-8")
    with patch.object(os, "getpid", return_value=11111):
        wb.release_boot(log_dir=str(tmp_path))
    data = json.loads(marker.read_text(encoding="utf-8"))
    assert data["boot_id"] == "old-boot"


def test_hooks_tolerate_appdata_not_writable(monkeypatch, tmp_path):
    """If appdata is not writable (sandbox, missing dir), the hooks must
    log and return -- not crash the worker."""
    from utils import worker_boot as wb_mod

    # Force the default log_dir to a non-existent path under a not-creatable
    # location, then claim_boot must still return something usable.
    def boom(*_a, **_k):
        raise OSError("no appdata")

    monkeypatch.setattr(wb_mod, "_runlogs_dir", boom)
    # Even with a borked runlogs dir, claim should not raise; it returns a
    # fresh id (writes are best-effort).
    boot = wb_mod.claim_boot()
    assert isinstance(boot, str) and len(boot) >= 16