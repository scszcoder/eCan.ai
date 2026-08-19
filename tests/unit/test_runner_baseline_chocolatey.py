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
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PS1 = REPO / "build_system" / "runner" / "register_runner.ps1" if (REPO / "build_system" / "runner").exists() else REPO / "build_system" / "scripts" / "runner" / "register_runner.ps1"
DOCS = REPO / "docs" / "Windows构建环境部署清单.md"

PS1_SOURCE = PS1.read_text(encoding="utf-8")
DOCS_SOURCE = DOCS.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# (a) Chocolatey install in register_runner.ps1
# ---------------------------------------------------------------------------

def test_register_runner_installs_chocolatey():
    """register_runner.ps1 must install Chocolatey at the canonical path so
    setup-signtool-env's choco fallback path works on self-hosted runners."""
    assert "chocolatey" in PS1_SOURCE.lower(), (
        "Expected register_runner.ps1 to install Chocolatey. Without it, "
        "setup-signtool-env's `choco install windows-sdk-10-...` fallback "
        "fails with `choco: command not found` on self-hosted runners, "
        "and code signing aborts on every Windows release."
    )


def test_register_runner_uses_canonical_choco_path():
    """The probe must check the GitHub-actions-image-default location
    `C:\\ProgramData\\chocolatey\\bin\\choco.exe`, not an invented path."""
    assert "C:\\ProgramData\\chocolatey\\bin" in PS1_SOURCE, (
        "Expected register_runner.ps1 to probe "
        "`C:\\ProgramData\\chocolatey\\bin\\choco.exe`. This is the "
        "canonical install location that GitHub-hosted windows-latest "
        "uses (per actions/runner-images Windows2025-VS2026-Readme.md)."
    )


def test_register_runner_chocolatey_install_is_idempotent():
    """Re-running register_runner.ps1 on a runner that already has Chocolatey
    must NOT re-fetch install.ps1 (which prompts + slows registration)."""
    body = PS1_SOURCE
    # Find the choco install block: from `# (c) Chocolatey.` to either
    # `# (d) Restart` or `} finally`.
    block_m = re.search(
        r"# \(c\) Chocolatey\. (?:.*?\n)+?(?=# \(d\) Restart|^\}\s*finally)",
        body,
        flags=re.MULTILINE,
    )
    assert block_m, "Could not locate Chocolatey install block in register_runner.ps1"
    block = block_m.group(0)
    assert "Test-Path $chocoBin" in block, (
        "Chocolatey install block must check `Test-Path $chocoBin` "
        "first and skip the install if choco.exe already exists. "
        "Otherwise re-running register_runner.ps1 re-downloads and "
        "re-runs the Chocolatey bootstrap."
    )


def test_register_runner_chocolatey_install_uses_official_install_url():
    """The install must use the canonical chocolatey.org URL, not a
    copy-paste from an outdated blog post."""
    assert "community.chocolatey.org/install.ps1" in PS1_SOURCE, (
        "Expected `community.chocolatey.org/install.ps1` URL. This is "
        "the canonical bootstrap URL listed at https://chocolatey.org/install. "
        "Other URLs (chocolatey.org/install.ps1) redirect here but we "
        "should reference the canonical form directly."
    )


def test_register_runner_chocolatey_enforces_tls12():
    """Older Windows VMs default to TLS 1.0/1.1, which fails the bootstrap
    download with a handshake error. The install must force TLS 1.2
    before invoking WebClient.DownloadString."""
    assert "[System.Net.ServicePointManager]::SecurityProtocol" in PS1_SOURCE, (
        "Expected `[System.Net.ServicePointManager]::SecurityProtocol = "
        "... -bor 3072` line in the Chocolatey install block. Without "
        "TLS 1.2 forced, the install.ps1 download fails on older Win10 "
        "VMs with `The underlying connection was closed`."
    )


def test_register_runner_chocolatey_failure_is_non_fatal():
    """If Chocolatey install fails (network blocked, DNS issue), the
    runner registration should still succeed with a warning. Otherwise
    a single broken host can't be registered at all, and the operator
    has no idea which step failed."""
    body = PS1_SOURCE
    # Find the choco install failure block by the Warn call
    block_m = re.search(
        r"(Log \"Chocolatey not found.*?Warn \"Chocolatey install failed.*?)\"",
        body,
        flags=re.DOTALL,
    )
    assert block_m, "Could not locate Chocolatey install failure block in register_runner.ps1"
    block = block_m.group(0)
    assert "Warn " in block, (
        "Chocolatey install failure must log via `Warn` (not Fail). "
        "Failing registration on a transient network issue blocks "
        "the whole runner. With a Warn, the runner still registers "
        "and the workflow's preflight + choco-based steps surface "
        "the issue with a precise error."
    )


# ---------------------------------------------------------------------------
# (b) ExecutionPolicy RemoteSigned already present + unchanged
# ---------------------------------------------------------------------------

def test_register_runner_sets_local_machine_execution_policy():
    """Existing contract: ExecutionPolicy=RemoteSigned on LocalMachine."""
    assert "Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope LocalMachine" in PS1_SOURCE, (
        "register_runner.ps1 must set ExecutionPolicy=RemoteSigned on "
        "LocalMachine scope. This matches GitHub-hosted runner-images' "
        "Group Policy override and unblocks `shell: powershell` steps."
    )


def test_register_runner_adds_git_bash_to_system_path():
    """Existing contract: Git Bash bin directory on SYSTEM PATH."""
    assert "'C:\\Program Files\\Git\\bin'" in PS1_SOURCE, (
        "register_runner.ps1 must add `C:\\Program Files\\Git\\bin` to "
        "SYSTEM PATH so `shell: bash` steps can resolve bash.exe in "
        "the runner-service context."
    )


def test_register_runner_restarts_svc_after_baseline():
    """ExecutionPolicy + PATH + Chocolatey all only take effect for new
    processes. The svc.cmd stop/start must come AFTER all three are set.
    We measure position by the LAST occurrence of each anchor (which is
    the install command, not the comment in the docstring)."""
    body = PS1_SOURCE
    # Find positions of the install commands (not the warn/hint messages
    # that quote them). The install commands appear at the start of the
    # line (`    Set-ExecutionPolicy ...`, `    [Environment]::SetEnvironmentVariable(`,
    # `$chocoBin = '...choco.exe'`).
    ep_idx = body.find("    Set-ExecutionPolicy -ExecutionPolicy RemoteSigned")
    # Git Bash assignment: `$gitBashDir = 'C:\\Program Files\\Git\\bin'`
    git_bash_idx = body.find("$gitBashDir = 'C:\\Program Files\\Git\\bin'")
    # Choco install command: `Invoke-Expression ((New-Object ...`
    choco_install_idx = body.find("Invoke-Expression ((New-Object")
    svc_restart_idx = body.find("    & .\\svc.cmd stop | Out-Null")
    assert ep_idx != -1 and git_bash_idx != -1 and choco_install_idx != -1 and svc_restart_idx != -1, (
        f"Missing anchor: ep={ep_idx}, git_bash={git_bash_idx}, "
        f"choco={choco_install_idx}, svc_restart={svc_restart_idx}"
    )
    assert ep_idx < svc_restart_idx, (
        "ExecutionPolicy set must happen before svc.cmd stop/start"
    )
    assert git_bash_idx < svc_restart_idx, (
        "Git Bash PATH update must happen before svc.cmd stop/start"
    )
    assert choco_install_idx < svc_restart_idx, (
        "Chocolatey install must happen before svc.cmd stop/start"
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


def test_docs_has_github_hosted_vs_self_hosted_table():
    """docs §九.3.1.1 (or equivalent) must have the GitHub-hosted vs
    self-hosted diff table that motivates the baseline install."""
    # Look for the table header phrase
    assert "GitHub-hosted `windows-latest` vs self-hosted" in DOCS_SOURCE or \
           "GitHub-hosted windows-latest vs self-hosted" in DOCS_SOURCE or \
           "GitHub-hosted `windows-latest`" in DOCS_SOURCE, (
        "docs §九.3.1 must contain the GitHub-hosted vs self-hosted "
        "tool diff table. Without it, operators don't know which "
        "tools need manual install vs auto-installed by workflow steps."
    )


def test_docs_includes_choco_verification_command():
    """The verification block at end of §九.3.1 must include `choco.exe`."""
    # Find the verification block
    m = re.search(
        r"\*\*验证\*\*.*?```powershell(.*?)```",
        DOCS_SOURCE,
        flags=re.DOTALL,
    )
    assert m, "Could not locate 验证 verification block in docs"
    block = m.group(1)
    assert "choco.exe" in block, (
        "docs §九.3.1 验证 block must include `where.exe choco.exe`. "
        "Without it, operators don't have a one-liner to confirm "
        "Chocolatey is on PATH after registration."
    )