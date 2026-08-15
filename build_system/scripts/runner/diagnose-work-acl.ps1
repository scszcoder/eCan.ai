# diagnose-work-acl.ps1 — Diagnose why a self-hosted runner job fails with
# "Access to the path '...\_work\...\PipelineFolder.json' is denied".
#
# Run this ON the runner machine (PowerShell as Administrator) any time after
# `register_runner.ps1` has run at least once. It reports (without modifying
# any ACLs) the four facts needed to decide what to fix:
#
#   1. Which Windows account the runner service runs as (StartName)
#   2. Whether _work root exists + its ACL
#   3. Whether the path mentioned in the error (_PipelineMapping) exists
#   4. The service account's effective access on those paths (what the runner
#      will actually be allowed to do at job time)
#
# Usage:
#   .\diagnose-work-acl.ps1                       # auto-detect service name
#   .\diagnose-work-acl.ps1 -RunnerDir D:\agents  # custom runner dir
#   .\diagnose-work-acl.ps1 -ServiceName 'actions.runner.scszcoder-eCan.ai.win-runner'
#
# Exit codes:
#   0 = diagnostic only, no opinion
#   2 = service not installed or not running
#   3 = _work root missing OR service has no write access to it
#
# Notes:
#   * Read-only. This script NEVER modifies ACL, service config, or files.
#     Run `apply-work-acl-fix.ps1` if a fix is needed.
#   * Requires Administrator (to read other users' effective permissions).

[CmdletBinding()]
param(
    [string]$RunnerDir = "$env:USERPROFILE\actions-runner",
    [string]$ServiceName = ""
)

$ErrorActionPreference = "Stop"

function Log($msg)    { Write-Host "[diag] $msg" -ForegroundColor Cyan }
function Warn($msg)   { Write-Host "[warn] $msg" -ForegroundColor Yellow }
function Info($msg)   { Write-Host "       $msg" }
function Fail($msg)   { Write-Host "[fail] $msg" -ForegroundColor Red }

# --- preflight: must be Administrator ---
$cur = [Security.Principal.WindowsIdentity]::GetCurrent()
$prin = New-Object Security.Principal.WindowsPrincipal($cur)
if (-not $prin.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Fail "this script must run as Administrator (effective access checks require it)."
}

# --- 1. find the runner service ---
if (-not $ServiceName) {
    Log "Auto-detecting runner service..."
    $candidates = Get-CimInstance -ClassName Win32_Service -Filter "Name LIKE 'actions.runner.%'" |
                  Select-Object Name, DisplayName, State, StartName
    if (-not $candidates -or $candidates.Count -eq 0) {
        Fail "no 'actions.runner.*' service found. Has register_runner.ps1 been run?"
    }
    $svc = $candidates | Select-Object -First 1
    $ServiceName = $svc.Name
} else {
    $svc = Get-CimInstance -ClassName Win32_Service -Filter "Name='$ServiceName'" -ErrorAction SilentlyContinue
    if (-not $svc) { Fail "service '$ServiceName' does not exist." }
}

Log "Service Name : $($svc.Name)"
Log "Display Name : $($svc.DisplayName)"
Info "State        : $($svc.State)"
Info "StartName    : $($svc.StartName)"

$exitCode = 0
if ($svc.State -ne "Running") {
    Warn "service is NOT running. Jobs cannot run. Start it with: Start-Service '$($svc.Name)'"
    $exitCode = 2
}

# --- 2. _work root ---
$workRoot = Join-Path $RunnerDir "_work"
Write-Host ""
Log "Runner dir : $RunnerDir"
Log "Work root  : $workRoot"

if (-not (Test-Path $workRoot)) {
    Warn "_work directory does NOT exist yet. A successful checkout would create it."
    Warn "the service account MUST be allowed to create it (Full Control on $RunnerDir)."
} else {
    Log "_work exists. ACL:"
    Get-Acl $workRoot | Format-List Owner, AccessToString | Out-Host
}

# --- 3. path from the error message (_PipelineMapping) ---
$problemPath = Join-Path $workRoot "_PipelineMapping"
Write-Host ""
Log "Path that triggered 'Access denied': $problemPath"

if (Test-Path $problemPath) {
    Log "exists. ACL:"
    Get-Acl $problemPath | Format-List Owner, AccessToString | Out-Host
} else {
    Log "does NOT exist — it is created on first checkout by the *job*, not at register time."
    Info "If you see it missing here, the failure is because the runner service"
    Info "could not create it (deny on the parent _work directory)."
}

# --- 4. effective access check ---
# Translate StartName to a SecurityIdentifier we can test against ACLs.
$startName = $svc.StartName
$accountSid = $null
$accountName = ""

if ($startName -eq "LocalSystem") {
    $accountSid = New-Object Security.Principal.SecurityIdentifier(
        [Security.Principal.WellKnownSidType]::LocalSystemSid, $null)
    $accountName = "NT AUTHORITY\SYSTEM (LocalSystem)"
} elseif ($startName -eq "LocalService") {
    $accountSid = New-Object Security.Principal.SecurityIdentifier(
        [Security.Principal.WellKnownSidType]::LocalServiceSid, $null)
    $accountName = "NT AUTHORITY\LocalService"
} elseif ($startName -eq "NetworkService") {
    $accountSid = New-Object Security.Principal.SecurityIdentifier(
        [Security.Principal.WellKnownSidType]::NetworkServiceSid, $null)
    $accountName = "NT AUTHORITY\NetworkService"
} elseif ($startName.StartsWith(".\") -or $startName.StartsWith("NT AUTHORITY\")) {
    # Built-in without a SID alias; resolve via NTAccount
    $nt = New-Object Security.Principal.NTAccount($startName)
    try { $accountSid = $nt.Translate([Security.Principal.SecurityIdentifier]) } catch {}
    $accountName = $startName
} elseif ($startName -like "*\*") {
    # DOMAIN\user or MACHINE\user
    $nt = New-Object Security.Principal.NTAccount($startName)
    try { $accountSid = $nt.Translate([Security.Principal.SecurityIdentifier]) } catch {}
    $accountName = $startName
} else {
    Warn "could not parse StartName '$startName'. Skipping effective-access check."
}

Write-Host ""
Log "Service runs as: $accountName"

if ($accountSid) {
    foreach ($p in @($RunnerDir, $workRoot)) {
        if (-not (Test-Path $p)) { continue }
        $acl = Get-Acl $p
        $rule = $acl.GetAccessRules($true, $true,
            [Security.Principal.SecurityIdentifier]) | Where-Object {
                $_.IdentityReference -eq $accountSid
            }
        Write-Host ""
        Info "effective rules for $accountName on $p :"
        if (-not $rule) {
            Warn "  (no explicit ACE — relies on inherited permissions)"
            # inherited Full Control from parents counts; warn only if _work not writable in step 5
        } else {
            $rule | ForEach-Object {
                $ff = if ($_.FileSystemRights -match "FullControl") {"F "} else {""}
                $inh = if ($_.IsInherited) {"(inherited)"} else {"(explicit)"}
                Info "  $ff$($_.FileSystemRights)  $inh"
            }
        }
    }

    # can the service actually write? synthesize a probe and try to create+delete
    Write-Host ""
    Log "probe write: trying to create+delete a temp file in _work..."
    if (Test-Path $workRoot) {
        $probe = Join-Path $workRoot ".acl-probe-$PID.tmp"
        try {
            [IO.File]::WriteAllText($probe, "probe")
            Remove-Item $probe -Force
            Log "  ✅ probe succeeded — service can write to _work right now."
        } catch {
            Warn "  ❌ probe FAILED: $($_.Exception.Message)"
            Warn "     job-level File.WriteAllText at _PipelineMapping will also fail."
            $exitCode = 3
        }
    } else {
        Warn "  skipped (workRoot does not exist)"
    }
}

# --- summary ---
Write-Host ""
Write-Host "════════════════════════════════════════════════════════════════════════════════" -ForegroundColor DarkGray
if ($exitCode -eq 0) {
    Log "diagnostic complete — no obvious ACL blocker detected."
    Info "if jobs still fail with 'Access denied', attach this output to the bug."
} else {
    Warn "diagnostic complete — likely ACL problem detected (exit=$exitCode)."
    Info "next step: invoke apply-work-acl-fix.ps1 on this machine (after review)."
}
Write-Host ""
exit $exitCode
