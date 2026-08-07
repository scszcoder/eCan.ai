<#
.SYNOPSIS
  Pre-flight check for the Feige detection harness: is the EventMonitor actually
  live before you trust a measure.py run?

.DESCRIPTION
  Scans the recent slice of runlogs/eCan.log (default: last 5 minutes) and prints
  a one-line verdict:

    MONITOR LIVE            heartbeats are flowing -> a measure run will be valid
    MONITOR STARTING        DOM loop started but no [HB] yet -> wait a few seconds
    BUILD FAILED            startup/task build crashed -> relaunch the app
    MONITOR NOT UP          no monitor activity in the window

  The all-zeros measure runs (answered=0/detected=0/HB count=0) are ALWAYS one of
  BUILD FAILED or MONITOR NOT UP. Run this and confirm MONITOR LIVE first.

.EXAMPLE
  .\check_monitor.ps1
  .\check_monitor.ps1 -SinceMinutes 10
  .\check_monitor.ps1 -Tail          # also dump the last few relevant lines
#>
param(
    [string]$Log = (Join-Path $PSScriptRoot 'runlogs\eCan.log'),
    [int]$SinceMinutes = 5,
    [switch]$Tail
)

if (-not (Test-Path $Log)) {
    Write-Host "log not found: $Log" -ForegroundColor Red
    exit 2
}

# --- isolate the recent slice (this log accumulates across sessions) -----------
$cutoff = (Get-Date).AddMinutes(-$SinceMinutes)
$all = Get-Content -Path $Log -Encoding UTF8
$tsRe = [regex]'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),'
$startIdx = 0
for ($i = $all.Count - 1; $i -ge 0; $i--) {
    $m = $tsRe.Match($all[$i])
    if ($m.Success) {
        $ts = [datetime]::ParseExact($m.Groups[1].Value, 'yyyy-MM-dd HH:mm:ss', $null)
        if ($ts -lt $cutoff) { $startIdx = $i + 1; break }
    }
}
$recent = if ($startIdx -le $all.Count - 1) { $all[$startIdx..($all.Count - 1)] } else { @() }

function Count-Match([string]$needle) {
    if ($recent.Count -eq 0) { return 0 }
    return ($recent | Select-String -SimpleMatch -Pattern $needle).Count
}

# --- markers -------------------------------------------------------------------
$hb          = Count-Match '[EventMonitor][HB]'
$loopStarted = Count-Match 'DOM monitor loop started'
$domObserved = Count-Match 'dom_observed'
$dedicated   = Count-Match 'DEDICATED detection tab'
$buildFail   = (Count-Match 'Timeout should be used inside a task') + (Count-Match 'agent_skills is empty')
$taskMaxFail = Count-Match 'reached max failures'

Write-Host ""
Write-Host ("window      : last {0} min  (since {1:HH:mm:ss})" -f $SinceMinutes, $cutoff)
Write-Host ("heartbeats  : {0}   loop-started: {1}   dom_observed: {2}   dedicated-tab: {3}" -f $hb, $loopStarted, $domObserved, $dedicated)
Write-Host ("build-fail  : {0}   task-max-fail: {1}" -f $buildFail, $taskMaxFail)
Write-Host ""

# --- verdict -------------------------------------------------------------------
if ($hb -gt 0) {
    $note = if ($buildFail -gt 0 -or $taskMaxFail -gt 0) { " (recovered after earlier errors)" } else { "" }
    Write-Host "VERDICT: MONITOR LIVE$note  -> measure run will be valid" -ForegroundColor Green
    $code = 0
}
elseif ($buildFail -gt 0 -or $taskMaxFail -gt 0) {
    Write-Host "VERDICT: BUILD FAILED  -> relaunch the app (skill/task build crashed; monitor never bound)" -ForegroundColor Red
    $code = 1
}
elseif ($loopStarted -gt 0) {
    Write-Host "VERDICT: MONITOR STARTING  -> loop up, no heartbeats yet; wait a few seconds and re-check" -ForegroundColor Yellow
    $code = 3
}
else {
    Write-Host "VERDICT: MONITOR NOT UP  -> no monitor activity in the window (app not running, or not bound to the emulation tab)" -ForegroundColor Yellow
    $code = 4
}

if ($Tail) {
    Write-Host ""
    Write-Host "--- recent relevant lines ---" -ForegroundColor DarkGray
    $recent |
        Select-String -SimpleMatch -Pattern '[EventMonitor][HB]', 'DOM monitor loop started',
            'Timeout should be used inside a task', 'agent_skills is empty', 'reached max failures',
            'DEDICATED detection tab' |
        Select-Object -Last 12 |
        ForEach-Object { Write-Host $_.Line }
}

exit $code
