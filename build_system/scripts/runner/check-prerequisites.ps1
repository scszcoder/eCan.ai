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
# For automatic fix-up (where safe — never auto-installs binaries),
# run setup-prerequisites.ps1 instead.

[CmdletBinding()]
param(
    [ValidateSet('diagnose', 'strict')]
    [string]$Mode = 'diagnose'
)

$ErrorActionPreference = 'Continue'

# Load the probe helper. The previous version of this script hardcoded
# `C:\Program Files\Git\bin\bash.exe` and `C:\Program Files\PowerShell\7\pwsh.exe`
# — which produced false FAILs on runners that installed Git/pwsh to
# non-standard paths (e.g. C:\Users\<user>\opt\pwsh7\, scoop, choco-shim
# dirs). See find-prerequisites.ps1 for the candidate list.
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $scriptRoot) { $scriptRoot = $PSScriptRoot }
if ($scriptRoot -and (Test-Path (Join-Path $scriptRoot 'find-prerequisites.ps1'))) {
    . (Join-Path $scriptRoot 'find-prerequisites.ps1')
} else {
    # Inline fallback so this script still works if run from a directory
    # other than its sibling. The inline version probes the same default
    # candidates; if find-prerequisites.ps1 is missing, you lose the
    # overridable candidate list but keep the same detection logic.
    function Find-PwshLocation {
        foreach ($cand in @(
                "$env:ProgramFiles\PowerShell\7\pwsh.exe",
                "${env:ProgramFiles(x86)}\PowerShell\7\pwsh.exe",
                "$env:LOCALAPPDATA\Programs\PowerShell\7\pwsh.exe",
                "$env:USERPROFILE\opt\pwsh7\pwsh.exe",
                "$env:USERPROFILE\bin\pwsh.exe"
            )) {
            if ($cand -and (Test-Path -LiteralPath $cand)) { return $cand }
        }
        try { return (Get-Command pwsh.exe -ErrorAction Stop).Source } catch { return $null }
    }
    function Find-BashLocation {
        foreach ($cand in @(
                "$env:ProgramFiles\Git\bin\bash.exe",
                "${env:ProgramFiles(x86)}\Git\bin\bash.exe",
                "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe",
                "$env:USERPROFILE\scoop\apps\git\current\bin\bash.exe",
                "$env:ProgramData\chocolatey\bin\bash.exe"
            )) {
            if ($cand -and (Test-Path -LiteralPath $cand)) { return $cand }
        }
        try { return (Get-Command bash.exe -ErrorAction Stop).Source } catch { return $null }
    }
    # Inline fallback for Find-PythonLocation. Filters WindowsApps Store
    # placeholder so `python3` in workflow bash steps doesn't exit 126.
    function Find-PythonLocation {
        foreach ($cand in @(
                'C:\Python312\python.exe',
                "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
                "$env:USERPROFILE\scoop\apps\python\current\python.exe"
            )) {
            if ($cand -and (Test-Path -LiteralPath $cand)) { return $cand }
        }
        foreach ($exeName in @('python.exe', 'python3.exe')) {
            try {
                $src = (Get-Command $exeName -ErrorAction Stop).Source
                if ($src -and ($src -notlike '*\AppData\Local\Microsoft\WindowsApps\*')) {
                    return $src
                }
            } catch { }
        }
        return $null
    }
    function Get-PwshDir { param([string]$PwshPath) if (-not $PwshPath) { return $null } [System.IO.Path]::GetDirectoryName($PwshPath) }
    function Get-BashDir { param([string]$BashPath) if (-not $BashPath) { return $null } [System.IO.Path]::GetDirectoryName($BashPath) }
    function Get-PythonDir { param([string]$PythonPath) if (-not $PythonPath) { return $null } [System.IO.Path]::GetDirectoryName($PythonPath) }
    function Get-PwshVersion { param([string]$Path) try { (& $Path --version 2>&1 | Select-Object -First 1).ToString().Trim() } catch { $null } }
    function Get-BashVersion { param([string]$Path) try { (& $Path --version 2>&1 | Select-Object -First 1).ToString().Trim() } catch { $null } }
    function Get-PythonVersion { param([string]$Path) try { (& $Path --version 2>&1 | Select-Object -First 1).ToString().Trim() } catch { $null } }
}

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

# Default canonical install paths — used only in failure messages so the
# operator knows the recommended install location.
$pwshBinHint = 'C:\Program Files\PowerShell\7\pwsh.exe'
$gitBashHint = 'C:\Program Files\Git\bin\bash.exe'
$pythonBinHint = 'C:\Python312\python.exe'

# Probe at runtime, do not assume a path.
$pwshBin    = Find-PwshLocation
$gitBashBin = Find-BashLocation
$pythonBin  = Find-PythonLocation
$pwshDir    = Get-PwshDir    -PwshPath $pwshBin
$gitBashDir = Get-BashDir    -BashPath $gitBashBin
$pythonDir  = Get-PythonDir  -PythonPath $pythonBin

$innoIscc    = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'
$chocoBin    = 'C:\ProgramData\chocolatey\bin\choco.exe'
$runnerDir   = if ($env:RUNNER_DIR) { $env:RUNNER_DIR } else { Join-Path $env:USERPROFILE 'actions-runner' }
$workDir     = Join-Path $runnerDir '_work'

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
if ($gitBashBin) {
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
    Write-Check '!' 'FAIL' "Git for Windows (bash.exe) not found anywhere. Install once on the runner: https://git-scm.com/download/win (or via scoop / choco). Default install path: $gitBashHint. See docs/Windows构建环境部署清单.md §九.3.1"
    $critical++
}

# ── (2b) Git Bash on PATH (service account) ────────────────────────────────
Write-Host ""
Write-Host "[2b] Git Bash on service PATH" -ForegroundColor Cyan
$svcPath = [Environment]::GetEnvironmentVariable('Path', 'Process')
if ($gitBashDir -and $svcPath -like "*$gitBashDir*") {
    Write-Check '✓' 'PASS' "'$gitBashDir' on service PATH"
} else {
    Write-Check '✗' 'FAIL' "Git Bash dir '$gitBashDir' NOT on service PATH — `shell: bash` steps will fail with 'bash: command not found'. Fix: add the Git for Windows bin dir to SYSTEM PATH (see docs/Windows构建环境部署清单.md §九.3.1). setup-prerequisites.ps1 can apply this automatically."
    $critical++
}

# ── (3) PowerShell 7 (pwsh.exe) ────────────────────────────────────────────
Write-Host ""
Write-Host "[3] PowerShell 7 (pwsh.exe)" -ForegroundColor Cyan
if ($pwshBin) {
    Write-Check '✓' 'PASS' "Found at $pwshBin"
    try {
        $ver = (& $pwshBin --version 2>&1 | Out-String).Trim()
        Write-Check '✓' 'PASS' "Responds: $ver"
    } catch {
        Write-Check '✗' 'FAIL' "Found but does not respond to --version"
        $critical++
    }
} else {
    Write-Check '✗' 'FAIL' "PowerShell 7 (pwsh.exe) not found anywhere. Install once on the runner: https://github.com/PowerShell/PowerShell/releases/download/v7.4.6/PowerShell-7.4.6-win-x64.msi (or via winget / choco). Default install path: $pwshBinHint. See docs/Windows构建环境部署清单.md §九.3.1"
    $critical++
}

# ── (3b) PowerShell 7 on PATH (service account) ────────────────────────────
Write-Host ""
Write-Host "[3b] PowerShell 7 on service PATH" -ForegroundColor Cyan
if ($pwshDir -and $svcPath -like "*$pwshDir*") {
    Write-Check '✓' 'PASS' "'$pwshDir' on service PATH"
} else {
    Write-Check '✗' 'FAIL' "PowerShell 7 dir '$pwshDir' NOT on service PATH — bash/git sub-shell calls to pwsh will fail. Fix: add the PowerShell 7 dir to SYSTEM PATH. setup-prerequisites.ps1 can apply this automatically."
    $critical++
}

# ── (3.5) Python 3.12 (python.exe) ──────────────────────────────────────────
# Required by docs/Windows构建环境部署清单.md §一.2 and build_validator
# (rejects Python < 3.12). Find-PythonLocation filters the WindowsApps
# Store placeholder that would otherwise exit 126 on `python3` in
# release-cn.yml bash steps.
Write-Host ""
Write-Host "[3.5] Python 3.12 (python.exe)" -ForegroundColor Cyan
if ($pythonBin) {
    Write-Check '✓' 'PASS' "Found at $pythonBin"
    try {
        $ver = (& $pythonBin --version 2>&1 | Out-String).Trim()
        Write-Check '✓' 'PASS' "Responds: $ver"
    } catch {
        Write-Check '✗' 'FAIL' "Found but does not respond to --version"
        $critical++
    }
} else {
    Write-Check '✗' 'FAIL' "Python 3.12 (python.exe) not found anywhere. Install once on the runner: `choco install python --version=3.12.10 -y --installarguments=`"InstallAllUsers=1 PrependPath=1 TargetDir=C:\Python312`"` (or download https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe and check 'Add Python to PATH' on the first screen). Default install path: $pythonBinHint. See docs/Windows构建环境部署清单.md §一.2. setup-prerequisites.ps1 can apply this automatically."
    $critical++
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

# ── (4b) Python 3.12 on PATH (service account) ──────────────────────────────
# `python3` in runner bash steps still resolves to the WindowsApps Store
# stub if C:\Python312\ is not on the service PATH *before* the
# WindowsApps entry. Sym: exit 126 / Permission denied.
Write-Host ""
Write-Host "[4b] Python 3.12 on service PATH" -ForegroundColor Cyan
$pythonScriptsHint = Join-Path (Split-Path $pythonBinHint -Parent) 'Scripts'
if ($pythonDir -and $svcPath -like "*$pythonDir*") {
    Write-Check '✓' 'PASS' "'$pythonDir' on service PATH"
} else {
    Write-Check '✗' 'FAIL' "Python install dir '$pythonDir' NOT on service PATH — `python3` in bash steps will resolve to the WindowsApps Store stub and exit 126 (Permission denied). Fix: add C:\Python312\ and C:\Python312\Scripts\ to SYSTEM PATH, BEFORE the WindowsApps entry. setup-prerequisites.ps1 can apply this automatically."
    $critical++
}

# ── (5) Chocolatey ────────────────────────────────────────────────────────
Write-Host ""
Write-Host "[5] Chocolatey (choco.exe)" -ForegroundColor Cyan
$chocoFound = $null
try {
    $pathHit = Get-Command choco.exe -ErrorAction Stop
    $chocoFound = $pathHit.Source
} catch { }
if (-not $chocoFound) {
    foreach ($cand in @(
            'C:\ProgramData\chocolatey\bin\choco.exe',
            "$env:LOCALAPPDATA\Chocolatey\bin\choco.exe",
            "$env:USERPROFILE\scoop\apps\chocolatey\current\bin\choco.exe"
        )) {
        if ($cand -and (Test-Path -LiteralPath $cand)) {
            $chocoFound = $cand
            break
        }
    }
}
if ($chocoFound) {
    Write-Check '✓' 'PASS' "Found at $chocoFound"
    try {
        $ver = (& $chocoFound --version 2>&1 | Out-String).Trim()
        Write-Check '✓' 'PASS' "Version: $ver"
    } catch {
        Write-Check '!' 'WARN' "Found but choco --version failed — setup-signtool-env fallback may not work"
        $warning++
    }
} else {
    Write-Check '!' 'WARN' "Not found at $chocoBin — setup-signtool-env's choco-based fallback will not work (Azure Trusted Signing should cover signing; choco is only a fallback). Install once: https://chocolatey.org/install"
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

# ── (8) ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE (429 mitigation) ────────────────
# Pre-populated action archives let the runner serve actions from a
# local directory instead of codeload.github.com, which on a shared-
# egress self-hosted runner IP gets 429'd once multiple concurrent
# jobs declare the same action. See warm-actions-cache.ps1 for the
# warm-up flow. This check is informational (warn-only) — the
# runner still works without it, just slower on cache-cold jobs.
Write-Host ""
Write-Host "[8] ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE (429 mitigation)" -ForegroundColor Cyan
$envFile = Join-Path $runnerDir '.env'
$cacheRoot = $null
if (Test-Path $envFile) {
    $line = Get-Content $envFile -ErrorAction SilentlyContinue |
        Where-Object { $_ -match '^ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE\s*=' } |
        Select-Object -First 1
    if ($line) {
        $cacheRoot = ($line -split '=', 2)[1].Trim()
    }
}
if ($cacheRoot -and (Test-Path $cacheRoot)) {
    $archiveCount = (Get-ChildItem -Path $cacheRoot -Recurse -Filter '*.zip' -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^[0-9a-f]{40}\.zip$' }).Count
    $totalBytes = (Get-ChildItem -Path $cacheRoot -Recurse -Filter '*.zip' -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^[0-9a-f]{40}\.zip$' } |
        Measure-Object -Property Length -Sum).Sum
    $sizeMb = [math]::Round($totalBytes / 1MB, 2)
    Write-Check '✓' 'PASS' "Cache root: $cacheRoot ($archiveCount archives, $sizeMb MB)"
} elseif ($cacheRoot) {
    Write-Check '!' 'WARN' "ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE set to '$cacheRoot' but directory missing. Run warm-actions-cache.ps1 to populate."
    $warning++
} else {
    Write-Check '!' 'WARN' "ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE not set in $envFile. Jobs download actions from codeload.github.com each run; on a shared-egress self-hosted runner this can hit 429 when release-cn.yml's jobs run concurrently. Run warm-actions-cache.ps1 once to populate."
    $warning++
}

# ── Summary ────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
if ($critical -gt 0) {
    Write-Host "RESULT: $critical critical issue(s), $warning warning(s)" -ForegroundColor Red
    Write-Host ""
    Write-Host "Run 'setup-prerequisites.ps1' to apply non-install fixes (PATH," -ForegroundColor Yellow
    Write-Host "ExecutionPolicy, _work ACL). For missing binaries (pwsh, bash, choco)," -ForegroundColor Yellow
    Write-Host "install once on the runner via the links printed above." -ForegroundColor Yellow
    Write-Host ""
    exit 1
} elseif ($warning -gt 0) {
    Write-Host "RESULT: 0 critical, $warning warning(s) — build should succeed" -ForegroundColor Yellow
    exit 2
} else {
    Write-Host "RESULT: All checks passed — runner is ready" -ForegroundColor Green
    exit 0
}
