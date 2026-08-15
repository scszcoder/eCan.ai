# register_runner.ps1 — Register/refresh a GitHub Actions self-hosted runner for eCan.ai
#
# Supports:  Windows (x64)
# Behavior:  Detects arch, downloads actions/runner release zip,
#            configures with --unattended + --replace, installs the
#            Windows service, and verifies the labels via GitHub REST API.
#
# Usage:
#   .\register_runner.ps1 -Token "ABC123..."
#
#   # OR pass token via env var to keep it out of process list:
#   $env:RUNNER_TOKEN="ABC123..." ; .\register_runner.ps1
#
# Required env (or you'll be prompted):
#   GITHUB_OWNER      — e.g. "liuqiang"
#   GITHUB_REPO       — e.g. "eCan.ai"
#   RUNNER_NAME       — display name (default: $env:COMPUTERNAME)
#
# The registration token is *one-shot* and valid for ~1 hour. Generate it from:
#   gh api -X POST /repos/$OWNER/$REPO/actions/runners/registration-token --jq '.token'
# Or: GitHub UI → Settings → Actions → Runners → "New self-hosted runner"

[CmdletBinding()]
param(
    [string]$Token = "",         # registration token; falls back to $env:RUNNER_TOKEN
    [string]$RunnerVersion = "2.336.0"
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
function Log($msg) { Write-Host "[register] $msg" -ForegroundColor Cyan }
function Warn($msg) { Write-Host "[warn] $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "[fail] $msg" -ForegroundColor Red; exit 1 }

# ---------------------------------------------------------------------------
# Resolve token
# ---------------------------------------------------------------------------
if (-not $Token -and $env:RUNNER_TOKEN) { $Token = $env:RUNNER_TOKEN }
if (-not $Token) {
    Fail "no token provided. Pass -Token <value> or set `$env:RUNNER_TOKEN"
}

# ---------------------------------------------------------------------------
# Resolve owner/repo
# ---------------------------------------------------------------------------
$owner = $env:GITHUB_OWNER
$repo  = $env:GITHUB_REPO

if (-not $owner -or -not $repo) {
    try {
        $ghRepo = & gh repo view --json owner,name 2>$null | ConvertFrom-Json
        if ($ghRepo) {
            $owner = $ghRepo.owner.login
            $repo  = $ghRepo.name
        }
    } catch {}
}

if (-not $owner -or -not $repo) {
    $owner = Read-Host "GitHub owner (e.g. liuqiang)"
    $repo  = Read-Host "GitHub repo  (e.g. eCan.ai)"
}

$repoUrl = "https://github.com/$owner/$repo"
Log "Repo URL: $repoUrl"

# ---------------------------------------------------------------------------
# Detect arch
# ---------------------------------------------------------------------------
switch ($env:PROCESSOR_ARCHITECTURE) {
    "AMD64" { $arch = "x64" }
    "ARM64" { $arch = "arm64" }
    default { Fail "unsupported arch: $($env:PROCESSOR_ARCHITECTURE)" }
}

$runnerName = $env:RUNNER_NAME
if (-not $runnerName) { $runnerName = $env:COMPUTERNAME }

# Labels are frozen by .github/workflows/release.yml matrix.
$labels = "self-hosted,windows,$arch,ecan-build"
Log "Detected: Windows $arch"
Log "Labels:   $labels"
Log "Runner:   $runnerName"

# ---------------------------------------------------------------------------
# Determine runner dir + zip name
# ---------------------------------------------------------------------------
$runnerDir = if ($env:RUNNER_DIR) { $env:RUNNER_DIR } else { Join-Path $env:USERPROFILE "actions-runner" }
if (-not (Test-Path $runnerDir)) {
    Log "Creating runner directory: $runnerDir"
    New-Item -ItemType Directory -Path $runnerDir -Force | Out-Null
}

$pkg = "actions-runner-win-$arch-$RunnerVersion.zip"

# ---------------------------------------------------------------------------
# Download / extract if config.cmd missing
# ---------------------------------------------------------------------------
Push-Location $runnerDir
try {
    if (-not (Test-Path ".\config.cmd")) {
        $dlUrl  = "https://github.com/actions/runner/releases/download/v$RunnerVersion/$pkg"
        $zipPath = Join-Path $runnerDir $pkg
        Log "Downloading actions-runner v$RunnerVersion"
        if (-not (Test-Path $zipPath)) {
            try {
                Invoke-WebRequest -Uri $dlUrl -OutFile $zipPath -UseBasicParsing
            } catch {
                Fail "download failed ($dlUrl). Check version at https://github.com/actions/runner/releases"
            }
        }
        Log "Extracting $pkg"
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [System.IO.Compression.ZipFile]::ExtractToDirectory($zipPath, $runnerDir)
        Remove-Item $zipPath -Force
    } else {
        Log "Existing runner found at $runnerDir (skipping download)"
    }

    # -----------------------------------------------------------------------  
    # Stop + remove existing service (if any) so --replace can update labels  
    # -----------------------------------------------------------------------  
    if (Test-Path ".\svc.cmd") {
        try { & .\svc.cmd stop } catch { Warn "svc stop: $_" }
        try { & .\svc.cmd uninstall } catch { Warn "svc uninstall: $_" }
    }

    # -----------------------------------------------------------------------  
    # Configure (unattended, replace)  
    # Note: --replace retains runner id, updates labels.  
    # -----------------------------------------------------------------------  
    Log "Configuring runner (--unattended --replace)"
    & .\config.cmd --unattended --replace `
        --url $repoUrl `
        --token $Token `
        --name $runnerName `
        --labels $labels `
        --work "_work" `
        --runasservice

    if ($LASTEXITCODE -ne 0) { Fail "config.cmd exited with $LASTEXITCODE" }

    # -----------------------------------------------------------------------  
    # Install + start Windows service  
    # -----------------------------------------------------------------------  
    Log "Installing runner as a Windows service"
    & .\svc.cmd install
    & .\svc.cmd start
    Start-Sleep -Seconds 3
    & .\svc.cmd status

    # -----------------------------------------------------------------------  
    # Post-install self-check: probe service account, _work writability
    # Catches "Access to the path ... is denied" (eCan §IX) before the next
    # job catches it. The diagnose script is a sibling of this file.
    # -----------------------------------------------------------------------  
    $selfScript  = $PSCommandPath
    $siblingDir  = if ($selfScript) { Split-Path -Parent $selfScript } else { $runnerDir }
    $diagScript  = Join-Path $siblingDir 'diagnose-work-acl.ps1'
    $fixScript   = Join-Path $siblingDir 'apply-work-acl-fix.ps1'

    if (Test-Path $diagScript) {
        Log "Running post-install diagnose (service account + _work ACL)..."
        try {
            & powershell -NoProfile -ExecutionPolicy Bypass -File $diagScript
            # Diagnose exits non-zero (2 = service not running, 3 = ACL deny)
            # when something downstream of registration is wrong.
            if ($LASTEXITCODE -ne 0) {
                # Only auto-fix exit=3 (ACL deny). Exit=2 means service isn't
                # running yet — start it instead of touching ACL.
                if ($LASTEXITCODE -eq 3 -and (Test-Path $fixScript)) {
                    Warn "diagnose reported ACL deny (exit 3). Running apply-work-acl-fix.ps1 automatically..."
                    try {
                        # Pipe "y" so the fix script's interactive confirm is satisfied
                        # for non-interactive CI use. Forward -RunnerDir so the fix
                        # script operates on the same path the diagnose just probed.
                        "y" | & powershell -NoProfile -ExecutionPolicy Bypass -File $fixScript -RunnerDir $runnerDir
                        if ($LASTEXITCODE -ne 0) {
                            Fail "apply-work-acl-fix.ps1 exited with $LASTEXITCODE. Service account may still be denied. Check volume-level policies (EFS, GPO)."
                        }
                        Log "ACL fix applied. Re-running diagnose to confirm..."
                        & powershell -NoProfile -ExecutionPolicy Bypass -File $diagScript | Out-Null
                        if ($LASTEXITCODE -ne 0) {
                            Fail "diagnose STILL fails (exit $LASTEXITCODE) after fix. Manual investigation required."
                        }
                    } catch {
                        Fail "apply-work-acl-fix.ps1 threw: $_"
                    }
                } elseif ($LASTEXITCODE -eq 2) {
                    Fail "service is not running (exit 2). Start with: Start-Service '$runnerName'"
                } else {
                    Warn "diagnose-work-acl.ps1 exited with $LASTEXITCODE. The runner is up, but the next job may hit 'Access to the path ... is denied'. Run apply-work-acl-fix.ps1 next."
                }
            }
        } catch {
            Warn "diagnose-work-acl.ps1 failed to launch: $_"
        }
    } else {
        Warn "diagnose-work-acl.ps1 not found at $diagScript — skipped. A freshly installed runner may still hit Access Deny on its first job; install the diagnose+fix pair before the next CI run."
    }

    # -----------------------------------------------------------------------  
    # Verify labels via GitHub REST API  
    # -----------------------------------------------------------------------  
    Log "Verifying labels via GitHub API..."
    try {
        $headers = @{}
        try {
            $ghTok = & gh auth token 2>$null
            if ($ghTok) { $headers["Authorization"] = "Bearer $ghTok" }
        } catch {}

        $api = "https://api.github.com/repos/$owner/$repo/actions/runners"
        $resp = Invoke-RestMethod -Uri $api -Headers $headers -Method Get
        $match = $resp.runners | Where-Object { $_.name -eq $runnerName } | Select-Object -First 1

        if (-not $match) {
            Warn "runner '$runnerName' not found in API response. Check UI manually."
        } else {
            $actual   = @($match.labels | ForEach-Object { $_.name })
            $expected = $labels -split ","
            $missing  = @($expected | Where-Object { $actual -notcontains $_ })

            Write-Host ""
            Write-Host "  Found: $($match.name)  (status=$($match.status), busy=$($match.busy))" -ForegroundColor Green
            Write-Host "    OS=$($match.os)  arch=$($match.architecture)"
            Write-Host "    Labels ($($actual.Count)): $($actual -join ', ')"
            if ($missing.Count -gt 0) {
                Write-Host "  MISSING required labels: $($missing -join ', ')" -ForegroundColor Red
                exit 3
            } else {
                Write-Host "  All required labels present: $($expected -join ', ')" -ForegroundColor Green
            }
        }
    } catch {
        Warn "could not query GitHub API to verify labels: $_"
    }
} finally {
    Pop-Location
}

@"
────────────────────────────────────────────────────────────────────────────
Done.

  Runner name : $runnerName
  Repo        : $repoUrl
  Labels      : $labels
  Next step   : In the 'Run workflow' UI, pick
                runner_group = ecan-windows-$arch
                (e.g. ecan-windows-x64)

  Service     : Get-Service "actions.runner.$($owner)-$($repo).$runnerName"
────────────────────────────────────────────────────────────────────────────
"@
