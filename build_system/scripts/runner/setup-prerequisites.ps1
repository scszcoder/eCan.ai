# setup-prerequisites.ps1 — Self-hosted runner environment setup & auto-install
#
# Usage (run as Administrator on the runner machine):
#   .\setup-prerequisites.ps1             # diagnose + verify + install if missing
#   .\setup-prerequisites.ps1 -Check      # diagnose only (dry-run)
#   .\setup-prerequisites.ps1 -ForceRestart  # also restart runner service
#
# What it sets up:
#   (1) PowerShell ExecutionPolicy → RemoteSigned (LocalMachine)
#   (2) Git for Windows  → install + add to SYSTEM PATH if missing
#   (3) PowerShell 7     → install MSI + add to SYSTEM PATH if missing
#   (4) Chocolatey       → install + add to SYSTEM PATH if missing
#   (5) _work directory ACL fix (calls apply-work-acl-fix.ps1 if needed)
#   (6) Restart runner service (so all child processes inherit new state)
#   (7) Test Gitee network reachability via `git ls-remote`
#       — self-hosted runners on China-based networks frequently have
#       DNS-poisoned gitee.com (gitee.com-XXXX.baiduads.com CNAME sink).
#       Network egress is set on the runner host, not in the workflow,
#       so we probe here and refuse to declare the runner ready if
#       gitee.com is unreachable from this machine. The probe uses
#       `git ls-remote` (not curl/.NET) because that is the exact code
#       path `git fetch origin` will take in release-cn.yml, so a
#       passing probe guarantees a passing checkout.
#
# Probe-then-install contract:
#   For each binary, we FIRST probe via Find-PwshLocation /
#   Find-BashLocation (PATH lookup + a handful of common candidate
#   install dirs). If found -> use that path. If not found ->
#   auto-install. This handles operators who install to non-standard
#   paths (C:\Users\<user>\opt\pwsh7\, scoop, choco-shim dirs) -- the
#   probe finds them, the install is skipped, and the existing install
#   is NOT shadowed by a default-path install.
#
#   The auto-install path is the LAST RESORT, not the first move. It
#   catches the case where the operator hasn't pre-installed anything
#   (run #86820634953). Failure to install hard-fails (Fail + exit 1),
#   so the operator sees the problem at the right step instead of a
#   `pwsh: command not found` 30 seconds into the build.
#
# This script is idempotent — running it on a healthy runner is a
# no-op for already-satisfied checks. Safe to re-run after any
# infrastructure change (e.g. Windows Update, Git upgrade) to
# repair drift.
#
# Used by:
#   - Operators on the runner machine directly (primary use)
#   - register_runner.ps1 (delegates here; does not duplicate logic)
#
# For CI-level diagnostics (no install, just check), use check-prerequisites.ps1.

[CmdletBinding()]
param(
    [switch]$Check,          # dry-run: diagnose only, do not modify anything
    [switch]$ForceRestart    # restart runner service even if no changes made
)

$ErrorActionPreference = 'Stop'

# ── Resolve script directory (works in CI too) ────────────────────────────
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $scriptRoot) { $scriptRoot = $PSScriptRoot }
if (-not $scriptRoot) {
    Write-Host "[setup] Could not resolve script directory. Set execution policy for this script directly." -ForegroundColor Yellow
    exit 1
}

# Load the probe helper so the install path is decided by a probe
# that handles non-standard install locations (C:\Users\<user>\opt\pwsh7\,
# scoop, choco-shim dirs). Probe-first avoids shadowing operator-style
# installs with a default-path install (run #86820634953).
. (Join-Path $scriptRoot 'find-prerequisites.ps1')

function Log($msg)   { Write-Host "  [OK]   $msg" -ForegroundColor Green }
function Warn($msg)  { Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Info($msg)  { Write-Host "  [INFO] $msg" -ForegroundColor Cyan }
function Fail($msg)  {
    Write-Host ""
    Write-Host "  [FAIL] $msg" -ForegroundColor Red
    Write-Host ""
    exit 1
}

function Test-IsAdmin {
    try {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
        $principal = New-Object Security.Principal.WindowsPrincipal($identity)
        return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    } catch { return $false }
}

$gitBashInstallDir = 'C:\Program Files\Git'
$gitBashDir        = Join-Path $gitBashInstallDir 'bin'
$gitBashBin        = Join-Path $gitBashDir        'bash.exe'
$pwshDir           = 'C:\Program Files\PowerShell\7'
$pwshBin           = Join-Path $pwshDir           'pwsh.exe'
$chocoBin          = 'C:\ProgramData\chocolatey\bin\choco.exe'
# Python 3.12.10 — matches GitHub-hosted windows-latest and
# docs/Windows构建环境部署清单.md §一.2 (build_validator rejects 3.11).
# choco's python3 package installs to $pythonInstallDir by default.
$pythonInstallDir  = 'C:\Python312'
$pythonBin         = Join-Path $pythonInstallDir 'python.exe'
$pythonScriptsDir  = Join-Path $pythonInstallDir 'Scripts'
$runnerDir         = if ($env:RUNNER_DIR) { $env:RUNNER_DIR } else { Join-Path $env:USERPROFILE 'actions-runner' }

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " eCan.ai Self-hosted Runner — Prerequisites Setup" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Script root : $scriptRoot"
Write-Host "Runner dir  : $runnerDir"
Write-Host "Mode        : $(if ($Check) { 'CHECK (dry-run)' } else { 'SETUP (probe + install if missing)' })"
Write-Host ""

if (-not (Test-IsAdmin)) {
    Write-Host "NOTICE: This script is not running as Administrator." -ForegroundColor Yellow
    Write-Host "  Steps that require elevation (ExecutionPolicy, PATH changes, MSI install) will prompt"
    Write-Host "  for UAC or fail. Run from an elevated PowerShell window for full setup."
    Write-Host ""
}

$changed = $false

# ═══════════════════════════════════════════════════════════════════
# (1) PowerShell ExecutionPolicy → RemoteSigned
# ═══════════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "[1] PowerShell ExecutionPolicy" -ForegroundColor Cyan
$effectiveEp = (Get-ExecutionPolicy -List | Where-Object { $_.Scope -eq 'LocalMachine' }).ExecutionPolicy
if ($effectiveEp -eq 'Restricted') {
    if ($Check) {
        Warn "Would set: ExecutionPolicy LocalMachine → RemoteSigned"
    } else {
        try {
            Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope LocalMachine -Force -ErrorAction Stop
            Log "ExecutionPolicy LocalMachine → RemoteSigned"
            $changed = $true
        } catch {
            Fail "Cannot set ExecutionPolicy: $_ — run as Administrator"
        }
    }
} else {
    Log "ExecutionPolicy LocalMachine already: $effectiveEp"
}

# ═══════════════════════════════════════════════════════════════════
# (2) Git for Windows — probe first, auto-install if missing
# ═══════════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "[2] Git for Windows" -ForegroundColor Cyan
$gitBashDiscovered = Find-BashLocation
$gitInstalled = [bool]$gitBashDiscovered

if ($gitInstalled) {
    # Re-resolve to the discovered path so PATH-forwarding below
    # uses the right binary location.
    $gitBashBin = $gitBashDiscovered
    $gitBashDir = Get-BashDir -BashPath $gitBashBin
    $ver = Get-BashVersion -Path $gitBashBin
    Log "Git Bash found at $gitBashBin ($ver) — no install needed"
} else {
    if ($Check) {
        Warn "Would install Git for Windows at $gitBashInstallDir (no bash.exe found via probe)"
    } else {
        Info "No bash.exe found anywhere — downloading Git for Windows v2.46.0..."
        $gitExe = "$env:TEMP\Git-Setup-2460.exe"
        try {
            Invoke-WebRequest -Uri 'https://github.com/git-for-windows/git/releases/download/v2.46.0.windows.1/Git-2.46.0-64-bit.exe' `
                             -OutFile $gitExe -UseBasicParsing
            Info "Installing (silent)..."
            # Inno Setup /DIR expects the install TARGET dir (= parent
            # that contains bin/), NOT the bin/ subdir. Passing /DIR=
            # bin/ was silently-ignored by Inno Setup, falling back
            # to its default `C:\Program Files\Git` (which happened to
            # match what we want, but is not explicitly pinned). The
            # install symlinks $gitBashBin at $gitBashInstallDir\bin\.
            Start-Process -Wait -FilePath $gitExe -ArgumentList '/VERYSILENT','/NORESTART','/NOCANCEL','/SP-','/CLOSEAPPLICATIONS','/RESTARTAPPLICATIONS',"/DIR$gitBashInstallDir"
            Remove-Item $gitExe -Force -ErrorAction SilentlyContinue
            if (Test-Path $gitBashBin) {
                Log "Git for Windows installed at $gitBashBin"
                $gitInstalled = $true
                $changed = $true
            } else {
                # Installer ran (exit 0) but bash.exe is not where we
                # expect. This happens with antivirus quarantine,
                # blocked install perms, etc. Don't silently pass.
                Fail "Installer ran but bash.exe not found at $gitBashBin. Install manually: https://git-scm.com/download/win, then re-run this script."
            }
        } catch {
            Fail "Download/install failed: $($_.Exception.Message)"
        }
    }
}

if ($gitInstalled) {
    $sysPath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $gitOnSysPath = $false
    if ($sysPath -and $sysPath -like "*$gitBashDir*") {
        $gitOnSysPath = $true
    }

    if (-not $gitOnSysPath) {
        if ($Check) {
            Warn "Would add '$gitBashDir' to SYSTEM PATH"
        } else {
            try {
                [Environment]::SetEnvironmentVariable(
                    'Path',
                    ($sysPath + ';' + $gitBashDir),
                    'Machine'
                )
                Log "Added '$gitBashDir' to SYSTEM PATH"
                $changed = $true
            } catch {
                Warn "Could not set SYSTEM PATH (needs Admin): add '$gitBashDir' manually"
            }
        }
    } else {
        Log "'$gitBashDir' already on SYSTEM PATH"
    }

    # Probe bash actually runs (handles stubs that exist but don't run).
    try {
        $bashVer = (& $gitBashBin --version 2>&1 | Select-Object -First 1).Trim()
        Info "bash: $bashVer"
    } catch {
        Warn "bash.exe found but does not respond to --version"
    }
}

# ═══════════════════════════════════════════════════════════════════
# (3) PowerShell 7 — probe first, auto-install if missing
# ═══════════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "[3] PowerShell 7" -ForegroundColor Cyan
$pwshDiscovered = Find-PwshLocation
$pwshInstalled = [bool]$pwshDiscovered

if ($pwshInstalled) {
    $pwshBin = $pwshDiscovered
    $pwshDir = Get-PwshDir -PwshPath $pwshBin
    $ver = Get-PwshVersion -Path $pwshBin
    Log "PowerShell 7 found at $pwshBin ($ver) — no install needed"
} else {
    if ($Check) {
        Warn "Would install PowerShell 7 v7.4.6 MSI (no pwsh.exe found via probe)"
    } else {
        Info "No pwsh.exe found anywhere — downloading PowerShell 7.4.6 MSI..."
        $msi = "$env:TEMP\pwsh-746.msi"
        try {
            Invoke-WebRequest -Uri 'https://github.com/PowerShell/PowerShell/releases/download/v7.4.6/PowerShell-7.4.6-win-x64.msi' `
                             -OutFile $msi -UseBasicParsing
            Info "Installing MSI (quiet)..."
            # Use Start-Process -PassThru to capture the real MSI exit
            # code. Calling `msiexec.exe /i ... | Out-Null` is unreliable:
            # msiexec is a GUI-subsystem app, so PowerShell doesn't
            # block on it AND $LASTEXITCODE reflects the last NATIVE
            # command in the pipeline (not necessarily msiexec).
            # References:
            #   https://stackoverflow.com/q/4124409
            #   https://stackoverflow.com/q/50867146
            $proc = Start-Process -FilePath "msiexec.exe" `
                -ArgumentList "/i `"$msi`" /qn /norestart" `
                -Wait -PassThru -NoNewWindow
            if ($proc.ExitCode -ne 0) {
                Fail "PowerShell 7 MSI install failed with exit code $($proc.ExitCode). Install manually: https://github.com/PowerShell/PowerShell/releases/download/v7.4.6/PowerShell-7.4.6-win-x64.msi"
            }
            Remove-Item $msi -Force -ErrorAction SilentlyContinue
            if (Test-Path $pwshBin) {
                Log "PowerShell 7 installed at $pwshBin"
                $pwshInstalled = $true
                $changed = $true
            } else {
                Fail "MSI exited 0 but pwsh.exe not found at $pwshBin. Install manually: https://github.com/PowerShell/PowerShell/releases/download/v7.4.6/PowerShell-7.4.6-win-x64.msi"
            }
        } catch {
            Fail "Download/install failed: $($_.Exception.Message)"
        }
    }
}

# Ensure pwsh on SYSTEM PATH (even if MSI already installed, the service
# account may not have inherited the user's PATH entry)
$sysPath2 = [Environment]::GetEnvironmentVariable('Path', 'Machine')
if ($pwshInstalled -and $sysPath2 -notlike "*$pwshDir*") {
    if ($Check) {
        Warn "Would add '$pwshDir' to SYSTEM PATH"
    } else {
        try {
            [Environment]::SetEnvironmentVariable(
                'Path',
                ($sysPath2 + ';' + $pwshDir),
                'Machine'
            )
            Log "Added '$pwshDir' to SYSTEM PATH"
            $changed = $true
        } catch {
            Warn "Could not set SYSTEM PATH (needs Admin): add '$pwshDir' manually"
        }
    }
} elseif ($pwshInstalled) {
    Log "'$pwshDir' already on SYSTEM PATH"
}

# ═══════════════════════════════════════════════════════════════════
# (3.5) Python 3.12 — probe first, auto-install if missing.
#
# Required by docs/Windows构建环境部署清单.md §一.2 and build_validator
# (rejects Python < 3.12). Without a real Python on PATH, `python3`
# in release-cn.yml bash steps resolves to the Windows 10 1709+ Store
# App Execution Alias at WindowsApps\python3.exe and exits 126.
# choco's python3 package installs to C:\Python312 by default, which
# matches the path we probe for in find-prerequisites.ps1.
# ═══════════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "[3.5] Python 3.12 (python.exe)" -ForegroundColor Cyan
$pythonDiscovered = Find-PythonLocation
$pythonInstalled = [bool]$pythonDiscovered

if ($pythonInstalled) {
    $pythonBin = $pythonDiscovered
    $pythonInstallDir = Get-PythonDir -PythonPath $pythonBin
    $ver = Get-PythonVersion -Path $pythonBin
    Log "Python found at $pythonBin ($ver) — no install needed"
} else {
    if ($Check) {
        Warn "Would install Python 3.12.10 via choco (no python.exe found via probe)"
    } else {
        if (-not (Test-Path $chocoBin)) {
            Fail "Python not installed and Chocolatey (choco.exe) is also missing — cannot auto-install. Install Python 3.12.10 manually from https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe (check 'Add python.exe to PATH' AND 'Disable path length limit' on the first screen), then re-run this script."
        }
        Info "No python.exe found — installing Python 3.12.10 via choco (this can take 2-3 minutes)..."
        $proc = Start-Process -FilePath $chocoBin `
            -ArgumentList 'install','python','--version=3.12.10','-y','--no-progress' `
            -Wait -PassThru -NoNewWindow
        if ($proc.ExitCode -ne 0) {
            Fail "Python choco install failed with exit code $($proc.ExitCode). Manual fix: download https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe and install with 'Add Python to PATH' checked, then re-run this script."
        }
        # choco's python3 package hardcodes TargetDir=C:\Python312 (ProgramFiles +
        # version), so the install hits $pythonBin by default; fall back to the
        # choco default if --installargs was ever overridden and the path differs.
        $pythonBin = Find-PythonLocation
        if ($pythonBin) {
            $pythonInstallDir = Get-PythonDir -PythonPath $pythonBin
            $ver = Get-PythonVersion -Path $pythonBin
            Log "Python installed at $pythonBin ($ver)"
            $pythonInstalled = $true
            $changed = $true
        } else {
            Fail "Python choco install succeeded but no python.exe found at $pythonInstallDir or any probed path. Manual install required."
        }
    }
}

# Ensure C:\Python312\ AND C:\Python312\Scripts\ are on SYSTEM PATH *before*
# WindowsApps. Order matters: prepending beats the per-user Store App Execution Alias.
if ($pythonInstalled) {
    $sysPath3 = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $needsPythonDir = $sysPath3 -notlike "*$pythonInstallDir*"
    $needsScriptsDir = $sysPath3 -notlike "*$pythonScriptsDir*"
    if ($needsPythonDir -or $needsScriptsDir) {
        if ($Check) {
            Warn "Would add '$pythonInstallDir' and '$pythonScriptsDir' to SYSTEM PATH"
        } else {
            try {
                $existing = $sysPath3 -split ';' | Where-Object { $_ } | ForEach-Object { $_.Trim() }
                $addList = @()
                if ($needsScriptsDir) { $addList += $pythonScriptsDir }
                if ($needsPythonDir) { $addList += $pythonInstallDir }
                $newPath = (($addList + $existing) -join ';')
                [Environment]::SetEnvironmentVariable('Path', $newPath, 'Machine')
                if ($needsScriptsDir) { Log "Added '$pythonScriptsDir' to SYSTEM PATH (prepended)" }
                if ($needsPythonDir)  { Log "Added '$pythonInstallDir' to SYSTEM PATH (prepended)" }
                $changed = $true
            } catch {
                Warn "Could not set SYSTEM PATH (needs Admin): add '$pythonInstallDir' and '$pythonScriptsDir' manually — without this, `python3` resolves to the WindowsApps Store stub and exits 126 (Permission denied)."
            }
        }
    } else {
        Log "'$pythonInstallDir' and '$pythonScriptsDir' already on SYSTEM PATH"
    }

    try {
        $pyVer = (& $pythonBin --version 2>&1 | Select-Object -First 1).Trim()
        Info "python: $pyVer"
    } catch {
        Warn "python.exe found but does not respond to --version"
    }
}

# ═══════════════════════════════════════════════════════════════════
# (4) Chocolatey — probe first, auto-install if missing
# ═══════════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "[4] Chocolatey" -ForegroundColor Cyan
$chocoDiscovered = $null
try {
    $pathHit = Get-Command choco.exe -ErrorAction Stop
    $chocoDiscovered = $pathHit.Source
} catch {
    foreach ($cand in @(
            'C:\ProgramData\chocolatey\bin\choco.exe',
            "$env:LOCALAPPDATA\Chocolatey\bin\choco.exe",
            "$env:USERPROFILE\scoop\apps\chocolatey\current\bin\choco.exe"
        )) {
        if ($cand -and (Test-Path -LiteralPath $cand)) {
            $chocoDiscovered = $cand
            break
        }
    }
}

if ($chocoDiscovered) {
    $chocoBin = $chocoDiscovered
    $ver = (& $chocoBin --version 2>&1 | Out-String).Trim()
    Log "Chocolatey found at $chocoBin ($ver) — no install needed"
} else {
    if ($Check) {
        Warn "Would install Chocolatey via community-chocolatey.org/install.ps1 (no choco found via probe)"
    } else {
        Info "No choco.exe found — installing Chocolatey (TLS 1.2 forced)..."
        try {
            # Ensure TLS 1.2 so older Windows VMs can download the bootstrap script
            [System.Net.ServicePointManager]::SecurityProtocol =
                [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
            Invoke-Expression ((New-Object System.Net.WebClient).DownloadString(
                'https://community.chocolatey.org/install.ps1'))
        } catch {
            # choco is required by setup-signtool-env as the fallback
            # path to install Windows SDK / signtool. Without it, the
            # first Windows build job fails inside setup-signtool-env
            # with `choco: command not found` 10 minutes into the
            # build — far from the obvious root cause. We Fail here
            # so the operator sees the problem at the right step.
            Fail "Chocolatey install failed: $_. Manual fix: `Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))` (elevated PowerShell)."
        }
        # Post-install verify (community bootstrap script may exit 0
        # even on partial failure; known issue with Invoke-Expression
        # chains against community.chocolatey.org).
        if (Test-Path $chocoBin) {
            $ver = (& $chocoBin --version 2>&1 | Out-String).Trim()
            Log "Chocolatey installed: $ver"
            $changed = $true
        } else {
            Fail "Chocolatey install script ran but choco.exe is still missing at $chocoBin. Manual fix: https://chocolatey.org/install"
        }
    }
}

# ═══════════════════════════════════════════════════════════════════
# (5) _work directory ACL fix (via sibling script)
# ═══════════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "[5] Runner _work directory ACL" -ForegroundColor Cyan
$diagScript = Join-Path $scriptRoot 'diagnose-work-acl.ps1'
$fixScript  = Join-Path $scriptRoot 'apply-work-acl-fix.ps1'

if ((Test-Path $diagScript) -and (Test-Path $fixScript)) {
    if ($Check) {
        Info "Would run diagnose-work-acl.ps1 + apply-work-acl-fix.ps1 if needed"
    } else {
        Info "Running diagnose..."
        try {
            $diagOut = & powershell -NoProfile -ExecutionPolicy Bypass -File $diagScript 2>&1
            $diagExit = $LASTEXITCODE
            if ($diagExit -eq 0) {
                Log "_work directory is accessible"
            } elseif ($diagExit -eq 3) {
                Warn "Diagnose reported ACL deny — applying fix..."
                "y" | & powershell -NoProfile -ExecutionPolicy Bypass -File $fixScript -RunnerDir $runnerDir
                if ($LASTEXITCODE -eq 0) {
                    Log "ACL fix applied successfully"
                    $changed = $true
                } else {
                    Warn "ACL fix exited with code $LASTEXITCODE — manual intervention may be needed"
                }
            } else {
                Warn "Diagnose exited with code $diagExit (service not running?): $diagOut"
            }
        } catch {
            Warn "Could not run diagnose-work-acl.ps1: $_"
        }
    }
} else {
    Warn "Sibling scripts not found at $scriptRoot — skipping ACL check"
}

# ═══════════════════════════════════════════════════════════════════
# (6) Restart runner service
# ═══════════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "[6] Restart runner service" -ForegroundColor Cyan
if ((Test-Path (Join-Path $runnerDir 'svc.cmd')) -and ($changed -or $ForceRestart)) {
    if ($Check) {
        Warn "Would restart runner service (svc.cmd stop && svc.cmd start)"
    } else {
        Info "Stopping runner service..."
        try { & "$runnerDir\svc.cmd" stop | Out-Null } catch { }
        Start-Sleep -Seconds 2
        Info "Starting runner service..."
        try {
            & "$runnerDir\svc.cmd" start | Out-Null
            Start-Sleep -Seconds 3
            & "$runnerDir\svc.cmd" status
            Log "Runner service restarted"
        } catch {
            Warn "Could not restart service: $_ — restart manually: C:\actions-runner\svc.cmd stop && C:\actions-runner\svc.cmd start"
        }
    }
} elseif (-not (Test-Path (Join-Path $runnerDir 'svc.cmd'))) {
    Info "Runner svc.cmd not found at $runnerDir — skipping service restart"
} else {
    Info "No changes made — skipping service restart (use -ForceRestart to restart anyway)"
}

# ═══════════════════════════════════════════════════════════════════
# (7) Test Gitee network reachability
# ═══════════════════════════════════════════════════════════════════
#
# Why this is here, not in release-cn.yml:
#   release-cn.yml's self-hosted jobs fetch source from the Gitee mirror
#   (https://gitee.com/songszchen/eCan.ai). On a China-based runner the
#   network egress to gitee.com is frequently broken: DNS resolves to a
#   poisoned CNAME (gitee.com-XXXX.baiduads.com), the Smart-HTTP endpoint
#   401s because the baiduads node doesn't proxy Git, and outbound TCP
#   to gitee.com is sometimes blocked at the firewall. None of these
#   are fixable from inside a workflow step — the runner's host DNS,
#   routing, and egress policy are set before GHA ever starts.
#
#   Putting DNS-polling logic inside the workflow tried to paper over
#   this but produced 100+ lines of parser that breaks on Chinese-
#   locale nslookup ("非权威应答:" not matched by awk IGNORECASE),
#   AND the resolved IPs are baiduads hijack points, not real Gitee.
#
#   So we put the gate here: at setup time, with admin context, we
#   actually probe whether the runner can reach gitee.com. If not, we
#   refuse to declare the runner ready and point the operator at the
#   real fix (system DNS, proxy on the service account, or move to a
#   github-hosted runner) instead of letting every build silently
#   time out at the same wall.
#
# ── Gitee reachability probe ────────────────────────────────────
#   The runner's NETWORK SERVICE context can have a different DNS
#   resolver and proxy chain from the user desktop. `git ls-remote`
#   is the cheapest end-to-end probe that exercises the same code
#   path as the actual `git fetch origin` step in release-cn.yml.
#   If `git ls-remote` returns 0, the runner can reach gitee.com
#   in the way that matters for builds.
$gitExe = Join-Path $gitBashDir 'git.exe'
$gitProbeUrl = 'https://gitee.com/songszchen/eCan.ai.git'
$gitProbeOk = $false
$gitProbeError = ''
try {
    # GIT_TERMINAL_PROMPT=0 keeps the probe non-interactive; we don't
    # supply a credential here because the public mirror is reachable
    # anonymously for ls-remote HEAD. If a future workflow pulls a
    # private repo here, add `git config credential.helper` first.
    $env:GIT_TERMINAL_PROMPT = '0'
    $out = & $gitExe ls-remote --exit-code $gitProbeUrl HEAD 2>&1
    if ($LASTEXITCODE -eq 0) {
        $gitProbeOk = $true
    } else {
        $gitProbeError = ($out | Select-Object -Last 1)
    }
} catch {
    $gitProbeError = $_.Exception.Message
}
$giteeReport = "  git ls-remote $gitProbeUrl HEAD: $(if ($gitProbeOk) { 'OK' } else { 'FAILED' })`n"

if (-not $gitProbeOk) {
    Write-Host ""
    Write-Host $giteeReport -ForegroundColor Red
    Fail ("Cannot reach gitee.com from this runner via git ls-remote. " +
          "This blocks every self-hosted release-cn job (source pull, " +
          "appcast push). Fix the runner host before re-running setup. " +
          "Note: USER-context git may work while runner-service git does " +
          "not, because the service account inherits different DNS " +
          "resolvers and proxy chains. Common fixes: (1) run `git config " +
          "--system http.proxy http://<proxy>:<port>` and " +
          "`netsh winhttp set proxy proxy-server=`<proxy>:<port>` bypass-list=localhost` " +
          "so the NETWORK SERVICE context also uses your local proxy, " +
          "(2) switch this build job to a GitHub-hosted runner " +
          "(runner_group=github-hosted).")
}
Log "Gitee reachable (git ls-remote OK)"

# ═══════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan

# Machine-readable summary line for callers (e.g. register_runner.ps1
# checks this to confirm setup completed cleanly). Format:
#   SETUP_RESULT=<OK|CHANGES_SKIPPED|FAIL> <key=value pairs>
# Empty / non-OK result blocks callers' tight loops that detect
# drift and re-invoke setup.
$setupResult = if ($changed) { 'OK' } else { 'CHANGES_SKIPPED' }
Write-Host "SETUP_RESULT=$setupResult"
Write-Host "  changed_count=$($changed)"
Write-Host "  runner_dir=$runnerDir"
Write-Host "  pwsh_bin=$pwshBin"
Write-Host "  git_bash_bin=$gitBashBin"
Write-Host "  python_bin=$pythonBin"
Write-Host "  choco_bin=$chocoBin"

if ($Check) {
    if ($changed) {
        Write-Host "DRY-RUN complete — $changed item(s) would be changed." -ForegroundColor Yellow
        Write-Host "Re-run without -Check to apply." -ForegroundColor Yellow
    } else {
        Write-Host "DRY-RUN complete — no changes needed." -ForegroundColor Green
    }
    Write-Host "============================================================" -ForegroundColor Cyan
    exit 0
}

Write-Host "SETUP complete." -ForegroundColor Green
Write-Host ""
Write-Host "  Next: run check-prerequisites.ps1 to verify all checks pass." -ForegroundColor Cyan
Write-Host "  Or:   trigger a test CI run — the runner should now succeed." -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# Exit code semantics:
#   0 = success (changed or no-op)
#   1 = Fail() was called (one of the steps hard-failed)
# We do NOT exit 1 on the no-op path — caller's "did it succeed?"
# check is "exit code was 0", and re-running repeatedly on a
# healthy runner should always exit 0.
exit 0
