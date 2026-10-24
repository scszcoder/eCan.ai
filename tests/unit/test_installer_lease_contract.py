"""The Inno Setup installer and the app must agree on the lease path.

The uninstaller writes the shutdown lease to
``%LOCALAPPDATA%\\<appdata dir>\\runlogs\\exit_intent.json`` — but it cannot
call Python, so the directory name is baked into the generated script. If that
name drifts from ``config/constants.py::APP_NAME`` (the app's own appdata
folder), the lease lands in a path the app never reads, and the watchdog keeps
relaunching an app the user removed.

These tests pin the generated installer script against the app's own
resolution of the appdata folder. They are contract tests, not snapshot
tests: they assert the *invariant* (same directory name), not the whole file.
"""

import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

BUILD_SCRIPT = PROJECT_ROOT / "build_system" / "ecan_build.py"


def _installer_script_text() -> str:
    return BUILD_SCRIPT.read_text(encoding="utf-8")


def test_build_script_contains_a_shutdown_lease_procedure():
    text = _installer_script_text()
    assert "WriteShutdownLease" in text
    assert "exit_intent.json" in text


def test_shutdown_lease_uses_the_inno_localappdata_constant():
    text = _installer_script_text()
    # The lease lives in the per-user appdata folder, not the install folder.
    assert "ExpandConstant('{{localappdata}}')" in text


def test_shutdown_lease_writes_a_permanent_grace():
    text = _installer_script_text()
    # "inf" = permanent lease; the Python side parses the string form.
    assert '"grace_s":"inf"' in text


def test_shutdown_lease_is_written_on_uninstall():
    text = _installer_script_text()
    uninstall_section = text.split("function InitializeUninstall", 1)
    assert len(uninstall_section) == 2
    assert "WriteShutdownLease" in uninstall_section[1]


def test_shutdown_lease_timestamp_is_unix_epoch_seconds():
    """The Python side compares ``at`` against ``time.time()`` — the installer
    must write the same unit, not a local-time string."""
    text = _installer_script_text()
    assert "DateTimeToStr(Now)" in text
    assert "DateTimeToStr(EncodeDate(1970, 1, 1))" in text
    # 100-ns ticks -> seconds. Integer division: no float rounding.
    assert "div 10000000" in text


def test_lease_dir_uses_the_resolved_appdata_dir_name():
    """The lease directory must be built from the variable resolved from
    config/constants.py, not from a second, independent lookup."""
    text = _installer_script_text()
    assert "appdata_dir_name" in text
    # The template must not re-derive the name from another source.
    assert "installer_config.get(\"app_name\", app_info.get(\"name\"" not in text


def test_appdata_dir_name_is_resolved_from_config_constants():
    text = _installer_script_text()
    assert "from config.constants import APP_NAME as _APP_NAME" in text


# --------------------------------------------------------------------------
# P0-2: the permanent uninstall lease must not survive a reinstall.
#
# The uninstaller writes a *permanent* lease ("grace_s": "inf") and nothing
# ever removes it. utils/exit_intent.py::on_startup deliberately keeps it
# (it cannot tell "uninstalled" from "still installed"), and the watchdog
# exits on it forever. So after a reinstall unattended mode is permanently
# dead: the watchdog returns 0 and never launches the app again, until the
# user hand-deletes exit_intent.json.
#
# Installing is the point at which "do not launch me" becomes "launch me
# again", so the installer is what must clear the marker.
# --------------------------------------------------------------------------

def _procedure_body(text: str, name: str) -> str:
    """Return one [Code] routine's body from the Inno template.

    Scoped to the routine so an assertion cannot be satisfied by a
    matching string that lives in some *other* routine. Inno spells these
    either ``procedure X();`` or ``function X(): Boolean;``.
    """
    for keyword in ("procedure", "function"):
        parts = text.split(f"{keyword} {name}", 1)
        if len(parts) == 2:
            return parts[1].split("\nend;", 1)[0]
    raise AssertionError(f"no '{name}' routine in the generated installer")


def test_installer_clears_a_permanent_lease_at_install_time():
    text = _installer_script_text()
    assert "ClearUninstallLease" in text
    setup_section = text.split("function InitializeSetup", 1)
    assert len(setup_section) == 2
    assert "ClearUninstallLease" in setup_section[1]


def test_clear_lease_procedure_targets_the_same_path_the_uninstaller_writes():
    """Both sides must use one lease path — a second, independently-derived
    path is exactly how a lease ends up somewhere the app never reads."""
    body = _procedure_body(_installer_script_text(), "ClearUninstallLease")
    assert "exit_intent.json" in body


def test_clear_lease_uses_the_inno_localappdata_constant():
    text = _installer_script_text()
    body = _procedure_body(text, "ClearUninstallLease")
    assert "ExpandConstant('{{localappdata}}')" in body
    assert "appdata_dir_name" in body


def test_lease_clear_is_guarded_so_a_missing_file_is_not_an_error():
    """A fresh install has no lease file at all. Inno Setup's DeleteFile
    fails on a missing file, so existence must be checked first."""
    body = _procedure_body(_installer_script_text(), "ClearUninstallLease")
    assert "FileExists" in body


def test_lease_clear_is_wrapped_in_try():
    """A failed cleanup must never abort the install."""
    body = _procedure_body(_installer_script_text(), "ClearUninstallLease")
    assert "except" in body


def test_lease_clear_only_removes_the_uninstall_marker():
    """An OTA update runs this very installer. Its finite lease is what stops
    the watchdog relaunching the old build mid-replacement, so a blanket
    delete would break OTA. Only a permanent uninstall marker is removed."""
    body = _procedure_body(_installer_script_text(), "ClearUninstallLease")
    # Both spellings of a permanent grace must match: the Inno uninstaller
    # writes "inf", utils/exit_intent.py writes Infinity.
    assert "uninstall" in body
    assert "inf" in body.lower()
    # It must read the contents rather than delete blindly.
    assert "LoadStringFromFile" in body
    assert "DeleteFile" in body


@pytest.mark.parametrize("app_id,expected", [
    ("intl", "eCan"),
    ("cn", "eCan.cn"),
])
def test_resolved_appdata_dir_matches_the_app_manifest(monkeypatch, app_id, expected):
    """The resolved directory name must equal the app's own appdata folder."""
    import importlib
    monkeypatch.setenv("ECAN_APP_ID", app_id)
    # config.constants resolves APP_NAME at import time from the manifest.
    for mod in ("config.constants", "utils.app_config_loader", "config.app_info"):
        sys.modules.pop(mod, None)
    constants = importlib.import_module("config.constants")
    assert constants.APP_NAME == expected


# --------------------------------------------------------------------------
# P1-5: the uninstall lease code was generated with identifiers that do not
# exist in the script (``LicenceFile``/``LicenceDir`` are probably from the
# licence-agreement page). Inno Setup refuses to compile an undeclared
# identifier, so the whole uninstall path was dead as written -- and with it
# the permanent "do not relaunch me" marker.
# --------------------------------------------------------------------------

def test_no_undeclared_licence_identifiers_survive():
    text = _installer_script_text()
    assert not re.search(r"\bLicence(File|Dir)\b", text), (
        "the generated script uses 'Licence*' identifiers that nothing declares"
    )


@pytest.mark.parametrize("name", ["WriteShutdownLease", "ClearUninstallLease"])
def test_each_lease_procedure_declares_the_variables_it_uses(name):
    """Inno's [Code] is Pascal: every local must be in that procedure's var
    block. Writing to an undeclared binding is a compile error."""
    body = _procedure_body(_installer_script_text(), name)
    var_block = body.split("begin", 1)[0]
    assert "LeaseFile: String;" in var_block
    assert "LeaseDir: String;" in var_block


def test_uninstall_reasserts_the_permanent_lease_after_the_optional_cleanup():
    """The optional data cleanup deletes ``%LOCALAPPDATA%\\<app>`` -- which is
    exactly where the lease lives. Without a rewrite afterwards, "uninstalled"
    is erased and the watchdog relaunches eCan on the next boot."""
    body = _procedure_body(_installer_script_text(), "InitializeUninstall")
    assert body.count("WriteShutdownLease();") >= 2
    assert body.rindex("WriteShutdownLease();") > body.rindex("DelTree")


def test_the_uninstall_lease_path_follows_the_app_name():
    """No hardcoded product folder: the uninstaller must resolve the same
    directory name as the app (``appdata_dir_name``)."""
    body = _procedure_body(_installer_script_text(), "WriteShutdownLease")
    assert "appdata_dir_name" in body
    assert "'eCan'" not in body
