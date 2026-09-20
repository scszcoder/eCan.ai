<#
.SYNOPSIS
  Non-stop Feige flood-test round-controller (2026-06-02).

.DESCRIPTION
  For each round in a config file this script:
    1. restores + re-patches the local Feige skill JSON (domCheckIntervalMs,
       cdpFilterExpr) via skill_patcher.py
    2. pushes emulation knobs to the emulation server (/api/emulation/config)
    3. sets per-round env vars (+ ECAN_AUTOLOGIN=1) and launches `python main.py`
    4. waits for the Feige EventMonitor to come alive (tails runlogs/eCan.log)
    5. starts a metrics run, fires a 20-customer flood, waits the round window
    6. stops the run -> the emulation server computes the 4 metrics and writes
       results/<run_id>.json
    7. tears the app down: kills the python tree and (existing-chrome mode,
       default) closes only the emulation tabs — your Chrome stays open.
       killChrome=true instead kills an app-spawned Chrome.
  ...then moves to the next round. A per-run summary is appended to
  results/summary.csv.

  AUTO-LOGIN: relies on the ECAN_AUTOLOGIN hook in the app (gui/LoginoutGUI.py).
  Saved credentials must already exist (the normal "remember me" login once).

  FEIGE TAB: there is no "monitored URL" to configure — the app keys the Feige
  tab off the "im.jinritemai.com" substring in any tab's URL and clones that
  tab for its typing pool. This script SEEDS that tab automatically by opening
  feigeUrl (default http://127.0.0.1:9876/im.jinritemai.com/) in the eCan Chrome
  via the DevTools API once it's up. Disable with settings.seedFeigeTab=false.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\emulation\run_flood_rounds.ps1 `
      -Config tools\emulation\rounds.sample.json
#>

param(
  [string]$Config = "",
  [int]$OnlyRound = -1   # 1-based; run a single round for debugging
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Config) { $Config = Join-Path $here "rounds.sample.json" }

# ── load config ────────────────────────────────────────────────────────
$cfg = Get-Content -Raw -Encoding UTF8 $Config | ConvertFrom-Json
$s = $cfg.settings
$repo    = $s.repoRoot
if (-not $repo) { $repo = (Resolve-Path (Join-Path $here "..\..")).Path }
$emuPort = if ($s.emuPort) { [int]$s.emuPort } else { 9876 }
$cdpPort = if ($s.cdpPort) { [int]$s.cdpPort } else { 9228 }
$python  = if ($s.python)  { $s.python } else { "python" }
$logRel = if ($s.logFile) { $s.logFile } else { "runlogs\eCan.log" }
$logFile = Join-Path $repo $logRel
# skillDir may be a single string or an array (multi-bot test). Normalize.
$skillDirs = @($s.skillDir) | Where-Object { $_ } | ForEach-Object { Join-Path $repo $_ }
$readyMarker = if ($s.readyMarker) { $s.readyMarker } else { "EventMonitor] DOM monitor loop start" }
$readyCount  = if ($s.readyMarkerCount) { [int]$s.readyMarkerCount } else { 1 }
$readyTimeoutSec = if ($s.readyTimeoutSec) { [int]$s.readyTimeoutSec } else { 300 }
$settleSec   = if ($s.settleSec) { [int]$s.settleSec } else { 30 }
$floodWaitSec = if ($s.floodWaitSec) { [int]$s.floodWaitSec } else { 180 }
$defaultFloodN = if ($s.floodN) { [int]$s.floodN } else { 20 }
$emuBase = "http://127.0.0.1:$emuPort"
$resultsDir = Join-Path $here "results"
$feigeUrl = if ($s.feigeUrl) { $s.feigeUrl } else { "http://127.0.0.1:$emuPort/im.jinritemai.com/" }
$seedFeigeTab = if ($null -ne $s.seedFeigeTab) { [bool]$s.seedFeigeTab } else { $true }
# "existing chrome" mode: you launch Chrome yourself on :$cdpPort and the app
# ATTACHES to it. In that mode the harness must NOT kill Chrome on teardown —
# it only kills the python app and closes the emulation tabs it opened. Set
# killChrome=true only if the app spawns its own ("new chromium") Chrome.
$killChrome = if ($null -ne $s.killChrome) { [bool]$s.killChrome } else { $false }
# Feige typing-tab pool size. DEFAULT_FEIGE_TYPING_TAB_COUNT in the app is 0
# (single-tab mode), so unless we set ECAN_FEIGE_TYPING_TAB_COUNT the harness
# would test a DIFFERENT config than the customer (who runs 6). Default to 6 to
# mirror the live setup; set to 0 to test single-tab mode on purpose.
$typingTabCount = if ($null -ne $s.typingTabCount) { [int]$s.typingTabCount } else { 6 }

function Log($msg) {
  Write-Host ("[harness {0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $msg)
}

function Invoke-Emu($method, $path, $bodyObj) {
  $uri = "$emuBase$path"
  try {
    if ($bodyObj -ne $null) {
      $json = $bodyObj | ConvertTo-Json -Depth 12 -Compress
      return Invoke-RestMethod -Method $method -Uri $uri -Body $json -ContentType "application/json" -TimeoutSec 30
    }
    return Invoke-RestMethod -Method $method -Uri $uri -TimeoutSec 30
  } catch {
    Log "emu call $method $path failed: $($_.Exception.Message)"
    return $null
  }
}

function Test-EmuUp {
  try { $r = Invoke-RestMethod -Uri "$emuBase/api/emulation/config" -TimeoutSec 4; return ($r -ne $null) }
  catch { return $false }
}

# Wait for the readiness marker to appear in the log AFTER $fromByte.
function Wait-ForReady($fromByte, $marker, $needCount, $timeoutSec) {
  $deadline = (Get-Date).AddSeconds($timeoutSec)
  while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 3
    if (-not (Test-Path $logFile)) { continue }
    try {
      $len = (Get-Item $logFile).Length
      $start = $fromByte
      if ($len -lt $start) { $start = 0 }   # log rotated
      $fs = [System.IO.File]::Open($logFile, 'Open', 'Read', 'ReadWrite')
      try {
        $null = $fs.Seek($start, 'Begin')
        $sr = New-Object System.IO.StreamReader($fs)
        $text = $sr.ReadToEnd()
        $sr.Close()
      } finally { $fs.Dispose() }
      $hits = ([regex]::Matches($text, [regex]::Escape($marker))).Count
      if ($hits -ge $needCount) { return $true }
    } catch {
      # file briefly locked during rotation; retry next tick
    }
  }
  return $false
}

# Read the runlog slice written since $fromByte (rotation- and lock-tolerant).
# Used by the pre-flight diagnostics below.
function Read-LogSlice($fromByte) {
  if (-not (Test-Path $logFile)) { return "" }
  try {
    $len = (Get-Item $logFile).Length
    $start = $fromByte
    if ($len -lt $start) { $start = 0 }   # log rotated
    $fs = [System.IO.File]::Open($logFile, 'Open', 'Read', 'ReadWrite')
    try {
      $null = $fs.Seek($start, 'Begin')
      $sr = New-Object System.IO.StreamReader($fs)
      $text = $sr.ReadToEnd()
      $sr.Close()
      return $text
    } finally { $fs.Dispose() }
  } catch { return "" }
}

function Count-InSlice($text, $pattern) {
  if (-not $text) { return 0 }
  return ([regex]::Matches($text, $pattern)).Count
}

# Pre-flight diagnosis when the Feige '新消息' monitor never came up. The
# monitor is started by a RUNNING Feige front-desk task (the app only
# auto-resumes agents already in a running state — it never creates/starts
# one). Without it: no monitor -> no typing pool -> no tabs -> nothing to
# flood. Greps the launch's log slice to tell the operator exactly which
# link in that chain broke.
function Show-FeigePreflightFailure($fromByte) {
  $t = Read-LogSlice $fromByte
  $startMon   = Count-InSlice $t 'start_monitors called'
  $loopStart  = Count-InSlice $t 'DOM monitor loop start'
  $feigeBuilt = Count-InSlice $t "(?i)Processing task: name=[^,]*(飞鸽|feige|front)"
  $feigeRun   = Count-InSlice $t "(?i)Resolved task '[^']*(飞鸽|feige|front)"
  Log "----------------------------------------------------------------"
  Log "PRE-FLIGHT FAILED: Feige '新消息' monitor never started this round."
  Log ("  start_monitors called      : {0}" -f $startMon)
  Log ("  DOM monitor loop start     : {0}  (the readiness marker)" -f $loopStart)
  Log ("  Feige task built (compiled) : {0}" -f $feigeBuilt)
  Log ("  Feige task resolved+running : {0}" -f $feigeRun)
  if ($feigeBuilt -eq 0) {
    Log "Diagnosis: NO Feige front-desk task exists in this account's DB."
    Log "  The autologin user has no agent bound to the 'customer_front_desk'"
    Log "  skill. Create/import one, or log in as the account that has it."
  } elseif ($feigeRun -eq 0) {
    Log "Diagnosis: a Feige task is configured but was NOT RUNNING, so it"
    Log "  never auto-resumed on login and the monitor never bound."
  } else {
    Log "Diagnosis: the Feige task ran but never reached start_monitors —"
    Log "  likely it could not find/focus the seeded im.jinritemai tab."
  }
  Log "Fix: launch the app in the GUI, START the front-desk agent (skill"
  Log "  'customer_front_desk') + the responders (rt_chat_bot*), confirm"
  Log "  'EventMonitor ... DOM monitor loop start' appears AND 6 typing tabs"
  Log "  open, then exit cleanly so autologin resumes them. Then re-run."
  Log "Skipping this round (no flood fired) to avoid testing a dead app."
  Log "----------------------------------------------------------------"
}

# After the monitor is up, confirm the typing pool actually opened its tabs.
# Soft (non-fatal) — single-tab mode still produces a valid (if more
# contended) run — but the operator wants to SEE whether the 6 tabs exist.
function Show-TypingPoolStatus($fromByte, $expected) {
  $t = Read-LogSlice $fromByte
  $opened = Count-InSlice $t 'opened new typing tab'
  $poolInit = Count-InSlice $t 'one-shot pool-init reached'
  if ($opened -ge $expected) {
    Log ("typing pool OK: {0}/{1} tabs opened" -f $opened, $expected)
  } elseif ($poolInit -eq 0) {
    Log ("WARNING: typing pool never initialized (0 tabs; expected {0}). Pool init never fired - check ECAN_FEIGE_TYPING_TAB_COUNT and that a customer/sidebar resolve occurred." -f $expected)
  } else {
    Log ("WARNING: typing pool under-populated: {0}/{1} tabs opened. Likely the one-shot pool-init race (degraded to single-tab); run will be MORE contended than the customer's multi-tab topology." -f $opened, $expected)
  }
}

# Wait until the eCan-controlled Chrome's DevTools endpoint is reachable.
function Wait-ForChrome($timeoutSec) {
  $deadline = (Get-Date).AddSeconds($timeoutSec)
  while ((Get-Date) -lt $deadline) {
    try {
      $v = Invoke-RestMethod -Uri "http://127.0.0.1:$cdpPort/json/version" -TimeoutSec 3
      if ($v) { return $true }
    } catch { }
    Start-Sleep -Seconds 2
  }
  return $false
}

# Seed the Feige tab: open the emulation URL in the eCan Chrome via the
# DevTools HTTP target API. The app keys the Feige tab off the
# "im.jinritemai.com" substring and clones this tab's URL for its typing
# pool, so this one open points the whole feature at the emulation. Idempotent
# enough — opening twice just yields an extra (harmless) emulation tab.
function Open-FeigeTab($url) {
  $u = "http://127.0.0.1:$cdpPort/json/new?$url"
  foreach ($verb in @('PUT','GET')) {   # newer Chrome requires PUT; older accepts GET
    try {
      $r = Invoke-RestMethod -Method $verb -Uri $u -TimeoutSec 5
      if ($r) { Log "seeded Feige tab ($verb) -> $url"; return $true }
    } catch { }
  }
  Log "WARNING: could not seed Feige tab at $url (open it manually in the eCan Chrome)"
  return $false
}

# Close just the emulation tabs (the seed + the app's cloned typing pool) via
# the DevTools API, leaving Chrome and any other tabs untouched. Matches the
# emulation host:port so only our tabs are closed.
function Close-EmuTabs {
  try {
    $targets = Invoke-RestMethod -Uri "http://127.0.0.1:$cdpPort/json" -TimeoutSec 5
  } catch {
    Log "could not list Chrome tabs for cleanup: $($_.Exception.Message)"
    return
  }
  $needle1 = "127.0.0.1:$emuPort"
  $needle2 = "localhost:$emuPort"
  $closed = 0
  foreach ($t in @($targets)) {
    $u = [string]$t.url
    if ($t.type -eq 'page' -and ($u.Contains($needle1) -or $u.Contains($needle2))) {
      try {
        Invoke-RestMethod -Uri "http://127.0.0.1:$cdpPort/json/close/$($t.id)" -TimeoutSec 5 | Out-Null
        $closed++
      } catch { }
    }
  }
  if ($closed -gt 0) { Log "closed $closed emulation tab(s)" }
}

# Tear down the app between rounds. ALWAYS kill the python main.py tree. Chrome
# handling depends on mode: in existing-chrome mode (default) keep Chrome alive
# and just close the emulation tabs; only kill Chrome if killChrome=true (the
# app spawned its own).
function Stop-AppTree($proc) {
  if ($proc -and -not $proc.HasExited) {
    Log "killing python tree pid=$($proc.Id)"
    & taskkill /PID $proc.Id /T /F 2>$null | Out-Null
  }
  if (-not $killChrome) {
    # existing-chrome mode: never touch Chrome; just clean up our tabs.
    Close-EmuTabs
    return
  }
  # app-spawned Chrome: kill it (matched by the eCan-specific debug port).
  try {
    $needle = "remote-debugging-port=$cdpPort"
    $chromes = Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" |
      Where-Object { $_.CommandLine -and $_.CommandLine.Contains($needle) }
    foreach ($c in $chromes) {
      Log "killing eCan chrome pid=$($c.ProcessId)"
      & taskkill /PID $c.ProcessId /T /F 2>$null | Out-Null
    }
  } catch {
    Log "chrome teardown query failed: $($_.Exception.Message)"
  }
}

# Track every env var name we set across rounds so we can clear stale ones.
$script:RoundEnvKeys = New-Object System.Collections.Generic.HashSet[string]
function Clear-RoundEnv {
  foreach ($k in @($script:RoundEnvKeys)) {
    if (Test-Path "env:$k") { Remove-Item "env:$k" -ErrorAction SilentlyContinue }
  }
}
function Set-RoundEnv($envObj) {
  Clear-RoundEnv
  if ($envObj) {
    foreach ($p in $envObj.PSObject.Properties) {
      Set-Item "env:$($p.Name)" $p.Value
      [void]$script:RoundEnvKeys.Add($p.Name)
    }
  }
}

# ── preflight ──────────────────────────────────────────────────────────
New-Item -ItemType Directory -Force -Path $resultsDir | Out-Null
Set-Location $repo

if (-not (Test-EmuUp)) {
  Log "emulation server not up on :$emuPort — starting it"
  Start-Process -FilePath $python -ArgumentList @((Join-Path $here "server.py"), "--port", "$emuPort") `
    -WorkingDirectory $repo -WindowStyle Minimized | Out-Null
  for ($i = 0; $i -lt 20; $i++) { Start-Sleep -Milliseconds 500; if (Test-EmuUp) { break } }
}
if (-not (Test-EmuUp)) { throw "emulation server did not come up on :$emuPort" }
Log "emulation server reachable at $emuBase"

# Existing-chrome mode: the app attaches to YOUR Chrome, so it must already be
# running on :$cdpPort before any round launches the app. We never start or stop
# it for you in this mode.
if (-not $killChrome) {
  if (-not (Wait-ForChrome 15)) {
    throw "existing-chrome mode: no Chrome DevTools endpoint on :$cdpPort. Launch it first, e.g.:`n" +
          "  chrome.exe --remote-debugging-port=$cdpPort --user-data-dir=`"C:\chrome_data`" --disable-features=SharedStorage,InterestCohort"
  }
  Log "eCan Chrome reachable on :$cdpPort (existing-chrome mode — will not be killed)"
}

# PIDs of any already-running eCan app (python main.py). The emulation server
# is `python server.py` and skill_patcher is short-lived, so this matches only
# the app itself.
function Get-EcanAppPids {
  try {
    $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction Stop |
      Where-Object { $_.CommandLine -and ($_.CommandLine -match 'main\.py') }
    return @($procs | ForEach-Object { $_.ProcessId })
  } catch { return @() }
}

# PRE-LAUNCH GUARD: a second eCan instance fighting over Chrome :$cdpPort means
# the harness's app can't bind the Feige '新消息' monitor -> the pre-flight times
# out and every round is skipped. Catch it up front (nothing patched yet, so a
# clean exit). This is the #1 cause of a dead harness run.
$existingPids = Get-EcanAppPids
if ($existingPids.Count -gt 0) {
  Log "ABORT: an eCan app (python main.py) is already running (PID(s): $($existingPids -join ', '))."
  Log "  Two instances fight over Chrome :$cdpPort, so the harness's app cannot bind"
  Log "  the Feige monitor and every round times out. Kill it and re-run. To kill:"
  Log "    Get-CimInstance Win32_Process -Filter `"Name='python.exe'`" | Where-Object { `$_.CommandLine -match 'main\.py' } | ForEach-Object { Stop-Process -Id `$_.ProcessId -Force }"
  exit 1
}

# Back up the skill(s) once (idempotent — won't clobber an existing pristine copy).
foreach ($sd in $skillDirs) { & $python (Join-Path $here "skill_patcher.py") backup $sd }

# Constant env across all rounds.
$env:ECAN_AUTOLOGIN = "1"
if ($s.emulationTestFlags) { $env:ECAN_EMULATION_TEST_FLAGS = "1" }
# Mirror the customer's multi-tab typing pool (app default is 0 = single-tab).
$env:ECAN_FEIGE_TYPING_TAB_COUNT = "$typingTabCount"
Log "typing-tab pool: ECAN_FEIGE_TYPING_TAB_COUNT=$typingTabCount"

$summaryCsv = Join-Path $resultsDir "summary.csv"
if (-not (Test-Path $summaryCsv)) {
  "timestamp,round,run_id,customers,total_queries,answered,placeholder_late,duplicate,placeholder_after_real,result_file" |
    Out-File -FilePath $summaryCsv -Encoding utf8
}

# ── round loop ─────────────────────────────────────────────────────────
$roundIdx = 0
foreach ($round in $cfg.rounds) {
  $roundIdx++
  if ($OnlyRound -gt 0 -and $roundIdx -ne $OnlyRound) { continue }
  $name = if ($round.name) { $round.name } else { "round$roundIdx" }
  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $runId = "${name}_$stamp"
  $floodN = if ($round.floodN) { [int]$round.floodN } else { $defaultFloodN }
  Log "==================== ROUND $roundIdx : $name ===================="

  # 1) skill knobs — restore to pristine, then patch this round's values
  foreach ($sd in $skillDirs) {
    & $python (Join-Path $here "skill_patcher.py") restore $sd | Out-Null
    if ($round.skill) {
      $pa = @((Join-Path $here "skill_patcher.py"), "patch", $sd)
      if ($round.skill.interval) { $pa += @("--interval", "$($round.skill.interval)") }
      if ($round.skill.cdpRoot)  { $pa += @("--cdp-root", $round.skill.cdpRoot) }
      if ($round.skill.cdpItem)  { $pa += @("--cdp-item", $round.skill.cdpItem) }
      if ($round.skill.cdpFields) {
        foreach ($f in $round.skill.cdpFields.PSObject.Properties) {
          $pa += @("--cdp-field", "$($f.Name)=$($f.Value)")
        }
      }
      & $python $pa
    }
  }

  # 2) emulation knobs (deep-merged onto DEFAULT_CONFIG by the server)
  $emuKnobs = if ($round.emulation) { $round.emulation } else { @{} }
  Invoke-Emu POST "/api/emulation/config" $emuKnobs | Out-Null

  # 3) per-round env + launch
  Set-RoundEnv $round.env
  # Make sure no eCan app is still running before we launch this round's — the
  # previous round's app may take a few seconds to die after teardown, and a
  # second live instance would fight over Chrome :$cdpPort and blind the monitor.
  $waited = 0
  while ((Get-EcanAppPids).Count -gt 0 -and $waited -lt 20) { Start-Sleep -Seconds 2; $waited += 2 }
  $strayPids = Get-EcanAppPids
  if ($strayPids.Count -gt 0) {
    Log "ABORT: eCan app still running (PID(s): $($strayPids -join ', ')) after ${waited}s — won't launch a 2nd instance into a Chrome conflict."
    Log "  Kill it and re-run. Restoring skills + emulation config and exiting."
    foreach ($sd in $skillDirs) { & $python (Join-Path $here "skill_patcher.py") restore $sd | Out-Null }
    try { Invoke-Emu POST "/api/emulation/reset" @{} | Out-Null } catch {}
    Clear-RoundEnv
    exit 1
  }
  $startByte = if (Test-Path $logFile) { (Get-Item $logFile).Length } else { 0 }
  Log "launching python main.py (env: $(@($script:RoundEnvKeys) -join ', '))"
  $proc = Start-Process -FilePath $python -ArgumentList @("main.py") `
    -WorkingDirectory $repo -PassThru

  try {
    # 4a) seed the emulation Feige tab once the eCan Chrome is up (the monitor
    #     can't go live until a tab with "im.jinritemai.com" exists).
    if ($seedFeigeTab) {
      Log "waiting for eCan Chrome on :$cdpPort to seed the Feige tab"
      if (Wait-ForChrome $readyTimeoutSec) { Open-FeigeTab $feigeUrl | Out-Null }
      else { Log "WARNING: eCan Chrome not reachable on :$cdpPort within ${readyTimeoutSec}s" }
    }

    # 4b) PRE-FLIGHT: wait for the Feige monitor to come alive. If it never
    #     does, the front-desk agent isn't running — fail fast with a clear
    #     diagnosis and SKIP this round instead of flooding a dead app for
    #     the whole window. (The round's finally{} still tears the app down.)
    Log "pre-flight: waiting for Feige monitor ('$readyMarker' x$readyCount, timeout ${readyTimeoutSec}s)"
    $ready = Wait-ForReady $startByte $readyMarker $readyCount $readyTimeoutSec
    if (-not $ready) {
      Show-FeigePreflightFailure $startByte
      continue
    }
    Log "app ready; settling ${settleSec}s"
    Start-Sleep -Seconds $settleSec

    # 5) start metrics run + fire flood
    Invoke-Emu POST "/api/emulation/run/start" @{ run_id = $runId; label = $name } | Out-Null
    # Per-round overrides: floodWaitSec (window length) + ramp knobs (staggered
    # joins + follow-ups) so threads grow past the detection-timeout cliff.
    $roundWait = if ($round.floodWaitSec) { [int]$round.floodWaitSec } else { $floodWaitSec }
    $floodBody = @{ n = $floodN }
    if ($round.flood) {
      if ($null -ne $round.flood.joinSpreadSec)      { $floodBody.joinSpreadSec = [int]$round.flood.joinSpreadSec }
      if ($null -ne $round.flood.followUpRounds)     { $floodBody.followUpRounds = [int]$round.flood.followUpRounds }
      if ($null -ne $round.flood.followUpIntervalMs) { $floodBody.followUpIntervalMs = [int]$round.flood.followUpIntervalMs }
      if ($null -ne $round.flood.imagePct)           { $floodBody.imagePct = [int]$round.flood.imagePct }
      if ($null -ne $round.flood.cardPct)            { $floodBody.cardPct = [int]$round.flood.cardPct }
    }
    Log "flood: $floodN customers; window ${roundWait}s; ramp=$(($floodBody | ConvertTo-Json -Compress))"
    Invoke-Emu POST "/api/emulation/flood" $floodBody | Out-Null
    Start-Sleep -Seconds $roundWait

    # Typing pool opens only once the front-desk DISPATCHES a customer
    # (resolve_feige_tab_target_id kicks the one-shot pool init) — never at
    # idle/settle. Report the authoritative tab count now, after the flood.
    Show-TypingPoolStatus $startByte $typingTabCount

    # 6) stop run -> server computes + writes results/<run_id>.json
    $stop = Invoke-Emu POST "/api/emulation/run/stop" $null
    $rep = if ($stop) { $stop.report } else { $null }
    if ($rep) {
      $m = $rep.metrics
      Log ("metrics: answered={0} late={1} dup={2} ph_after_real={3} (queries={4}, customers={5})" -f `
        $m.answered_queries, $m.placeholder_late, $m.duplicate_responses, $m.placeholder_after_real, `
        $rep.total_queries, $rep.customers)
      $row = ("{0},{1},{2},{3},{4},{5},{6},{7},{8},{9}" -f `
        (Get-Date -Format "s"), $name, $runId, $rep.customers, $rep.total_queries, `
        $m.answered_queries, $m.placeholder_late, $m.duplicate_responses, $m.placeholder_after_real, `
        $rep.written)
      Add-Content -Path $summaryCsv -Value $row -Encoding utf8
    } else {
      Log "WARNING: no report returned for $runId"
    }

    # 6b) detection-lag analysis: join the emulation's q_sent times with the
    # app's dom_observed (epoch ts_ms) to get TRUE detection latency
    # (customer-typed -> detected), and correlate spikes with monitor HB
    # starvation / no_match. This is the signal the customer logs can't give.
    $resultJson = Join-Path $resultsDir "$runId.json"
    if (Test-Path $resultJson) {
      Log "analyzing detection lag for $runId"
      & $python (Join-Path $here "analyze_detection_lag.py") `
        --results $resultJson --log $logFile `
        --out (Join-Path $resultsDir "${runId}_detection.json")
    } else {
      Log "detection-lag: results file not found ($resultJson) — skipping"
    }
  } finally {
    # 7) teardown
    Stop-AppTree $proc
    Start-Sleep -Seconds 5   # let ports/profile locks free
  }
}

# ── cleanup ────────────────────────────────────────────────────────────
Clear-RoundEnv
foreach ($sd in $skillDirs) { & $python (Join-Path $here "skill_patcher.py") restore $sd | Out-Null }
# Reset the emulation config to pristine defaults so chaos knobs (esp. the
# load-dependent scrapeStall) never leak into a later MANUAL run and freeze
# the page. /api/emulation/reset writes DEFAULT_CONFIG (scrapeStall disabled).
try { Invoke-Emu POST "/api/emulation/reset" @{} | Out-Null; Log "emulation config reset to defaults" } catch { Log "WARNING: could not reset emulation config: $_" }
Log "all rounds complete. summary -> $summaryCsv"
