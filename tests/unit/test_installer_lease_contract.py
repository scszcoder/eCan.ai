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


# P2: the {localappdata} constant is spelled with doubled braces for the
# f-string template ({{ renders as {), so a quadrupled spelling survives
# rendering as the literal text "{{localappdata}}". ExpandConstant then
# returns a path that does not exist and the block is dead code -- which is
# how "also clean %LOCALAPPDATA%\<app>" silently never ran.
def test_the_localappdata_constant_is_never_double_escaped():
    text = _installer_script_text()
    assert "{{{{localappdata}}}}" not in text, (
        "four braces render as the literal {{localappdata}}; the constant never expands"
    )


def test_the_uninstaller_deletes_the_per_appdata_folder_when_asked():
    """The user answered "remove my data"; the per-user folder is where that
    data actually lives, so the branch that deletes it must be reachable."""
    body = _procedure_body(_installer_script_text(), "InitializeUninstall")
    assert "ExpandConstant('{{localappdata}}" in body
    assert "DelTree(ExpandConstant('{{localappdata}}" in body


# --------------------------------------------------------------------------
# Render the template, do not just read it.
# --------------------------------------------------------------------------

# Every config the release workflows build: the shared base plus the two
# per-app ones (apps/{cn,intl}/build/build_config_{app}.json), because CI
# renders one of those and a broken template only shows up where it renders.
CONFIGS = [
    PROJECT_ROOT / "build_system" / "build_config.json",
    PROJECT_ROOT / "apps" / "cn" / "build" / "build_config_cn.json",
    PROJECT_ROOT / "apps" / "intl" / "build" / "build_config_intl.json",
]
CONFIG_IDS = ["base", "cn", "intl"]


def _render_installer_script(config_path, tmp_path, monkeypatch) -> bytes:
    """Actually generate setup.iss, the way the Windows build does."""
    from build_system.ecan_build import BuildConfig, BuildEnvironment, InstallerBuilder

    config = BuildConfig(config_path)
    builder = InstallerBuilder(config, BuildEnvironment(), tmp_path, mode="prod")
    # Icon polishing looks at dist/, which a unit test has no business having.
    monkeypatch.setattr(builder, "_ensure_windows_icon_quality", lambda: True)
    iss_file = builder._create_inno_script()
    assert iss_file is not None, (
        "the Inno Setup template failed to render; _create_inno_script() logs "
        "the reason and returns None, which on CI reads as "
        "'[ERROR] Installer creation failed' after PyInstaller has already run"
    )
    return iss_file.read_bytes()


@pytest.mark.parametrize("config_path", CONFIGS, ids=CONFIG_IDS)
def test_the_template_renders_to_a_script(config_path, tmp_path, monkeypatch):
    """The whole .iss template is a Python f-string interpolating local names.

    Every other test here greps the *template*, which is exactly how a real
    build failure got through them (run #...: "Failed to create Inno Setup
    script: name 'localappdata' is not defined"): the text looked right, but a
    single-braced Inno constant is a Python name lookup inside an f-string, so
    rendering raised ``NameError`` and no installer was produced. Rendering the
    template is the only test that covers the thing ISCC actually consumes.
    """
    text = _render_installer_script(config_path, tmp_path, monkeypatch).decode("utf-8-sig")
    assert "[Setup]" in text and "[Code]" in text
    # Constants double correctly are single-braced once rendered...
    assert "ExpandConstant('{localappdata}" in text
    assert "ExpandConstant('{app}')" in text
    assert "DestDir: \"{app}\"" in text
    # ...and nothing is left carrying the doubled spelling, which Inno takes
    # literally and then cannot expand.
    assert "{{localappdata}}" not in text
    assert "{{app}}" not in text


@pytest.mark.parametrize("config_path", CONFIGS, ids=CONFIG_IDS)
def test_the_rendered_script_is_utf8_bom(config_path, tmp_path, monkeypatch):
    """ISCC on CI reads the file as Unicode only because of the BOM; the
    uninstaller's inline JSON must survive as literal ASCII."""
    raw = _render_installer_script(config_path, tmp_path, monkeypatch)
    assert raw.startswith(b"\xef\xbb\xbf")
    assert b'"grace_s":"inf"' in raw
 
 
# --------------------------------------------------------------------------
# Brace accounting over the whole rendered script.
# --------------------------------------------------------------------------
#
# This is the part of the file that has been "fixed" wrongly several times,
# always in the same two directions:
#
#   too few  -> single-braced Inno constant in the f-string is a Python name
#               lookup: the render dies with NameError after PyInstaller has
#               already produced a dist ("[ERROR] Failed to create Inno Setup
#               script: name 'localappdata' is not defined").
#   too many -> quadrupled spelling renders to literally `{{app}}`, which Inno
#               treats as an escaped literal brace, i.e. dead text that never
#               expands. No error anywhere: the branch simply never fires
#               (how "delete my data on uninstall" silently did nothing).
#
# Reading the template cannot tell you which of the two you have, so these
# tests read the *rendered* output and account for every brace in it.

# A doubled brace in the rendered script is an escaped literal brace. Only two
# constructs are supposed to hold one, and both must stay as they are: the
# AppId is a GUID in braces (Inno's own idiom) and the uninstall registry key
# really does contain that GUID in braces. Existing installs are registered
# under exactly these names, so changing them would orphan uninstall entries
# and the OTA lookup that reads InstallLocation.
_LITERAL_BRACE_LINES = (
    re.compile(r"^AppId=\{\{[0-9A-Fa-f-]+\}\}$"),
    re.compile(r'^Root: [^;]+; Subkey: ".*Uninstall\\\{\{[0-9A-Fa-f-]+\}\}_is1";'),
)

# Every constant this script is allowed to expand. If a new one is needed,
# add it here deliberately -- that is the point: an unexpanded or mis-spelled
# constant is exactly the failure this file keeps regressing into.
_ALLOWED_CONSTANTS = re.compile(
    r"^(?:app|localappdata|appdata|userappdata|commonappdata|srcexe|uninstallexe"
    r"|group|userdesktop|pf|tmp|win|sys|autopf|cm:[\w,]+)$"
)
_EXPAND_CONSTANT_CALL = re.compile(r"ExpandConstant\('([^']*)'\)")


@pytest.mark.parametrize("config_path", CONFIGS, ids=CONFIG_IDS)
def test_no_expandconstant_argument_holds_an_escaped_brace(config_path, tmp_path, monkeypatch):
    """`ExpandConstant('{{app}}')` expands nothing: Inno hands the caller the
    text `{app}`, so every check built on it is false and every path built
    from it is wrong -- silently. This is what the uninstaller used to do."""
    text = _render_installer_script(config_path, tmp_path, monkeypatch).decode("utf-8-sig")

    calls = _EXPAND_CONSTANT_CALL.findall(text)
    assert calls, "the rendered script no longer calls ExpandConstant at all"
    for argument in calls:
        assert "{{" not in argument and "}}" not in argument, (
            f"ExpandConstant('{argument}') carries an escaped brace, so Inno "
            "will never expand the constant inside it"
        )
        for token in re.findall(r"\{([^{}]+)\}", argument):
            assert _ALLOWED_CONSTANTS.match(token), (
                f"ExpandConstant('{argument}') uses {token!r}, which this test "
                "does not know to be a real Inno constant"
            )


@pytest.mark.parametrize("config_path", CONFIGS, ids=CONFIG_IDS)
def test_doubled_braces_appear_only_where_a_literal_brace_is_required(
    config_path, tmp_path, monkeypatch
):
    """Catches the other direction: an over-braced constant renders to literal
    text and silently becomes dead code."""
    text = _render_installer_script(config_path, tmp_path, monkeypatch).decode("utf-8-sig")

    offenders = [
        line.strip()
        for line in text.splitlines()
        if ("{{" in line or "}}" in line)
        and not any(pattern.match(line.strip()) for pattern in _LITERAL_BRACE_LINES)
    ]
    assert offenders == [], (
        "these lines carry literal (escaped) braces, so nothing in them will be "
        "expanded; Inno constants in this template are written with doubled "
        "braces in Python and come out single-braced here:\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("config_path", CONFIGS, ids=CONFIG_IDS)
def test_the_uninstaller_resolves_the_real_install_path(config_path, tmp_path, monkeypatch):
    """`InitializeUninstall` builds every "delete my data" path from
    InstallPath, so if that one line does not expand, the whole cleanup block
    is unreachable while still compiling and running without complaint."""
    text = _render_installer_script(config_path, tmp_path, monkeypatch).decode("utf-8-sig")

    assert "InstallPath := ExpandConstant('{app}');" in text
    assert "'{{app}}'" not in text
    # Downstream paths are built by concatenation, so if InstallPath is wrong
    # they are all wrong together; pin one of them to prove the shape.
    assert "UserDataDirs[0] := InstallPath + '\\\\my_prompts';" in text
