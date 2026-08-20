"""
Contract tests for build_system/scripts/runner/register_runner.ps1.

The Windows self-hosted runner powers `release-cn.yml` jobs that depend
on `shell: bash` step execution (commit fd0ed0c0). If `bash.exe` is not
on PATH the job fails with the opaque `##[error]bash: command not
found`, masking the very symptom its Validate Gitee credentials step
was meant to surface.

register_runner.ps1 must fail-fast at registration time with a clear
remediation if bash is missing. These tests pin the contract so it
cannot regress silently.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PS1 = REPO / "build_system" / "scripts" / "runner" / "register_runner.ps1"
README = REPO / "build_system" / "scripts" / "runner" / "README.md"

PS1_SOURCE = PS1.read_text(encoding="utf-8")
README_SOURCE = README.read_text(encoding="utf-8")


def _script_body() -> str:
    """The body of the script after the param() block."""
    m = re.search(r"^param\([^)]*\)\s*\n", PS1_SOURCE, flags=re.MULTILINE)
    assert m, "expected param() block at top of register_runner.ps1"
    return PS1_SOURCE[m.end():]


def test_bash_preflight_uses_get_command():
    """The pre-flight must probe PATH, not assume a hard-coded path."""
    body = _script_body()
    assert "Get-Command bash.exe -ErrorAction Stop" in body, (
        "Expected 'Get-Command bash.exe -ErrorAction Stop' probe in "
        "register_runner.ps1. The pre-flight must come before service "
        "install so a missing bash fails fast, not at the next job run."
    )


def test_bash_preflight_exits_4_when_missing():
    """Distinct exit code 4 lets callers / CI differentiate bash-missing
    from generic failure (1), service-not-running (2), or label drift (3).
    """
    body = _script_body()
    exits = re.findall(r"^\s*exit\s+(\d+)", body, flags=re.MULTILINE)
    assert "4" in exits, (
        "Expected `exit 4` for bash-missing path. Distinct from the "
        "existing 1/2/3 exit codes so the catch in deploy / operator "
        "playbooks can route to the right remediation."
    )
    # exit 4 must appear in BASH probes, not just generic error handling
    assert body.count("exit 4") >= 2, (
        "Expected at least 2 `exit 4` exits — one for 'bash not on PATH' "
        "and one for 'bash --version returns nothing' (PATH-shadowing "
        "stub case)."
    )


def test_bash_preflight_runs_actual_bash_version():
    """A stub on PATH (e.g. msys2 PATH collision) reports as bash but
    exits 0 with no output. The pre-flight must run `bash --version`
    and check the output, not just file existence.
    """
    body = _script_body()
    assert "bash --version" in body, (
        "Expected `bash --version` invocation. Existence-only check "
        "would miss the stub-on-PATH case described in the script "
        "comment."
    )


def test_bash_preflight_before_svc_install():
    """The pre-flight must gate the service install. Otherwise the
    runner installs successfully, picks up jobs, and only fails at
    the first bash-using step — much harder to diagnose.
    """
    body = _script_body()
    bash_block_idx = body.find("Get-Command bash.exe")
    svc_install_idx = body.find("svc.cmd install")
    assert bash_block_idx != -1, "pre-flight missing"
    assert svc_install_idx != -1, "svc.cmd install marker missing"
    assert bash_block_idx < svc_install_idx, (
        "Pre-flight must run before 'svc.cmd install'. Currently "
        f"bash probe at offset {bash_block_idx} comes after svc install "
        f"at offset {svc_install_idx}."
    )


def test_bash_preflight_includes_remediation_hint():
    """Error output must tell the operator what to do, not just fail
    with a message. Otherwise the next operator hits the same wall.
    """
    body = _script_body()
    assert "https://git-scm.com/download/win" in body, (
        "Expected remediation link to Git for Windows installer."
    )
    assert "C:\\Program Files\\Git\\bin" in body, (
        "Expected PATH guidance pointing to the canonical"
        " Git Bash location."
    )


def test_readme_documents_exit_code_4():
    """Lifecycle parity: if the script exits 4, the README must explain
    what 4 means. Otherwise operators see the code and don't know what
    to do.
    """
    # Match either "Exit code 4" / "exit code 4" / "**4**" / "退出码列包含 4".
    assert re.search(
        r"(Exit code 4|exit code 4|exit codes?.*\b4\b|\b4\b.*bash missing|\b4\b.*bash 缺失)",
        README_SOURCE,
        flags=re.IGNORECASE,
    ), (
        "README must document exit code 4. Currently it only documents "
        "1/2/3."
    )


def test_readme_documents_bash_remediation():
    """The common-failures table must include the bash-missing row."""
    assert "MISSING bash on PATH" in README_SOURCE, (
        "README §6 常见失败 must include the bash-missing row, "
        "otherwise the next operator on a fresh Windows runner hits "
        "`bash: command not found` with no pointer to the fix."
    )


def test_script_does_not_declare_unused_label_helper():
    """Sanity check: the bash pre-flight additions did not leave
    behind a dead `Write-Host` line or comment that contradicts the
    code (e.g. 'exit 1' comment next to 'exit 4' code).
    """
    body = _script_body()
    # No "exit 1" inside the bash-missing block
    block = body.split("MISSING bash on PATH")[1].split("exit 4")[0]
    assert "exit 1" not in block, (
        "Found stray 'exit 1' inside the bash-missing block. The "
        "block must exit 4 so the docs / orchestrate can match it."
    )
