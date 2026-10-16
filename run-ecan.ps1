#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Launch the eCan.ai desktop app from a PowerShell terminal.

.DESCRIPTION
    DEV mode (default): starts the Vite dev server (gui_v2) on port 3000 if it
    isn't already running, waits until it's ready, then launches the PySide6
    app (main.py) in dev mode using the project's .venv Python. When the app
    window is closed, the Vite server THIS script started is stopped
    (use -KeepVite to leave it running for a fast relaunch).

    PROD mode (-Prod): runs the app against the built gui_v2\dist bundle
    (no Vite server needed). Add -Build to rebuild dist first.

    The app logs stream to this terminal. Close the app window to return.

.PARAMETER Prod
    Run against the built gui_v2\dist bundle instead of the Vite dev server.

.PARAMETER Build
    (Prod only) Run `npm run build` in gui_v2 before launching.

.PARAMETER KeepVite
    (Dev only) Leave the Vite dev server running after the app exits.

.PARAMETER VitePort
    Vite dev server port the app loads from. Default 3000 (matches vite.config.ts).

.EXAMPLE
    .\run-ecan.ps1
    Run in dev mode (auto-starts Vite).

.EXAMPLE
    .\run-ecan.ps1 -KeepVite
    Dev mode, but leave Vite running afterwards.

.EXAMPLE
    .\run-ecan.ps1 -Prod -Build
    Rebuild the frontend, then run against the built bundle.

.NOTES
    If you see "running scripts is disabled on this system", launch with:
        powershell -ExecutionPolicy Bypass -File .\run-ecan.ps1
    or allow local scripts once:
        Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
#>
[CmdletBinding()]
param(
    [switch]$Prod,
    [switch]$Build,
    [switch]$KeepVite,
    [int]$VitePort = 3000
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
Set-Location $root

# --- Resolve the project's venv Python -------------------------------------
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    throw "venv Python not found at '$python'. Create the virtualenv and install requirements (requirements-windows.txt) first."
}

function Test-Port {
    param([int]$Port)
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $client.Connect('127.0.0.1', $Port)
        $client.Close()
        return $true
    } catch {
        return $false
    }
}

# ===========================================================================
# PROD MODE
# ===========================================================================
if ($Prod) {
    $env:ECBOT_WEB_MODE = 'prod'

    if ($Build) {
        Write-Host "[run-ecan] Building frontend (gui_v2)..." -ForegroundColor Cyan
        Push-Location (Join-Path $root 'gui_v2')
        try { & npm.cmd run build; if ($LASTEXITCODE -ne 0) { throw "npm run build failed (exit $LASTEXITCODE)." } }
        finally { Pop-Location }
    }

    $dist = Join-Path $root 'gui_v2\dist\index.html'
    if (-not (Test-Path $dist)) {
        throw "Prod mode needs a build: '$dist' not found. Re-run with -Build."
    }

    Write-Host "[run-ecan] Starting eCan.ai in PROD mode (built dist)..." -ForegroundColor Green
    & $python main.py
    exit $LASTEXITCODE
}

# ===========================================================================
# DEV MODE (default)
# ===========================================================================
$env:ECBOT_WEB_MODE = 'dev'
$viteProc    = $null
$startedVite = $false

if (Test-Port $VitePort) {
    Write-Host "[run-ecan] Vite already running on port $VitePort - reusing it." -ForegroundColor Yellow
} else {
    $npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
    if (-not $npm) { $npm = (Get-Command npm -ErrorAction SilentlyContinue).Source }
    if (-not $npm) { throw "npm not found on PATH. Install Node.js or add it to PATH." }

    $guiDir = Join-Path $root 'gui_v2'
    if (-not (Test-Path (Join-Path $guiDir 'node_modules'))) {
        Write-Host "[run-ecan] gui_v2\node_modules missing - running npm install..." -ForegroundColor Cyan
        Push-Location $guiDir
        try { & $npm install; if ($LASTEXITCODE -ne 0) { throw "npm install failed (exit $LASTEXITCODE)." } }
        finally { Pop-Location }
    }

    Write-Host "[run-ecan] Starting Vite dev server (gui_v2) on port $VitePort..." -ForegroundColor Cyan
    $viteProc    = Start-Process -FilePath $npm -ArgumentList 'run', 'dev' -WorkingDirectory $guiDir -PassThru -WindowStyle Minimized
    $startedVite = $true

    $deadline = (Get-Date).AddSeconds(60)
    while (-not (Test-Port $VitePort)) {
        if ((Get-Date) -gt $deadline) { throw "Vite did not come up on port $VitePort within 60s. Check the minimized npm window." }
        Start-Sleep -Milliseconds 500
    }
    Write-Host "[run-ecan] Vite ready on http://localhost:$VitePort/" -ForegroundColor Green
}

try {
    Write-Host "[run-ecan] Starting eCan.ai in DEV mode. Close the app window to exit." -ForegroundColor Green
    & $python main.py
} finally {
    if ($startedVite -and -not $KeepVite) {
        Write-Host "[run-ecan] Stopping Vite dev server..." -ForegroundColor Cyan
        if ($viteProc -and -not $viteProc.HasExited) {
            # npm spawns a child node process - kill the whole tree.
            & taskkill.exe /PID $viteProc.Id /T /F *> $null
        }
    } elseif ($startedVite -and $KeepVite) {
        Write-Host "[run-ecan] Leaving Vite running on http://localhost:$VitePort/ (-KeepVite)." -ForegroundColor Yellow
    }
}
