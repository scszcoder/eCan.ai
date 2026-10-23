"""Settings must not claim unattended mode is on when nothing is watching.

``unattended.json`` records the *user's choice*. Whether a watchdog actually
runs is a separate decision: ``should_skip_watchdog()`` refuses to start one
in dev mode, under pytest, or when ``ECAN_NO_WATCHDOG`` is set. Before this,
``status()``/``set_enabled()`` reported only ``enabled``, so the Settings
switch read "on" in dev while no watchdog would ever be spawned -- the UI
promised crash recovery that could not happen, and nothing said so.

These tests pin the honest signal (``watchdog_available``) against both
reporters, so the switch cannot drift back to echoing the marker alone.
"""

import json

import pytest

from utils import unattended as ua


def _write_marker(tmp_path, enabled=True):
    tmp_path.mkdir(parents=True, exist_ok=True)
    marker = tmp_path / "unattended.json"
    marker.write_text(json.dumps({"enabled": enabled}), encoding="utf-8")
    return marker


@pytest.fixture
def marker(tmp_path, monkeypatch):
    """A real marker file, so is_enabled() reads the filesystem like the app does."""
    m = _write_marker(tmp_path, True)
    monkeypatch.setattr(ua, "_marker", lambda: m)
    monkeypatch.setattr(ua, "_watchdog_pid", lambda: None)
    return m


# --------------------------------------------------------------------------
# status(): the reader Settings uses to paint the switch.
# --------------------------------------------------------------------------


def test_status_reports_available_in_production(monkeypatch, marker):
    monkeypatch.delenv("ECAN_NO_WATCHDOG", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(ua, "_is_dev_mode", lambda: False)
    out = ua.status()
    assert out["enabled"] is True
    assert out["watchdog_available"] is True


def test_status_does_not_claim_available_in_dev(monkeypatch, marker):
    """The dev-skip case: on, but nothing is watching."""
    monkeypatch.delenv("ECAN_NO_WATCHDOG", raising=False)
    monkeypatch.delenv("ECAN_DEV_WATCHDOG", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(ua, "_is_dev_mode", lambda: True)
    out = ua.status()
    assert out["enabled"] is True          # the switch stays on ...
    assert out["watchdog_available"] is False   # ... but the UI is told why
    assert out["watchdog_running"] is False


def test_status_honours_the_dev_opt_in(monkeypatch, marker):
    """A developer running the watchdog from source is 'available'."""
    monkeypatch.delenv("ECAN_NO_WATCHDOG", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("ECAN_DEV_WATCHDOG", "1")
    monkeypatch.setattr(ua, "_is_dev_mode", lambda: True)
    assert ua.status()["watchdog_available"] is True


@pytest.mark.parametrize("skip_env", ["ECAN_NO_WATCHDOG", "PYTEST_CURRENT_TEST"])
def test_status_is_unavailable_under_the_skip_envs(monkeypatch, marker, skip_env):
    monkeypatch.delenv("ECAN_NO_WATCHDOG", raising=False)
    monkeypatch.delenv("ECAN_DEV_WATCHDOG", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(ua, "_is_dev_mode", lambda: False)
    monkeypatch.setenv(skip_env, "1")
    assert ua.status()["watchdog_available"] is False


def test_status_off_still_reports_available(monkeypatch, tmp_path):
    """Availability is about the environment, not the toggle."""
    off = _write_marker(tmp_path, False)
    monkeypatch.setattr(ua, "_marker", lambda: off)
    monkeypatch.setattr(ua, "_watchdog_pid", lambda: None)
    monkeypatch.delenv("ECAN_NO_WATCHDOG", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(ua, "_is_dev_mode", lambda: False)
    out = ua.status()
    assert out["enabled"] is False and out["watchdog_available"] is True


# --------------------------------------------------------------------------
# set_enabled(): the writer, whose result the Settings page trusts directly.
# --------------------------------------------------------------------------


def test_set_enabled_reports_the_skip_on_this_platform(monkeypatch, tmp_path):
    """Turning it on from dev says so, instead of returning a bare True.

    This is the exact shape of the bug: ``enabled: True`` with no watchdog
    possible, which the UI used to render as a working feature.
    """
    m = _write_marker(tmp_path, True)
    monkeypatch.setattr(ua, "_marker", lambda: m)
    monkeypatch.setattr(ua, "_is_dev_mode", lambda: True)
    monkeypatch.delenv("ECAN_NO_WATCHDOG", raising=False)
    monkeypatch.delenv("ECAN_DEV_WATCHDOG", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    res = ua.set_enabled(True)
    assert res["enabled"] is True
    assert res["watchdog_available"] is False
    assert res["logon_task"] is False      # not Windows: no logon task either


def test_set_enabled_reports_available_when_it_can_run(monkeypatch, tmp_path):
    m = _write_marker(tmp_path, True)
    monkeypatch.setattr(ua, "_marker", lambda: m)
    monkeypatch.setattr(ua, "ensure_watchdog_running", lambda: None)
    monkeypatch.setattr(ua, "_is_dev_mode", lambda: False)
    monkeypatch.delenv("ECAN_NO_WATCHDOG", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    assert ua.set_enabled(True)["watchdog_available"] is True


def test_set_enabled_turning_off_keeps_the_key(monkeypatch, tmp_path):
    """Turning it off also reports availability -- the key must not vanish.

    The frontend keys the warning off an explicit ``=== false``; a missing
    key would be treated as 'available' and hide the message.
    """
    m = _write_marker(tmp_path, False)
    monkeypatch.setattr(ua, "_marker", lambda: m)
    monkeypatch.setattr(ua, "_stop_watchdog", lambda: None)
    monkeypatch.setattr(ua, "_is_dev_mode", lambda: True)
    monkeypatch.delenv("ECAN_NO_WATCHDOG", raising=False)
    monkeypatch.delenv("ECAN_DEV_WATCHDOG", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    res = ua.set_enabled(False)
    assert res["enabled"] is False
    assert "watchdog_available" in res


def test_ipc_handler_passes_the_signal_through(monkeypatch, tmp_path):
    """``unattended.set`` returns status(), so the flag reaches the UI."""
    m = _write_marker(tmp_path, True)
    monkeypatch.setattr(ua, "_marker", lambda: m)
    monkeypatch.setattr(ua, "_is_dev_mode", lambda: True)
    monkeypatch.delenv("ECAN_NO_WATCHDOG", raising=False)
    monkeypatch.delenv("ECAN_DEV_WATCHDOG", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    from gui.ipc.types import create_request
    from gui.ipc.w2p_handlers import unattended_handler as uh

    resp = uh.handle_set(create_request("unattended.set"), {"enabled": True})
    assert resp["status"] == "success"
    assert resp["result"]["watchdog_available"] is False
    assert resp["result"]["enabled"] is True