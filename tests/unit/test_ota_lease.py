"""The OTA installer must claim a shutdown lease before it replaces the exe.

``ota/core/installer.py`` terminates the running app (hard, with
``taskkill /F``) and then replaces the executable. During that window the
watchdog must not relaunch the old build.

The lease has to be claimed *before* the process is killed — afterwards the
code no longer runs.

These tests exercise the helper in isolation; the platform-specific process
killing is not involved.
"""

import json
import time

import pytest

from utils import exit_intent as ei


def test_claim_ota_lease_writes_a_marker(tmp_path):
    from ota.core import installer as ins
    ok = ins.claim_ota_lease(log_dir=str(tmp_path))
    assert ok is True
    lease = ei.read_exit_lease(str(tmp_path))
    assert lease["reason"] == "ota_update"


def test_ota_lease_outlasts_the_install(tmp_path):
    from ota.core import installer as ins
    ins.claim_ota_lease(log_dir=str(tmp_path))
    lease = ei.read_exit_lease(str(tmp_path))
    # The installer replaces the exe, then relaunches; the lease must cover
    # that whole window.
    assert lease["grace_s"] >= 300


def test_ota_lease_is_active_right_after_claiming(tmp_path):
    from ota.core import installer as ins
    ins.claim_ota_lease(log_dir=str(tmp_path))
    assert ei.is_exiting(log_dir=str(tmp_path)) is True


def test_ota_lease_never_raises(tmp_path, monkeypatch):
    from ota.core import installer as ins

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(ei, "mark_exiting", boom)
    assert ins.claim_ota_lease(log_dir=str(tmp_path)) is False
