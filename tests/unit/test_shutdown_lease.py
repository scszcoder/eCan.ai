"""The shutdown lease must be taken *before* the long teardown starts.

gui/WebGUI.py::closeEvent does roughly 8 seconds of work between "the user
pressed Yes" and ``os._exit(0)``: live-chat drain, lightrag stop, MCP
cleanup, port release. If the process dies inside that window — power loss,
OOM killer, taskkill /F — no clean-exit flag is ever written and the watchdog
relaunches an app the user deliberately closed.

So the lease is claimed at the *start* of the teardown, not at the end.

These tests exercise the helper that the GUI calls, without importing PySide6
(so they run on a machine without the GUI toolkit installed).
"""

import time

import pytest

from utils import exit_intent as ei


def test_claim_shutdown_lease_writes_marker(tmp_path):
    ok = ei.claim_shutdown_lease(reason="user_exit", log_dir=str(tmp_path))
    assert ok is True
    assert ei.is_exiting(log_dir=str(tmp_path)) is True


def test_claim_shutdown_lease_uses_default_grace(tmp_path):
    ei.claim_shutdown_lease(reason="user_exit", log_dir=str(tmp_path))
    data = ei.read_exit_lease(str(tmp_path))
    assert data["grace_s"] == ei.DEFAULT_GRACE_S


def test_claim_shutdown_lease_grace_outlives_a_full_teardown(tmp_path):
    """The lease must outlast the ~8s teardown window with a wide margin."""
    ei.claim_shutdown_lease(reason="user_exit", log_dir=str(tmp_path))
    data = ei.read_exit_lease(str(tmp_path))
    assert data["grace_s"] >= 60


def test_claim_shutdown_lease_is_idempotent(tmp_path):
    ei.claim_shutdown_lease(reason="user_exit", log_dir=str(tmp_path))
    ei.claim_shutdown_lease(reason="user_exit", log_dir=str(tmp_path))
    assert ei.is_exiting(log_dir=str(tmp_path)) is True


def test_claim_shutdown_lease_never_raises(tmp_path, monkeypatch):
    """A broken lease must not stop the app from closing."""
    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(ei, "mark_exiting", boom)
    assert ei.claim_shutdown_lease(reason="user_exit", log_dir=str(tmp_path)) is False


def test_claim_shutdown_lease_expires_on_its_own(tmp_path):
    ei.claim_shutdown_lease(reason="user_exit", grace_s=1, log_dir=str(tmp_path))
    assert ei.is_exiting(log_dir=str(tmp_path), now=time.time() + 2) is False


def test_ota_lease_outlives_a_normal_upgrade_window(tmp_path):
    """An OTA replacement takes longer than a plain quit."""
    ei.claim_shutdown_lease(reason="ota_update", grace_s=600, log_dir=str(tmp_path))
    data = ei.read_exit_lease(str(tmp_path))
    assert data["grace_s"] >= 300


def test_uninstall_lease_is_permanent(tmp_path):
    ei.claim_shutdown_lease(reason="uninstall", grace_s=float("inf"), log_dir=str(tmp_path))
    assert ei.is_exiting(log_dir=str(tmp_path), now=time.time() + 10**7) is True
