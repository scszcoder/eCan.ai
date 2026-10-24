"""Unattended mode must be able to start itself on Linux and macOS too.

``utils/unattended.py`` used to create a *Windows* logon task and return early
on every other platform: the Settings switch said "on", ``unattended.json``
recorded the user's choice, and nothing whatsoever happened at the next login.
These tests pin the three spellings of "start eCan at logon" -- logon task,
XDG desktop entry, LaunchAgent -- and, just as important, that writing them
never touches the real home directory during a test run.

Every test that exercises the writer points ``ECAN_AUTOSTART_HOME`` at
``tmp_path``, which is also what keeps ``_under_test()`` from refusing.
"""
import json
import os
import plistlib
import stat
import sys
import xml.etree.ElementTree as ET

import pytest

from utils import unattended as ua
from utils import watchdog_breaker as wb


# The fixture below stubs the launcher so no test can spawn a real watchdog.
# A test that asserts on *how* it is spawned needs the real thing back.
_REAL_ENSURE_WATCHDOG_RUNNING = ua.ensure_watchdog_running


@pytest.fixture(autouse=True)
def isolated_autostart(monkeypatch, tmp_path):
    """Never let a test write into the developer's real autostart directory."""
    monkeypatch.setenv("ECAN_AUTOSTART_HOME", str(tmp_path / "autostart"))
    monkeypatch.setattr(ua, "_marker", lambda: tmp_path / "unattended.json")
    monkeypatch.setattr(ua, "_breaker_path", lambda: tmp_path / "watchdog_breaker.json")
    monkeypatch.setattr(ua, "ensure_watchdog_running", lambda: None)
    monkeypatch.setattr(ua, "_stop_watchdog", lambda: None)
    return tmp_path / "autostart"


def _platform(monkeypatch, value):
    monkeypatch.setattr(ua.sys, "platform", value)


class _Result:
    returncode = 0
    stdout = stderr = ""


# ---------------------------------------------------------------------------
# Which mechanism, and where
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("platform,kind", [
    ("win32", "logon_task"),
    ("darwin", "launchagent"),
    ("linux", "xdg_autostart"),
    ("freebsd13", "none"),
])
def test_every_platform_has_an_answer(monkeypatch, platform, kind):
    _platform(monkeypatch, platform)
    assert ua.autostart_kind() == kind


def test_linux_entry_lands_in_xdg_config_home(monkeypatch, tmp_path):
    _platform(monkeypatch, "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.delenv("ECAN_AUTOSTART_HOME")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    # _under_test() still says yes (pytest is importable), which is the point
    # of the second half of this test: the real home is never used.
    assert ua._autostart_path() is None


def test_linux_entry_falls_back_to_dot_config(monkeypatch):
    _platform(monkeypatch, "linux")
    path = ua._autostart_path()
    assert path is not None and path.name.endswith(".desktop")
    assert path.parent.name == "autostart"


def test_macos_entry_is_a_launchagent(monkeypatch):
    _platform(monkeypatch, "darwin")
    path = ua._autostart_path()
    assert path is not None and path.suffix == ".plist"


def test_windows_has_no_file(monkeypatch):
    _platform(monkeypatch, "win32")
    assert ua._autostart_path() is None


def test_the_entry_is_per_build_and_file_name_safe():
    slug = ua._slug()
    assert slug.endswith("-unattended")
    assert slug.replace("-", "").isalnum()
    assert "/" not in slug and " " not in slug


def test_the_file_name_matches_the_task_name():
    """Two build variants must not share one entry (they did, once)."""
    assert ua._task_names()[0] == ua.task_name()
    assert ua._slug() in (ua.task_name().lower().replace(" ", "-"),
                          ua._slug())


def test_a_test_run_does_not_touch_the_real_home(monkeypatch):
    """Without the override, the writer must refuse rather than pollute $HOME."""
    _platform(monkeypatch, "linux")
    monkeypatch.delenv("ECAN_AUTOSTART_HOME")
    assert ua._under_test() is True
    assert ua._autostart_path() is None
    ok, err = ua._install_autostart()
    assert ok is False and "ECAN_AUTOSTART_HOME" in err


# ---------------------------------------------------------------------------
# What gets written: a .desktop entry
# ---------------------------------------------------------------------------

def test_exec_quoting_survives_a_path_with_spaces(monkeypatch):
    _platform(monkeypatch, "linux")
    monkeypatch.setattr(ua, "watchdog_command",
                        lambda: ["/opt/My App/eCan", "--watchdog"])
    entry = ua._desktop_entry()
    assert 'Exec="/opt/My App/eCan" --watchdog' in entry
    # An unescaped % would be read as a field code and swallow the argument.
    assert ua._exec_quote("100%") == '"100%%"'
    assert ua._exec_quote("a$b") == '"a\\$b"'
    assert ua._exec_quote("`x`") == '"\\`x\\`"'
    assert ua._exec_quote("/plain/eCan") == "/plain/eCan"


def test_desktop_entry_is_hidden_and_has_no_terminal(monkeypatch):
    _platform(monkeypatch, "linux")
    entry = ua._desktop_entry()
    assert "[Desktop Entry]" in entry
    assert "Type=Application" in entry
    assert "Terminal=false" in entry
    # A supervisor is not something to click in the application menu.
    assert "NoDisplay=true" in entry
    assert "X-GNOME-Autostart-enabled=true" in entry
    assert f"Name={ua.task_name()}" in entry


def test_install_writes_a_readable_desktop_file(monkeypatch, isolated_autostart):
    _platform(monkeypatch, "linux")
    ok, err = ua._install_autostart()
    assert (ok, err) == (True, "")
    path = ua._autostart_path()
    assert path.exists()
    assert path.read_text(encoding="utf-8") == ua._desktop_entry()
    assert stat.S_IMODE(path.stat().st_mode) & 0o400
    # No half-written sibling left behind: a truncated .desktop is silently
    # ignored by the desktop at the next login.
    assert list(path.parent.glob("*.tmp")) == []
    assert ua._autostart_installed() is True


def test_install_is_idempotent(monkeypatch, isolated_autostart):
    _platform(monkeypatch, "linux")
    assert ua._install_autostart()[0]
    assert ua._install_autostart()[0]
    assert ua._autostart_installed() is True


def test_remove_deletes_the_entry(monkeypatch, isolated_autostart):
    _platform(monkeypatch, "linux")
    ua._install_autostart()
    assert ua._remove_autostart() is True
    assert ua._autostart_installed() is False
    # Removing what is not there is a success, not an error: it is what an
    # uninstall does on a machine that never enabled the feature.
    assert ua._remove_autostart() is True


def test_install_reports_an_unwritable_location_instead_of_raising(monkeypatch, tmp_path):
    _platform(monkeypatch, "linux")
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(ua, "_autostart_path", lambda: blocker / "sub" / "e.desktop")
    ok, err = ua._install_autostart()
    assert ok is False and err


# ---------------------------------------------------------------------------
# What gets written: a LaunchAgent
# ---------------------------------------------------------------------------

def test_launchd_plist_is_valid_and_does_not_fight_the_user(monkeypatch):
    _platform(monkeypatch, "darwin")
    monkeypatch.setattr(ua, "watchdog_command", lambda: ["/Applications/eCan.app/x", "--watchdog"])
    parsed = plistlib.loads(ua._launchd_plist().encode("utf-8"))
    assert parsed["Label"] == ua._launchd_label()
    assert parsed["ProgramArguments"] == ["/Applications/eCan.app/x", "--watchdog"]
    assert parsed["RunAtLoad"] is True
    # KeepAlive only for a *failed* exit. A plain true would relaunch the
    # watchdog after the user quit eCan, i.e. reopen the app they just closed;
    # false would leave the supervisor unsupervised.
    assert parsed["KeepAlive"] == {"SuccessfulExit": False}
    assert parsed["ThrottleInterval"] == 300       # a crashing watchdog: 1/5min
    assert parsed["ProcessType"] == "Interactive"


def test_launchd_plist_escapes_xml(monkeypatch):
    _platform(monkeypatch, "darwin")
    monkeypatch.setattr(ua, "watchdog_command", lambda: ['/tmp/a&b<c>"d"', "--watchdog"])
    parsed = plistlib.loads(ua._launchd_plist().encode("utf-8"))
    assert parsed["ProgramArguments"][0] == '/tmp/a&b<c>"d"'


def test_install_loads_the_agent_and_tolerates_launchctl_failing(monkeypatch, isolated_autostart):
    _platform(monkeypatch, "darwin")
    calls = []

    def fake_launchctl(args):
        calls.append(args[0])
        if args[0] == "bootstrap":
            r = _Result()
            r.returncode = 5
            r.stderr = "Load failed"
            return r
        if args[0] == "load":
            r = _Result()
            r.returncode = 1
            r.stderr = "nope"
            return r
        return _Result()

    monkeypatch.setattr(ua, "_launchctl", fake_launchctl)
    ok, err = ua._install_autostart()
    # The plist is on disk, so the entry still runs at the next login: the
    # switch did what it promised even though launchd refused just now.
    assert (ok, err) == (True, "")
    assert ua._autostart_path().exists()
    assert calls == ["bootout", "bootstrap", "load"]


def test_install_uses_bootstrap_when_it_works(monkeypatch, isolated_autostart):
    _platform(monkeypatch, "darwin")
    calls = []
    monkeypatch.setattr(ua, "_launchctl", lambda args: (calls.append(args[0]), _Result())[1])
    assert ua._install_autostart() == (True, "")
    assert calls == ["bootout", "bootstrap"]


def test_remove_unloads_the_agent(monkeypatch, isolated_autostart):
    _platform(monkeypatch, "darwin")
    calls = []
    monkeypatch.setattr(ua, "_launchctl", lambda args: (calls.append(args[0]), _Result())[1])
    ua._install_autostart()
    calls.clear()
    assert ua._remove_autostart() is True
    assert calls == ["bootout", "unload"]
    assert not ua._autostart_path().exists()


# ---------------------------------------------------------------------------
# Windows keeps its logon task
# ---------------------------------------------------------------------------

def test_install_creates_the_logon_task_without_a_console(monkeypatch):
    _platform(monkeypatch, "win32")
    seen = []

    def fake_run(cmd, **kw):
        seen.append((cmd[1], kw.get("creationflags")))
        return _Result()

    monkeypatch.setattr(ua.subprocess, "run", fake_run)
    assert ua._install_autostart() == (True, "")
    assert ("/Create", ua._NO_WINDOW) in seen
    # Both spellings of the legacy name are cleared, so an upgrade does not
    # leave two watchdogs fighting over the singleton.
    assert seen.count(("/Delete", ua._NO_WINDOW)) == len(ua._task_names())


def test_install_reports_a_failing_schtasks(monkeypatch):
    _platform(monkeypatch, "win32")

    def fake_run(cmd, **kw):
        if cmd[1] == "/Create":
            r = _Result()
            r.returncode = 1
            r.stderr = "access denied"
            return r
        return _Result()

    monkeypatch.setattr(ua.subprocess, "run", fake_run)
    ok, err = ua._install_autostart()
    assert ok is False and "access denied" in err


# ---------------------------------------------------------------------------
# The switch itself, on every platform
# ---------------------------------------------------------------------------

def test_switch_on_linux_creates_the_entry(monkeypatch, isolated_autostart):
    _platform(monkeypatch, "linux")
    res = ua.set_enabled(True)
    assert res["enabled"] is True and res["autostart"] is True
    assert res["autostart_kind"] == "xdg_autostart"
    # logon_task stays Windows-only: the old UI reads it for the old wording.
    assert res["logon_task"] is False
    assert ua._autostart_path().exists()
    assert "error" not in res


def test_switch_off_linux_removes_the_entry(monkeypatch, isolated_autostart):
    _platform(monkeypatch, "linux")
    ua.set_enabled(True)
    res = ua.set_enabled(False)
    assert res["enabled"] is False and res["autostart"] is False
    assert not ua._autostart_path().exists()


def test_switch_on_macos_reports_the_mechanism(monkeypatch, isolated_autostart):
    _platform(monkeypatch, "darwin")
    monkeypatch.setattr(ua, "_launchctl", lambda args: _Result())
    res = ua.set_enabled(True)
    assert res["autostart"] is True and res["autostart_kind"] == "launchagent"
    assert ua._autostart_path().exists()


def test_status_reports_the_entry_and_the_breaker(monkeypatch, isolated_autostart):
    _platform(monkeypatch, "linux")
    out = ua.status()
    assert out["autostart"] is False and out["autostart_kind"] == "xdg_autostart"
    assert out["logon_task"] is False
    assert out["breaker"]["gave_up"] is False and out["breaker"]["tripped"] is False
    ua.set_enabled(True)
    assert ua.status()["autostart"] is True


def test_status_survives_a_damaged_breaker_file(monkeypatch, isolated_autostart):
    _platform(monkeypatch, "linux")
    (isolated_autostart.parent / "watchdog_breaker.json").write_text("{not json", encoding="utf-8")
    out = ua.status()
    assert out["breaker"]["gave_up"] is False          # reads as "closed", never raises


def test_watchdog_is_detached_from_the_parent_process_group(monkeypatch):
    """A watchdog that dies with the launching terminal covers nothing."""
    seen = {}
    # Undo the fixture's stub: this test is about how the launch happens.
    monkeypatch.setattr(ua, "ensure_watchdog_running", _REAL_ENSURE_WATCHDOG_RUNNING)
    monkeypatch.setattr(ua, "is_enabled", lambda: True)
    monkeypatch.setattr(ua, "_watchdog_pid", lambda: None)
    monkeypatch.setattr(ua, "should_skip_watchdog", lambda *a, **k: False)
    monkeypatch.setattr(ua.subprocess, "Popen", lambda *a, **k: seen.update(k))
    new_group = getattr(ua.subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    _platform(monkeypatch, "linux")
    ua.ensure_watchdog_running()
    assert seen.get("start_new_session") is True
    seen.clear()
    _platform(monkeypatch, "win32")
    ua.ensure_watchdog_running()
    assert "creationflags" in seen and seen["creationflags"] & new_group


# ---------------------------------------------------------------------------
# The "try again" button behind a given-up watchdog
# ---------------------------------------------------------------------------

def _seed_gave_up(path):
    state = wb.new_state()
    state["gave_up"] = True
    state["opened_at"] = 1_800_000_000.0
    state["consecutive_failures"] = 11
    state["total_failures"] = 11
    state["probes"] = wb.GIVE_UP_AFTER_PROBES
    assert wb.save(path, state)


def test_breaker_summary_reads_the_shared_file(monkeypatch, isolated_autostart):
    path = isolated_autostart.parent / "watchdog_breaker.json"
    assert ua.breaker_summary()["gave_up"] is False        # nothing on disk yet
    _seed_gave_up(path)
    info = ua.breaker_summary()
    assert info["gave_up"] is True and info["consecutive_failures"] == 11


def test_turning_the_switch_on_is_a_human_try_again(monkeypatch, isolated_autostart):
    _platform(monkeypatch, "linux")
    path = isolated_autostart.parent / "watchdog_breaker.json"
    _seed_gave_up(path)
    ua.set_enabled(True)
    # Without this the switch would read "on" while nothing launched for up
    # to six hours -- the exact confusion this feature is supposed to end.
    assert wb.load(path)["gave_up"] is False
    assert ua.breaker_summary()["gave_up"] is False


def test_reset_does_not_create_a_file_that_was_never_there(monkeypatch, isolated_autostart):
    path = isolated_autostart.parent / "watchdog_breaker.json"
    ua.reset_watchdog_breaker()
    assert not path.exists()


def test_reset_never_raises(monkeypatch, isolated_autostart):
    monkeypatch.setattr(ua, "_breaker_path", lambda: isolated_autostart / "nope" / "x.json")
    # An unwritable path must not raise out of the Settings handler, and it
    # must still answer with a usable (closed) verdict rather than nothing.
    assert ua.reset_watchdog_breaker()["gave_up"] is False


def test_ipc_reset_breaker_round_trip(monkeypatch, isolated_autostart):
    _platform(monkeypatch, "linux")
    from gui.ipc.types import create_request
    from gui.ipc.w2p_handlers import unattended_handler as uh

    path = isolated_autostart.parent / "watchdog_breaker.json"
    _seed_gave_up(path)
    resp = uh.handle_reset_breaker(create_request("unattended.reset_breaker"), {})
    assert resp["status"] == "success"
    assert resp["result"]["breaker"]["gave_up"] is False
    assert wb.load(path)["gave_up"] is False


# ---------------------------------------------------------------------------
# Uninstall
# ---------------------------------------------------------------------------

def test_uninstall_removes_the_entry_on_every_platform(monkeypatch, isolated_autostart):
    _platform(monkeypatch, "linux")
    ua.set_enabled(True)
    assert ua._autostart_path().exists()
    monkeypatch.setattr("utils.exit_intent.claim_shutdown_lease", lambda **k: None)
    ua.disable_for_uninstall(log_dir=str(isolated_autostart.parent))
    # A leftover entry would make the next login try to start a deleted app.
    assert not ua._autostart_path().exists()
    assert ua.is_enabled() is False


def test_uninstall_on_windows_removes_the_logon_task(monkeypatch, isolated_autostart):
    _platform(monkeypatch, "win32")
    seen = []
    monkeypatch.setattr(ua.subprocess, "run",
                        lambda cmd, **kw: (seen.append(cmd[1]), _Result())[1])
    monkeypatch.setattr("utils.exit_intent.claim_shutdown_lease", lambda **k: None)
    ua.disable_for_uninstall(log_dir=str(isolated_autostart.parent))
    assert "/Delete" in seen


# Windows: the logon task as XML, the only spelling that can carry a policy.

def test_the_logon_task_xml_carries_what_the_command_line_cannot(monkeypatch):
    _platform(monkeypatch, "win32")
    monkeypatch.setattr(ua, "watchdog_command",
                        lambda: [r"C:\Program Files\eCan\eCan.exe", "--watchdog"])
    root = ET.fromstring(ua._windows_task_xml().encode("utf-16"))
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}

    def text(path):
        return root.findtext(path, namespaces=ns)

    # PT0S: without it Task Scheduler applies its 72 h default and kills the
    # watchdog on day four, silently. This is the line that makes a kiosk
    # survive a week, and the one /SC ONLOGON cannot set at all.
    assert text("t:Settings/t:ExecutionTimeLimit") == "PT0S"
    # Restart-on-failure: the supervisor gets supervised.
    assert text("t:Settings/t:RestartOnFailure/t:Interval") == ua.TASK_RESTART_INTERVAL
    assert text("t:Settings/t:RestartOnFailure/t:Count") == str(ua.TASK_RESTART_COUNT)
    # One watchdog only: a second would just fight over the singleton lock.
    assert text("t:Settings/t:MultipleInstancesPolicy") == "IgnoreNew"
    assert text("t:Triggers/t:LogonTrigger/t:Enabled") == "true"
    # Same user, no elevation: it must not hold a privilege eCan does not.
    assert text("t:Principals/t:Principal/t:LogonType") == "InteractiveToken"
    assert text("t:Principals/t:Principal/t:RunLevel") == "LeastPrivilege"
    assert text("t:Actions/t:Exec/t:Command") == r"C:\Program Files\eCan\eCan.exe"
    assert text("t:Actions/t:Exec/t:Arguments") == "--watchdog"


def test_the_logon_task_runs_as_the_current_user(monkeypatch):
    """An InteractiveToken principal needs a user, and an exported ONLOGON
    task always has one. Without it schtasks rejects the XML and we fall back
    to /SC ONLOGON -- which cannot express PT0S or restart-on-failure."""
    _platform(monkeypatch, "win32")
    monkeypatch.setenv("USERNAME", "kiosk")
    monkeypatch.setenv("USERDOMAIN", "SHOP1")
    monkeypatch.setattr(ua, "watchdog_command", lambda: ["eCan.exe", "--watchdog"])
    root = ET.fromstring(ua._windows_task_xml().encode("utf-16"))
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    assert root.findtext("t:Principals/t:Principal/t:UserId", namespaces=ns) == "SHOP1\\kiosk"


def test_the_logon_task_omits_the_user_element_when_unknown(monkeypatch):
    """A blank <UserId></UserId> is invalid; leaving the element out is the
    only safe spelling when the environment does not name a user."""
    _platform(monkeypatch, "win32")
    monkeypatch.delenv("USERNAME", raising=False)
    monkeypatch.delenv("USERDOMAIN", raising=False)
    monkeypatch.setattr(ua, "watchdog_command", lambda: ["eCan.exe", "--watchdog"])
    root = ET.fromstring(ua._windows_task_xml().encode("utf-16"))
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    user = root.find("t:Principals/t:Principal/t:UserId", ns)
    assert user is None
    # The rest of the policy is still there.
    assert root.findtext("t:Settings/t:ExecutionTimeLimit", namespaces=ns) == "PT0S"

def test_install_registers_the_task_from_a_utf16_file(monkeypatch):
    _platform(monkeypatch, "win32")
    seen = {}

    def fake_run(cmd, **kw):
        if "/XML" in cmd:
            seen["path"] = cmd[cmd.index("/XML") + 1]
            with open(seen["path"], "rb") as fh:
                seen["bytes"] = fh.read()
        return _Result()

    monkeypatch.setattr(ua.subprocess, "run", fake_run)
    assert ua._install_logon_task() == (True, "")
    # The document declares UTF-16, so the bytes on disk must be UTF-16 with a
    # BOM: schtasks believes the declaration and fails with nothing but "The
    # task XML is malformed" when it is a lie.
    assert seen["bytes"].startswith((b"\xff\xfe", b"\xfe\xff"))
    assert ET.fromstring(seen["bytes"]) is not None
    # And the temp file is not left behind in the system temp dir for ever.
    assert not os.path.exists(seen["path"])


def test_a_rejected_xml_still_leaves_a_working_logon_task(monkeypatch):
    _platform(monkeypatch, "win32")
    creates = []

    def fake_run(cmd, **kw):
        creates.append(list(cmd))
        r = _Result()
        if "/XML" in cmd:
            r.returncode = 1
            r.stderr = "The task XML is malformed"
        return r

    monkeypatch.setattr(ua.subprocess, "run", fake_run)
    # A task with a 72 h limit beats no task at all: fall back, and say so.
    assert ua._install_autostart() == (True, "")
    plain = [c for c in creates if c[1] == "/Create" and "/XML" not in c]
    assert plain and "ONLOGON" in plain[0] and "/TR" in plain[0]


def test_when_no_spelling_works_the_switch_reports_it(monkeypatch, isolated_autostart):
    _platform(monkeypatch, "win32")

    def fake_run(cmd, **kw):
        if cmd[1] == "/Create":
            r = _Result()
            r.returncode = 1
            r.stderr = "access denied"
            return r
        return _Result()

    monkeypatch.setattr(ua.subprocess, "run", fake_run)
    res = ua.set_enabled(True)
    assert res["autostart"] is False and "access denied" in res["error"]


# Linux: the systemd unit, the layer underneath the .desktop entry.

def test_the_systemd_unit_supervises_the_watchdog(monkeypatch):
    _platform(monkeypatch, "linux")
    monkeypatch.setattr(ua, "watchdog_command",
                        lambda: ["/opt/eCan/eCan.AppImage", "--watchdog"])
    unit = ua._systemd_unit()
    assert "ExecStart=/opt/eCan/eCan.AppImage --watchdog" in unit
    # on-failure, not always: exit 0 means the watchdog stood down on purpose
    # (the user quit eCan, or it gave up on a broken build). Restarting that
    # would reopen the very loop this feature exists to prevent.
    assert "Restart=on-failure" in unit
    assert f"RestartSec={ua.SYSTEMD_RESTART_SEC}" in unit
    assert f"StartLimitBurst={ua.SYSTEMD_START_LIMIT_BURST}" in unit
    assert f"StartLimitIntervalSec={ua.SYSTEMD_START_LIMIT_INTERVAL_SEC}" in unit
    assert "Type=simple" in unit
    assert "WantedBy=default.target" in unit


def test_the_systemd_unit_does_not_borrow_desktop_entry_escaping(monkeypatch):
    _platform(monkeypatch, "linux")
    # A path may hold a `$` (an unpacked AppImage tree does). systemd refuses
    # an unknown backslash-dollar escape inside a quoted word, so reusing
    # _exec_quote() here would produce a unit that never starts.
    monkeypatch.setattr(ua, "watchdog_command",
                        lambda: ["/opt/my apps/$ecan", "--watchdog"])
    unit = ua._systemd_unit()
    assert "\\$" not in unit
    assert '"/opt/my apps/$ecan"' in unit


def test_install_writes_and_enables_the_unit(monkeypatch, tmp_path):
    _platform(monkeypatch, "linux")
    unit_path = tmp_path / "ecan-unattended.service"
    monkeypatch.setattr(ua, "_systemd_unit_path", lambda: unit_path)
    monkeypatch.setattr(ua, "_systemd_managed", lambda: True)
    calls = []
    monkeypatch.setattr(ua, "_systemctl", lambda args: (calls.append(args), _Result())[1])
    assert ua._install_systemd_unit() == ""
    assert "Restart=on-failure" in unit_path.read_text(encoding="utf-8")
    assert ["daemon-reload"] in calls
    assert any(c[:2] == ["enable", "--now"] for c in calls)
    assert not (tmp_path / "ecan-unattended.service.tmp").exists()


def test_an_image_without_systemd_does_not_fail_the_switch(monkeypatch, isolated_autostart):
    _platform(monkeypatch, "linux")

    def no_systemd(args):
        r = _Result()
        r.returncode = 1
        r.stderr = "System has not been booted with systemd"
        return r

    monkeypatch.setattr(ua, "_systemd_managed", lambda: True)
    monkeypatch.setattr(ua, "_systemctl", no_systemd)
    monkeypatch.setattr(ua, "_systemd_unit_path",
                        lambda: isolated_autostart / "ecan-unattended.service")
    res = ua.set_enabled(True)
    # The .desktop entry is the main mechanism and it did work; the unit is a
    # bonus, so a container or a non-systemd distro must not show an error.
    assert res["autostart"] is True and "error" not in res
    assert ua._autostart_path().exists()


def test_switching_off_removes_the_unit_too(monkeypatch, isolated_autostart):
    _platform(monkeypatch, "linux")
    unit = isolated_autostart / (ua._slug() + ".service")
    ua.set_enabled(True)
    assert unit.exists()            # written into the redirected drop-in dir
    ua.set_enabled(False)
    # Leaving the unit enabled would have systemd restarting the watchdog that
    # the switch was just told to stop.
    assert not unit.exists()


def test_a_redirected_drop_in_never_touches_the_real_systemd(monkeypatch, isolated_autostart):
    _platform(monkeypatch, "linux")
    monkeypatch.setattr(ua, "_systemctl",
                        lambda args: pytest.fail(f"systemctl {args} called on the host"))
    # ECAN_AUTOSTART_HOME is set by the fixture: writing and deleting the files
    # is the whole contract. Enabling a unit that points into a temp directory
    # would arm the developer's own session at every login.
    assert ua.set_enabled(True)["autostart"] is True
    assert ua.set_enabled(False)["autostart"] is False
