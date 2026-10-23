"""The dev opt-in: a persisted flag that actually starts the watchdog in dev.

``should_skip_watchdog()`` has always refused to start a watchdog in dev,
which was right for the common case but blocked the one developer who wants
it: the one reproducing a crash-loop, or working on the watchdog itself. That
opt-in existed only as ``ECAN_DEV_WATCHDOG``, scoped to a shell -- so the
Settings UI could not express it, and "unattended mode is on" in dev did
nothing.

``allow_in_dev`` in ``unattended.json`` is the persisted counterpart. These
tests pin the property that makes it safe to store next to ``enabled``:
it defaults to off and cannot be turned on by a stale, copied or
hand-edited marker. If that ever regresses, a developer's normal
``python main.py`` silently starts respawning after a crash.

Note on ``PYTEST_CURRENT_TEST``: pytest (re)sets it around each test's call
phase, so deleting it inside a fixture is not enough -- the delete has to
happen in the test body. Every test that expects a watchdog to be allowed
therefore calls ``_outside_pytest(mp)`` first, as
tests/unit/test_unattended_dev_skip.py does.
"""

import json

import pytest

from utils import unattended as ua


def _marker_with(tmp_path, **fields):
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "unattended.json"
    path.write_text(json.dumps(fields), encoding="utf-8")
    return path


def _outside_pytest(mp):
    """Stand in for a real shell: pytest's own guard must not apply."""
    mp.delenv("PYTEST_CURRENT_TEST", raising=False)


@pytest.fixture
def prod(monkeypatch):
    """A packaged-style run: not dev, no opt-out, not a test."""
    monkeypatch.delenv("ECAN_NO_WATCHDOG", raising=False)
    monkeypatch.delenv("ECAN_DEV_WATCHDOG", raising=False)
    monkeypatch.setattr(ua, "_is_dev_mode", lambda: False)
    return monkeypatch


@pytest.fixture
def dev(monkeypatch):
    monkeypatch.delenv("ECAN_NO_WATCHDOG", raising=False)
    monkeypatch.delenv("ECAN_DEV_WATCHDOG", raising=False)
    monkeypatch.setattr(ua, "_is_dev_mode", lambda: True)
    return monkeypatch


# --------------------------------------------------------------------------
# The default must not change: a marker without the key still skips in dev.
# --------------------------------------------------------------------------


def test_legacy_marker_without_the_key_still_skips_in_dev(dev, tmp_path):
    m = _marker_with(tmp_path, enabled=True)
    dev.setattr(ua, "_marker", lambda: m)
    assert ua.allows_dev_watchdog() is False
    assert ua.should_skip_watchdog() is True


def test_stale_marker_from_a_qa_run_cannot_arm_the_watchdog(dev, tmp_path):
    """The property the env var was chosen for, now that the value is stored."""
    m = _marker_with(tmp_path, enabled=True, allow_in_dev=False)
    dev.setattr(ua, "_marker", lambda: m)
    assert ua.should_skip_watchdog() is True


def test_enabled_alone_does_not_imply_a_dev_watchdog(dev, tmp_path):
    """``enabled`` must not be enough -- that is the bug this flag exists for."""
    m = _marker_with(tmp_path, enabled=True)
    dev.setattr(ua, "_marker", lambda: m)
    assert ua.is_enabled() is True
    assert ua.should_skip_watchdog() is True


# --------------------------------------------------------------------------
# The opt-in itself.
# --------------------------------------------------------------------------


def test_allow_in_dev_lets_the_watchdog_run_in_dev(dev, tmp_path):
    m = _marker_with(tmp_path, enabled=True, allow_in_dev=True)
    dev.setattr(ua, "_marker", lambda: m)
    _outside_pytest(dev)
    assert ua.should_skip_watchdog() is False


def test_allow_in_dev_argument_overrides_the_marker(dev, tmp_path):
    """set_enabled computes the answer before the write, so this must win."""
    m = _marker_with(tmp_path, enabled=True, allow_in_dev=False)
    dev.setattr(ua, "_marker", lambda: m)
    _outside_pytest(dev)
    assert ua.should_skip_watchdog(allow_in_dev=True) is False
    assert ua.should_skip_watchdog(allow_in_dev=False) is True


def test_env_opt_in_still_works_without_the_marker(dev, tmp_path):
    """ECAN_DEV_WATCHDOG keeps working -- it is the per-shell shortcut."""
    m = _marker_with(tmp_path, enabled=True)
    dev.setattr(ua, "_marker", lambda: m)
    dev.setenv("ECAN_DEV_WATCHDOG", "1")
    _outside_pytest(dev)
    assert ua.should_skip_watchdog() is False


def test_dev_mode_is_irrelevant_in_production(prod, tmp_path):
    """allow_in_dev changes nothing outside dev -- it is not a second switch."""
    m = _marker_with(tmp_path, enabled=True, allow_in_dev=False)
    prod.setattr(ua, "_marker", lambda: m)
    _outside_pytest(prod)
    assert ua.should_skip_watchdog() is False


# --------------------------------------------------------------------------
# The guards that must survive any opt-in.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("opt_in", [True, False])
def test_explicit_opt_out_beats_the_marker(dev, tmp_path, opt_in):
    m = _marker_with(tmp_path, enabled=True, allow_in_dev=opt_in)
    dev.setattr(ua, "_marker", lambda: m)
    dev.setenv("ECAN_NO_WATCHDOG", "1")
    _outside_pytest(dev)
    assert ua.should_skip_watchdog() is True


@pytest.mark.parametrize("opt_in", [True, False])
def test_pytest_never_spawns_a_watchdog(dev, tmp_path, opt_in):
    """Absolute: a test run must not respawn eCan, whatever the marker says."""
    m = _marker_with(tmp_path, enabled=True, allow_in_dev=opt_in)
    dev.setattr(ua, "_marker", lambda: m)
    dev.setenv("PYTEST_CURRENT_TEST", "test_x::test_y (call)")
    assert ua.should_skip_watchdog() is True


# --------------------------------------------------------------------------
# Persistence: set_enabled must not clobber the flag it was not asked about.
# --------------------------------------------------------------------------


def test_toggling_enabled_preserves_the_dev_opt_in(dev, tmp_path):
    m = _marker_with(tmp_path, enabled=True, allow_in_dev=True)
    dev.setattr(ua, "_marker", lambda: m)
    res = ua.set_enabled(True)          # allow_in_dev omitted -> keep stored
    assert res["allow_in_dev"] is True
    assert ua.allows_dev_watchdog() is True


def test_set_enabled_turning_off_defaults_the_dev_opt_in(dev, tmp_path):
    """An old marker (no key) reads as off; we must not invent a true."""
    m = _marker_with(tmp_path, enabled=True)
    dev.setattr(ua, "_marker", lambda: m)
    assert ua.set_enabled(False)["allow_in_dev"] is False


def test_set_enabled_can_set_the_dev_opt_in(dev, tmp_path):
    m = _marker_with(tmp_path, enabled=True, allow_in_dev=False)
    dev.setattr(ua, "_marker", lambda: m)
    _outside_pytest(dev)
    res = ua.set_enabled(True, allow_in_dev=True)
    assert res["allow_in_dev"] is True
    assert res["watchdog_available"] is True
    assert json.loads(m.read_text(encoding="utf-8"))["allow_in_dev"] is True


def test_set_enabled_reports_available_for_the_value_it_wrote(dev, tmp_path):
    """watchdog_available must describe the stored state, not the old one."""
    m = _marker_with(tmp_path, enabled=True, allow_in_dev=False)
    dev.setattr(ua, "_marker", lambda: m)
    _outside_pytest(dev)
    assert ua.set_enabled(True, allow_in_dev=True)["watchdog_available"] is True
    assert ua.set_enabled(True, allow_in_dev=False)["watchdog_available"] is False


# --------------------------------------------------------------------------
# status(): what the UI renders.
# --------------------------------------------------------------------------


def test_status_reports_the_dev_controls(dev, tmp_path):
    m = _marker_with(tmp_path, enabled=True, allow_in_dev=False)
    dev.setattr(ua, "_marker", lambda: m)
    dev.setattr(ua, "_watchdog_pid", lambda: None)
    _outside_pytest(dev)
    out = ua.status()
    assert out["dev_mode"] is True          # the UI shows the opt-in
    assert out["allow_in_dev"] is False
    assert out["watchdog_available"] is False


def test_status_hides_the_opt_in_outside_dev(prod, tmp_path):
    m = _marker_with(tmp_path, enabled=True)
    prod.setattr(ua, "_marker", lambda: m)
    prod.setattr(ua, "_watchdog_pid", lambda: None)
    _outside_pytest(prod)
    assert ua.status()["dev_mode"] is False


# --------------------------------------------------------------------------
# The IPC boundary: an older frontend omits the key and must not clear it.
# --------------------------------------------------------------------------


def test_handler_keeps_the_opt_in_when_the_frontend_omits_it(dev, tmp_path):
    m = _marker_with(tmp_path, enabled=True, allow_in_dev=True)
    dev.setattr(ua, "_marker", lambda: m)
    dev.setattr(ua, "_watchdog_pid", lambda: None)

    from gui.ipc.types import create_request
    from gui.ipc.w2p_handlers import unattended_handler as uh

    resp = uh.handle_set(create_request("unattended.set"), {"enabled": True})
    assert resp["status"] == "success"
    assert resp["result"]["allow_in_dev"] is True


def test_handler_sets_the_opt_in_when_the_frontend_sends_it(dev, tmp_path):
    m = _marker_with(tmp_path, enabled=True, allow_in_dev=False)
    dev.setattr(ua, "_marker", lambda: m)
    dev.setattr(ua, "_watchdog_pid", lambda: None)
    _outside_pytest(dev)

    from gui.ipc.types import create_request
    from gui.ipc.w2p_handlers import unattended_handler as uh

    resp = uh.handle_set(create_request("unattended.set"),
                         {"enabled": True, "allow_in_dev": True})
    assert resp["result"]["allow_in_dev"] is True
    assert resp["result"]["watchdog_available"] is True


# --------------------------------------------------------------------------
# The path that actually spawns it.
# --------------------------------------------------------------------------


def test_ensure_watchdog_running_spawns_in_dev_with_the_flag(dev, tmp_path):
    m = _marker_with(tmp_path, enabled=True, allow_in_dev=True)
    dev.setattr(ua, "_marker", lambda: m)
    dev.setattr(ua, "_watchdog_pid", lambda: None)
    _outside_pytest(dev)
    spawned = []
    dev.setattr(ua.subprocess, "Popen", lambda *a, **k: spawned.append(a))
    ua.ensure_watchdog_running()
    assert len(spawned) == 1


def test_ensure_watchdog_running_still_skips_in_dev_without_the_flag(dev, tmp_path):
    m = _marker_with(tmp_path, enabled=True)
    dev.setattr(ua, "_marker", lambda: m)
    dev.setattr(ua, "_watchdog_pid", lambda: None)
    _outside_pytest(dev)
    spawned = []
    dev.setattr(ua.subprocess, "Popen", lambda *a, **k: spawned.append(a))
    ua.ensure_watchdog_running()
    assert spawned == []


def test_uninstall_still_removes_a_marker_that_has_the_flag(dev, tmp_path):
    """disable_for_uninstall deletes the file, so the flag goes with it."""
    m = _marker_with(tmp_path, enabled=True, allow_in_dev=True)
    dev.setattr(ua, "_marker", lambda: m)
    dev.setattr(ua, "_stop_watchdog", lambda: None)
    ua.disable_for_uninstall()
    assert not m.exists()
    assert ua.allows_dev_watchdog() is False