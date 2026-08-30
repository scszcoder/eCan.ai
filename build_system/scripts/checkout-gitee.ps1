# checkout-gitee.ps1 — Replace actions/checkout@v6 against the Gitee mirror.
#
# Why this exists:
#   The previous bash version of this step relied on actions/checkout@v6
#   with a github-server-url override, which on a non-github.com URL + PAT
#   issues an HTTP basic-auth header with username x-access-token (the GitHub
#   PAT convention). Gitee's Git Smart-HTTP endpoint accepts oauth2:<token>
#   but rejects x-access-token:<token> with 401. See logs from run
#   #86639859775 for the exact failure pattern.
#
#   The first pwsh port of this step introduced a Process.Start +
#   WaitForExit loop with a 30s timeout and an "SSH fallback" branch —
#   but the SSH fallback never actually fired (the $useSsh guard was
#   undefined, so it always fell through to the HTTPS path on retry).
#   When the runner couldn't reach gitee.com at all, the second HTTPS
#   attempt ran with no timeout wrapper and hung until the step's
#   30-minute cap. This file replaces that whole thing.
#
# Contract:
#   - Single function Invoke-CheckoutGitee -Ref <ref> -Token <token>
#   - HTTPS only (no SSH fallback). Gitee is the canonical mirror for
#     release-cn; if HTTPS cannot reach it, fail fast with a clear
#     message rather than hanging for 30 minutes.
#   - Uses Find-GitExe from build_system/scripts/runner/find-prerequisites.ps1
#     so non-standard Git for Windows install paths (operator-style,
#     scoop, choco, portable) are all covered.
#   - Uses URL-embedded credentials (https://oauth2:<token>@gitee.com/...).
#     This is more reliable than GIT_ASKPASS on Windows runners where
#     path translation between pwsh and the git subprocess can fail.
#   - Sets http.timeout=30 on both ls-remote and fetch so a single hung
#     handshake aborts within 30s instead of stepping on the step-level
#     10-minute cap.
#
# Call site (one per build-* job in release-cn.yml):
#   - name: Checkout from Gitee mirror
#     if: github.event.inputs.runner_group != 'github-hosted'
#     shell: pwsh
#     timeout-minutes: 10
#     env:
#       GITEE_TOKEN: ${{ secrets.GITEE_TOKEN }}
#     run: |
#       # Before checkout this repository file must first be downloaded to
#       # RUNNER_TEMP from Gitee; dot-source that temporary copy here.
#       . $helper
#       Invoke-CheckoutGitee -Ref "${{ github.event.inputs.ref || github.ref }}" -Token $env:GITEE_TOKEN

[CmdletBinding()]
param()

function Invoke-CheckoutGitee {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Ref,

        [Parameter(Mandatory)]
        [string]$Token,

        # Override only for tests. Defaults to the Gitee mirror used by release-cn.
        [string]$RemoteUrl = 'https://gitee.com/songszchen/eCan.ai.git',

        # Override only for tests. Defaults to $env:GITHUB_WORKSPACE.
        [string]$WorkTree = $env:GITHUB_WORKSPACE
    )

    $ErrorActionPreference = 'Stop'

    if (-not $WorkTree) {
        Write-Error '::error::GITHUB_WORKSPACE is not set; cannot determine working tree.'
        return
    }
    if (-not $Ref) {
        Write-Error '::error::Ref is empty.'
        return
    }

    # Find git.exe. Reuse Find-GitExe from find-prerequisites.ps1 when
    # dot-sourced; otherwise inline a minimal PATH-only fallback so this
    # helper also works when called outside the workflow runner.
    $prereq = Join-Path (Split-Path -Parent $PSCommandPath) 'runner/find-prerequisites.ps1'
    if (-not (Get-Command Find-GitExe -ErrorAction SilentlyContinue)) {
        if (Test-Path -LiteralPath $prereq) { . $prereq }
    }
    if (-not (Get-Command Find-GitExe -ErrorAction SilentlyContinue)) {
        function Find-GitExe {
            $pathHit = Get-Command git -ErrorAction SilentlyContinue
            if ($pathHit) { return $pathHit.Source }
            $pathHit = Get-Command git.exe -ErrorAction SilentlyContinue
            if ($pathHit) { return $pathHit.Source }
            return $null
        }
    }
    $gitExe = Find-GitExe
    if (-not $gitExe) {
        Write-Error '::error::git.exe not found. Re-run the preflight "Ensure Git Bash + PowerShell 7" step.'
        return
    }
    Write-Host "[DEBUG] Using git.exe=$gitExe"

    # Resolve mingw64/bin/git.exe when present — git.exe at cmd\git.exe
    # uses MSYS2 libcurl which bypasses the Windows system proxy and
    # fixes TLS hangs on runners behind corporate MITM proxies.
    $dir = Split-Path -Parent $gitExe
    for ($i = 0; $i -lt 4 -and $dir; $i++) {
        $candidate = Join-Path $dir 'mingw64\bin\git.exe'
        if (Test-Path -LiteralPath $candidate) {
            $gitExe = $candidate
            break
        }
        $dir = Split-Path -Parent $dir
    }

    # Strip the PAT of any stray CR/LF that some secret stores inject,
    # then embed it in the remote URL. oauth2:<token>@ is the form Gitee
    # accepts on its Smart-HTTP endpoint.
    $clean = ($Token -replace '[\r\n]+', '')
    if (-not $clean) {
        Write-Error '::error::GITEE_TOKEN is empty after sanitization. Did the secret store the value with stray whitespace?'
        return
    }

    # Pin the working tree to GITHUB_WORKSPACE (the runner's checkout
    # dir). Re-init wipes any stale .git/ that a previous attempt left
    # behind when it timed out mid-fetch.
    Set-Location -LiteralPath $WorkTree
    if (Test-Path -LiteralPath '.git') { Remove-Item -Recurse -Force '.git' }
    & $gitExe init -q -b main .

    # Configure git to bypass proxy env vars that the runner inherits
    # from the corporate MITM gateway. Without this, libcurl routes
    # through the proxy and the CONNECT handshake to gitee.com hangs.
    $env:HTTP_PROXY = ''
    $env:HTTPS_PROXY = ''
    $env:NO_PROXY = '*'
    $env:http_proxy = ''
    $env:https_proxy = ''
    $env:no_proxy = '*'
    $env:GIT_TERMINAL_PROMPT = '0'

    & $gitExe remote remove origin 2>$null
    $originUrl = "https://oauth2:${clean}@${RemoteUrl -replace '^https://', ''}"
    & $gitExe config --global http.sslVerify false
    & $gitExe config --global http.proxy ""
    & $gitExe config --global https.proxy ""
    & $gitExe remote add origin $originUrl
    Write-Host "[DEBUG] Remote set to HTTPS via gitee.com (oauth2 embed)"

    # git's HTTP timeout is configured via git config (http.timeout), NOT
    # via the GIT_HTTP_TIMEOUT environment variable (which git does not
    # read). Setting it here means a hung TLS handshake aborts at 30s
    # instead of riding out the step's 10-minute cap.
    & $gitExe config --global http.timeout 30

    # Resolve bare ref (strip refs/heads/ or refs/tags/).
    $bareRef = if ($Ref -match '^refs/(heads|tags)/(.*)$') { $Matches[2] } else { $Ref }

    # ls-remote is wrapped in Process.Start + WaitForExit(30s) so a
    # network hang aborts within 30s with a clear ::error:: line, not
    # an opaque 10-minute step timeout.
    $timeoutSec = 30
    Write-Host "[DEBUG] ls-remote via HTTPS (${timeoutSec}s timeout)..."
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $gitExe
    $psi.Arguments = "ls-remote --exit-code origin `"refs/heads/${bareRef}`" `"refs/tags/${bareRef}`""
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $proc = [System.Diagnostics.Process]::Start($psi)
    $ok = $proc.WaitForExit($timeoutSec * 1000)
    if (-not $ok) {
        $proc.Kill($true)
        $proc.WaitForExit(5000)
        $proc.Dispose()
        Write-Error "::error::HTTPS ls-remote to gitee.com timed out after ${timeoutSec}s. The runner cannot reach gitee.com; check that this runner's egress firewall permits TCP:443 to *.gitee.com. (No SSH fallback in this step — fail fast rather than hang.)"
        return
    }
    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    $lsExit = $proc.ExitCode
    $proc.Dispose()
    if ($stderr) { $stderr -split "`n" | Where-Object { $_.Trim() } | ForEach-Object { Write-Host "[DEBUG] stderr: $_" } }
    if ($lsExit -ne 0) {
        $firstLine = if ($stdout) { ($stdout -split "`n" | Select-Object -First 1).ToString() } else { '' }
        Write-Error "::error::git ls-remote failed (exit=$lsExit): $firstLine. Either '$bareRef' has not been mirrored to Gitee yet, or auth to gitee.com was rejected. Verify the mirror at https://gitee.com/songszchen/eCan.ai and re-trigger sync-to-gitee if the ref is missing."
        return
    }
    $lsRaw = $stdout -split "`n" | Where-Object { $_.Trim() }
    $fullRef = ($lsRaw | Select-Object -First 1) -split "`t" | Select-Object -Last 1
    if (-not $fullRef) {
        Write-Error "::error::Ref '$Ref' not found on gitee.com/songszchen/eCan.ai. ls-remote returned no refs for bareRef='$bareRef'. Either the branch/tag has not been mirrored yet, or Gitee has not yet caught up to GitHub."
        return
    }
    Write-Host "[DEBUG] ls-remote resolved $Ref -> $fullRef"

    # Fetch with --depth=1 + a refspec that lands the fetched commit at
    # the matching local namespace. http.timeout=30 already set above
    # ensures a hung CONNECT aborts within 30s.
    & $gitExe -c protocol.version=2 fetch --no-tags --prune --no-recurse-submodules --depth=1 origin "${fullRef}:${fullRef}"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "::error::git fetch failed (exit=$LASTEXITCODE). See DEBUG stderr above for the underlying error."
        return
    }

    # Working-tree checkout.
    if ($fullRef -like 'refs/heads/*') {
        $localShort = $fullRef.Substring('refs/heads/'.Length)
        & $gitExe checkout --force -B $localShort $fullRef
    } elseif ($fullRef -like 'refs/tags/*') {
        $localShort = $fullRef.Substring('refs/tags/'.Length)
        & $gitExe checkout --force $localShort
    } else {
        Write-Error "::error::Internal: resolved fullRef '$fullRef' is neither refs/heads/* nor refs/tags/*. Failing fast rather than guessing."
        return
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Error "::error::git checkout failed (exit=$LASTEXITCODE) on $fullRef."
        return
    }

    $head = (& $gitExe rev-parse --short HEAD).Trim()
    Write-Host "[OK] Checked out $Ref at $head"
}
