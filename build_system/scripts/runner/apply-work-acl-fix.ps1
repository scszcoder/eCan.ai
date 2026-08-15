# apply-work-acl-fix.ps1 — Apply the standard self-hosted runner ACL fix
# after `diagnose-work-acl.ps1` reports a deny.
#
# What it does:
#   1. Re-enable permission inheritance on <RUNNER_DIR> and <RUNNER_DIR>\_work
#      (recursively). This undoes the typical failure mode where some past
#      process locked down inheritance.
#   2. Grant Full Control on both, recursively, to the Windows account that
#      the runner service runs as (LocalSystem by default).
#   3. Verify the grant by re-running the probe write.
#
# This script WRITES filesystem ACLs. Review carefully before running.
#
# Usage:
#   .\apply-work-acl-fix.ps1                                  # defaults: %USERPROFILE%\actions-runner, LocalSystem
#   .\apply-work-acl-fix.ps1 -RunnerDir D:\agents
#   .\apply-work-acl-fix.ps1 -ServiceAccount "DOMAIN\svc-actions"
#
# Requires Administrator.

[CmdletBinding()]
param(
    [string]$RunnerDir      = "$env:USERPROFILE\actions-runner",
    [string]$ServiceAccount = "NT AUTHORITY\SYSTEM"
)

$ErrorActionPreference = "Stop"

function Log($msg) { Write-Host "[fix] $msg" -ForegroundColor Cyan }
function Warn($msg){ Write-Host "[warn] $msg" -ForegroundColor Yellow }
function Fail($msg){ Write-Host "[fail] $msg" -ForegroundColor Red; exit 99 }

# preflight
$cur = [Security.Principal.WindowsIdentity]::GetCurrent()
$prin = New-Object Security.Principal.WindowsPrincipal($cur)
if (-not $prin.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Fail "must run as Administrator."
}
if (-not (Test-Path $RunnerDir)) {
    Fail "runner dir not found: $RunnerDir. Has register_runner.ps1 been run here?"
}
$workRoot = Join-Path $RunnerDir "_work"

Write-Host ""
Log "This script will modify ACLs on:"
Log "  - $RunnerDir"
Log "  - $workRoot"
Log "granting Full Control (recursive) to: $ServiceAccount"
$ans = Read-Host "Proceed? [y/N]"
if ($ans -notmatch '^[Yy]') { Fail "aborted by user." }

# --- 1. enable inheritance (recursive) ---
Log "step 1/3 — enabling permission inheritance..."
foreach ($p in @($RunnerDir, $workRoot)) {
    if (-not (Test-Path $p)) { continue }
    $cmd = "icacls `"$p`" /inheritance:e /T /C"
    Log "  $cmd"
    cmd.exe /c $cmd | Out-Null
}

# --- 2. grant explicit Full Control ---
Log "step 2/3 — granting Full Control to $ServiceAccount..."
foreach ($p in @($RunnerDir, $workRoot)) {
    if (-not (Test-Path $p)) { continue }
    $cmd = "icacls `"$p`" /grant `"$ServiceAccount`":(OI)(CI)F /T /C"
    Log "  $cmd"
    cmd.exe /c $cmd | Out-Null
}

# --- 3. probe ---
Log "step 3/3 — probe write..."
$probe = Join-Path $workRoot ".acl-probe-$PID.tmp"
try {
    [IO.File]::WriteAllText($probe, "post-fix probe")
    Remove-Item $probe -Force
    Log "  ✅ write OK. Service account should now succeed at job time."
} catch {
    Warn "  ❌ write STILL fails: $($_.Exception.Message)"
    Warn "     the deny may come from a parent volume (e.g. D:\ protected by EFS,"
    Warn "     or a GPO-enforced Deny). Investigate at the volume level."
    exit 1
}

Write-Host ""
Log "done. Re-run your workflow."
exit 0
