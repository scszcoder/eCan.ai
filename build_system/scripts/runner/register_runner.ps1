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

    # -----------------------------------------------------------------------  
    # Operator-side baseline setup. These are the requirements every
    # GHA runner host must satisfy for release-cn.yml's self-hosted
    # Windows jobs to succeed. Without them, the workflow's preflight
    # step fails BEFORE the first build step runs (`##[error]Process
    # completed with exit code 1` or `bash: command not found`).
    # Doing it here means operator runs ONE script and the runner
    # is ready; without it, every job has a 30-second baseline tax.
    #
    # Why each fix:
    #
    # (a) ExecutionPolicy RemoteSigned on LocalMachine. The GHA
    # runner scripts its `shell: powershell` steps via
    # `powershell -command ". '<guid>.ps1'"` (dot-sources a temp
    # file in `_work\_temp`). Without a non-Restricted policy that
    # does NOT block unsigned local scripts, `Restricted` rejects
    # the dot-source with `UnauthorizedAccess` BEFORE the step body
    # runs. GitHub-hosted runner-images override this via Group
    # Policy to `RemoteSigned`; self-hosted runners get this here.
    # (`RemoteSigned` blocks unsigned internet scripts but allows
    # the runner's local temp files, which is the right balance.)
    #
    # (b) Git Bash on SYSTEM PATH. `shell: bash` resolves to
    # `bash.exe` via PATH. Git for Windows' installer only adds
    # `C:\Program Files\Git\bin` to the *user* PATH; the
    # `actions.runner.*-svc` service account starts from SYSTEM
    # PATH and never sees it. So `shell: bash` fails with
    # `##[error]bash: command not found` even when Git for
    # Windows is installed. We add the bin directory to SYSTEM
    # PATH here.
    #
    # Path semantics: $gitBashInstallDir = the install target dir
    # (parent), passed to the installer via /DIR. $gitBashDir =
    # the bin subdir we probe and put on SYSTEM PATH. Git for
    # Windows installs $gitBashInstallDir\bin\bash.exe (and
    # $gitBashInstallDir\mingw64\bin\*). Inno Setup's /DIR expects
    # the install target dir, NOT the bin subdir — passing /DIR
    # with the bin subdir was silently-ignored and the install
    # fell back to the default `C:\Program Files\Git`. This
    # happened to work because the default matches what we want,
    # but it's an undocumented accident.
    Log "Configuring runner baseline (ExecutionPolicy + Git Bash + pwsh + Chocolatey on PATH)..."

    # (a) ExecutionPolicy. The GHA runner scripts its `shell: powershell`
    # steps via `powershell -command ". '<guid>.ps1'"` (dot-sources a temp
    # file in `_work\_temp`). Without a non-Restricted policy that does
    # NOT block unsigned local scripts, `Restricted` rejects the dot-source
    # with `UnauthorizedAccess` BEFORE the step body runs. `RemoteSigned`
    # blocks unsigned internet scripts but allows the runner's local temp
    # files, which is the right balance.
    try {
        Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope LocalMachine -Force -ErrorAction Stop
        Log "Set-ExecutionPolicy: LocalMachine=RemoteSigned"
    } catch {
        Fail "ExecutionPolicy cannot be set on LocalMachine scope (needs elevation). Re-run register_runner.ps1 from an elevated PowerShell. Without this, the runner's first `shell: powershell` job will fail with `UnauthorizedAccess` because WinPS 5.1's in-box default is `Restricted` and blocks the runner's inline-script wrapper. Manual fix: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope LocalMachine -Force` (elevated PowerShell), then `C:\actions-runner\svc.cmd stop && C:\actions-runner\svc.cmd start`."
    }

    $gitBashInstallDir = 'C:\Program Files\Git'
    $gitBashDir        = Join-Path $gitBashInstallDir 'bin'
    $gitBashBin        = Join-Path $gitBashDir        'bash.exe'
    if (Test-Path $gitBashBin) {
        $currentMachinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
        if ($currentMachinePath -notlike "*$gitBashDir*") {
            [Environment]::SetEnvironmentVariable(
                'Path',
                ($currentMachinePath + ';' + $gitBashDir),
                'Machine'
            )
            Log "Added '$gitBashDir' to SYSTEM PATH"
        } else {
            Log "Git Bash bin dir already on SYSTEM PATH"
        }
    } else {
        # Git for Windows not installed. Symmetric with the pwsh branch
        # below: download + install here, not warn-and-skip. The preflight
        # step in release-cn.yml (line ~280) also has a fallback
        # install path, but doing it here means:
        #   - register-time cost (one-time), not per-job cost
        #   - matches docs §九.3.1 line 382 contract that
        #     register_runner.ps1 "auto-installs" Git for Windows
        #   - re-running register_runner.ps1 on an already-installed
        #     runner is a no-op (Test-Path $gitBashBin succeeds above)
        # Git for Windows is shipped as an exe installer (not an MSI);
        # /VERYSILENT is the Inno-Setup flag for unattended install.
        # /DIR<path> pins the install TARGET dir — the parent that
        # contains bin/, NOT bin/ itself. Passing /DIR=$gitBashDir
        # (= bin/) was silently ignored by Inno Setup, falling back
        # to its default C:\Program Files\Git, which happened to
        # match. Pin it explicitly so a future Inno-Setup / Git for
        # Windows behavior change doesn't break this.
        Log "Git for Windows not found at $gitBashBin — installing Git for Windows"
        try {
            $gitExe = "$env:TEMP\Git-Setup.exe"
            Invoke-WebRequest -UseBasicParsing -OutFile $gitExe `
                'https://github.com/git-for-windows/git/releases/download/v2.46.0.windows.1/Git-2.46.0-64-bit.exe'
            Log "Downloaded Git for Windows installer (v2.46.0)"
            # /VERYSILENT = Inno Setup unattended. /DIR<path> pins
            # the install target dir (= the parent of bin/). /NORESTART
            # suppresses post-install reboot prompt. /NOCANCEL
            # disables the cancel button. /SP- and /CLOSEAPPLICATIONS
            # are the standard Inno-Setup silent install flags.
            # /RESTARTAPPLICATIONS lets the installer restart apps
            # it needs to (none in our case, but harmless).
            Start-Process -Wait -FilePath $gitExe `
                -ArgumentList '/VERYSILENT','/NORESTART','/NOCANCEL','/SP-','/CLOSEAPPLICATIONS','/RESTARTAPPLICATIONS',`
                              "/DIR$gitBashInstallDir"
            Remove-Item $gitExe -Force -ErrorAction SilentlyContinue
            Log "Git for Windows installer exited (code: $LASTEXITCODE)"
            # Post-install verify: re-probe the exact binary we expect.
            # Without this, a silently-failing installer (exit 0 but no
            # files on disk) would let the script continue thinking Git
            # Bash is present. Test-Path after Start-Process -Wait is
            # the only authoritative check.
            if (-not (Test-Path $gitBashBin)) {
                Fail "Git for Windows installer exited $LASTEXITCODE but $gitBashBin is missing. The install silently failed. Manual fix: download from https://github.com/git-for-windows/git/releases/download/v2.46.0.windows.1/Git-2.46.0-64-bit.exe and run `/VERYSILENT /DIR`$gitBashInstallDir``. Without it, every `shell: bash` step in release-cn.yml will fail with `bash: command not found`."
            }
            Log "Git for Windows installed at $gitBashInstallDir"
        } catch {
            Fail "Git for Windows install failed: $_. Manual fix: download from https://github.com/git-for-windows/git/releases/download/v2.46.0.windows.1/Git-2.46.0-64-bit.exe and run `/VERYSILENT /DIR$gitBashInstallDir`. Without it, every `shell: bash` step in release-cn.yml will fail with `bash: command not found`."
        }
    }

    # (b2) PowerShell 7 (pwsh.exe) on SYSTEM PATH.
    # release-{intl,cn}.yml uses `shell: pwsh` for every Windows build step
    # (Install Windows-specific packages, Inno Setup, Build, Prepare artifacts, etc.)
    # because those steps rely on PowerShell 7 features (`?.`, `??`, ternary `?:`,
    # etc.) that are absent from Windows PowerShell v1.
    # GitHub-hosted `windows-latest` ships pwsh at
    # `C:\Program Files\PowerShell\7\pwsh.exe` out of the box.
    # Self-hosted runners do NOT — the MSI must be installed here.
    # The install is idempotent (re-running is safe); we skip if already present.
    $pwshBin = 'C:\Program Files\PowerShell\7\pwsh.exe'
    $pwshDir = 'C:\Program Files\PowerShell\7'
    if (Test-Path $pwshBin) {
        Log "pwsh already installed at $pwshBin"
    } else {
        Log "pwsh not found at $pwshBin — installing PowerShell 7 MSI"
        try {
            $msi = "$env:TEMP\pwsh-setup.msi"
            Invoke-WebRequest -Uri 'https://github.com/PowerShell/PowerShell/releases/download/v7.4.6/PowerShell-7.4.6-win-x64.msi' `
                             -OutFile $msi -UseBasicParsing
            Log "Downloaded pwsh MSI (v7.4.6)"
            # Use Start-Process -PassThru to capture the real MSI exit code.
            # Calling `msiexec.exe /i ... | Out-Null` is unreliable:
            # msiexec is a GUI-subsystem application, so PowerShell
            # doesn't block on it AND $LASTEXITCODE reflects the last
            # NATIVE command in the pipeline, which may not be
            # msiexec. Start-Process -Wait -PassThru gives us
            # $proc.ExitCode = msiexec's actual exit code (see
            # https://stackoverflow.com/q/4124409 and
            # https://stackoverflow.com/q/50867146).
            $proc = Start-Process -FilePath "msiexec.exe" `
                -ArgumentList "/i `"$msi`" /qn /norestart" `
                -Wait -PassThru -NoNewWindow
            Log "pwsh MSI exit code: $($proc.ExitCode)"
            Remove-Item $msi -Force -ErrorAction SilentlyContinue
            # Post-install verify: re-probe the exact binary we expect.
            # Without this, a silently-failing MSI (exit 0 but no files on
            # disk — e.g. blocked install permission, antivirus quarantine,
            # etc.) would let the script continue thinking pwsh is present.
            if (-not (Test-Path $pwshBin)) {
                Fail "pwsh MSI installer exited $($proc.ExitCode) but $pwshBin is missing. The install silently failed. Manual fix: download from https://github.com/PowerShell/PowerShell/releases/download/v7.4.6/PowerShell-7.4.6-win-x64.msi and run `msiexec /i PowerShell-7.4.6-win-x64.msi /qn`. Without pwsh, every `shell: pwsh` step in release workflows will fail with `pwsh: command not found`."
            }
            Log "pwsh installed at $pwshBin"
        } catch {
            Fail "pwsh MSI install failed: $_. Manual fix: download from https://github.com/PowerShell/PowerShell/releases/download/v7.4.6/PowerShell-7.4.6-win-x64.msi and run `msiexec /i PowerShell-7.4.6-win-x64.msi /qn`. Without pwsh, every `shell: pwsh` step in release workflows will fail with `pwsh: command not found`."
        }
    }
    # Ensure the pwsh directory is on the machine-level PATH (the MSI adds
    # it to the installing user's PATH; the service account is a separate
    # SID and may not inherit it).
    $currentMachinePath2 = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    if ($currentMachinePath2 -notlike "*$pwshDir*") {
        [Environment]::SetEnvironmentVariable(
            'Path',
            ($currentMachinePath2 + ';' + $pwshDir),
            'Machine'
        )
        Log "Added '$pwshDir' to SYSTEM PATH for pwsh"
    } else {
        Log "pwsh dir already on SYSTEM PATH"
    }

    # (c) Chocolatey. GitHub-hosted `windows-latest` ships with
    # Chocolatey 2.7.3 at C:\ProgramData\chocolatey\bin. Setup-
    # signtool-env (used by every Windows build job) uses choco as
    # a fallback for installing Windows SDK / signtool. Without
    # Chocolatey, that step fails with `choco: command not found`.
    #
    # Idempotency: skip if `choco.exe` is already on PATH.
    # Install procedure is the canonical
    # https://chocolatey.org/install one-liner, with TLS 1.2 forced
    # (some older Windows VMs default to TLS 1.0 which makes the
    # install.ps1 download fail with handshake errors).
    $chocoBin = 'C:\ProgramData\chocolatey\bin\choco.exe'
    if (Test-Path $chocoBin) {
        Log "Chocolatey already installed at $chocoBin"
    } else {
        Log "Chocolatey not found at $chocoBin — installing via community-chocolatey.org/install.ps1"
        try {
            # Force TLS 1.2 (older Windows defaults to TLS 1.0).
            # ExecutionPolicy is already RemoteSigned from step (a),
            # so the bootstrap script runs without `-Scope Process`
            # workarounds.
            [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
            Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
        } catch {
            Fail "Chocolatey install failed: $_. Manual fix: open elevated PowerShell and run `Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))`. Without choco, the Windows SDK signtool fallback in setup-signtool-env will fail during the first Windows build job — and that failure happens 10 minutes into the job, not at register time. We Fail here so the operator sees the problem at the right step. The runner service install + start above has already succeeded, so the runner is registered; this Fail is to surface the choco gap before the operator walks away."
        }
        # Post-install verify (the bootstrap script may exit 0 even on
        # partial failure — known issue with `Invoke-Expression` chains
        # against community.chocolatey.org).
        if (-not (Test-Path $chocoBin)) {
            Fail "Chocolatey install reported success but $chocoBin is still missing. Manual fix: open elevated PowerShell and run `Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))`. Without choco, the Windows SDK signtool fallback in setup-signtool-env will fail during the first Windows build job."
        }
        Log "Chocolatey installed at $chocoBin"
    }

    # (d) Restart the runner service so child processes inherit
    # the new ExecutionPolicy + PATH + pwsh. The existing service was
    # started earlier in this script; stop+start so its next
    # child process re-reads the new env. New `shell: bash` /
    # `shell: pwsh` / `shell: cmd` job will then succeed with the
    # full baseline.
    try {
        & .\svc.cmd stop | Out-Null
        Start-Sleep -Seconds 2
        & .\svc.cmd start | Out-Null
        Log "Runner service restarted (new child processes will inherit new ExecutionPolicy + PATH + Chocolatey)"
    } catch {
        Warn "could not restart runner service: $_`. Restart manually with: & C:\actions-runner\svc.cmd stop && C:\actions-runner\svc.cmd start"
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
