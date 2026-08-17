# warm-actions-cache.ps1 — Pre-populate the GitHub Actions runner's
# ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE so future jobs skip the
# codeload.github.com download (which is subject to per-IP secondary
# rate limiting on self-hosted runners).
#
# Background — see .github/workflows/README §"429 限流" and the
# commit message of this script's introduction.
#
# On a shared-egress self-hosted runner (e.g. behind office NAT),
# codeload.github.com anonymous downloads are subject to GitHub's
# secondary rate limit. When release-cn.yml declares the same action
# (e.g. actions/cache@v5) in 4 jobs and several run concurrently,
# the runner's source IP gets 429'd:
#
#     Warning: Failed to download action
#     'https://codeload.github.com/actions/cache/zip/<SHA>'.
#     Error: Response status code does not indicate success: 429
#
# Runner ≥2.319 supports ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE:
# when set, the runner looks for cached action archives under
# that directory first, and skips the network round-trip when
# found. The GitHub-hosted runners use this same mechanism
# internally (see actions/runner#2857).
#
# This script:
#   1. Resolves each tag→SHA via the GitHub REST API (anonymous,
#      which is fine for public actions like `actions/*`).
#   2. Downloads the codeload.github.com zipball for the SHA.
#   3. Saves it to <root>\<owner_repo>\<SHA>.zip with the runner's
#      naming convention (underscore-joined owner_repo).
#   4. Writes ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE=<root> to the
#      runner's .env file so the service picks it up after restart.
#   5. Restarts the runner service.
#
# The script is idempotent — re-runs only download missing SHAs.
# Already-cached SHAs are skipped (no network call).
#
# Required:
#   - Administrator PowerShell (so we can write .env + restart svc).
#   - Network access to api.github.com + codeload.github.com.
#
# Optional:
#   - GITHUB_TOKEN env var: if set, passed as Bearer to lift the
#     anonymous 60/hour API rate limit. The codeload zipball download
#     is anonymous regardless of token.
#
# Usage:
#   .\warm-actions-cache.ps1                         # warm default set
#   .\warm-actions-cache.ps1 -Actions @{owner='foo'; repo='bar'; tag='v1'}  # custom set
#   .\warm-actions-cache.ps1 -CacheRoot D:\action-cache
#   .\warm-actions-cache.ps1 -Check                  # dry-run (no download, no restart)
#   .\warm-actions-cache.ps1 -SkipServiceRestart     # write .env but don't restart
#
[CmdletBinding()]
param(
    # Where to put the action archives. Defaults to
    # <runnerDir>\action-archive-cache (sibling of _work, same drive).
    [string]$CacheRoot,

    # The runner install directory. Defaults to $env:RUNNER_DIR or
    # $env:USERPROFILE\actions-runner.
    [string]$RunnerDir,

    # What to warm. Each entry is @{owner='...'; repo='...'; tag='...'; alias='...'_repo}
    # `alias` defaults to "<owner>_<repo>" (the runner's directory naming).
    # Pinned to the versions eCan.ai release-{cn,intl}.yml currently
    # references — see Grep result that produced this list.
    [hashtable[]]$Actions = @(
        @{ owner = 'actions';           repo = 'checkout';         tag = 'v6' },
        @{ owner = 'actions';           repo = 'cache';            tag = 'v5' },
        @{ owner = 'actions';           repo = 'setup-node';       tag = 'v6' },
        @{ owner = 'actions';           repo = 'setup-python';     tag = 'v6' },
        @{ owner = 'actions';           repo = 'upload-artifact';  tag = 'v6' },
        @{ owner = 'actions';           repo = 'download-artifact';tag = 'v7' }
    ),

    # Dry-run mode (no downloads, no .env mutation, no restart).
    [switch]$Check,

    # Write .env but skip svc.cmd stop/start. Useful for operators
    # who want to schedule the restart themselves.
    [switch]$SkipServiceRestart
)

$ErrorActionPreference = 'Stop'

# ── Resolve paths ────────────────────────────────────────────────────────────
if (-not $RunnerDir) {
    $RunnerDir = if ($env:RUNNER_DIR) { $env:RUNNER_DIR } else { Join-Path $env:USERPROFILE 'actions-runner' }
}
if (-not (Test-Path $RunnerDir)) {
    throw "Runner directory not found at $RunnerDir. Set -RunnerDir or \$env:RUNNER_DIR."
}
$svcCmd = Join-Path $RunnerDir 'svc.cmd'
$envFile = Join-Path $RunnerDir '.env'

if (-not $CacheRoot) {
    $CacheRoot = Join-Path $RunnerDir 'action-archive-cache'
}

if ($Check) {
    Write-Host "[CHECK] dry-run — no downloads, no .env changes, no service restart" -ForegroundColor Yellow
}

function Log($msg) { Write-Host "  [OK]   $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Info($msg) { Write-Host "  [INFO] $msg" -ForegroundColor Cyan }
function Fail($msg) {
    Write-Host ""
    Write-Host "  [FAIL] $msg" -ForegroundColor Red
    Write-Host ""
    exit 1
}

# ── Header ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Warm GitHub Actions runner archive cache" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Runner dir : $RunnerDir"
Write-Host "Cache root : $CacheRoot"
Write-Host "Actions    : $($Actions.Count) entries"
if ($env:GITHUB_TOKEN) {
    Write-Host "Auth       : GITHUB_TOKEN present (sha256=$([System.BitConverter]::ToString([System.Security.Cryptography.SHA256]::Create().ComputeHash([System.Text.Encoding]::UTF8.GetBytes($env:GITHUB_TOKEN)))[0..3] -join '').ToLower())"
} else {
    Write-Host "Auth       : anonymous (60/hour API quota; fine for 6 actions)"
}
Write-Host "Mode       : $(if ($Check) { 'CHECK (dry-run)' } else { 'APPLY' })"
Write-Host ""

# ── Create cache root ────────────────────────────────────────────────────────
if (-not $Check) {
    if (-not (Test-Path $CacheRoot)) {
        Info "Creating cache root at $CacheRoot"
        New-Item -ItemType Directory -Force -Path $CacheRoot | Out-Null
    } else {
        Info "Cache root already exists at $CacheRoot"
    }
}

# ── Resolve tag→SHA via GitHub REST API ──────────────────────────────────────
# For each tag we want to cache, we need the commit SHA the runner
# will resolve at job-start. The runner resolves tags itself via
# the same API, so we mirror its lookup here. Anonymous is fine for
# public actions; if GITHUB_TOKEN is set we use it to lift the
# 60/hour anonymous quota.
function Resolve-TagToSha {
    param([string]$Owner, [string]$Repo, [string]$Tag)

    $url = "https://api.github.com/repos/$Owner/$Repo/git/refs/tags/$Tag"
    $headers = @{
        'User-Agent'      = 'eCan.ai-warm-actions-cache/1.0'
        'Accept'          = 'application/vnd.github+json'
        'X-GitHub-Api-Version' = '2022-11-28'
    }
    if ($env:GITHUB_TOKEN) {
        $headers['Authorization'] = "Bearer $env:GITHUB_TOKEN"
    }

    try {
        $resp = Invoke-RestMethod -Uri $url -Headers $headers -Method Get -TimeoutSec 30
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        if ($code -eq 403 -or $code -eq 429) {
            Fail "GitHub API rate-limited ($code) while resolving $Owner/$Repo@$Tag. Set \$env:GITHUB_TOKEN and re-run."
        }
        if ($code -eq 404) {
            Fail "Tag $Owner/$Repo@$Tag not found (404). Check the version string."
        }
        throw
    }

    # Annotated tags return object.sha pointing at a tag object;
    # the runner dereferences one level to get the commit SHA.
    # We do the same deref here.
    $tagSha = $resp.object.sha
    $tagType = $resp.object.type

    if ($tagType -eq 'tag') {
        # Annotated tag object — deref to commit.
        $derefUrl = "https://api.github.com/repos/$Owner/$Repo/git/tags/$tagSha"
        try {
            $deref = Invoke-RestMethod -Uri $derefUrl -Headers $headers -Method Get -TimeoutSec 30
            return $deref.object.sha
        } catch {
            # If the tag deref fails, fall back to the tag sha —
            # it's still valid for codeload (which serves the same
            # archive at the ref).
            Warn "Could not deref annotated tag $Owner/$Repo@$Tag ($_); using tag object sha $tagSha"
            return $tagSha
        }
    }

    # Lightweight tag — sha already points at the commit.
    return $tagSha
}

# ── Download + cache a single action's archive ──────────────────────────────
function Cache-Action {
    param(
        [string]$Owner,
        [string]$Repo,
        [string]$Tag,
        [string]$Alias
    )

    $dirName = if ($Alias) { $Alias } else { "${Owner}_${Repo}" }
    $actionDir = Join-Path $CacheRoot $dirName

    Info "Resolving $Owner/$Repo@$Tag → SHA via api.github.com"
    $sha = Resolve-TagToSha -Owner $Owner -Repo $Repo -Tag $Tag
    Write-Host "    SHA = $sha" -ForegroundColor DarkGray

    $archivePath = Join-Path $actionDir "$sha.zip"
    if (Test-Path $archivePath) {
        Log "$dirName@$Tag already cached ($archivePath)"
        return @{ Owner = $Owner; Repo = $Repo; Tag = $Tag; Sha = $sha; Cached = $true; Bytes = (Get-Item $archivePath).Length }
    }

    if ($Check) {
        Info "[CHECK] would download $Owner/$Repo@$Tag ($sha) to $archivePath"
        return @{ Owner = $Owner; Repo = $Repo; Tag = $Tag; Sha = $sha; Cached = $false; Bytes = 0 }
    }

    if (-not (Test-Path $actionDir)) {
        New-Item -ItemType Directory -Force -Path $actionDir | Out-Null
    }

    # codeload.github.com serves the repo zipball at the SHA. This
    # is exactly what the runner downloads — see runner source
    # ActionManager.cs#L1191 referenced in actions/runner#4232.
    $zipUrl = "https://codeload.github.com/$Owner/$Repo/zip/$sha"
    Write-Host "    GET $zipUrl" -ForegroundColor DarkGray

    try {
        $tmp = Join-Path $env:TEMP "ecan_action_${Owner}_${Repo}_${sha}.zip.tmp"
        Invoke-WebRequest -Uri $zipUrl -OutFile $tmp -UseBasicParsing -TimeoutSec 60
        Move-Item -Force $tmp $archivePath
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        if ($code -eq 429) {
            Fail "codeload.github.com rate-limited (429) on $Owner/$Repo@$Tag. Re-run later, or proxy through a less-shared IP."
        }
        throw
    }

    $bytes = (Get-Item $archivePath).Length
    Log "$dirName@$Tag cached ($([math]::Round($bytes / 1KB, 1)) KB)"
    return @{ Owner = $Owner; Repo = $Repo; Tag = $Tag; Sha = $sha; Cached = $true; Bytes = $bytes }
}

# ── Process each action ─────────────────────────────────────────────────────
$results = @()
foreach ($a in $Actions) {
    $result = Cache-Action -Owner $a.owner -Repo $a.repo -Tag $a.tag -Alias $a.alias
    $results += $result
}

# ── Write ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE to .env ────────────────────────
# The runner reads .env at startup. Setting the variable here and
# restarting the service is what makes the cache active for the
# next job. Existing .env lines are preserved (we only touch
# ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE).
$envLineKey = 'ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE'
$envLineValue = $CacheRoot
$envLineFull = "$envLineKey=$envLineValue"

if ($Check) {
    Info "[CHECK] would write to $envFile: $envLineFull"
    Info "[CHECK] would restart runner service (svc.cmd stop && start)"
} else {
    if (Test-Path $envFile) {
        $existing = Get-Content $envFile -Raw -Encoding UTF8
        # Replace existing ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE line if present
        $pattern = "^[\s#]*$envLineKey=.*$"
        if ($existing -match "(?m)$pattern") {
            $new = ($existing -split "`n" | Where-Object { $_ -notmatch "(?m)$pattern" }) + $envLineFull
            $new -join "`n" | Set-Content -Path $envFile -Encoding UTF8 -NoNewline
            Log "Updated $envLineKey in existing $envFile"
        } else {
            Add-Content -Path $envFile -Value $envLineFull -Encoding UTF8
            Log "Appended $envLineKey to existing $envFile"
        }
    } else {
        Set-Content -Path $envFile -Value $envLineFull -Encoding UTF8
        Log "Created $envFile with $envLineKey=$envLineValue"
    }
}

# ── Restart the runner service so .env is picked up ──────────────────────────
# .env is read by the runner listener at startup. Until we restart,
# jobs continue to use the in-memory env which doesn't have our var.
if (-not $Check -and -not $SkipServiceRestart) {
    if (Test-Path $svcCmd) {
        Info "Stopping runner service..."
        try { & $svcCmd stop | Out-Null } catch { Warn "svc.cmd stop threw: $_" }
        Start-Sleep -Seconds 2
        Info "Starting runner service..."
        try {
            & $svcCmd start | Out-Null
            Start-Sleep -Seconds 3
            & $svcCmd status | Out-Null
            Log "Runner service restarted (.env now in effect)"
        } catch {
            Fail "Could not restart service: $_. Restart manually: $svcCmd stop && $svcCmd start"
        }
    } else {
        Warn "svc.cmd not found at $svcCmd — restart the runner manually to pick up .env"
    }
} elseif ($SkipServiceRestart) {
    Info "-SkipServiceRestart set — restart the runner manually: $svcCmd stop && $svcCmd start"
}

# ── Summary ──────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
$cached = ($results | Where-Object { $_.Cached }).Count
$downloaded = ($results | Where-Object { -not $_.Cached -and $_.Bytes -gt 0 }).Count
$totalBytes = ($results | Measure-Object -Property Bytes -Sum).Sum
Write-Host "  Cached    : $cached (already on disk, skipped network)"
Write-Host "  Downloaded: $downloaded (this run)"
Write-Host "  Total size: $([math]::Round($totalBytes / 1MB, 2)) MB"
Write-Host "  Cache root: $CacheRoot"
if (-not $Check) {
    Write-Host "  .env      : $envFile (ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE set)"
}
Write-Host "============================================================" -ForegroundColor Cyan

if ($Check) {
    Write-Host ""
    Write-Host "DRY-RUN complete — re-run without -Check to apply." -ForegroundColor Yellow
}
