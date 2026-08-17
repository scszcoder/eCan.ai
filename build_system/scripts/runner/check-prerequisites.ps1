# check-prerequisites.ps1 — Self-hosted runner prerequisite diagnostic
#
# Exit codes:
#   0 = all OK
#   1 = critical failure (build will definitely fail)
#   2 = warning (build may succeed but with degraded features)
#
# Used by: .github/workflows/release-*.yml preflight step (inline).
# Also callable by operators on the runner machine directly.
#
# For automatic fix-up, run setup-prerequisites.ps1 instead.

[CmdletBinding()]
param(
    [ValidateSet('diagnose', 'strict')]
    [string]$Mode = 'diagnose'
)

$ErrorActionPreference = 'Continue'

function Write-Check($symbol, $status, $message) {
    $color = if ($status -eq 'PASS') { 'Green' }
         elseif ($status -eq 'FAIL') { 'Red' }
         elseif ($status -eq 'WARN') { 'Yellow' }
         else { 'White' }
    Write-Host "  $symbol $message" -ForegroundColor $color
}

function Test-Command($cmd) {
    try {
        $null = Get-Command $cmd -ErrorAction Stop
        return $true
    } catch { return $false }
}

function Test-CommandPath($exePath) {
    try {
        $resolved = $ExecutionContext.InvokeCommand.GetCommand($exePath, 'Application')
        return ($null -ne $resolved)
    } catch { return $false }
}

$gitBashBin  = Join-Path 'C:\Program Files\Git\bin' 'bash.exe'
$gitBashDir  = 'C:\Program Files\Git\bin'
$pwshBin     = 'C:\Program Files\PowerShell\7\pwsh.exe'
$pwshDir     = 'C:\Program Files\PowerShell\7'
$innoIscc    = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'
$chocoBin    = 'C:\ProgramData\chocolatey\bin\choco.exe'
$runnerDir   = if ($env:RUNNER_DIR) { $env:RUNNER_DIR } else { Join-Path $env:USERPROFILE 'actions-runner' }
$workDir     = Join-Path $runnerDir '_work'
$gitWorkDir  = if ($env:GITHUB_WORKSPACE) {
                    Join-Path $env:GITHUB_WORKSPACE '.git'
                } else {
                    Join-Path $workDir $env:GITHUB_REPO
                }

$critical = 0
$warning  = 0

Write-Host ""
Write-Host "=== eCan.ai Self-hosted Runner Prerequisites ===" -ForegroundColor Cyan
Write-Host "Runner dir  : $runnerDir"
Write-Host "Work dir    : $workDir"
Write-Host "GitHub env  : $env:GITHUB_ENV"
Write-Host "========================================" -ForegroundColor Cyan

# ── (1) PowerShell ExecutionPolicy ─────────────────────────────────────────
Write-Host ""
Write-Host "[1] PowerShell ExecutionPolicy" -ForegroundColor Cyan
$machPolicy = Get-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\PowerShell\1\ShellIds\Microsoft.PowerShell' -Name ExecutionPolicy -ErrorAction SilentlyContinue
$effectiveEp = (Get-ExecutionPolicy -List | Where-Object { $_.Scope -eq 'LocalMachine' }).ExecutionPolicy
if ($effectiveEp -eq 'Restricted') {
    Write-Check '✗' 'FAIL' "ExecutionPolicy is Restricted — `shell: powershell` steps will fail with UnauthorizedAccess before any script body runs. Fix: Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope LocalMachine -Force (elevated PowerShell), then: svc.cmd stop && svc.cmd start"
    $critical++
} else {
    Write-Check '✓' 'PASS' "ExecutionPolicy (LocalMachine): $effectiveEp"
}

# ── (2) Git Bash ──────────────────────────────────────────────────────────
Write-Host ""
Write-Host "[2] Git Bash (bash.exe)" -ForegroundColor Cyan
if (Test-Path $gitBashBin) {
    Write-Check '✓' 'PASS' "Found at $gitBashBin"
    # Probe: does it actually run?
    try {
        $ver = (& $gitBashBin --version 2>&1 | Select-Object -First 1).Trim()
        Write-Check '✓' 'PASS' "Responds: $ver"
    } catch {
        Write-Check '✗' 'FAIL' "Found but does not respond to --version (stub on PATH shadowing Git Bash?)"
        $critical++
    }
} else {
    Write-Check '✗' 'FAIL' "Not found at $gitBashBin — install Git for Windows (https://git-scm.com/download/win)"
    $critical++
}

# ── (2b) Git Bash on PATH (service account) ────────────────────────────────
Write-Host ""
Write-Host "[2b] Git Bash on service PATH" -ForegroundColor Cyan
$svcPath = [Environment]::GetEnvironmentVariable('Path', 'Process')
if ($svcPath -notlike "*$gitBashDir*") {
    Write-Check '✗' 'FAIL' "'$gitBashDir' NOT on service PATH — `shell: bash` steps will fail with 'bash: command not found'. Fix: add 'C:\Program Files\Git\bin' to SYSTEM PATH (see docs/Windows构建环境部署清单.md §九.3.1)"
    $critical++
} else {
    Write-Check '✓' 'PASS' "'$gitBashDir' on service PATH"
}

# ── (3) PowerShell 7 (pwsh.exe) ────────────────────────────────────────────
Write-Host ""
Write-Host "[3] PowerShell 7 (pwsh.exe)" -ForegroundColor Cyan
if (Test-Path $pwshBin) {
    Write-Check '✓' 'PASS' "Found at $pwshBin"
    try {
        $ver = (& $pwshBin --version 2>&1 | Out-String).Trim()
        Write-Check '✓' 'PASS' "Responds: $ver"
    } catch {
        Write-Check '✗' 'FAIL' "Found but does not respond to --version"
        $critical++
    }
} else {
    Write-Check '✗' 'FAIL' "Not found at $pwshBin — every `shell: pwsh` step will fail with 'pwsh: command not found'. Fix: install PowerShell 7 MSI (https://github.com/PowerShell/PowerShell/releases/download/v7.4.6/PowerShell-7.4.6-win-x64.msi)"
    $critical++
}

# ── (3b) PowerShell 7 on PATH (service account) ────────────────────────────
Write-Host ""
Write-Host "[3b] PowerShell 7 on service PATH" -ForegroundColor Cyan
if ($svcPath -notlike "*$pwshDir*") {
    Write-Check '✗' 'FAIL' "'$pwshDir' NOT on service PATH — bash/git sub-shell calls to pwsh will fail. Fix: add 'C:\Program Files\PowerShell\7' to SYSTEM PATH"
    $critical++
} else {
    Write-Check '✓' 'PASS' "'$pwshDir' on service PATH"
}

# ── (4) Inno Setup 6 (Windows only) ───────────────────────────────────────
if ($env:PROCESSOR_ARCHITECTURE -eq 'AMD64') {
    Write-Host ""
    Write-Host "[4] Inno Setup 6 (ISCC.exe)" -ForegroundColor Cyan
    if (Test-Path $innoIscc) {
        Write-Check '✓' 'PASS' "Found at $innoIscc"
    } else {
        Write-Check '!' 'WARN' "Not found at $innoIscc — Windows installer build will trigger auto-download (~5MB). First build may be slower."
        $warning++
    }
}

# ── (5) Chocolatey ────────────────────────────────────────────────────────
Write-Host ""
Write-Host "[5] Chocolatey (choco.exe)" -ForegroundColor Cyan
if (Test-Path $chocoBin) {
    Write-Check '✓' 'PASS' "Found at $chocoBin"
    try {
        $ver = (& $chocoBin --version 2>&1 | Out-String).Trim()
        Write-Check '✓' 'PASS' "Version: $ver"
    } catch {
        Write-Check '!' 'WARN' "Found but choco --version failed — setup-signtool-env fallback may not work"
        $warning++
    }
} else {
    Write-Check '!' 'WARN' "Not found at $chocoBin — setup-signtool-env's choco-based fallback will not work (Azure Trusted Signing should cover signing; choco is only a fallback)"
    $warning++
}

# ── (6) _work directory access ────────────────────────────────────────────
Write-Host ""
Write-Host "[6] Runner _work directory access" -ForegroundColor Cyan
if (Test-Path $workDir) {
    Write-Check '✓' 'PASS' "_work directory exists at $workDir"
    try {
        $testFile = Join-Path $workDir ".ecan_prereq_test_$PID"
        [System.IO.File]::WriteAllText($testFile, "test")
        Remove-Item $testFile -Force
        Write-Check '✓' 'PASS' "Service account can write to _work"
    } catch {
        Write-Check '✗' 'FAIL' "Service account cannot write to _work: $($_.Exception.Message). Fix: run apply-work-acl-fix.ps1 from build_system/scripts/runner/"
        $critical++
    }
} else {
    Write-Check '!' 'WARN' "_work dir not found yet (normal before first job); will be created at $workDir"
}

# ── (7) GitHub Actions runner service ─────────────────────────────────────
Write-Host ""
Write-Host "[7] GitHub Actions runner service" -ForegroundColor Cyan
$svcName = 'actions.runner.*'
$svc = Get-Service -Name $svcName -ErrorAction SilentlyContinue | Select-Object -First 1
if ($svc) {
    $status = $svc.Status
    if ($status -eq 'Running') {
        Write-Check '✓' 'PASS' "Service '$($svc.Name)' is Running"
    } else {
        Write-Check '✗' 'FAIL' "Service '$($svc.Name)' is $status (not Running). Fix: restart with C:\actions-runner\svc.cmd start"
        $critical++
    }
} else {
    Write-Check '!' 'WARN' "No runner service found matching '$svcName'"
}

# ── Summary ────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
if ($critical -gt 0) {
    Write-Host "RESULT: $critical critical issue(s), $warning warning(s)" -ForegroundColor Red
    Write-Host ""
    Write-Host "Run 'setup-prerequisites.ps1' to apply fixes automatically," -ForegroundColor Yellow
    Write-Host "or follow the remediation instructions above per check." -ForegroundColor Yellow
    Write-Host ""
    exit 1
} elseif ($warning -gt 0) {
    Write-Host "RESULT: 0 critical, $warning warning(s) — build should succeed" -ForegroundColor Yellow
    exit 2
} else {
    Write-Host "RESULT: All checks passed — runner is ready" -ForegroundColor Green
    exit 0
}
