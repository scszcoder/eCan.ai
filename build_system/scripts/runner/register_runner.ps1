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
# Resolve token — DEFERRABLE
# The token is only required if this is a FRESH registration
# ($runnerDir\.runner doesn't exist). For a re-registration of an
# already-configured runner, the existing `.runner` file carries
# agentId/agentName/serverUrl/gitHubUrl, and the `config.cmd --replace`
# step that consumes the token is skipped. The token check is deferred
# to AFTER the already-registered detection runs (see `.runner`
# probe in the main try-block below). A -Token flag always forces
# full re-register; missing flag + present .runner = refresh path.
# ---------------------------------------------------------------------------
if (-not $Token -and $env:RUNNER_TOKEN) { $Token = $env:RUNNER_TOKEN }
# NOTE: no immediate Fail on missing token here. The check happens
# inside the try-block after probing for .\config.cmd / .\.runner.
# Helper below is for clarity; the actual fail lives near
# config.cmd --replace so re-runs that hit the early-exit
# "already-registered" branch don't trip on a missing token.
function Require-Token {
    if (-not $Token) {
        Fail "no token provided. Pass -Token <value> or set `$env:RUNNER_TOKEN. (If you are RE-registering an existing runner, you may have been auto-skipped — but token is still required because config.cmd --replace was selected. Run with -Token to force re-register, or pre-flight via setup-prerequisites.ps1 alone if you just want to apply environment drift fixes.)"
    }
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
# Pre-flight: bash.exe must be reachable on PATH
# ---------------------------------------------------------------------------
# release-cn.yml's Validate Gitee credentials / Prepare Gitee credential
# helper / Checkout from Gitee mirror steps all use `shell: bash` (commit
# fd0ed0c0). They run on this self-hosted runner. If bash.exe is not on
# PATH (Git for Windows not installed, or installed but not in PATH),
# those steps fail with the opaque error:
#
#   ##[error]bash: command not found
#
# — masking the very symptom the steps were added to surface. Check now,
# before installing the service, with a clear remediation pointer.
# ---------------------------------------------------------------------------
$bash = $null
$bashProbe = $null
try {
    $bash = (Get-Command bash.exe -ErrorAction Stop).Source
} catch {
    $bashProbe = $_.Exception.Message
}

if (-not $bash) {
    Write-Host ""
    Write-Host "  MISSING bash on PATH (release-cn.yml requires shell: bash)" -ForegroundColor Red
    Write-Host "    Probe: $bashProbe" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Remediation:" -ForegroundColor Yellow
    Write-Host "    1. Install Git for Windows (https://git-scm.com/download/win)" -ForegroundColor Yellow
    Write-Host "    2. Add 'C:\Program Files\Git\bin' (or your install path) to PATH" -ForegroundColor Yellow
    Write-Host "    3. Open a new shell and verify: bash --version" -ForegroundColor Yellow
    Write-Host "    4. Re-run this script" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Exit code 4 = bash missing (distinct from 1=arg, 2=service, 3=labels)" -ForegroundColor Yellow
    exit 4
}

# Probe bash actually runs and reports a version. Some packaged bash
# shims exist on PATH but exit 0 with no output (e.g. msys2 PATH ordering
# puts a stub first). Verify the real thing.
$bashVersion = $null
try {
    $bashVersion = (& bash --version 2>&1 | Select-Object -First 1).Trim()
} catch {
    $bashVersion = $null
}

if (-not $bashVersion) {
    Write-Host "  bash found at $bash but did not respond to --version" -ForegroundColor Red
    Write-Host "  This usually means a stub on PATH is shadowing Git Bash. Reorder PATH so 'C:\Program Files\Git\bin' precedes any msys2 / cygwin / chocolatey entries." -ForegroundColor Yellow
    exit 4
}

Log "bash:    $bash"
Log "bash:    $bashVersion"

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
    #
    # Skip-token path: if `$runnerDir\.runner` already exists from a
    # previous run, the runner is already registered with the GitHub
    # backend (agentId, agentName, etc. are persisted in `.runner`).
    # We validate the existing `.runner` (agentName matches
    # `$runnerName`, gitHubUrl matches `$repoUrl`) and skip
    # `config.cmd --replace`, which is what consumes the token.
    # This makes re-running `register_runner.ps1` without a token
    # safe and idempotent: it just refreshes the service state,
    # applies setup drift fixes (via setup-prerequisites.ps1), and
    # verifies labels. To FORCE a full re-register (e.g. you changed
    # RUNNER_NAME), pass -Token; that re-runs config.cmd --replace.
    # -----------------------------------------------------------------------  
    $runnerStateFile = Join-Path $runnerDir '.runner'
    $alreadyRegistered = $false
    if (Test-Path $runnerStateFile) {
        try {
            $runnerState = Get-Content $runnerStateFile -Raw | ConvertFrom-Json -ErrorAction Stop
            $nameMatches = ($runnerState.agentName -eq $runnerName)
            $urlMatches  = ($runnerState.gitHubUrl -eq $repoUrl)
            if ($nameMatches -and $urlMatches) {
                $alreadyRegistered = $true
                Log "Detected already-registered runner at $runnerStateFile"
                Log "  agentName=$($runnerState.agentName)  agentId=$($runnerState.agentId)"
                Log "  gitHubUrl=$($runnerState.gitHubUrl)  poolName=$($runnerState.poolName)"
                if (-not $Token) {
                    Log "No token provided, but runner is already registered — proceeding in refresh mode (no config.cmd --replace, no token needed)"
                } else {
                    Log "Token provided AND runner already registered — proceeding in refresh mode (token ignored; pass -NoReplace via future flag to force re-register)"
                }
            } else {
                $reason = if (-not $nameMatches) {
                    "agentName mismatch: existing=$($runnerState.agentName), requested=$runnerName"
                } else {
                    "gitHubUrl mismatch: existing=$($runnerState.gitHubUrl), requested=$repoUrl"
                }
                Fail "Existing `.runner` at $runnerStateFile says $reason. To change runner name or repo, first unregister with `.\config.cmd remove --token <removal-token>`, delete $runnerStateFile, then re-run register_runner.ps1 with -Token <fresh-token>."
            }
        } catch {
            Fail "Cannot parse existing `.runner` at $runnerStateFile ($_). Delete the file (it will be regenerated by config.cmd --replace) and re-run with -Token <fresh-token>."
        }
    }

    if (-not $alreadyRegistered) {
        # Fresh registration path — requires a registration token
        Require-Token
        Log "Configuring runner (--unattended --replace)"
        & .\config.cmd --unattended --replace `
            --url $repoUrl `
            --token $Token `
            --name $runnerName `
            --labels $labels `
            --work "_work" `
            --runasservice

        if ($LASTEXITCODE -ne 0) { Fail "config.cmd exited with $LASTEXITCODE" }
        Log "Runner newly registered (config.cmd --replace wrote .runner with agentId)"
    } else {
        # Refresh path — labels were specified by the operator at the
        # most recent registration. config.cmd --replace only matters
        # when labels or other settings genuinely changed; we don't
        # invoke it here because we cannot do so without a token, and
        # a re-run should not require generating a new registration
        # token. If label drift is the goal, the operator can run:
        #   .\config.cmd --replace --url $repoUrl --token <token> --name $runnerName --labels <new-labels>
        # separately. The API verify step below catches label drift
        # anyway.
        Log "Skipping config.cmd --replace (refresh mode)"
    }

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

    # -----------------------------------------------------------------------  
    # Operator-side baseline setup — DELEGATED to setup-prerequisites.ps1.
    # This script does NOT re-implement setup logic; two copies would
    # drift. setup-prerequisites.ps1 is the single source of truth,
    # callable standalone (operator runs it directly to fix drift
    # between CI runs) or via this script. It is idempotent:
    # re-running on a healthy runner exits 0 with
    # SETUP_RESULT=CHANGES_SKIPPED. It needs no token. The runner
    # service restart is also delegated (step 6 of the setup script).
    # -----------------------------------------------------------------------  
    $siblingSetup = Join-Path (Split-Path -Parent $PSCommandPath) 'setup-prerequisites.ps1'
    if (-not (Test-Path $siblingSetup)) {
        # Fallback: setup-prerequisites.ps1 may live next to svc.cmd
        # (the runner home dir) if this script was copied alongside
        # the runner package.
        $siblingSetup = Join-Path $runnerDir 'setup-prerequisites.ps1'
    }
    if (Test-Path $siblingSetup) {
        # Inherit tokens: GITHUB_OWNER, GITHUB_REPO, RUNNER_NAME,
        # RUNNER_DIR — already set above; re-export so the child
        # script sees them via $env:. -ForceRestart so the service
        # always re-reads env on its next start (setup may also be
        # a CHANGES_SKIPPED no-op and we still want restart after
        # any drift-fix).
        $env:GITHUB_OWNER = $owner
        $env:GITHUB_REPO  = $repo
        $env:RUNNER_NAME  = $runnerName
        $env:RUNNER_DIR   = $runnerDir
        & powershell -NoProfile -ExecutionPolicy Bypass -File $siblingSetup -ForceRestart
        if ($LASTEXITCODE -ne 0) {
            Fail "setup-prerequisites.ps1 exited with code $LASTEXITCODE. Run setup-prerequisites.ps1 directly to see the [FAIL] message and diagnose. After fixing, re-run register_runner.ps1 (no token needed for an already-registered runner — see `Detected already-registered` log above)."
        }
        Log "Baseline setup completed (see [OK] / [WARN] / [FAIL] lines from setup-prerequisites.ps1)"
    } else {
        Warn "setup-prerequisites.ps1 not found next to this script ($siblingSetup). The operator-side baseline checks (ExecutionPolicy, Git Bash, pwsh, Chocolatey, _work ACL) were NOT applied. Download build_system/scripts/runner/setup-prerequisites.ps1 from the repo and run it manually before the next CI job."
    }

    # -----------------------------------------------------------------------
    # Pre-warm ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE. The runner ≥2.319
    # serves action archives from a local directory if that directory
    # is set via .env. Without this, every job re-downloads actions
    # from codeload.github.com, which on a shared-egress self-hosted
    # runner IP gets 429'd once release-cn.yml declares the same
    # action (e.g. actions/cache@v5) in multiple concurrent jobs.
    #
    # The warm script:
    #   - Resolves tag→SHA via api.github.com
    #   - Downloads codeload.github.com zipball once per action
    #   - Writes ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE to <runnerDir>\.env
    #   - Restarts the runner service so .env takes effect
    #
    # Re-running warm-actions-cache.ps1 is safe — already-cached SHAs
    # are skipped (no network call). Errors here are non-fatal: the
    # runner will still work; jobs will just download actions the
    # normal way and may hit the 429.
    # -----------------------------------------------------------------------
    $siblingWarm = Join-Path (Split-Path -Parent $PSCommandPath) 'warm-actions-cache.ps1'
    if (Test-Path $siblingWarm) {
        Log "Pre-warming ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE..."
        try {
            & powershell -NoProfile -ExecutionPolicy Bypass -File $siblingWarm
            if ($LASTEXITCODE -ne 0) {
                Warn "warm-actions-cache.ps1 exited with code $LASTEXITCODE. The runner will still register; the next CI job may hit 429 until you run warm-actions-cache.ps1 manually (see build_system/scripts/runner/warm-actions-cache.ps1)."
            } else {
                Log "Action archive cache warmed (see [OK]/[WARN] lines from warm-actions-cache.ps1)"
            }
        } catch {
            Warn "warm-actions-cache.ps1 threw: $_. The runner will still register; run it manually before the next CI job."
        }
    } else {
        Info "warm-actions-cache.ps1 not found at $siblingWarm — skipping action archive warm-up. The runner will download actions from codeload.github.com on each job; this can hit 429 on shared-egress IPs. Download build_system/scripts/runner/warm-actions-cache.ps1 and run it before the next CI job."
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
