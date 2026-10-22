"""Unattended mode must not start a watchdog in dev, CI or unit tests.

The watchdog relaunches eCan when it dies. That is exactly what we want on a
production kiosk, and exactly what we do *not* want while a developer is
iterating: a stale ``unattended.json`` left behind by a QA run would make
every ``python main.py`` restart itself after the developer closed the window.

These tests pin the skip rules and the environment override.
"""

import json

import pytest

from utils import unattended as ua


def _write_marker(tmp_path, enabled=True):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "unattended.json").write_text(json.dumps({"enabled": enabled}), encoding="utf-8")
    return tmp_path / "unattended.json"


def test_should_skip_when_env_no_watchdog(monkeypatch):
    monkeypatch.setenv("ECAN_NO_WATCHDOG", "1")
    assert ua.should_skip_watchdog() is True


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_should_skip_env_accepts_common_truthy_values(monkeypatch, value):
    monkeypatch.setenv("ECAN_NO_WATCHDOG", value)
    assert ua.should_skip_watchdog() is True


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "maybe"])
def test_should_skip_env_ignores_falsy_values(monkeypatch, value):
    monkeypatch.setenv("ECAN_NO_WATCHDOG", value)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(ua, "_is_dev_mode", lambda: False)
    assert ua.should_skip_watchdog() is False


def test_should_skip_in_dev_mode(monkeypatch):
    monkeypatch.delenv("ECAN_NO_WATCHDOG", raising=False)
    monkeypatch.setattr(ua, "_is_dev_mode", lambda: True)
    assert ua.should_skip_watchdog() is True


def test_should_skip_under_pytest(monkeypatch):
    monkeypatch.delenv("ECAN_NO_WATCHDOG", raising=False)
    monkeypatch.setattr(ua, "_is_dev_mode", lambda: False)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_x::test_y (call)")
    assert ua.should_skip_watchdog() is True


def test_should_not_skip_in_production(monkeypatch):
    monkeypatch.delenv("ECAN_NO_WATCHDOG", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(ua, "_is_dev_mode", lambda: False)
    assert ua.should_skip_watchdog() is False


def test_ensure_watchdog_running_does_not_spawn_in_dev(monkeypatch, tmp_path):
    monkeypatch.setenv("ECAN_NO_WATCHDOG", "1")
    monkeypatch.setattr(ua, "is_enabled", lambda: True)
    monkeypatch.setattr(ua, "_watchdog_pid", lambda: None)
    spawned = []
    monkeypatch.setattr(ua.subprocess, "Popen", lambda *a, **k: spawned.append(a))
    ua.ensure_watchdog_running()
    assert spawned == []


def test_ensure_watchdog_running_spawns_in_production(monkeypatch):
    monkeypatch.delenv("ECAN_NO_WATCHDOG", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(ua, "_is_dev_mode", lambda: False)
    monkeypatch.setattr(ua, "is_enabled", lambda: True)
    monkeypatch.setattr(ua, "_watchdog_pid", lambda: None)
    spawned = []
    monkeypatch.setattr(ua.subprocess, "Popen", lambda *a, **k: spawned.append(a))
    ua.ensure_watchdog_running()
    assert len(spawned) == 1


def test_ensure_watchdog_running_respects_disabled_mode(monkeypatch):
    monkeypatch.delenv("ECAN_NO_WATCHDOG", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(ua, "_is_dev_mode", lambda: False)
    monkeypatch.setattr(ua, "is_enabled", lambda: False)
    monkeypatch.setattr(ua, "_watchdog_pid", lambda: None)
    spawned = []
    monkeypatch.setattr(ua.subprocess, "Popen", lambda *a, **k: spawned.append(a))
    ua.ensure_watchdog_running()
    assert spawned == []


# --------------------------------------------------------------------------
# Dev keepalive opt-in.
#
# Skipping the watchdog in dev is right *by default*: a stale unattended.json
# from a QA run would otherwise restart every ``python main.py`` the developer
# launches. But a developer deliberately working on the watchdog itself — or
# reproducing a crash-loop — needs it running against the source tree, and
# ``main.py --watchdog`` already works there.
#
# The opt-in is an environment variable rather than a settings toggle because
# the value that would be convenient to flip in the GUI (unattended.json) is
# exactly the one a stale copy of can silently re-enable it. An env var is set
# per shell, so it cannot leak into an unrelated run.
# --------------------------------------------------------------------------


def test_dev_keepalive_opt_in_overrides_the_dev_skip(monkeypatch):
    """ECAN_DEV_WATCHDOG=1 lets a developer run the watchdog from source."""
    monkeypatch.delenv("ECAN_NO_WATCHDOG", raising=False)
    # Not a pytest run: this test stands in for a developer's shell.
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("ECAN_DEV_WATCHDOG", "1")
    monkeypatch.setattr(ua, "_is_dev_mode", lambda: True)
    assert ua.should_skip_watchdog() is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_dev_keepalive_opt_in_accepts_common_truthy_values(monkeypatch, value):
    monkeypatch.delenv("ECAN_NO_WATCHDOG", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("ECAN_DEV_WATCHDOG", value)
    monkeypatch.setattr(ua, "_is_dev_mode", lambda: True)
    assert ua.should_skip_watchdog() is False


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "maybe"])
def test_dev_keepalive_opt_in_ignores_falsy_values(monkeypatch, value):
    """A stray non-truthy value must not accidentally enable the watchdog."""
    monkeypatch.delenv("ECAN_NO_WATCHDOG", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("ECAN_DEV_WATCHDOG", value)
    monkeypatch.setattr(ua, "_is_dev_mode", lambda: True)
    assert ua.should_skip_watchdog() is True


def test_dev_keepalive_opt_in_does_not_override_the_explicit_opt_out(monkeypatch):
    """ECAN_NO_WATCHDOG is a deliberate 'not here' and wins over the opt-in.

    CI sets ECAN_NO_WATCHDOG to keep the watchdog out of the whole test run. If
    a developer exports ECAN_DEV_WATCHDOG in their shell profile, CI must not
    silently start spawning watchdogs.
    """
    monkeypatch.setenv("ECAN_NO_WATCHDOG", "1")
    monkeypatch.setenv("ECAN_DEV_WATCHDOG", "1")
    monkeypatch.setattr(ua, "_is_dev_mode", lambda: True)
    assert ua.should_skip_watchdog() is True


def test_dev_keepalive_opt_in_does_not_spawn_under_pytest(monkeypatch):
    """The opt-in must not make the unit-test run spawn real watchdogs."""
    monkeypatch.delenv("ECAN_NO_WATCHDOG", raising=False)
    monkeypatch.setenv("ECAN_DEV_WATCHDOG", "1")
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_x::test_y (call)")
    monkeypatch.setattr(ua, "_is_dev_mode", lambda: True)
    assert ua.should_skip_watchdog() is True


def test_ensure_watchdog_running_spawns_in_dev_with_opt_in(monkeypatch):
    monkeypatch.delenv("ECAN_NO_WATCHDOG", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("ECAN_DEV_WATCHDOG", "1")
    monkeypatch.setattr(ua, "_is_dev_mode", lambda: True)
    monkeypatch.setattr(ua, "is_enabled", lambda: True)
    monkeypatch.setattr(ua, "_watchdog_pid", lambda: None)
    spawned = []
    monkeypatch.setattr(ua.subprocess, "Popen", lambda *a, **k: spawned.append(a))
    ua.ensure_watchdog_running()
    assert len(spawned) == 1
