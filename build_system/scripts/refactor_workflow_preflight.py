"""Refactor the Ensure-Git-Bash-PowerShell preflight blocks in
release-cn.yml + release-intl.yml to PROBE-THEN-INSTALL.

Old behavior: hardcoded-path probe (`C:\\Program Files\\Git\\bin\\bash.exe`,
`C:\\Program Files\\PowerShell\\7\\pwsh.exe`) which missed non-standard
installs (operator-style paths, scoop, choco-shim) and triggered a
multi-minute install that silently shadowed the existing install
(run #86820634953).

New behavior:
  1. Probe via Find-PwshLocation / Find-BashLocation (PATH lookup +
     a handful of common candidate dirs). If found -> use that path.
  2. If NOT found -> auto-install (the canonical URLs, with the
     correctness fixes from previous audits: /DIR$gitBashInstallDir,
     msiexec -PassThru, post-install verify).
  3. Install failure -> `::error::` + `exit 1` so the operator sees
     the problem at the right step.

The `run: |` block is the inline equivalent of setup-prerequisites.ps1
(probe + install + verify). Each block is byte-identical between cn
and intl after the symmetry-check normalisation.

Used by: 10 Windows preflight blocks in release-{cn,intl}.yml.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

WORKFLOWS = [
    REPO / ".github/workflows/release-cn.yml",
    REPO / ".github/workflows/release-intl.yml",
]

# Probe-then-install run body. The leading `        run: |` is NOT
# part of NEW_RUN_BODY -- we keep the existing line and replace
# ONLY the lines that follow it.
NEW_RUN_BODY = (
    "          # Probe PowerShell 7 + Git Bash via the dedicated helper.\n"
    "          # This handles non-standard installs (operator-style\n"
    "          # C:\\Users\\<user>\\opt\\pwsh7\\, scoop, choco-shim dirs)\n"
    "          # before falling back to auto-install. Without the\n"
    "          # probe-first check, an auto-install would shadow an\n"
    "          # existing install at a non-canonical path\n"
    "          # (run #86820634953).\n"
    "          $helper = Join-Path $env:GITHUB_WORKSPACE 'build_system/scripts/runner/find-prerequisites.ps1'\n"
    "          if (Test-Path -LiteralPath $helper) {\n"
    "            . $helper\n"
    "          } else {\n"
    "            # Inline fallback for older checkouts. Same\n"
    "            # candidate list, same probe-first install-fallback\n"
    "            # semantics as find-prerequisites.ps1.\n"
    "            function Find-PwshLocation {\n"
    "              foreach ($c in @(\"$env:ProgramFiles\\PowerShell\\7\\pwsh.exe\", \"${env:ProgramFiles(x86)}\\PowerShell\\7\\pwsh.exe\", \"$env:LOCALAPPDATA\\Programs\\PowerShell\\7\\pwsh.exe\", \"$env:USERPROFILE\\opt\\pwsh7\\pwsh.exe\")) { if ($c -and (Test-Path -LiteralPath $c)) { return $c } }\n"
    "              try { return (Get-Command pwsh.exe -ErrorAction Stop).Source } catch { return $null }\n"
    "            }\n"
    "            function Find-BashLocation {\n"
    "              foreach ($c in @(\"$env:ProgramFiles\\Git\\bin\\bash.exe\", \"${env:ProgramFiles(x86)}\\Git\\bin\\bash.exe\", \"$env:LOCALAPPDATA\\Programs\\Git\\bin\\bash.exe\", \"$env:USERPROFILE\\scoop\\apps\\git\\current\\bin\\bash.exe\", \"$env:ProgramData\\chocolatey\\bin\\bash.exe\")) { if ($c -and (Test-Path -LiteralPath $c)) { return $c } }\n"
    "              try { return (Get-Command bash.exe -ErrorAction Stop).Source } catch { return $null }\n"
    "            }\n"
    "            function Get-PwshDir { param([string]$P) if (-not $P) { return $null } [System.IO.Path]::GetDirectoryName($P) }\n"
    "            function Get-BashDir { param([string]$P) if (-not $P) { return $null } [System.IO.Path]::GetDirectoryName($P) }\n"
    "          }\n"
    "\n"
    "          $gitBashInstallDir = 'C:\\Program Files\\Git'\n"
    "          $gitBashBin       = Join-Path $gitBashInstallDir 'bin\\bash.exe'\n"
    "          $pwshInstallDir   = 'C:\\Program Files\\PowerShell\\7'\n"
    "          $pwshBin          = Join-Path $pwshInstallDir   'pwsh.exe'\n"
    "\n"
    "          # --- (1) PowerShell ExecutionPolicy sanity check ---\n"
    "          # Read directly from registry (Get-ExecutionPolicy\n"
    "          # -List triggers loading of Microsoft.PowerShell.Security\n"
    "          # whose Security.types.ps1xml fails AuthorizationManager\n"
    "          # validation on some pwsh 7 installations).\n"
    "          $effectiveEp = (Get-ItemProperty -Path 'HKLM:\\SOFTWARE\\Microsoft\\PowerShell\\1\\ShellIds\\Microsoft.PowerShell' -Name ExecutionPolicy -ErrorAction SilentlyContinue).ExecutionPolicy\n"
    "          if (-not $effectiveEp) {\n"
    "            $effectiveEp = (Get-ItemProperty -Path 'HKLM:\\SOFTWARE\\Microsoft\\PowerShell\\7\\ShellIds\\Microsoft.PowerShell' -Name ExecutionPolicy -ErrorAction SilentlyContinue).ExecutionPolicy\n"
    "          }\n"
    "          if (-not $effectiveEp) { $effectiveEp = 'RemoteSigned' }\n"
    "          if ($effectiveEp -eq 'Restricted') {\n"
    "            Write-Host \"::error::PowerShell ExecutionPolicy (LocalMachine) is Restricted. The GHA runner dot-sources inline scripts via `powershell -command \\\". '<guid>.ps1'\\\"`, which Restricted rejects with `UnauthorizedAccess` BEFORE any step body runs. GitHub-hosted runners override this via Group Policy to `RemoteSigned`; self-hosted runners must do the same. Run on the runner machine (elevated PowerShell): `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope LocalMachine -Force`, then restart the runner service (`C:\\actions-runner\\svc.cmd stop && C:\\actions-runner\\svc.cmd start`). This is set automatically by build_system/scripts/runner/setup-prerequisites.ps1 on the runner -- if it's still missing, run that script first.\"\n"
    "            exit 1\n"
    "          }\n"
    "          Write-Host \"[OK] PowerShell ExecutionPolicy (LocalMachine): $effectiveEp\"\n"
    "\n"
    "          # --- (2) Git Bash (PROBE-THEN-INSTALL) ---\n"
    "          $gitBashBin = Find-BashLocation\n"
    "          if ($gitBashBin) {\n"
    "            Write-Host \"[OK] Git Bash found at $gitBashBin (no install needed)\"\n"
    "          } else {\n"
    "            Write-Host \"[INFO] Git Bash not found via probe -- installing via direct download\"\n"
    "            $gitExe = \"$env:TEMP\\Git-Setup.exe\"\n"
    "            try {\n"
    "              Invoke-WebRequest -UseBasicParsing -OutFile $gitExe \"https://github.com/git-for-windows/git/releases/download/v2.46.0.windows.1/Git-2.46.0-64-bit.exe\"\n"
    "              # Inno Setup /DIR expects the install TARGET dir\n"
    "              # (parent of bin/), NOT bin/ subdir.\n"
    "              Start-Process -Wait -FilePath $gitExe -ArgumentList '/VERYSILENT', '/NORESTART', '/NOCANCEL', '/SP-', '/CLOSEAPPLICATIONS', '/RESTARTAPPLICATIONS', \"/DIR$gitBashInstallDir\"\n"
    "              Remove-Item $gitExe -Force -ErrorAction SilentlyContinue\n"
    "            } catch {\n"
    "              Write-Host \"::error::Git for Windows install failed: $($_.Exception.Message). Install Git for Windows manually: https://git-scm.com/download/win\"\n"
    "              exit 1\n"
    "            }\n"
    "            if (-not (Test-Path $gitBashBin)) {\n"
    "              Write-Host \"::error::Git for Windows installer ran but $gitBashBin is still missing. Install Git for Windows manually: https://git-scm.com/download/win\"\n"
    "              exit 1\n"
    "            }\n"
    "            Write-Host \"[OK] Git Bash installed at $gitBashBin\"\n"
    "          }\n"
    "          $gitBashDir = Get-BashDir -BashPath $gitBashBin\n"
    "\n"
    "          # (2b) Git Bash's bin directory on the runner-service\n"
    "          # PATH? Git for Windows' installer only adds to user\n"
    "          # PATH, but the service inherits SYSTEM PATH. Forward\n"
    "          # to $GITHUB_PATH so all subsequent steps in this job\n"
    "          # see it (and the service-level PATH still needs to be\n"
    "          # set on the runner -- see docs 九.3.1).\n"
    "          $svcPath = [Environment]::GetEnvironmentVariable('Path', 'Process')\n"
    "          if ($svcPath -notlike \"*$gitBashDir*\") {\n"
    "            $gitBashDir | Out-File -Append -FilePath $env:GITHUB_PATH -Encoding utf8\n"
    "            Write-Host \"[OK] Appended '$gitBashDir' to GITHUB_PATH for subsequent steps\"\n"
    "          } else {\n"
    "            Write-Host \"[OK] Git Bash already on service PATH\"\n"
    "          }\n"
    "\n"
    "          # --- (3) PowerShell 7 (PROBE-THEN-INSTALL) ---\n"
    "          $pwshBin = Find-PwshLocation\n"
    "          if ($pwshBin) {\n"
    "            Write-Host \"[OK] PowerShell 7 found at $pwshBin (no install needed)\"\n"
    "          } else {\n"
    "            Write-Host \"[INFO] PowerShell 7 not found via probe -- installing via direct MSI download\"\n"
    "            $msi = \"$env:TEMP\\pwsh.msi\"\n"
    "            try {\n"
    "              Invoke-WebRequest -UseBasicParsing -OutFile $msi \"https://github.com/PowerShell/PowerShell/releases/download/v7.4.6/PowerShell-7.4.6-win-x64.msi\"\n"
    "              # Start-Process -PassThru captures the real MSI exit\n"
    "              # code; `msiexec ... | Out-Null` is unreliable\n"
    "              # (msiexec is GUI-subsystem, PowerShell doesn't\n"
    "              # block, $LASTEXITCODE reflects last NATIVE cmd).\n"
    "              $proc = Start-Process -FilePath \"msiexec.exe\" -ArgumentList \"/i `\"$msi`\" /qn /norestart\" -Wait -PassThru -NoNewWindow\n"
    "              if ($proc.ExitCode -ne 0) {\n"
    "                Write-Host \"::error::PowerShell 7 MSI install failed with exit code $($proc.ExitCode). Install PowerShell 7 manually on the runner -- see docs/Windows构建环境部署清单.md 九.3.1\"\n"
    "                exit 1\n"
    "              }\n"
    "              Remove-Item $msi -Force -ErrorAction SilentlyContinue\n"
    "            } catch {\n"
    "              Write-Host \"::error::PowerShell 7 install failed: $($_.Exception.Message). Install PowerShell 7 manually on the runner -- see docs/Windows构建环境部署清单.md 九.3.1\"\n"
    "              exit 1\n"
    "            }\n"
    "            if (-not (Test-Path $pwshBin)) {\n"
    "              Write-Host \"::error::PowerShell 7 install reported success but $pwshBin is still missing. Install PowerShell 7 manually on the runner -- see docs/Windows构建环境部署清单.md 九.3.1\"\n"
    "              exit 1\n"
    "            }\n"
    "            Write-Host \"[OK] PowerShell 7 installed at $pwshBin\"\n"
    "          }\n"
    "          $pwshDir = Get-PwshDir -PwshPath $pwshBin\n"
    "\n"
    "          # (3b) PowerShell 7's directory on the runner-service PATH?\n"
    "          # Same reasoning as (2b) for Git Bash: the service runs as\n"
    "          # SYSTEM and inherits SYSTEM PATH, not the user's. Forward\n"
    "          # to $GITHUB_PATH so bash/git operations that invoke pwsh\n"
    "          # as a sub-shell (e.g. git config --list | pwsh -c \"...\")\n"
    "          # do not fail with \"command not found\".\n"
    "          $svcPath = [Environment]::GetEnvironmentVariable('Path', 'Process')\n"
    "          if ($svcPath -notlike \"*$pwshDir*\") {\n"
    "            $pwshDir | Out-File -Append -FilePath $env:GITHUB_PATH -Encoding utf8\n"
    "            Write-Host \"[OK] Appended '$pwshDir' to GITHUB_PATH for subsequent steps\"\n"
    "          } else {\n"
    "            Write-Host \"[OK] PowerShell 7 already on service PATH\"\n"
    "          }\n"
    "\n"
    "          # --- (4) Final summary ---\n"
    "          Write-Host \"[OK] Prerequisite check complete: Git Bash + PowerShell 7 reachable, ExecutionPolicy=$($effectiveEp)\"\n"
    "\n"  # preserve blank separator before next step
)

# Markers that uniquely identify the OLD block. We accept both em-dash
# (U+2014) and ASCII `--` because previous edits left both versions
# in different blocks.
GIT_MARKER_HEAD = "Git Bash not found at $gitBashBin"
GIT_MARKER_TAIL = "via direct download"
PWSH_MARKER_HEAD = "PowerShell 7 not found at $pwshBin"
PWSH_MARKER_TAIL = "via direct MSI download"


def _is_old_block_run(text: str, run_line_start: int) -> bool:
    """Does the `run:` block starting at run_line_start look like an
    OLD block (the one we want to replace)? It must contain BOTH
    the Git-install warning AND the pwsh-install warning."""
    snippet = text[run_line_start:run_line_start + 30000]
    return (
        GIT_MARKER_HEAD in snippet
        and GIT_MARKER_TAIL in snippet
        and PWSH_MARKER_HEAD in snippet
        and PWSH_MARKER_TAIL in snippet
    )


def find_block_bounds(text: str, search_from: int = 0) -> tuple[int, int] | None:
    """Find the byte range [start, end) of one OLD block's run-body
    content. The replacement must KEEP the leading `        run: |`
    line intact and replace only the content lines.

    Returns:
      start_offset: byte position right AFTER the `        run: |` line
      end_offset:   byte position of the next step (the `\n` before
                    `      - name:`)
    """
    idx = text.find(GIT_MARKER_HEAD, search_from)
    if idx == -1:
        return None
    nl = text.rfind("\n        run:", 0, idx)
    if nl == -1:
        raise RuntimeError("could not find `        run:` before Git marker")
    run_line_start = nl + 1
    if not _is_old_block_run(text, run_line_start):
        return find_block_bounds(text, idx + 1)
    run_line_end_nl = text.find("\n", run_line_start)
    if run_line_end_nl == -1 or run_line_end_nl == run_line_start:
        raise RuntimeError(f"could not find end of `run:` line at {run_line_start}")
    body_start = run_line_end_nl + 1
    scan_from = run_line_start
    m = re.search(r"\n      - ", text[scan_from:])
    if not m:
        raise RuntimeError(
            f"could not find next `- ` step after byte {run_line_start}; "
            f"the block likely runs to EOF -- abort"
        )
    body_end = scan_from + m.start() + 1
    return body_start, body_end


def refactor_workflow(path: Path) -> tuple[int, str]:
    """Replace all OLD blocks in `path`. Returns (count, new_text)."""
    text = path.read_text()
    replacements = 0
    while True:
        bounds = find_block_bounds(text)
        if bounds is None:
            break
        start, end = bounds
        text = text[:start] + NEW_RUN_BODY + text[end:]
        replacements += 1
    return replacements, text


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        paths = [Path(a) for a in argv[1:]]
    else:
        paths = WORKFLOWS
    total = 0
    for wf in paths:
        n, new_text = refactor_workflow(wf)
        wf.write_text(new_text)
        print(f"{wf}: replaced {n} block(s)")
        total += n
    print(f"Total: {total}")
    if not argv[1:] and total != 10:
        print(f"ERROR: expected 10 replacements (5 cn + 5 intl), got {total}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
