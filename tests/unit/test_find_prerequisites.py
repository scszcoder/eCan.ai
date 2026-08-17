"""
Unit tests for build_system/scripts/runner/find-prerequisites.ps1.

The helper is a pure PowerShell probe — no installs, no side effects.
We test it on macOS (the dev machine) by injecting a temp directory
that mimics a Windows install layout (pwsh.exe + bash.exe as empty
files), then asserting the helpers find them.

The test handles two constraints:

  1. PowerShell 7 (`pwsh`) is not installed on the dev machine, so we
     skip the "PATH lookup hits" case. We exercise the candidate-dirs
     path only by setting the candidate-list parameters explicitly.

  2. The `Test-Path`-like check on macOS uses regular `Test-Path`
     semantics (POSIX), but the helper uses `Test-Path -LiteralPath`
     which works the same way for absolute paths on macOS. We don't
     need to mock it — we just create real files.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "build_system/scripts/runner/find-prerequisites.ps1"


def _run_pwsh_script(script_body: str, env_extra: dict[str, str] | None = None) -> tuple[int, str, str]:
    """Run a small PowerShell fragment under `pwsh` if available, else
    under `powershell` (Windows). On macOS (no pwsh), the test is
    skipped at module level below."""
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    if not pwsh:
        pytest.skip("pwsh / powershell not available on this machine")
    full = (REPO / "build_system/scripts/runner/find-prerequisites.ps1").read_text()
    full += "\n\n" + script_body
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run([pwsh, "-NoProfile", "-Command", full], capture_output=True, text=True, env=env)
    return proc.returncode, proc.stdout, proc.stderr


# -----------------------------------------------------------------------
# Skip the whole module if pwsh is not on PATH (the dev machine is macOS
# without pwsh by default). Windows CI has pwsh.
# -----------------------------------------------------------------------
if not (shutil.which("pwsh") or shutil.which("powershell")):
    pytest.skip("pwsh/powershell not available; skipping find-prerequisites tests", allow_module_level=True)


class TestFindPwshLocation:
    """Exercise Find-PwshLocation via injected candidate lists."""

    def test_finds_pwsh_in_first_candidate(self, tmp_path: Path):
        # Create a fake pwsh.exe. The helper does NOT require it to actually
        # run (Test-PwshRunnable checks --version); we only assert Find-*Location
        # returns the first existing path. Empty file is enough for Test-Path.
        fake = tmp_path / "pwsh.exe"
        fake.write_bytes(b"")
        # Re-run the helper with our candidate list as the only entry.
        rc, out, err = _run_pwsh_script(
            f"$p = Find-PwshLocation -PwshCandidates @('{fake}') ; Write-Host \"PATH=$p\"",
            env_extra={"ProgramFiles": str(tmp_path), "USERPROFILE": str(tmp_path)},
        )
        assert rc == 0, (out, err)
        assert str(fake) in out

    def test_returns_null_when_no_candidate_matches(self, tmp_path: Path):
        # No candidates exist → return $null → script prints "PATH=".
        rc, out, _ = _run_pwsh_script(
            "$p = Find-PwshLocation -PwshCandidates @() ; Write-Host \"PATH=$p\"",
        )
        assert rc == 0
        assert "PATH=" in out
        # The value after `PATH=` should be empty (no false positive).
        line = [line for line in out.splitlines() if line.startswith("PATH=")][-1]
        assert line == "PATH=", f"expected empty PATH= but got `{line}`"

    def test_skips_missing_candidates_in_order(self, tmp_path: Path):
        # Three candidates; only the third exists. The helper should skip
        # the first two (non-existent) and return the third.
        missing_a = tmp_path / "missing_a.exe"
        missing_b = tmp_path / "missing_b.exe"
        good = tmp_path / "pwsh.exe"
        good.write_bytes(b"")
        rc, out, _ = _run_pwsh_script(
            f"$p = Find-PwshLocation -PwshCandidates @('{missing_a}','{missing_b}','{good}') ; Write-Host \"PATH=$p\"",
        )
        assert rc == 0
        line = [line for line in out.splitlines() if line.startswith("PATH=")][-1]
        assert line == f"PATH={good}"

    def test_default_candidates_include_program_files_powershell_7(self):
        """Pin the default candidate list so a future edit doesn't silently
        drop the canonical Program Files path. The exact string must show
        up in the helper source."""
        text = SCRIPT.read_text()
        assert "$env:ProgramFiles\\PowerShell\\7\\pwsh.exe" in text, (
            "default $PwshCandidates must include "
            "$env:ProgramFiles\\PowerShell\\7\\pwsh.exe so the "
            "MSI-default install path is always probed"
        )
        assert "${env:ProgramFiles(x86)}\\PowerShell\\7\\pwsh.exe" in text
        assert "$env:USERPROFILE\\opt\\pwsh7\\pwsh.exe" in text, (
            "must include $env:USERPROFILE\\opt\\pwsh7\\pwsh.exe — this is "
            "the path the operator installed pwsh at on the runner that "
            "hit #86820634953. Without it, the helper falls back to "
            "PATH lookup only and may miss an unscoped user install."
        )


class TestFindBashLocation:
    def test_finds_bash_in_first_candidate(self, tmp_path: Path):
        fake = tmp_path / "bash.exe"
        fake.write_bytes(b"")
        rc, out, _ = _run_pwsh_script(
            f"$b = Find-BashLocation -BashCandidates @('{fake}') ; Write-Host \"BASH=$b\"",
            env_extra={"ProgramFiles": str(tmp_path), "USERPROFILE": str(tmp_path)},
        )
        assert rc == 0
        line = [line for line in out.splitlines() if line.startswith("BASH=")][-1]
        assert line == f"BASH={fake}"

    def test_returns_null_when_no_candidate_matches(self):
        rc, out, _ = _run_pwsh_script(
            "$b = Find-BashLocation -BashCandidates @() ; Write-Host \"BASH=$b\"",
        )
        assert rc == 0
        line = [line for line in out.splitlines() if line.startswith("BASH=")][-1]
        assert line == "BASH="

    def test_default_candidates_include_program_files_git(self):
        text = SCRIPT.read_text()
        assert "$env:ProgramFiles\\Git\\bin\\bash.exe" in text
        assert "$env:USERPROFILE\\scoop\\apps\\git\\current\\bin\\bash.exe" in text, (
            "default candidates must include scoop path — operators "
            "regularly install Git for Windows via scoop and that path "
            "won't match the canonical Program Files location."
        )


class TestPathForwardingHelpers:
    """Verify Get-PwshDir / Get-BashDir return the directory (not the
    binary path) so the caller can append it to GITHUB_PATH."""

    def test_get_pwsh_dir_returns_parent_dir(self, tmp_path: Path):
        exe = tmp_path / "pwsh.exe"
        exe.write_bytes(b"")
        rc, out, _ = _run_pwsh_script(
            f"$d = Get-PwshDir -PwshPath '{exe}' ; Write-Host \"DIR=$d\"",
        )
        assert rc == 0
        line = [line for line in out.splitlines() if line.startswith("DIR=")][-1]
        assert line == f"DIR={tmp_path}"

    def test_get_pwsh_dir_returns_null_for_null_input(self):
        rc, out, _ = _run_pwsh_script(
            "$d = Get-PwshDir -PwshPath $null ; Write-Host \"DIR=$d\"",
        )
        assert rc == 0
        line = [line for line in out.splitlines() if line.startswith("DIR=")][-1]
        assert line == "DIR="

    def test_get_bash_dir_returns_parent_dir(self, tmp_path: Path):
        exe = tmp_path / "bash.exe"
        exe.write_bytes(b"")
        rc, out, _ = _run_pwsh_script(
            f"$d = Get-BashDir -BashPath '{exe}' ; Write-Host \"DIR=$d\"",
        )
        assert rc == 0
        line = [line for line in out.splitlines() if line.startswith("DIR=")][-1]
        assert line == f"DIR={tmp_path}"
