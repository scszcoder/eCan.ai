"""Unattended mode: start eCan at logon and restart it when it crashes or
hangs (utils/app_watchdog.py). Off by default; switched in Settings.

On: a marker file (``unattended.json`` in the app data folder) plus one
autostart entry that runs ``eCan --watchdog`` -- a logon task on Windows, a
``~/.config/autostart/*.desktop`` entry on Linux, a LaunchAgent on macOS (see
``autostart_kind()``); the watchdog starts eCan and keeps it up. While on, eCan
also makes sure a watchdog is running when it starts by hand, so a crash is
covered either way.
Off: both removed. Every command runs without a console window.

The marker carries two independent switches: ``enabled`` (keep eCan alive on
this PC) and ``allow_in_dev`` (also run a watchdog against the source tree).
The second exists because a developer iterating on a crashing build does not
want an automatic relaunch, while a developer *deliberately* reproducing a
crash-loop does. Both default to off.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from utils.logger_helper import logger_helper as logger

#: The logon task name every build used before it was derived from the app
#: name. Still deleted on cleanup so an upgraded install does not leave a
#: second task behind (see task_name()).
LEGACY_TASK_NAME = "eCan Unattended"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def task_name() -> str:
    """The Windows logon task name, e.g. ``"eCan Unattended"``.

    Derived from the app name instead of hard-coded. The name used to be the
    constant ``"eCan Unattended"``, so every build variant (eCan.cn,
    eCan.intl) shared one task: installing the second variant overwrote the
    first one's logon task, and the two builds then fought over the same
    watchdog singleton. Result: a logon that started only one of them, or
    neither, with no error anywhere.
    """
    try:
        from config.constants import APP_NAME
        name = str(APP_NAME or "").strip()
    except Exception:
        name = ""
    return f"{name or 'eCan'} Unattended"


def _task_names() -> list:
    """The current logon task name plus the legacy one, deduplicated."""
    current = task_name()
    return [current] if current == LEGACY_TASK_NAME else [current, LEGACY_TASK_NAME]


def _delete_logon_task() -> None:
    """Remove every logon task this app may have created. Never raises."""
    for name in _task_names():
        try:
            _schtasks(["/Delete", "/TN", name, "/F"])
        except Exception as exc:
            logger.debug(f"[Unattended] could not remove logon task {name!r}: {exc}")


def _marker() -> Path:
    from config.app_info import app_info
    return Path(app_info.appdata_path) / "unattended.json"


def _read_marker() -> dict:
    """The marker file's contents, or {} when absent/unreadable."""
    try:
        data = json.loads(_marker().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def is_enabled() -> bool:
    return bool(_read_marker().get("enabled"))


def allows_dev_watchdog() -> bool:
    """Whether the user also wants a watchdog while running from source.

    A separate flag from ``is_enabled()`` on purpose. ``enabled`` means "keep
    eCan alive on this PC"; in dev the user is iterating, not running a kiosk,
    so it must not imply "relaunch my crashed build". An older marker (or a
    stale copy from a QA run) has no ``allow_in_dev``, and therefore keeps the
    dev skip -- so the flag cannot be switched on by accident, which is the
    property the environment variable used to provide.
    """
    return bool(_read_marker().get("allow_in_dev"))


def _write_marker(enabled: bool, allow_in_dev: bool) -> None:
    _marker().write_text(json.dumps({"enabled": bool(enabled),
                                     "allow_in_dev": bool(allow_in_dev)}),
                         encoding="utf-8")


def watchdog_command() -> list:
    from utils.app_watchdog import app_command
    return app_command() + ["--watchdog"]


def _schtasks(args: list) -> subprocess.CompletedProcess:
    # errors="replace": schtasks prints in the console codepage. On a zh-CN
    # Windows that is cp936, and a task name or a localized message with a byte
    # it cannot decode would raise UnicodeDecodeError out of a *status query* --
    # turning "the task is missing" into a broken unattended switch.
    return subprocess.run(["schtasks"] + args, capture_output=True, text=True,
                          errors="replace", creationflags=_NO_WINDOW, timeout=30)


def _task_command_line() -> str:
    return " ".join(f'"{a}"' if " " in a or not a else a for a in watchdog_command())



#: Task Scheduler's restart policy, written into the task XML. The command-line
#: spelling of a logon task cannot express any of it, and the defaults it *does*
#: pick are wrong for a supervisor that must run for days: ``ExecutionTimeLimit``
#: defaults to 72 hours (Task Scheduler then kills the watchdog and never starts
#: it again, so unattended mode dies silently on day four), and there is no
#: restart-on-failure at all -- if the watchdog itself dies, nothing says so.
TASK_RESTART_INTERVAL = "PT5M"
TASK_RESTART_COUNT = 999


def _current_user_id() -> str:
    """The task principal: this user, spelled ``DOMAIN\\user`` (or bare name).

    Empty when the environment does not say -- the element is then left out
    rather than written blank, which ``schtasks`` rejects.
    """
    user = os.environ.get("USERNAME") or ""
    domain = os.environ.get("USERDOMAIN") or ""
    return f"{domain}\\{user}" if user and domain else user


def _windows_task_xml() -> str:
    """The logon task as XML: the only spelling that can carry those settings.

    Element order follows what Task Scheduler itself exports for a task created
    with ``/SC ONLOGON``; ``schtasks`` validates the XML against that schema, so
    a reordered document is rejected outright. The caller keeps the command-line
    form as a fallback for the (unlikely) case that this is rejected anyway:
    a task with a 72 h limit is worse than a task with none, but far better than
    no autostart entry at all.
    """
    cmd = watchdog_command()
    args = " ".join(f'"{a}"' if " " in a or not a else a for a in cmd[1:])
    # Task Scheduler needs a principal user for an InteractiveToken task (an
    # exported ONLOGON task always carries one). It must be the unelevated user
    # who runs eCan, never SYSTEM: the watchdog is only there to restart the
    # GUI that lives in that session.
    user_id = _current_user_id()
    user_line = (f'      <UserId>{_xml_escape(user_id)}</UserId>\n'
                 if user_id else '')
    return (
        '<?xml version="1.0" encoding="UTF-16"?>\n'
        '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n'
        '  <RegistrationInfo>\n'
        f'    <Description>{_xml_escape(task_name())}</Description>\n'
        '  </RegistrationInfo>\n'
        '  <Triggers>\n'
        '    <LogonTrigger>\n'
        '      <Enabled>true</Enabled>\n'
        '    </LogonTrigger>\n'
        '  </Triggers>\n'
        '  <Principals>\n'
        f'    <Principal id="Author">\n{user_line}'
        # Same user as the app, unelevated: the watchdog must not hold a
        # privilege the app it restarts does not have.
        '      <LogonType>InteractiveToken</LogonType>\n'
        '      <RunLevel>LeastPrivilege</RunLevel>\n'
        '    </Principal>\n'
        '  </Principals>\n'
        '  <Settings>\n'
        # One watchdog, never two: a second one would just fight over the lock.
        '    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n'
        '    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\n'
        '    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\n'
        '    <AllowHardTerminate>true</AllowHardTerminate>\n'
        '    <StartWhenAvailable>true</StartWhenAvailable>\n'
        '    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>\n'
        '    <IdleSettings>\n'
        '      <StopOnIdleEnd>false</StopOnIdleEnd>\n'
        '      <RestartOnIdle>false</RestartOnIdle>\n'
        '    </IdleSettings>\n'
        '    <AllowStartOnDemand>true</AllowStartOnDemand>\n'
        '    <Enabled>true</Enabled>\n'
        '    <Hidden>false</Hidden>\n'
        '    <RunOnlyIfIdle>false</RunOnlyIfIdle>\n'
        '    <WakeToRun>false</WakeToRun>\n'
        # PT0S = no time limit. This is the line that keeps a kiosk covered on
        # day four, and the one the command-line form cannot set.
        '    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>\n'
        '    <Priority>7</Priority>\n'
        f'    <RestartOnFailure>\n      <Interval>{TASK_RESTART_INTERVAL}</Interval>\n'
        f'      <Count>{TASK_RESTART_COUNT}</Count>\n    </RestartOnFailure>\n'
        '  </Settings>\n'
        '  <Actions Context="Author">\n'
        '    <Exec>\n'
        f'      <Command>{_xml_escape(cmd[0])}</Command>\n'
        f'      <Arguments>{_xml_escape(args)}</Arguments>\n'
        '    </Exec>\n'
        '  </Actions>\n'
        '</Task>\n'
    )

def _install_logon_task() -> tuple:
    """Register the logon task from its XML. Returns ``(ok, error_text)``.

    ``/Create /F`` makes this idempotent (it replaces an existing task), which
    matters because the switch can be toggled any number of times.

    The temporary file is written UTF-16 *with* a BOM and the document declares
    that same encoding: ``schtasks`` believes the declaration, so UTF-8 bytes
    under an ``encoding="UTF-16"`` header fail with nothing but "The task XML
    is malformed" -- no line number, no hint.
    """
    xml = _windows_task_xml()
    tmp = None
    try:
        fd, name = tempfile.mkstemp(prefix="ecan-logon-task-", suffix=".xml")
        tmp = Path(name)
        with os.fdopen(fd, "w", encoding="utf-16") as fh:
            fh.write(xml)
        r = _schtasks(["/Create", "/TN", task_name(), "/XML", str(tmp), "/F"])
    except Exception as exc:
        return False, str(exc)[:300]
    finally:
        if tmp is not None:
            try:
                tmp.unlink()
            except Exception:
                pass                # a stray temp file is not a failed install
    if r.returncode != 0:
        return False, ((r.stderr or r.stdout or "").strip())[:300]
    return True, ""

# ---------------------------------------------------------------------------
# Autostart, per platform
#
# One entry, three mechanisms: a logon task on Windows, a desktop entry in
# ~/.config/autostart on Linux (AppImage, deb, flatpak all honour it), and a
# LaunchAgent on macOS. The entry is written from *inside* eCan, so the command
# it records is the one that works today: the AppImage path (``$APPIMAGE``, not
# the temporary squashfs mount point), the bundle executable, or the source
# tree -- see utils/app_watchdog.app_command().
# ---------------------------------------------------------------------------

def _slug() -> str:
    """A file-name-safe, per-build identifier, e.g. ``ecan-unattended``.

    Per build for the same reason task_name() is: eCan.cn and eCan.intl on one
    machine must not overwrite each other's autostart entry and then fight over
    the watchdog singleton.
    """
    try:
        from config.constants import APP_NAME
        raw = str(APP_NAME or "eCan")
    except Exception:
        raw = "eCan"
    out = "".join(ch.lower() if ch.isalnum() else "-" for ch in raw)
    while "--" in out:
        out = out.replace("--", "-")
    return (out.strip("-") or "ecan") + "-unattended"


def autostart_kind() -> str:
    """Which autostart mechanism this platform uses (``"none"`` if it has none)."""
    if sys.platform == "win32":
        return "logon_task"
    if sys.platform == "darwin":
        return "launchagent"
    if sys.platform.startswith("linux"):
        return "xdg_autostart"
    return "none"


def _under_test() -> bool:
    """True when a test process is driving this module.

    Used to refuse writing into the *real* home directory: an autostart entry
    created by a test run would arm the developer's own machine to start eCan
    at every login -- hours later, with no obvious cause, and it survives the
    test run. Tests that do want to exercise the writer point
    ``ECAN_AUTOSTART_HOME`` at a temporary directory (so this returns False).

    Sniffed from ``sys.modules`` as well as the environment variable, because
    the tests that clear ``PYTEST_CURRENT_TEST`` do it to simulate production
    and would otherwise slip past.
    """
    if os.environ.get("ECAN_AUTOSTART_HOME"):
        return False
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    return any(m in sys.modules for m in ("pytest", "_pytest"))


def _autostart_path() -> "Path | None":
    """Where the Linux/macOS autostart entry lives, or None if there is none.

    None on Windows (a logon task has no file) and under test (see
    ``_under_test()``), so the error path is the same on every platform:
    ``_install_autostart`` reports "no location" instead of writing somewhere
    unexpected.
    """
    kind = autostart_kind()
    if kind not in ("xdg_autostart", "launchagent"):
        return None
    name = f"{_slug()}.plist" if kind == "launchagent" else f"{_slug()}.desktop"
    try:
        override = os.environ.get("ECAN_AUTOSTART_HOME")
        if override:
            return Path(override) / name
        if _under_test():
            return None
        home = Path.home()
        if kind == "xdg_autostart":
            # XDG_CONFIG_HOME is honoured because a flatpak or a snap may set
            # it; falling back to ~/.config is what every desktop reads.
            base = Path(os.environ.get("XDG_CONFIG_HOME") or (home / ".config"))
            return base / "autostart" / name
        return home / "Library" / "LaunchAgents" / name
    except Exception:
        return None


def _exec_quote(arg: str) -> str:
    """Quote one ``Exec=`` argument the way the Desktop Entry spec wants.

    Quoting is not cosmetic here: an unquoted path with a space (nearly every
    macOS bundle) or an unescaped ``$`` silently produces an entry that does
    nothing at login -- and nothing ever reports it, because the thing that
    would have is the watchdog that never started.
    """
    arg = str(arg)
    if arg and all(ch.isalnum() or ch in "/._-:+=" for ch in arg):
        return arg
    escaped = (arg.replace("\\", "\\\\").replace('"', '\\"')
                  .replace("`", "\\`").replace("$", "\\$").replace("%", "%%"))
    return f'"{escaped}"'


def _desktop_entry() -> str:
    """The ``.desktop`` file used by every Linux desktop for autostart."""
    return "\n".join([
        "[Desktop Entry]",
        "Type=Application",
        f"Name={task_name()}",
        "Comment=Restart eCan automatically if it crashes or hangs",
        "Exec=" + " ".join(_exec_quote(a) for a in watchdog_command()),
        "Terminal=false",
        # It is a background supervisor, not something to click.
        "NoDisplay=true",
        "X-GNOME-Autostart-enabled=true",
        "Hidden=false",
        "",
    ])


def _xml_escape(value: str) -> str:
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _launchd_label() -> str:
    return "com." + _slug().replace("-", ".")


def _launchd_plist() -> str:
    """The LaunchAgent used by macOS for autostart."""
    args = "".join(f"        <string>{_xml_escape(a)}</string>\n"
                   for a in watchdog_command())
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n<dict>\n'
        f'    <key>Label</key>\n    <string>{_launchd_label()}</string>\n'
        '    <key>ProgramArguments</key>\n    <array>\n'
        f'{args}    </array>\n'
        '    <key>RunAtLoad</key>\n    <true/>\n'
        # KeepAlive only for an *unsuccessful* exit. A plain ``true`` would
        # restart the watchdog after it deliberately stood down (the user quit
        # eCan: exit 0), which would relaunch the app the user just closed. A
        # ``SuccessfulExit=false`` dict gives the one thing the .desktop and
        # logon-task spellings cannot: launchd restarts the watchdog if the
        # watchdog itself dies or gives up on the loop (exit 3), so the
        # supervisor is itself supervised -- and stops for good when it says
        # "I am done".
        '    <key>KeepAlive</key>\n    <dict>\n'
        '        <key>SuccessfulExit</key>\n        <false/>\n'
        '    </dict>\n'
        # Minimum spacing between those restarts: a watchdog that crashes on
        # start is retried at most every five minutes, never in a tight loop.
        '    <key>ThrottleInterval</key>\n    <integer>300</integer>\n'
        '    <key>ProcessType</key>\n    <string>Interactive</string>\n'
        '</dict>\n</plist>\n'
    )


def _launchctl(args: list) -> subprocess.CompletedProcess:
    # errors="replace" for the same reason as _schtasks(): this output is
    # diagnostics, and a byte the locale cannot decode must not turn a status
    # query into an exception.
    return subprocess.run(["launchctl"] + args, capture_output=True, text=True,
                          errors="replace", timeout=30)


def _launchd_load(path: Path) -> str:
    """Best-effort (re)load of a LaunchAgent. Returns an error string, "" if ok.

    Two spellings because macOS has two: ``bootstrap gui/$UID`` on 10.10+ and
    ``load -w`` before that (still what some MDM-managed images permit). The
    ``bootout`` first is what makes this idempotent -- re-enabling an already
    loaded agent otherwise fails with "service already loaded" and would be
    reported as a broken switch.

    A failure here is *not* fatal for the caller: the plist is on disk, so the
    agent still runs at the next login, which is what the switch promises.
    """
    if not hasattr(os, "getuid"):
        return ""
    uid = os.getuid()
    try:
        _launchctl(["bootout", f"gui/{uid}", str(path)])     # expected to fail if unloaded
    except Exception:
        pass
    errors = []
    for args in (["bootstrap", f"gui/{uid}", str(path)], ["load", "-w", str(path)]):
        try:
            r = _launchctl(args)
            if r.returncode == 0:
                return ""
            errors.append((r.stderr or r.stdout or "").strip())
        except Exception as exc:
            errors.append(str(exc))
    return " / ".join(e for e in errors if e)[:300]


def _launchd_unload(path: Path) -> None:
    """Unload a LaunchAgent if it is loaded. Never raises."""
    if not hasattr(os, "getuid"):
        return
    uid = os.getuid()
    for args in (["bootout", f"gui/{uid}", str(path)], ["unload", "-w", str(path)]):
        try:
            _launchctl(args)
        except Exception as exc:
            logger.debug(f"[Unattended] launchctl {args[0]} skipped: {exc}")


#: systemd --user restart policy. The Linux counterpart of launchd's
#: ``KeepAlive``/``ThrottleInterval``: restart the watchdog if it *fails*, five
#: minutes apart, and let systemd itself stop after a burst.
SYSTEMD_RESTART_SEC = 300
SYSTEMD_START_LIMIT_BURST = 6
SYSTEMD_START_LIMIT_INTERVAL_SEC = 3600


def _systemd_unit_path() -> "Path | None":
    """Where the Linux systemd --user unit lives, or None on other platforms."""
    if autostart_kind() != "xdg_autostart":
        return None
    try:
        override = os.environ.get("ECAN_AUTOSTART_HOME")
        if override:
            return Path(override) / f"{_slug()}.service"
        if _under_test():
            return None
        base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
        return base / "systemd" / "user" / f"{_slug()}.service"
    except Exception:
        return None


def _systemd_quote(arg: str) -> str:
    """Quote one ``ExecStart`` argument the way systemd wants it.

    Deliberately *not* ``_exec_quote()``: that one escapes backticks and ``$``
    for the Desktop Entry spec, and systemd rejects an unknown ``\\$`` escape
    inside a double-quoted word, so borrowing it would produce a unit that
    refuses to start. Only the three characters systemd itself reads are
    escaped here.
    """
    text = str(arg).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    return f'"{text}"' if " " in text or '"' in text or not text else text


def _systemd_unit() -> str:
    """The ``.service`` that starts and supervises eCan's watchdog."""
    exec_start = " ".join(_systemd_quote(a) for a in watchdog_command())
    return "\n".join([
        "[Unit]",
        f"Description={task_name()} (crash/hang watchdog)",
        f"StartLimitIntervalSec={SYSTEMD_START_LIMIT_INTERVAL_SEC}",
        f"StartLimitBurst={SYSTEMD_START_LIMIT_BURST}",
        "",
        "[Service]",
        "Type=simple",
        f"ExecStart={exec_start}",
        # on-failure, not always: exit 0 means the watchdog stood down on
        # purpose (the user quit eCan, or it already gave up on a broken
        # build), and restarting that would reopen exactly the loop this
        # whole feature exists to prevent.
        "Restart=on-failure",
        f"RestartSec={SYSTEMD_RESTART_SEC}",
        # A supervisor must not be killed for being quiet, and must not hold
        # a logout hostage either.
        "TimeoutStopSec=10",
        "",
        "[Install]",
        "WantedBy=default.target",
        "",
    ])


def _systemctl(args: list) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", "--user"] + args, capture_output=True,
                          text=True, errors="replace", timeout=30)


def _systemd_managed() -> bool:
    """Whether ``systemctl`` may be called here.

    False when ``ECAN_AUTOSTART_HOME`` redirects the drop-in: that variable
    points the *files* at a temporary directory (the test suite, a portable
    install), and ``systemctl --user enable`` against such a file would arm a
    unit in the developer's real session that starts eCan out of /tmp.
    """
    return not os.environ.get("ECAN_AUTOSTART_HOME")


def _systemd_apply(path: Path) -> str:
    """Load and enable the unit. Returns an error string, "" when it worked."""
    if not _systemd_managed():
        return ""
    try:
        for args in (["daemon-reload"], ["enable", "--now", path.name]):
            r = _systemctl(args)
            if r.returncode != 0:
                return ((r.stderr or r.stdout or "").strip())[:300]
    except Exception as exc:
        return str(exc)[:300]
    return ""


def _install_systemd_unit() -> str:
    """Write and enable the systemd --user unit. "" or an error string.

    The second layer on top of the .desktop entry. A desktop entry fires once,
    at login, and nothing brings the watchdog back if it dies afterwards (the
    OOM killer, a crash in its own startup): on a kiosk that runs for weeks the
    supervisor would be unsupervised exactly when it is needed. systemd is the
    Linux counterpart of launchd's ``KeepAlive`` -- and, like the launchctl
    call on macOS, it is best-effort: plenty of images have no user session bus
    at all, and that must not fail the switch, because the .desktop entry above
    already does the main job.
    """
    path = _systemd_unit_path()
    if path is None:
        return ""               # unsupported platform, or under test
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(_systemd_unit(), encoding="utf-8")
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o644)
        except Exception:
            pass
    except Exception as exc:
        try:
            tmp.unlink()
        except Exception:
            pass
        return str(exc)[:300]
    return _systemd_apply(path)


def _systemd_remove(path: Path) -> None:
    """Disable the unit and delete it. Never raises."""
    if _systemd_managed():
        try:
            _systemctl(["disable", "--now", path.name])
        except Exception as exc:
            logger.debug(f"[Unattended] systemctl disable skipped: {exc}")
    try:
        if path.exists():
            path.unlink()
    except Exception as exc:
        logger.debug(f"[Unattended] could not remove {path}: {exc}")
        return
    if _systemd_managed():
        try:
            _systemctl(["daemon-reload"])
        except Exception as exc:
            logger.debug(f"[Unattended] systemctl daemon-reload skipped: {exc}")

def _install_autostart() -> tuple:
    """Create the platform's autostart entry. Returns ``(ok, error_text)``.

    Never raises: the switch reports the failure through ``error`` so Settings
    can say what went wrong, instead of the button silently doing nothing.
    """
    kind = autostart_kind()
    if kind == "none":
        return False, f"no autostart mechanism for {sys.platform}"
    if kind == "logon_task":
        try:
            # An older build registered the task under the legacy name; leaving
            # it in place would start a second watchdog at every logon.
            _delete_logon_task()
        except Exception as exc:
            return False, str(exc)[:300]
        ok, err = _install_logon_task()
        if ok:
            return True, ""
        # The XML form was rejected (a hardened image, an ancient build of
        # schtasks). Fall back to the command-line form: it cannot express the
        # restart policy, but it does start the watchdog at logon, and a
        # limited task beats no task. Say so, so Settings can explain it.
        try:
            r = _schtasks(["/Create", "/TN", task_name(), "/TR", _task_command_line(),
                           "/SC", "ONLOGON", "/RL", "LIMITED", "/F"])
        except Exception as exc:
            return False, (err or str(exc))[:300]
        if r.returncode == 0:
            logger.warning(f"[Unattended] created the logon task without its restart policy "
                           f"({err}); the watchdog will not be restarted until the next logon")
            return True, ""
        return False, ((r.stderr or r.stdout or "").strip() or err)[:300]

    path = _autostart_path()
    if path is None:
        return False, ("no autostart location for this user "
                       "(set ECAN_AUTOSTART_HOME to override)")
    body = _launchd_plist() if kind == "launchagent" else _desktop_entry()
    # Write to a sibling then rename: a `.desktop` or plist truncated by a
    # crash mid-write is read by the desktop as "no such program" at the next
    # login, again silently -- and the file is the whole feature.
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(body, encoding="utf-8")
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o644)
        except Exception:
            pass
    except Exception as exc:
        try:
            tmp.unlink()
        except Exception:
            pass
        return False, str(exc)[:300]
    if kind == "launchagent":
        try:
            err = _launchd_load(path)
        except Exception as exc:
            err = str(exc)[:300]
        if err:
            logger.warning(f"[Unattended] {path.name} written; launchd did not load it "
                           f"yet (it still runs at the next login): {err}")
    elif kind == "xdg_autostart":
        try:
            err = _install_systemd_unit()
        except Exception as exc:
            err = str(exc)[:300]
        if err:
            logger.warning(f"[Unattended] {path.name} written; the systemd unit could not "
                           f"be enabled (the entry still runs at the next login): {err}")
    return True, ""


def _autostart_installed() -> bool:
    """Whether the platform's autostart entry is present right now."""
    if autostart_kind() == "logon_task":
        try:
            return _schtasks(["/Query", "/TN", task_name()]).returncode == 0
        except Exception:
            return False
    path = _autostart_path()
    try:
        return bool(path) and path.exists()
    except Exception:
        return False


def _remove_autostart() -> bool:
    """Delete the platform's autostart entry. Returns whether it is gone."""
    if autostart_kind() == "logon_task":
        _delete_logon_task()
        return not _autostart_installed()
    path = _autostart_path()
    if path is None:
        # Nothing was ever written here (Windows, or a test run); report
        # "nothing left behind" rather than a failure.
        return True
    kind = autostart_kind()
    if kind == "launchagent":
        _launchd_unload(path)
    elif kind == "xdg_autostart":
        # Both layers: leaving the unit enabled would have systemd restarting
        # the very watchdog that "start at login" was just told to stop.
        unit = _systemd_unit_path()
        if unit is not None:
            _systemd_remove(unit)
    try:
        if path.exists():
            path.unlink()
    except Exception as exc:
        logger.debug(f"[Unattended] could not remove {path}: {exc}")
    try:
        return not path.exists()
    except Exception:
        return False


def _breaker_path() -> Path:
    """Where the crash-loop breaker keeps its state (shared with the watchdog)."""
    from utils.app_watchdog import runlogs_dir
    return runlogs_dir() / "watchdog_breaker.json"


def breaker_summary() -> dict:
    """The crash-loop breaker's verdict, for Settings and for upset users.

    Never raises: ``status()`` is what the Settings panel calls, and a damaged
    breaker file must not blank the whole panel.
    """
    try:
        from utils import watchdog_breaker
        return watchdog_breaker.summary(watchdog_breaker.load(_breaker_path()))
    except Exception as exc:
        logger.debug(f"[Unattended] breaker summary unavailable: {exc}")
        return {"tripped": False, "gave_up": False, "consecutive_failures": 0,
                "total_failures": 0, "probes": 0, "cooldown_sec": 0.0,
                "last_reason": "", "last_uptime_s": 0.0, "loop_error_streak": 0,
                "last_failure_iso": "", "gave_up_iso": ""}


def reset_watchdog_breaker() -> dict:
    """Give a given-up watchdog another chance: the human said "try again".

    This is the only way out of ``gave_up`` that is not a demonstrably healthy
    app, so it is deliberately a *human* action (toggling the switch, or the
    Settings button). It stays bounded: a fresh storm is capped at
    ``GIVE_UP_AFTER_PROBES`` probes again, so holding the button down cannot
    turn into an unattended relaunch loop.
    """
    try:
        from utils import watchdog_breaker
        path = _breaker_path()
        if not path.exists():
            # Nothing has ever failed here, so there is nothing to forget --
            # and this is the common case (the switch is also toggled on a
            # healthy machine). Not writing keeps the log directory clean and
            # keeps a test run from creating files in the developer's real one.
            return watchdog_breaker.summary(watchdog_breaker.load(path))
        state = watchdog_breaker.reset(path)
        logger.info(f"[Unattended] crash-loop breaker reset ({path})")
        return watchdog_breaker.summary(state)
    except Exception as exc:
        logger.debug(f"[Unattended] could not reset breaker: {exc}")
        return {}


def set_enabled(enabled: bool, allow_in_dev: bool | None = None) -> dict:
    """Turn unattended mode on/off.

    ``allow_in_dev`` is the separate opt-in for running a watchdog against
    the source tree. ``None`` (the default) leaves the stored value alone, so
    toggling unattended mode never silently flips the dev behaviour; pass it
    explicitly to change it.

    Returns ``{enabled, allow_in_dev, logon_task, autostart, autostart_kind,
    watchdog_available, error?}``. ``watchdog_available`` is reported because
    ``enabled`` alone does not mean the feature is live: the marker records the
    user's choice, while ``should_skip_watchdog()`` decides whether a watchdog
    can actually be started in the current environment. See ``status()``.

    Turning it on also **resets the crash-loop breaker**: that switch is a
    human saying "try again", which is exactly the signal a given-up watchdog
    is waiting for. Without it the switch would read "on" while nothing was
    launched for up to six hours. It stays bounded -- each storm is capped at
    ``GIVE_UP_AFTER_PROBES`` probes, so pressing the button repeatedly cannot
    turn into an unattended relaunch loop.
    """
    current = _read_marker()
    dev_flag = current.get("allow_in_dev", False) if allow_in_dev is None else bool(allow_in_dev)
    # Answered against dev_flag, not the stored marker: the value being
    # written is not readable yet.
    result = {"enabled": bool(enabled), "allow_in_dev": bool(dev_flag), "logon_task": False,
              "autostart": False, "autostart_kind": autostart_kind(),
              "watchdog_available": not should_skip_watchdog(allow_in_dev=dev_flag)}
    _write_marker(enabled=bool(enabled), allow_in_dev=bool(dev_flag))
    try:
        if enabled:
            ok, err = _install_autostart()
            result["autostart"] = ok
            # Kept Windows-only on purpose: an older UI reads this key to show
            # "logon task created", and on Linux/macOS there is no task to
            # report. ``autostart`` is the platform-neutral answer.
            result["logon_task"] = ok and sys.platform == "win32"
            if err:
                result["error"] = err
            reset_watchdog_breaker()
            ensure_watchdog_running()
        else:
            # ``autostart`` must mean the same thing on both branches --
            # "the login entry is in place" -- because the UI renders the
            # returned dict directly. Reporting the *result of the removal*
            # here made a switched-off PC show "start at login: on".
            removed = _remove_autostart()
            result["autostart"] = _autostart_installed()
            if not removed:
                result["error"] = "could not remove the start-at-login entry"
            _stop_watchdog()
    except Exception as e:
        result["error"] = str(e)
    logger.info(f"[Unattended] set {'on' if enabled else 'off'}: {result}")
    return result


def status() -> dict:
    """What Settings renders: the switch states plus what is really running.

    ``enabled`` is the user's choice for this PC (the marker file).
    ``allow_in_dev`` is their separate opt-in for a source-tree run.
    ``watchdog_available`` is whether a watchdog can run at all here. The
    three differ in dev/CI -- ``should_skip_watchdog()`` returns True and no
    watchdog is ever started -- so showing only ``enabled`` would report
    "on" for a feature that is demonstrably doing nothing.

    ``autostart`` is whether the platform entry that starts the watchdog at
    login is actually in place (logon task / .desktop file / LaunchAgent);
    ``autostart_kind`` says which mechanism that is, so the UI can explain
    itself on a platform it has never run on. ``breaker`` is the crash-loop
    breaker's verdict -- the one thing that explains "the switch is on and
    eCan is not running": it gave up after N failed relaunches.

    ``logon_task`` stays Windows-only and mirrors ``autostart`` there, because
    the frontend already reads that key for the old wording.
    """
    allow_dev = allows_dev_watchdog()
    out = {"enabled": is_enabled(), "allow_in_dev": allow_dev, "logon_task": False,
           "autostart": False, "autostart_kind": autostart_kind(),
           "watchdog_running": _watchdog_pid() is not None,
           # The UI offers the dev opt-in only in a source-tree run, so it
           # needs to know which one this is -- it cannot infer it from
           # watchdog_available, which is also false under CI.
           "dev_mode": _is_dev_mode(),
           "watchdog_available": not should_skip_watchdog(allow_in_dev=allow_dev),
           "breaker": breaker_summary()}
    out["autostart"] = _autostart_installed()
    if sys.platform == "win32":
        out["logon_task"] = out["autostart"]
    return out


def _watchdog_pid():
    import psutil
    from utils.app_watchdog import runlogs_dir, _read_lock_identity
    try:
        # The lock file carries (pid, create_time) as JSON -- a bare pid
        # is not an identity, because the OS recycles pids. A legacy
        # bare-pid file still parses.
        pid, create_time = _read_lock_identity(runlogs_dir() / "watchdog.lock")
        if not pid or not psutil.pid_exists(pid):
            return None
        proc = psutil.Process(pid)
        # The fingerprint is what makes the pid an identity. Without this
        # check a recycled pid makes the caller believe a watchdog is
        # running: ensure_watchdog_running() then returns early and the PC
        # is left with no crash cover at all, silently.
        if create_time:
            from utils.app_watchdog import CREATE_TIME_TOLERANCE_S
            if abs(proc.create_time() - float(create_time)) > CREATE_TIME_TOLERANCE_S:
                return None
        if "--watchdog" in " ".join(proc.cmdline()):
            return pid
    except Exception:
        pass
    return None


#: How long to wait for a terminated watchdog to actually die before
#: escalating to SIGKILL. The watchdog has no signal handler, so it dies
#: immediately on SIGTERM (measured: ~2 ms); the wait is for the OS to
#: reap it. The budget is generous because it is only spent when
#: something is actually wrong.
WATCHDOG_STOP_TIMEOUT_S = 5.0
#: How long to wait after SIGKILL before giving up and returning anyway.
#: A logout must not be held hostage by a wedged watchdog.
WATCHDOG_KILL_TIMEOUT_S = 2.0


def _stop_watchdog() -> None:
    """Terminate the watchdog and wait until it is really gone.

    ``psutil.Process.terminate()`` sends SIGTERM and returns immediately —
    it does not wait for the process to die. That is not good enough here:
    the start path decides whether a watchdog is already running by asking
    ``_watchdog_pid()``, which only checks that the pid is alive and its
    cmdline contains ``--watchdog``. A watchdog that has been *sent* SIGTERM
    but has not died yet still satisfies both checks.

    So without the wait, "log out, then log back in" can lose the
    watchdog entirely: the stop sends SIGTERM and returns, the start sees
    the dying watchdog and skips starting a replacement, and then the
    watchdog dies. Unattended mode is silently dead for the rest of the
    session — a crash of eCan is no longer covered, and nothing reports
    it, because the thing that would have reported it is the thing that
    did not start.

    Escalate to SIGKILL if the process does not go away, and give up
    after that rather than block the logout forever.
    """
    import psutil
    pid = _watchdog_pid()
    if not pid:
        return
    try:
        proc = psutil.Process(pid)
    except Exception:
        return
    try:
        proc.terminate()
    except Exception:
        return

    try:
        proc.wait(timeout=WATCHDOG_STOP_TIMEOUT_S)
        return
    except Exception:
        pass

    # Still alive after SIGTERM. Escalate.
    try:
        proc.kill()
    except Exception:
        pass
    try:
        proc.wait(timeout=WATCHDOG_KILL_TIMEOUT_S)
    except Exception:
        logger.debug("[Unattended] watchdog did not die after SIGKILL")


def stop_watchdog() -> None:
    """Stop the crash/hang watchdog, if one is running.

    The counterpart of ``ensure_watchdog_running``.  Called when the user
    logs out: unattended mode exists to keep a *signed-in* eCan alive, so
    once nobody is signed in there is nothing to keep alive — and a
    watchdog that relaunches the app would just bring back a login screen
    the user deliberately walked away from.
    """
    try:
        _stop_watchdog()
    except Exception as exc:
        logger.debug(f"[Unattended] could not stop watchdog: {exc}")


def _truthy_env(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in ("1", "true", "yes", "on")


def _is_dev_mode() -> bool:
    """True when eCan runs from the source tree instead of a packaged build."""
    try:
        from config.app_settings import app_settings
        return bool(app_settings.is_dev_mode)
    except Exception:
        return False


def should_skip_watchdog(allow_in_dev: bool | None = None) -> bool:
    """Whether the crash/hang watchdog must not be started here.

    The watchdog relaunches eCan when it dies — right for a production kiosk,
    wrong while a developer iterates: a crash while debugging would spawn a
    replacement instance under the developer's feet. (A *clean* exit is
    merely quiet: the app records ``clean_exit`` and the watchdog waits
    ``QUIT_HOLD_SEC`` -- 30 min -- before starting eCan again, so closing the
    window does not bounce immediately. It does bounce eventually, which is
    the point of unattended mode; that is also why the switch, not the close
    button, is what stops the watchdog.)

    Skip when:
      * ``ECAN_NO_WATCHDOG`` is set to a truthy value (explicit opt-out for
        CI, installer tests, performance runs);
      * the app runs in dev mode and neither ``ECAN_DEV_WATCHDOG`` nor the
        marker's ``allow_in_dev`` is set;
      * we are inside a pytest run.

    Two opt-ins, deliberately equivalent in effect but different in scope:

    * ``ECAN_DEV_WATCHDOG`` — scoped to one shell, for a developer who wants
      it *for this run*.
    * ``allow_in_dev`` in ``unattended.json`` — persisted, so the Settings UI
      can drive it. It defaults to off and lives beside ``enabled`` rather
      than replacing it, which is what keeps the property the env var was
      chosen for: a stale or hand-edited marker cannot silently arm a
      watchdog. Both must be *explicitly* set.

    The explicit opt-out still wins over both, so an exported opt-in in a
    developer's shell profile cannot make CI spawn watchdogs. The pytest
    guard is absolute for the same reason: a test run must never spawn one,
    whatever the marker says.
    """
    if _truthy_env("ECAN_NO_WATCHDOG"):
        return True
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    if _is_dev_mode() and not (_truthy_env("ECAN_DEV_WATCHDOG") or _dev_opt_in(allow_in_dev)):
        return True
    return False


def _dev_opt_in(allow_in_dev: bool | None) -> bool:
    """The effective dev opt-in: an explicit argument wins over the marker."""
    if allow_in_dev is not None:
        return bool(allow_in_dev)
    return allows_dev_watchdog()


def ensure_watchdog_running() -> None:
    """When unattended mode is on and no watchdog is up, start one."""
    if not is_enabled() or _watchdog_pid() is not None:
        return
    if should_skip_watchdog():
        logger.info("[Unattended] watchdog not started (dev mode without allow_in_dev, "
                    "or CI/opt-out/test environment)")
        return
    # The watchdog must outlive the process that started it -- that is its
    # entire job -- so it is detached from this process group as well:
    #
    # * Windows: a new process group and no console, so closing the parent's
    #   console (or Ctrl-C in it) does not take the watchdog with it.
    # * POSIX: a new *session*. Without it, the watchdog is in eCan's process
    #   group and dies with the terminal that launched eCan (Ctrl-C, a closed
    #   SSH session, a logout that kills the group) -- which is precisely the
    #   moment unattended mode is expected to keep working.
    if sys.platform == "win32":
        # ``getattr`` rather than attribute access: the CREATE_* constants are
        # only defined on Windows, and this branch must stay importable and
        # testable on POSIX (the values below are the documented ones).
        options = {"creationflags": (_NO_WINDOW
                                     | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
                                     | getattr(subprocess, "DETACHED_PROCESS", 0x00000008))}
    else:
        options = {"start_new_session": True}
    subprocess.Popen(watchdog_command(), close_fds=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                     **options)
    logger.info("[Unattended] crash/hang watchdog started")


def disable_for_uninstall(log_dir: str | None = None) -> None:
    """Stop unattended mode for good: the user is removing the app.

    Removes the marker (so a later reinstall does not immediately re-arm the
    watchdog), stops a running watchdog, removes the platform's autostart
    entry (logon task / .desktop file / LaunchAgent) and writes a permanent
    shutdown lease so the watchdog does not relaunch an executable that no
    longer exists.

    Never raises — an uninstall must not fail because of cleanup.
    """
    try:
        # The marker lives in the app data folder, not in runlogs -- so a
        # caller that passes the runlogs directory (the natural reading of
        # ``log_dir``, and what exit_intent uses) needs the parent. Both
        # spellings are cleared: looking only inside runlogs meant the
        # uninstall never found the marker, so a reinstall came up with
        # unattended mode silently re-armed.
        if log_dir:
            base = Path(log_dir)
            candidates = [base / "unattended.json", base.parent / "unattended.json"]
        else:
            candidates = [_marker()]
        for marker in candidates:
            if marker.exists():
                marker.unlink()
    except Exception as exc:
        logger.debug(f"[Unattended] could not remove marker: {exc}")
    try:
        _stop_watchdog()
    except Exception as exc:
        logger.debug(f"[Unattended] could not stop watchdog: {exc}")
    # Every platform, not just Windows: a leftover .desktop file or LaunchAgent
    # would make the next login try to start an app that has been uninstalled.
    _remove_autostart()
    try:
        from utils.exit_intent import claim_shutdown_lease
        claim_shutdown_lease(reason="uninstall", log_dir=log_dir)
    except Exception as exc:
        logger.debug(f"[Unattended] could not write uninstall lease: {exc}")
    logger.info("[Unattended] unattended mode disabled for uninstall")
