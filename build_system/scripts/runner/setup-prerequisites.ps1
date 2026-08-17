# setup-prerequisites.ps1 — Self-hosted runner environment setup & auto-fix
#
# Usage (run as Administrator on the runner machine):
#   .\setup-prerequisites.ps1         # diagnose + fix everything
#   .\setup-prerequisites.ps1 -Check   # diagnose only (dry-run)
#
# What it sets up:
#   (1) PowerShell ExecutionPolicy → RemoteSigned (LocalMachine)
#   (2) Git for Windows → install + add to SYSTEM PATH
#   (3) PowerShell 7    → install MSI + add to SYSTEM PATH
#   (4) Chocolatey      → install + add to SYSTEM PATH
#   (5) Restart runner service (so all child processes inherit new state)
#   (6) ACL fix for _work directory (calls apply-work-acl-fix.ps1 if needed)
#
# This script is idempotent — running it on a healthy runner is a no-op
# for already-satisfied checks. Safe to re-run after any infrastructure
# change (e.g. Windows Update, Git upgrade).
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

function Log($msg)   { Write-Host "  [OK]   $msg" -ForegroundColor Green }
function Warn($msg)  { Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Info($msg)  { Write-Host "  [INFO] $msg" -ForegroundColor Cyan }
function Fail($msg)  { Write-Host "  [FAIL] $msg" -ForegroundColor Red }

function Test-IsAdmin {
    try {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
        $principal = New-Object Security.Principal.WindowsPrincipal($identity)
        return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    } catch { return $false }
}

$gitBashBin   = Join-Path 'C:\Program Files\Git\bin' 'bash.exe'
$gitBashDir   = 'C:\Program Files\Git\bin'
$pwshBin      = 'C:\Program Files\PowerShell\7\pwsh.exe'
$pwshDir      = 'C:\Program Files\PowerShell\7'
$chocoBin     = 'C:\ProgramData\chocolatey\bin\choco.exe'
$runnerDir    = if ($env:RUNNER_DIR) { $env:RUNNER_DIR } else { Join-Path $env:USERPROFILE 'actions-runner' }

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " eCan.ai Self-hosted Runner — Prerequisites Setup" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Script root : $scriptRoot"
Write-Host "Runner dir  : $runnerDir"
Write-Host "Mode        : $(if ($Check) { 'CHECK (dry-run)' } else { 'SETUP (apply fixes)' })"
Write-Host ""

if (-not (Test-IsAdmin)) {
    Write-Host "NOTICE: This script is not running as Administrator." -ForegroundColor Yellow
    Write-Host "  Steps that require elevation (ExecutionPolicy, PATH changes) will prompt"
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
# (2) Git for Windows
# ═══════════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "[2] Git for Windows" -ForegroundColor Cyan
$gitInstalled = (Test-Path $gitBashBin)
$gitOnPath = $false
try {
    $null = Get-Command bash.exe -ErrorAction Stop
    $gitOnPath = $true
} catch { }

if (-not $gitInstalled) {
    if ($Check) {
        Warn "Would install Git for Windows at C:\Program Files\Git"
    } else {
        Info "Downloading Git for Windows v2.46.0..."
        $gitExe = "$env:TEMP\Git-Setup-2460.exe"
        try {
            Invoke-WebRequest -Uri 'https://github.com/git-for-windows/git/releases/download/v2.46.0.windows.1/Git-2.46.0-64-bit.exe' `
                             -OutFile $gitExe -UseBasicParsing
            Info "Installing (silent)..."
            Start-Process -Wait -FilePath $gitExe -ArgumentList '/VERYSILENT','/NORESTART','/NOCANCEL','/SP-','/CLOSEAPPLICATIONS','/RESTARTAPPLICATIONS',"/DIR$gitBashDir"
            Remove-Item $gitExe -Force -ErrorAction SilentlyContinue
            if (Test-Path $gitBashBin) {
                Log "Git for Windows installed at $gitBashBin"
                $gitInstalled = $true
                $changed = $true
            } else {
                Fail "Installer ran but bash.exe not found. Install manually: https://git-scm.com/download/win"
            }
        } catch {
            Fail "Download/install failed: $($_.Exception.Message)"
        }
    }
} else {
    Log "Git for Windows installed at $gitBashBin"
}

if ($gitInstalled) {
    $gitOnSysPath = $false
    $sysPath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
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

    # Probe bash actually runs
    try {
        $ver = (& $gitBashBin --version 2>&1 | Select-Object -First 1).Trim()
        Info "bash: $ver"
    } catch {
        Warn "bash.exe found but does not respond to --version"
    }
}

# ═══════════════════════════════════════════════════════════════════
# (3) PowerShell 7
# ═══════════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "[3] PowerShell 7" -ForegroundColor Cyan
if (-not (Test-Path $pwshBin)) {
    if ($Check) {
        Warn "Would install PowerShell 7 v7.4.6 MSI"
    } else {
        Info "Downloading PowerShell 7.4.6 MSI..."
        $msi = "$env:TEMP\pwsh-746.msi"
        try {
            Invoke-WebRequest -Uri 'https://github.com/PowerShell/PowerShell/releases/download/v7.4.6/PowerShell-7.4.6-win-x64.msi' `
                             -OutFile $msi -UseBasicParsing
            Info "Installing MSI (quiet)..."
            msiexec.exe /i $msi /qn /norestart | Out-Null
            Remove-Item $msi -Force -ErrorAction SilentlyContinue
            if (Test-Path $pwshBin) {
                Log "PowerShell 7 installed at $pwshBin"
                $changed = $true
            } else {
                Fail "MSI installed but pwsh.exe not found. Install manually: https://github.com/PowerShell/PowerShell/releases/download/v7.4.6/PowerShell-7.4.6-win-x64.msi"
            }
        } catch {
            Fail "Download/install failed: $($_.Exception.Message)"
        }
    }
} else {
    $ver = try { (& $pwshBin --version 2>&1 | Out-String).Trim() } catch { "unknown" }
    Log "PowerShell 7 already installed: $ver"
}

# Ensure pwsh on SYSTEM PATH (even if MSI already installed, the service
# account may not have inherited the user's PATH entry)
$sysPath2 = [Environment]::GetEnvironmentVariable('Path', 'Machine')
if ($sysPath2 -notlike "*$pwshDir*") {
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
} else {
    Log "'$pwshDir' already on SYSTEM PATH"
}

# ═══════════════════════════════════════════════════════════════════
# (4) Chocolatey
# ═══════════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "[4] Chocolatey" -ForegroundColor Cyan
if (Test-Path $chocoBin) {
    $ver = try { (& $chocoBin --version 2>&1 | Out-String).Trim() } catch { "unknown" }
    Log "Chocolatey already installed: v$ver"
} else {
    if ($Check) {
        Warn "Would install Chocolatey via community-chocolatey.org/install.ps1"
    } else {
        Info "Installing Chocolatey (TLS 1.2 forced)..."
        try {
            # Ensure TLS 1.2 so older Windows VMs can download the bootstrap script
            [System.Net.ServicePointManager]::SecurityProtocol =
                [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
            Invoke-Expression ((New-Object System.Net.WebClient).DownloadString(
                'https://community.chocolatey.org/install.ps1'))
            if (Test-Path $chocoBin) {
                Log "Chocolatey installed"
                $changed = $true
            } else {
                Warn "Install script ran but choco.exe not found. Retry manually or install from https://chocolatey.org/install"
            }
        } catch {
            Warn "Chocolatey install failed: $_"
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
# Summary
# ═══════════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
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
