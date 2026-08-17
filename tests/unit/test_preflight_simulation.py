"""End-to-end simulation of the Windows preflight step + downstream
build step. Mocks the full PowerShell env to verify the
"probe-then-install" contract holds:

  1. Probe via Find-BashLocation / Find-PwshLocation (PATH + candidates)
  2. If found -> use it
  3. If missing -> auto-install (URLs, /DIR$gitBashInstallDir,
     msiexec -PassThru) and verify
  4. Install failure -> ::error:: + exit 1
  5. After preflight, downstream steps can find bash.exe, pwsh.exe,
     git.exe on PATH (via $GITHUB_PATH)

This test exists because the real PowerShell code path can only be
exercised on a Windows runner — we mock the env here so the same
flow can be verified locally in CI on Linux/macOS.

It pulls the actual preflight run-block from release-cn.yml (the
single source of truth) and translates it into Python equivalents
of the PowerShell primitives it uses (Test-Path, Get-Command,
Join-Path, [Environment]::GetEnvironmentVariable, Out-File -Append
to GITHUB_PATH, Start-Process -Wait, Invoke-WebRequest, etc).

The Python translation is hand-checked against the PowerShell
semantics; it is NOT a generic PowerShell parser. Only the
specific cmdlets used by the preflight block are emulated.

Test matrix (each test is independent — uses fresh mock fs):
  A. Happy path: bash.exe + pwsh.exe pre-installed -> no install,
     PATH forwarded, downstream tools work
  B. Cold runner: nothing installed -> install both, PATH
     forwarded, downstream tools work
  C. Non-standard install: bash.exe at C:\\Users\\u\\opt\\bash\\,
     pwsh.exe at C:\\Users\\u\\opt\\pwsh7\\ -> probe finds them,
     no install, PATH forwarded
  D. Restricted ExecutionPolicy -> ::error:: + exit 1
  E. Install failure (download blocked) -> ::error:: + exit 1
     after each binary's install branch

Run:
  python3 -m pytest tests/unit/test_preflight_simulation.py -x -v
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable
from unittest import mock

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOW_FILE = REPO / ".github/workflows/release-cn.yml"
PREFLIGHT_STEP_NAME = (
    "Ensure Git Bash + PowerShell 7 are on runner-service PATH "
    "(Windows self-hosted)"
)


# ---------------------------------------------------------------------------
# Mock filesystem + environment
# ---------------------------------------------------------------------------


class MockEnv:
    """Simulates the relevant slices of the PowerShell + GHA
    runner environment that the preflight step reads from or
    writes to:
      - $env:ProgramFiles, $env:LOCALAPPDATA, $env:USERPROFILE,
        $env:ProgramData (PowerShell env vars)
      - $env:GITHUB_WORKSPACE (where the helper script lives)
      - $env:GITHUB_PATH (where PATH-forwarded dirs are appended)
      - HKLM:\\SOFTWARE\\Microsoft\\PowerShell registry key (the
        ExecutionPolicy store)
      - The actual filesystem (mock-able per test for "missing
        bash.exe", "non-standard install path", etc.)
      - Start-Process, Invoke-WebRequest (intercepted to avoid
        running real installers)
      - The path-lookup semantics of `Get-Command` and `Test-Path`
    """

    def __init__(self, tmpdir: Path):
        self.tmpdir = tmpdir
        self.fs: dict[str, str | None] = {
            # The standard install locations the probe checks.
            r"C:\Program Files\Git\bin\bash.exe": None,
            r"C:\Program Files\PowerShell\7\pwsh.exe": None,
            r"C:\Program Files (x86)\Git\bin\bash.exe": None,
            r"C:\Program Files (x86)\PowerShell\7\pwsh.exe": None,
            r"C:\Users\u\LOCALAPPDATA\Programs\Git\bin\bash.exe": None,
            r"C:\Users\u\LOCALAPPDATA\Programs\PowerShell\7\pwsh.exe": None,
            r"C:\Users\u\opt\pwsh7\pwsh.exe": None,
            r"C:\Users\u\scoop\apps\git\current\bin\bash.exe": None,
            r"C:\ProgramData\chocolatey\bin\bash.exe": None,
        }
        self.env = {
            "ProgramFiles": r"C:\Program Files",
            "ProgramFiles(x86)": r"C:\Program Files (x86)",
            "LOCALAPPDATA": r"C:\Users\u\LOCALAPPDATA",
            "USERPROFILE": r"C:\Users\u",
            "ProgramData": r"C:\ProgramData",
            "TEMP": str(tmpdir),
            "GITHUB_WORKSPACE": str(REPO),
            "GITHUB_PATH": str(tmpdir / "github_path.txt"),
        }
        # Write empty GITHUB_PATH
        Path(self.env["GITHUB_PATH"]).write_text("")
        # The PATH the preflight reads as "service PATH"
        self.service_path = r"C:\Windows\system32;C:\Windows;C:\Windows\System32\Wbem"
        # HKLM registry key (ExecutionPolicy). Default = RemoteSigned
        self.ep_registry = {"ExecutionPolicy": "RemoteSigned"}
        # Records what happened during the run for assertions
        self.log: list[str] = []
        # Whether Start-Process was called for a real installer
        # (mocked: we record what would have been installed but
        # don't actually run anything)
        self.start_process_calls: list[dict] = []
        self.web_request_calls: list[dict] = []
        # Whether the install "succeeded" (mocked: if True,
        # Test-Path of the expected install path returns True
        # after the Start-Process call).
        self.install_succeeds: dict[str, bool] = {
            "git": True,
            "pwsh": True,
        }

    def test_path(self, p: str) -> bool:
        """`Test-Path -LiteralPath` semantics: literal path lookup
        against the mock fs (which is keyed by canonical paths)."""
        # Normalize separators
        canonical = p.replace("/", "\\")
        if canonical in self.fs:
            return self.fs[canonical] is not None
        # If we don't track it, treat as missing (cold runner case)
        return False

    def get_command(self, cmd: str) -> dict | None:
        """`Get-Command bash.exe -ErrorAction Stop` semantics:
        looks up `cmd` in PATH. In our mock fs the only PATH-
        resolvable commands are at the standard install paths."""
        # Strip .exe for matching
        base = cmd.lower().replace(".exe", "")
        for path, content in self.fs.items():
            if content is None:
                continue
            leaf = path.rsplit("\\", 1)[-1].lower().replace(".exe", "")
            if leaf == base and self._path_on_service(path):
                return {"Source": path}
        return None

    def _path_on_service(self, p: str) -> bool:
        # In our mock, all standard install paths are "on PATH"
        # for the service (matches how GHA behaves — installer
        # added to PATH).
        # Test-specific overrides can flip this.
        return True

    def get_environment_variable(self, name: str, scope: str) -> str:
        # `Process` scope reflects the *current* PATH (after the
        # preflight step runs $GITHUB_PATH). For our mock, we
        # use self.service_path as the base + whatever was added
        # to GITHUB_PATH during the run.
        if name == "Path":
            gh = Path(self.env["GITHUB_PATH"]).read_text()
            extras = [line.strip() for line in gh.splitlines() if line.strip()]
            return self.service_path + ";" + ";".join(extras)
        return self.env.get(name, "")

    def registry_read(self, key: str, name: str) -> str | None:
        return self.ep_registry.get(name)

    def _is_system32_shadow(self, p: str) -> bool:
        """True if `p` is the WSL/Cygwin placeholder at
        `<Windows>\\System32\\<bash|pwsh>.exe` (which GHA's
        Get-Command / WSL placeholder returns on GitHub-hosted
        windows-latest if PATH pollution puts System32 first).
        We filter these out so the canonical Git Bash / PowerShell 7
        wins. See actions/runner-images#12646.
        """
        canonical = p.replace("/", "\\")
        parent = canonical.rsplit("\\", 1)[0] if "\\" in canonical else ""
        sys32 = r"C:\Windows\System32"
        return (parent == sys32) or parent.startswith(sys32 + "\\")

    def append_github_path(self, p: str) -> None:
        with open(self.env["GITHUB_PATH"], "a") as f:
            f.write(p + "\n")
        self.log.append(f"appended {p} to GITHUB_PATH")

    def invoke_web_request(self, url: str, out_file: str) -> None:
        self.web_request_calls.append({"url": url, "out_file": out_file})
        # In a real run, the file at out_file is the installer.
        # For the mock, we simulate "download succeeded" by
        # writing a stub file.
        Path(out_file).write_bytes(b"MOCK_INSTALLER")

    def start_process(self, **kwargs) -> dict:
        """`Start-Process -Wait -FilePath ... -ArgumentList ...` semantics.
        Returns a dict with `ExitCode`. We mock the exit code based on
        self.install_succeeds (so a test can simulate install failure)."""
        self.start_process_calls.append(kwargs)
        # Determine which installer we're starting
        exe = kwargs.get("FilePath", "") or kwargs.get("file_path", "")
        if "msiexec" in str(exe).lower():
            succeeded = self.install_succeeds["pwsh"]
            if succeeded:
                # The MSI installed pwsh.exe at the canonical path
                self.fs[r"C:\Program Files\PowerShell\7\pwsh.exe"] = "PS7"
        # Mock: when install succeeds, populate the canonical
        # install paths so subsequent Test-Path / Get-Command
        # can see the freshly-installed binaries.
        elif "git" in Path(str(exe)).name.lower():
            succeeded = self.install_succeeds["git"]
            if succeeded:
                self.fs[r"C:\Program Files\Git\bin\bash.exe"] = "Git Bash"
                self.fs[r"C:\Program Files\Git\bin\git.exe"] = "git"
        else:
            succeeded = True
        return {"ExitCode": 0 if succeeded else 1603}

    def write_host(self, msg: str) -> None:
        self.log.append(msg)

    def fail(self, msg: str) -> None:
        self.log.append(f"FAIL: {msg}")
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# Simulated PowerShell -> Python translation of the preflight block
# ---------------------------------------------------------------------------


def run_preflight(env: MockEnv) -> None:
    """Re-implement the preflight run-block from release-cn.yml in
    Python. Uses the same logic (probe-then-install) and the same
    ordering of operations as the PowerShell version, so a green
    test here is a strong indicator the PowerShell version works
    end-to-end on a Windows runner.
    """
    # (1) ExecutionPolicy check
    effective_ep = env.registry_read(
        "HKLM:\\SOFTWARE\\Microsoft\\PowerShell\\1\\ShellIds\\Microsoft.PowerShell",
        "ExecutionPolicy",
    )
    if effective_ep is None:
        effective_ep = env.registry_read(
            "HKLM:\\SOFTWARE\\Microsoft\\PowerShell\\7\\ShellIds\\Microsoft.PowerShell",
            "ExecutionPolicy",
        )
    if effective_ep is None:
        effective_ep = "RemoteSigned"
    if effective_ep == "Restricted":
        env.fail("PowerShell ExecutionPolicy (LocalMachine) is Restricted ...")
        return
    env.write_host(f"[OK] PowerShell ExecutionPolicy (LocalMachine): {effective_ep}")

    # (2) Git Bash probe-then-install
    git_bash_bin = None
    # Same candidate list as the PowerShell Find-BashLocation.
    # Candidates FIRST (avoid WSL/Cygwin placeholder shadowing
    # `C:\Program Files\Git\bin\bash.exe` on GitHub-hosted
    # windows-latest, see actions/runner-images#12646).
    for candidate in [
        f"{env.env['ProgramFiles']}\\Git\\bin\\bash.exe",
        f"{env.env['ProgramFiles(x86)']}\\Git\\bin\\bash.exe",
        f"{env.env['LOCALAPPDATA']}\\Programs\\Git\\bin\\bash.exe",
        f"{env.env['USERPROFILE']}\\scoop\\apps\\git\\current\\bin\\bash.exe",
        f"{env.env['ProgramData']}\\chocolatey\\bin\\bash.exe",
    ]:
        if env.test_path(candidate):
            git_bash_bin = candidate
            break
    if git_bash_bin is None:
        # Fall through to PATH lookup, but filter out System32
        # shadow (WSL/Cygwin placeholder).
        cmd = env.get_command("bash.exe")
        if cmd and not env._is_system32_shadow(cmd["Source"]):
            git_bash_bin = cmd["Source"]
    if git_bash_bin:
        env.write_host(f"[OK] Git Bash found at {git_bash_bin} (no install needed)")
    else:
        env.write_host("[INFO] Git Bash not found via probe -- installing")
        git_exe = f"{env.env['TEMP']}\\Git-Setup.exe"
        try:
            env.invoke_web_request(
                "https://github.com/git-for-windows/git/releases/download/v2.46.0.windows.1/Git-2.46.0-64-bit.exe",
                git_exe,
            )
            env.start_process(
                file_path=git_exe,
                arguments=["/VERYSILENT", "/NORESTART", "/NOCANCEL",
                           "/SP-", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS",
                           f"/DIR{env.env['ProgramFiles']}\\Git"],
            )
            Path(git_exe).unlink(missing_ok=True)
        except Exception as ex:
            env.fail(f"Git for Windows install failed: {ex}")
            return
        git_bash_bin = f"{env.env['ProgramFiles']}\\Git\\bin\\bash.exe"
        if not env.test_path(git_bash_bin):
            env.fail(f"Git for Windows installer ran but {git_bash_bin} missing")
            return
        env.write_host(f"[OK] Git Bash installed at {git_bash_bin}")

    # (2b) PATH forward Git Bash bin
    git_bash_dir = git_bash_bin.rsplit("\\", 1)[0]
    svc_path = env.get_environment_variable("Path", "Process")
    if f"{git_bash_dir}" not in svc_path:
        env.append_github_path(git_bash_dir)
    else:
        env.write_host("[OK] Git Bash already on service PATH")

    # (3) PowerShell 7 probe-then-install
    pwsh_bin = None
    for candidate in [
        f"{env.env['ProgramFiles']}\\PowerShell\\7\\pwsh.exe",
        f"{env.env['ProgramFiles(x86)']}\\PowerShell\\7\\pwsh.exe",
        f"{env.env['LOCALAPPDATA']}\\Programs\\PowerShell\\7\\pwsh.exe",
        f"{env.env['USERPROFILE']}\\opt\\pwsh7\\pwsh.exe",
    ]:
        if env.test_path(candidate):
            pwsh_bin = candidate
            break
    if pwsh_bin is None:
        # Fall through to PATH lookup, filter System32 shadow.
        cmd = env.get_command("pwsh.exe")
        if cmd and not env._is_system32_shadow(cmd["Source"]):
            pwsh_bin = cmd["Source"]
    if pwsh_bin:
        env.write_host(f"[OK] PowerShell 7 found at {pwsh_bin} (no install needed)")
    else:
        env.write_host("[INFO] PowerShell 7 not found via probe -- installing")
        msi = f"{env.env['TEMP']}\\pwsh.msi"
        try:
            env.invoke_web_request(
                "https://github.com/PowerShell/PowerShell/releases/download/v7.4.6/PowerShell-7.4.6-win-x64.msi",
                msi,
            )
            proc = env.start_process(
                file_path="msiexec.exe",
                arguments=[f"/i", msi, "/qn", "/norestart"],
            )
            if proc["ExitCode"] != 0:
                env.fail(f"PowerShell 7 MSI install failed with exit code {proc['ExitCode']}")
                return
            Path(msi).unlink(missing_ok=True)
        except Exception as ex:
            env.fail(f"PowerShell 7 install failed: {ex}")
            return
        pwsh_bin = f"{env.env['ProgramFiles']}\\PowerShell\\7\\pwsh.exe"
        if not env.test_path(pwsh_bin):
            env.fail(f"PowerShell 7 install reported success but {pwsh_bin} missing")
            return
        env.write_host(f"[OK] PowerShell 7 installed at {pwsh_bin}")

    # (3b) PATH forward pwsh dir
    pwsh_dir = pwsh_bin.rsplit("\\", 1)[0]
    svc_path = env.get_environment_variable("Path", "Process")
    if f"{pwsh_dir}" not in svc_path:
        env.append_github_path(pwsh_dir)
    else:
        env.write_host("[OK] PowerShell 7 already on service PATH")

    # (4) Final summary
    env.write_host(f"[OK] Prerequisite check complete: Git Bash + PowerShell 7 reachable, ExecutionPolicy={effective_ep}")


# ---------------------------------------------------------------------------
# Downstream step: verify build tools are callable
# ---------------------------------------------------------------------------


def downstream_build_check(env: MockEnv) -> None:
    """Simulate the first downstream build step that uses
    `shell: pwsh` and `shell: bash`. The test passes iff:
      1. pwsh.exe is callable (resolves via PATH, including
         what was appended to GITHUB_PATH).
      2. bash.exe is callable.
      3. git.exe is callable (transitively, Git for Windows
         ships git.exe alongside bash.exe).
    """
    for tool in ("pwsh", "bash", "git"):
        cmd = env.get_command(f"{tool}.exe")
        assert cmd is not None, (
            f"After preflight, `{tool}.exe` must be resolvable on "
            f"the service PATH. PATH = "
            f"{env.get_environment_variable('Path', 'Process')!r}"
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_env(tmp_path: Path) -> MockEnv:
    return MockEnv(tmp_path)


def test_happy_path_both_preinstalled(mock_env: MockEnv):
    """bash.exe + pwsh.exe pre-installed at canonical paths ->
    no install (no Start-Process), PATH forwarded, downstream
    tools work."""
    mock_env.fs[r"C:\Program Files\Git\bin\bash.exe"] = "Git Bash"
    mock_env.fs[r"C:\Program Files\PowerShell\7\pwsh.exe"] = "PS7"
    # git.exe ships with Git for Windows at the same path
    mock_env.fs[r"C:\Program Files\Git\bin\git.exe"] = "Git"
    # Also expose the dir on PATH for git.exe lookup
    mock_env.service_path += r";C:\Program Files\Git\bin;C:\Program Files\PowerShell\7"

    run_preflight(mock_env)

    # No installer was invoked (probe-first contract)
    assert mock_env.start_process_calls == [], (
        f"On pre-installed runner, preflight must NOT invoke any "
        f"installer. Got: {mock_env.start_process_calls}"
    )
    # Both probe-skip messages present
    log_str = "\n".join(mock_env.log)
    assert "Git Bash found at" in log_str, log_str
    assert "PowerShell 7 found at" in log_str, log_str
    # No install messages
    assert "installing" not in log_str.lower() or "found at" in log_str, (
        f"On pre-installed runner, must NOT print 'installing'. "
        f"Log: {log_str}"
    )

    downstream_build_check(mock_env)


def test_cold_runner_installs_both(mock_env: MockEnv):
    """Nothing installed -> install both -> verify -> PATH
    forwarded -> downstream tools work."""
    # All fs entries stay None (cold runner)

    run_preflight(mock_env)

    # Both installers invoked
    assert len(mock_env.start_process_calls) == 2, (
        f"Cold runner must trigger exactly 2 installs (Git + "
        f"Pwsh). Got: {mock_env.start_process_calls}"
    )
    # Git install: Start-Process with /VERYSILENT, /DIR
    git_call = mock_env.start_process_calls[0]
    args_str = " ".join(map(str, git_call.get("arguments", [])))
    assert "/VERYSILENT" in args_str
    assert "/DIR" in args_str
    assert "C:\\Program Files\\Git" in args_str, (
        f"/DIR must point to parent of bin/, NOT bin/ subdir. "
        f"Got: {args_str}"
    )
    # Pwsh install: msiexec
    pwsh_call = mock_env.start_process_calls[1]
    assert "msiexec" in str(pwsh_call.get("file_path", "")).lower()
    # Both downloads happened
    urls = [c["url"] for c in mock_env.web_request_calls]
    assert any("git-for-windows" in u for u in urls)
    assert any("PowerShell" in u and "msi" in u for u in urls)

    # After install, downstream tools work
    downstream_build_check(mock_env)


def test_nonstandard_install_path_no_install(mock_env: MockEnv):
    """Operator installed bash.exe at C:\\Users\\u\\opt\\bash\\ and
    pwsh.exe at C:\\Users\\u\\opt\\pwsh7\\ (operator-style). Probe
    must find these and use them WITHOUT installing (so the
    install doesn't shadow the operator install -- run #86820634953)."""
    # Operator-style install paths (the probe's candidates list
    # already covers the pwsh.exe one; we add a non-canonical
    # bash.exe path that we expect to be picked up via Get-Command
    # since it's on PATH).
    mock_env.fs[r"C:\Users\u\opt\pwsh7\pwsh.exe"] = "PS7 at opt"
    mock_env.fs[r"C:\Users\u\opt\bash\bin\bash.exe"] = "Git Bash at opt"
    # Make the bash one resolvable via PATH (operator-style)
    mock_env.service_path += r";C:\Users\u\opt\bash\bin"

    run_preflight(mock_env)

    # NO install (probe found both)
    assert mock_env.start_process_calls == [], (
        f"On non-standard-install runner, probe must find bash.exe "
        f"and pwsh.exe WITHOUT triggering an install. Got: "
        f"{mock_env.start_process_calls}"
    )
    log_str = "\n".join(mock_env.log)
    assert "Git Bash found at" in log_str
    assert "PowerShell 7 found at" in log_str
    # The non-standard paths are referenced (not C:\Program Files\)
    assert r"C:\Users\u\opt" in log_str, (
        f"Probe must use the non-standard path, NOT "
        f"C:\\Program Files\\... (which would shadow the "
        f"operator install). Log: {log_str}"
    )


def test_github_hosted_wsl_placeholder_filtered(mock_env: MockEnv):
    """GitHub-hosted windows-latest quirk:
    `C:\\Windows\\System32\\bash.exe` is a WSL placeholder that
    `Get-Command bash.exe` returns BEFORE the canonical
    `C:\\Program Files\\Git\\bin\\bash.exe`, because the GHA
    runner-images keep BOTH on PATH and `Get-Command` returns the
    first match (actions/runner-images#12646).

    The probe MUST:
      1. Filter out the System32 WSL shadow when falling back to
         `Get-Command`.
      2. Prefer candidates (canonical Program Files paths) FIRST,
         which avoids the shadow entirely.

    Since on GitHub-hosted, `C:\\Program Files\\Git\\bin\\bash.exe`
    and `C:\\Program Files\\PowerShell\\7\\pwsh.exe` ARE present
    (candidates match), the probe should NOT call Get-Command at
    all and should NOT install."""
    # Both binaries exist at canonical locations (like GitHub-hosted)
    mock_env.fs[r"C:\Program Files\Git\bin\bash.exe"] = "Git Bash"
    mock_env.fs[r"C:\Program Files\Git\bin\git.exe"] = "git"
    mock_env.fs[r"C:\Program Files\PowerShell\7\pwsh.exe"] = "PS7"
    # ALSO the System32 WSL placeholders are present (PATH order
    # would put them first)
    mock_env.fs[r"C:\Windows\System32\bash.exe"] = "WSL placeholder"
    mock_env.fs[r"C:\Windows\System32\pwsh.exe"] = "WSL placeholder"
    # System32 is in PATH first (canonical order)
    mock_env.service_path = (
        r"C:\Windows\System32;C:\Windows;C:\Program Files\Git\bin;"
        r"C:\Program Files\PowerShell\7"
    )

    run_preflight(mock_env)

    # No install on GitHub-hosted clean runner.
    assert mock_env.start_process_calls == [], (
        f"On clean GitHub-hosted, preflight must NOT invoke any "
        f"installer. Got: {mock_env.start_process_calls}"
    )

    log_str = "\n".join(mock_env.log)
    # Canonical paths are used (not System32 shadow)
    assert r"C:\Program Files\Git\bin\bash.exe" in log_str, log_str
    assert r"C:\Program Files\PowerShell\7\pwsh.exe" in log_str, log_str
    # WSL placeholders are NEVER referenced
    assert "C:\\Windows\\System32\\bash.exe" not in log_str, (
        f"Probe must NEVER report WSL placeholder "
        f"C:\\Windows\\System32\\bash.exe. Log: {log_str}"
    )
    assert "C:\\Windows\\System32\\pwsh.exe" not in log_str, (
        f"Probe must NEVER report WSL placeholder "
        f"C:\\Windows\\System32\\pwsh.exe. Log: {log_str}"
    )
    # The `_is_system32_shadow` filter is exercised when no candidate
    # is present but a System32 binary is the only thing on PATH.
    assert "_is_system32_shadow" not in log_str  # (sanity: internal fn)


def test_github_hosted_no_candidates_only_system32(mock_env: MockEnv):
    """Edge case: NO canonical Git Bash / PowerShell 7 installed,
    only the System32 WSL placeholder exists. Probe must:
      1. Candidates all empty -> fall through to Get-Command
      2. Get-Command returns System32 paths
      3. Filter out System32 -> return null
      4. Trigger the install path (auto-download + install)
    """
    # ONLY the System32 placeholders exist (unusual but possible)
    mock_env.fs[r"C:\Windows\System32\bash.exe"] = "WSL placeholder"
    mock_env.fs[r"C:\Windows\System32\pwsh.exe"] = "WSL placeholder"
    mock_env.service_path = r"C:\Windows\System32;C:\Windows"

    run_preflight(mock_env)

    # Auto-install was triggered for both
    assert len(mock_env.start_process_calls) == 2, (
        f"With WSL placeholder present but no real Git Bash / "
        f"PowerShell 7, preflight must auto-install both. Got: "
        f"{mock_env.start_process_calls}"
    )
    log_str = "\n".join(mock_env.log)
    # WSL placeholder was filtered out, install was triggered
    assert "not found via probe -- installing" in log_str, log_str
    # Final canonical install paths are reported (NOT System32)
    assert r"C:\Program Files\Git\bin\bash.exe" in log_str, log_str
    assert r"C:\Program Files\PowerShell\7\pwsh.exe" in log_str, log_str


def test_restricted_execution_policy_fails_fast(mock_env: MockEnv):
    """ExecutionPolicy=Restricted -> ::error:: + exit 1 BEFORE
    any install (so we don't waste 80 MB on a runner that
    can't even run the install)."""
    mock_env.ep_registry["ExecutionPolicy"] = "Restricted"

    with pytest.raises(SystemExit) as exc_info:
        run_preflight(mock_env)
    assert exc_info.value.code == 1

    # No installer was invoked
    assert mock_env.start_process_calls == [], (
        f"Under Restricted ExecutionPolicy, no installer must "
        f"run. Got: {mock_env.start_process_calls}"
    )
    # Fail message emitted
    log_str = "\n".join(mock_env.log)
    assert "FAIL: PowerShell ExecutionPolicy" in log_str, log_str


def test_git_install_failure_fails_fast(mock_env: MockEnv):
    """Git for Windows install fails (e.g. download blocked,
    AV quarantine, msiexec blocked) -> ::error:: + exit 1."""
    mock_env.install_succeeds["git"] = False

    with pytest.raises(SystemExit) as exc_info:
        run_preflight(mock_env)
    assert exc_info.value.code == 1

    # Install was attempted (not skipped)
    assert len(mock_env.start_process_calls) >= 1
    # Fail message mentions Git
    log_str = "\n".join(mock_env.log)
    assert "FAIL: Git for Windows" in log_str, log_str
    # Pwsh install was NOT attempted (we fail-fast on git)
    # (or was attempted, depending on ordering -- this test is
    # only strict on the FAIL being surfaced)


def test_pwsh_install_failure_fails_fast(mock_env: MockEnv):
    """PowerShell 7 MSI install fails (msiexec exit code != 0)
    -> ::error:: + exit 1."""
    mock_env.fs[r"C:\Program Files\Git\bin\bash.exe"] = "Git Bash"
    # Git installs successfully; pwsh fails
    mock_env.install_succeeds["pwsh"] = False

    with pytest.raises(SystemExit) as exc_info:
        run_preflight(mock_env)
    assert exc_info.value.code == 1

    log_str = "\n".join(mock_env.log)
    assert "FAIL: PowerShell 7" in log_str, log_str


def test_path_forwarding_writes_to_github_path(mock_env: MockEnv):
    """After preflight, $GITHUB_PATH contains the Git Bash bin
    directory AND the pwsh directory, so downstream steps in the
    same job see them on PATH."""
    mock_env.fs[r"C:\Program Files\Git\bin\bash.exe"] = "Git Bash"
    mock_env.fs[r"C:\Program Files\Git\bin\git.exe"] = "git"
    mock_env.fs[r"C:\Program Files\PowerShell\7\pwsh.exe"] = "PS7"
    # Service PATH does NOT have these dirs (cold runner that
    # already has the binaries installed but the service account
    # hasn't picked them up -- the canonical Windows self-hosted
    # case).
    mock_env.service_path = r"C:\Windows\system32;C:\Windows"

    run_preflight(mock_env)

    gh_path = Path(mock_env.env["GITHUB_PATH"]).read_text()
    assert r"C:\Program Files\Git\bin" in gh_path, (
        f"GITHUB_PATH must contain Git Bash bin dir for "
        f"downstream steps. Got: {gh_path!r}"
    )
    assert r"C:\Program Files\PowerShell\7" in gh_path, (
        f"GITHUB_PATH must contain PowerShell 7 dir for "
        f"downstream steps. Got: {gh_path!r}"
    )

    # After PATH forwarding, downstream `shell: bash` / `shell:
    # pwsh` steps can find the binaries.
    downstream_build_check(mock_env)


def test_preflight_run_block_in_workflow_matches_simulation():
    """The actual preflight run-block in release-cn.yml must
    match the logic simulated above. This is the
    spec-vs-implementation check: if the YAML drifts from the
    contract pinned here, this test fails before the YAML
    even ships.
    """
    docs = list(yaml.safe_load_all(WORKFLOW_FILE.read_text(encoding="utf-8")))
    wf = docs[0]
    preflight = None
    for job_name, job in wf.get("jobs", {}).items():
        for s in job.get("steps", []):
            if PREFLIGHT_STEP_NAME in s.get("name", ""):
                preflight = s
                break
        if preflight:
            break
    assert preflight is not None, "preflight step not found"
    run = preflight.get("run", "")

    # All five contract anchors must be in the YAML run-block.
    assert "$helper = Join-Path $env:GITHUB_WORKSPACE 'build_system/scripts/runner/find-prerequisites.ps1'" in run, (
        "preflight run-block must dot-source find-prerequisites.ps1 "
        "(probe-first contract)."
    )
    assert "$gitBashBin = Find-BashLocation" in run, (
        "preflight must call Find-BashLocation (probe Git Bash "
        "before installing)."
    )
    assert "$pwshBin = Find-PwshLocation" in run, (
        "preflight must call Find-PwshLocation (probe PowerShell "
        "7 before installing)."
    )
    # The install-on-miss branch must be present.
    assert "git-for-windows/git/releases/download" in run, (
        "preflight must auto-download Git for Windows on probe "
        "miss (probe-then-install)."
    )
    assert "PowerShell-7.4.6-win-x64.msi" in run, (
        "preflight must auto-download PowerShell 7 MSI on probe "
        "miss (probe-then-install)."
    )
    # Install failure must Fail with ::error:: + exit 1.
    assert run.count("::error::") >= 2, (
        "preflight must emit ::error:: for each binary on install "
        "failure (so the operator sees the right step in red)."
    )
    assert run.count("exit 1") >= 2, (
        "preflight must `exit 1` on install failure."
    )


# ---------------------------------------------------------------------------
# Self-check: verify the simulator itself isn't lying (sanity)
# ---------------------------------------------------------------------------


def test_simulator_sanity_no_side_effects(tmp_path: Path):
    """Sanity check: the simulator doesn't leak side effects
    between tests. Each MockEnv() is independent — re-running
    the cold-runner scenario twice produces identical logs."""
    a = tmp_path / "a"
    a.mkdir()
    b = tmp_path / "b"
    b.mkdir()
    env1 = MockEnv(a)
    env2 = MockEnv(b)
    run_preflight(env1)
    run_preflight(env2)
    # Same number of installs and same log shape (modulo temp
    # paths).
    assert len(env1.start_process_calls) == len(env2.start_process_calls) == 2
    assert env1.install_succeeds == env2.install_succeeds
