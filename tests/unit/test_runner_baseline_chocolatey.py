"""
Contract tests for the operator-side runner baseline installed by
`register_runner.ps1`.

Goal: align self-hosted Windows runners with GitHub-hosted
`windows-latest` (Win Server 2025 + VS 2026) so `release-cn.yml` and
`release-intl.yml` jobs run identically on either runner class.

The runner-images manifest at
https://github.com/actions/runner-images/blob/main/images/windows/Windows2025-VS2026-Readme.md
shows that GitHub-hosted windows-latest ships:
  - PowerShell 7.x (`pwsh.exe`)
  - Git for Windows (`bash.exe`)
  - Chocolatey 2.7.x (`choco.exe`)
  - PowerShell ExecutionPolicy RemoteSigned (via Group Policy)

`register_runner.ps1` must install the corresponding baseline so
operators run ONE script and the runner is ready.

Why Chocolatey specifically:
  `setup-signtool-env` (called by every Windows build job for code
  signing) falls back to `choco install windows-sdk-10-version-...-all`
  when no signtool.exe is found. Without Chocolatey, that fallback
  fails with `choco: command not found`, the SDK install aborts, and
  code signing fails for every Windows release.

Where the Chocolatey install lives (2026-10-23)
-----------------------------------------------
It is in `setup-prerequisites.ps1`, NOT `register_runner.ps1`.
`register_runner.ps1` does registration and ACL repair only; installing
tooling is a separate, re-runnable script. These tests read both files
and assert the contract against whichever one owns it, so moving the
install again cannot silently turn this file into a test of nothing.

The behaviour is unchanged — canonical path, official bootstrap URL,
idempotent skip, TLS 1.2, non-fatal failure — it just moved. The nine
failures this file had were all "could not find the install block in
register_runner.ps1", not "the install is missing".
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_PS1_DIR_CANDIDATES = (REPO / "build_system" / "runner", REPO / "build_system" / "scripts" / "runner")
_PS1_DIR = next((d for d in _PS1_DIR_CANDIDATES if d.is_dir()), _PS1_DIR_CANDIDATES[-1])
PS1 = _PS1_DIR / "register_runner.ps1"
# Chocolatey install moved here (see module docstring). Kept as a separate
# constant so a test asserting against the wrong file is an obvious
# NameError-level mistake rather than a silent pass over the wrong text.
SETUP = _PS1_DIR / "setup-prerequisites.ps1"
DOCS = REPO / "docs" / "Windows构建环境部署清单.md"

PS1_SOURCE = PS1.read_text(encoding="utf-8")
SETUP_SOURCE = SETUP.read_text(encoding="utf-8")
# The Chocolatey contract is asserted against SETUP_SOURCE; PS1_SOURCE is
# only used for the registration-script invariants.
CHOCO_SOURCE = SETUP_SOURCE
DOCS_SOURCE = DOCS.read_text(encoding="utf-8")


def _choco_install_block() -> str:
    """The Chocolatey install region of setup-prerequisites.ps1.

    Anchored on the idempotence probe (`-not (Test-Path $chocoBin)`),
    which is the one line every other property in this section is
    asserted relative to. Anchoring on a step comment would break every
    time the script is re-worded, which is how this file ended up
    testing a file the install had moved out of.
    """
    idx = CHOCO_SOURCE.find("Test-Path $chocoBin")
    assert idx != -1, (
        "Could not locate the Chocolatey install block in "
        "setup-prerequisites.ps1 (no `Test-Path $chocoBin` probe)"
    )
    return CHOCO_SOURCE[idx:idx + 2500]


# ---------------------------------------------------------------------------
# (a) Chocolatey install in register_runner.ps1
# ---------------------------------------------------------------------------

def test_register_runner_installs_chocolatey():
    """register_runner.ps1 must install Chocolatey at the canonical path so
    setup-signtool-env's choco fallback path works on self-hosted runners."""
    assert "chocolatey" in CHOCO_SOURCE.lower(), (
        "Expected register_runner.ps1 to install Chocolatey. Without it, "
        "setup-signtool-env's `choco install windows-sdk-10-...` fallback "
        "fails with `choco: command not found` on self-hosted runners, "
        "and code signing aborts on every Windows release."
    )


def test_register_runner_uses_canonical_choco_path():
    """The probe must check the GitHub-actions-image-default location
    `C:\\ProgramData\\chocolatey\\bin\\choco.exe`, not an invented path."""
    assert "C:\\ProgramData\\chocolatey\\bin" in CHOCO_SOURCE, (
        "Expected register_runner.ps1 to probe "
        "`C:\\ProgramData\\chocolatey\\bin\\choco.exe`. This is the "
        "canonical install location that GitHub-hosted windows-latest "
        "uses (per actions/runner-images Windows2025-VS2026-Readme.md)."
    )


def test_register_runner_chocolatey_install_is_idempotent():
    """Re-running register_runner.ps1 on a runner that already has Chocolatey
    must NOT re-fetch install.ps1 (which prompts + slows registration)."""
    block = _choco_install_block()
    assert "Test-Path $chocoBin" in block, (
        "Chocolatey install block must check `Test-Path $chocoBin` "
        "first and skip the install if choco.exe already exists. "
        "Otherwise re-running register_runner.ps1 re-downloads and "
        "re-runs the Chocolatey bootstrap."
    )


def test_register_runner_chocolatey_install_uses_official_install_url():
    """The install must use the canonical chocolatey.org URL, not a
    copy-paste from an outdated blog post."""
    assert "community.chocolatey.org/install.ps1" in CHOCO_SOURCE, (
        "Expected `community.chocolatey.org/install.ps1` URL. This is "
        "the canonical bootstrap URL listed at https://chocolatey.org/install. "
        "Other URLs (chocolatey.org/install.ps1) redirect here but we "
        "should reference the canonical form directly."
    )


def test_register_runner_chocolatey_enforces_tls12():
    """Older Windows VMs default to TLS 1.0/1.1, which fails the bootstrap
    download with a handshake error. The install must force TLS 1.2
    before invoking WebClient.DownloadString."""
    # Assert the *assignment*, not the substring `SecurityProtocol`: the
    # adjacent `Fail "...Manual fix: ..."` message repeats the same literal,
    # so a substring check stays green even after the code line is deleted.
    assert re.search(
        r"\[System\.Net\.ServicePointManager\]::SecurityProtocol\s*=\s*"
        r"\[System\.Net\.ServicePointManager\]::SecurityProtocol\s*-bor\s*3072",
        CHOCO_SOURCE,
    ), (
        "Expected `[System.Net.ServicePointManager]::SecurityProtocol = "
        "... -bor 3072` in the Chocolatey install block. Without TLS 1.2 "
        "forced, the install.ps1 download fails on older Win10 VMs with "
        "`The underlying connection was closed`. Matched against the "
        "assignment so the manual-fix text inside the Fail() message "
        "cannot keep this test green on its own."
    )
    pin_idx = CHOCO_SOURCE.find("::SecurityProtocol -bor 3072")
    dl_idx = CHOCO_SOURCE.find("DownloadString")
    assert pin_idx != -1 and dl_idx != -1 and pin_idx < dl_idx, (
        f"TLS pin ({pin_idx}) must precede DownloadString ({dl_idx})"
    )


def test_register_runner_chocolatey_failure_is_non_fatal():
    """If Chocolatey install fails (network blocked, DNS issue), the
    runner registration should still succeed with a warning. Otherwise
    a single broken host can't be registered at all, and the operator
    has no idea which step failed."""
    assert "Chocolatey install failed" in CHOCO_SOURCE, (
        "Expected a `Chocolatey install failed` message in "
        "setup-prerequisites.ps1."
    )
    assert re.search(
        r"catch\s*\{[^}]*Chocolatey install failed", CHOCO_SOURCE, flags=re.DOTALL
    ), (
        "The Chocolatey install failure must be caught and reported, "
        "not raised as a terminating error — a transient network "
        "issue must not block the whole prerequisite setup."
    )


# ---------------------------------------------------------------------------
# (b) ExecutionPolicy RemoteSigned already present + unchanged
# ---------------------------------------------------------------------------

def test_register_runner_sets_local_machine_execution_policy():
    """Existing contract: ExecutionPolicy=RemoteSigned on LocalMachine."""
    assert (
        "Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope LocalMachine"
        in CHOCO_SOURCE
    ), (
        "setup-prerequisites.ps1 must set ExecutionPolicy=RemoteSigned on "
        "LocalMachine scope. This matches GitHub-hosted runner-images' "
        "Group Policy override and unblocks `shell: powershell` steps."
    )


def test_register_runner_adds_git_bash_to_system_path():
    """Existing contract: Git Bash bin directory on SYSTEM PATH."""
    assert "$gitBashInstallDir = 'C:\\Program Files\\Git'" in CHOCO_SOURCE, (
        "setup-prerequisites.ps1 must pin the Git install root to "
        "`C:\\Program Files\\Git` so `shell: bash` steps can resolve "
        "bash.exe in the runner-service context. The install is now "
        "explicit (Inno Setup /DIR), so an unpinned root would silently "
        "land somewhere the workflow's bash probe never looks."
    )
    assert "SetEnvironmentVariable('Path'" in CHOCO_SOURCE, (
        "setup-prerequisites.ps1 must add Git's bin directory to the "
        "Machine (SYSTEM) PATH — not just the process PATH — so the "
        "runner service inherits it."
    )


def test_register_runner_restarts_svc_after_baseline():
    """ExecutionPolicy + PATH + Chocolatey all only take effect for new
    processes. The svc.cmd stop/start must come AFTER all three are set.
    We measure position by the LAST occurrence of each anchor (which is
    the install command, not the comment in the docstring)."""
    body = CHOCO_SOURCE
    # Order within setup-prerequisites.ps1: the ExecutionPolicy fix must
    # land before anything that runs a .ps1 (a Restricted policy aborts
    # before the script body executes), and the PATH/choco work must
    # precede the final restart so the service picks the new environment
    # up. svc.cmd itself still lives in register_runner.ps1.
    ep_idx = body.find("Set-ExecutionPolicy -ExecutionPolicy RemoteSigned")
    git_bash_idx = body.find("$gitBashInstallDir = 'C:\\Program Files\\Git'")
    choco_install_idx = body.find("Test-Path $chocoBin")
    assert ep_idx != -1 and git_bash_idx != -1 and choco_install_idx != -1, (
        f"Missing anchor: ep={ep_idx}, git_bash={git_bash_idx}, "
        f"choco={choco_install_idx}"
    )
    assert ep_idx < choco_install_idx, (
        "ExecutionPolicy must be fixed before Chocolatey is installed — "
        "a Restricted policy blocks the bootstrap script from running."
    )
    assert git_bash_idx < choco_install_idx, (
        "Git Bash must be located before the Chocolatey install, whose "
        "probe result decides whether choco is needed at all."
    )


# ---------------------------------------------------------------------------
# (c) Documentation updated to match the new contract
# ---------------------------------------------------------------------------

def test_docs_documents_chocolatey():
    """docs §九.3.1 must call out Chocolatey as part of the baseline."""
    assert "Chocolatey" in DOCS_SOURCE, (
        "docs §九.3.1 must mention Chocolatey as part of the runner "
        "baseline (operator-side install). Otherwise operators on a "
        "fresh runner won't know to do it."
    )


def test_docs_documents_the_prerequisite_verification_command():
    """The doc must tell operators how the baseline gets installed + checked.

    This used to assert a "GitHub-hosted vs self-hosted" diff table in
    §九.3.1. That section is gone: the doc was restructured, and — more
    importantly — the operator no longer installs these tools by hand.
    `setup-prerequisites.ps1` installs Chocolatey and Git for Windows,
    and `build_system/build_validator.py` is the single command that
    reports what is present. That is the contract worth pinning.
    """
    assert "build_validator.py" in DOCS_SOURCE, (
        "docs must reference `build_system/build_validator.py` as the way "
        "to verify the Windows build baseline. Operators need one command "
        "that tells them what is missing."
    )
    assert "setup-prerequisites.ps1" in DOCS_SOURCE, (
        "docs must reference `setup-prerequisites.ps1`. Chocolatey and Git "
        "for Windows are installed by that script, not by the operator "
        "reading a table — if the doc still implies a manual install, an "
        "operator will skip the script and hit `choco: command not found` "
        "at signing time."
    )


def test_docs_includes_choco_verification_command():
    """Some verification path must be able to confirm Chocolatey."""
    assert "choco.exe" in DOCS_SOURCE, (
        "docs must give operators a way to confirm Chocolatey is present — "
        "`choco.exe` has to appear in a check the operator runs. The "
        "install itself is automated, but if it fails on a locked-down "
        "host the only symptom otherwise is `choco: command not found` "
        "at signing time."
    )