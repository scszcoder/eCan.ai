# find-prerequisites.ps1 — Probe-only helper for Git Bash + PowerShell 7
#
# This script is a DETECT-ONLY helper. It does NOT install anything.
# The CALLER decides what to do based on the result:
#   - If found -> use that path (the install is NOT shadowed)
#   - If missing -> install (the canonical URLs are documented
#     in the preflight / setup-prerequisites.ps1)
# This probe-then-install contract is what makes the workflow
# preflight self-healing — happy path is a no-op (probe finds
# the binary), cold runner triggers an install, both paths
# complete the workflow end-to-end.
#
# Why this exists (vs. hardcoded paths):
#   The previous setup-prerequisites.ps1 + workflow preflight
#   hardcoded:
#     $gitBashBin = 'C:\Program Files\Git\bin\bash.exe'
#     $pwshBin    = 'C:\Program Files\PowerShell\7\pwsh.exe'
#   But operators regularly install to non-standard paths:
#     - C:\Users\<user>\opt\pwsh7\pwsh.exe  (operator-style install)
#     - C:\ProgramData\chocolatey\bin\bash.exe  (choco install)
#     - C:\Users\<user>\scoop\apps\git\current\bin\bash.exe
#     - D:\PowerShell\7\pwsh.exe
#   The hardcoded probe-then-install sequence missed non-standard
#   installs and shadowed them with a default-path install
#   (run #86820634953). This helper fixes that by checking
#   multiple candidate paths before falling through to install.
#
# Detection strategy (in priority order):
#   1. PATH lookup via Get-Command (most authoritative — respects the
#      operator's actual PATH).
#   2. Canonical install dirs candidates (Program Files, Program Files (x86),
#      user-scope LocalAppData, operator-style $USERPROFILE\opt,
#      scoop, chocolatey).
#   3. The first candidate that exists and responds to --version wins.
#
# Used by:
#   - setup-prerequisites.ps1 (probes before doing any install)
#   - .github/workflows/release-{cn,intl}.yml preflight steps (inline)
#   - Any future CLI that needs the same autodetect
#
# Output: writes nothing to stdout. All detection is via return values.
# Callers should emit their own ::error:: / ::warning:: messages using
# the values returned by the helper functions.

[CmdletBinding()]
param(
    # Common-candidate dirs to probe, in priority order. Defaults below
    # cover Program Files, Program Files (x86), per-user, operator-style,
    # scoop, Chocolatey. Callers can override (e.g. tests) or extend.
    [string[]]$PwshCandidates = @(
        # PATH lookup is handled separately inside Find-PwshLocation.
        # Anything below is a canned install location.
        "$env:ProgramFiles\PowerShell\7\pwsh.exe",
        "${env:ProgramFiles(x86)}\PowerShell\7\pwsh.exe",
        "$env:LOCALAPPDATA\Programs\PowerShell\7\pwsh.exe",
        "$env:USERPROFILE\opt\pwsh7\pwsh.exe",
        "$env:USERPROFILE\bin\pwsh.exe",
        'D:\PowerShell\7\pwsh.exe',
        'C:\PowerShell\7\pwsh.exe'
    ),
    [string[]]$BashCandidates = @(
        "$env:ProgramFiles\Git\bin\bash.exe",
        "${env:ProgramFiles(x86)}\Git\bin\bash.exe",
        "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe",
        "$env:USERPROFILE\scoop\apps\git\current\bin\bash.exe",
        "$env:ProgramData\chocolatey\bin\bash.exe",
        'D:\Git\bin\bash.exe',
        'C:\Git\bin\bash.exe'
    )
)

# ---------------------------------------------------------------------------
# Find-PwshLocation — return the first existing + runnable pwsh.exe.
# Returns $null if not found anywhere.
# ---------------------------------------------------------------------------
function Find-PwshLocation {
    [CmdletBinding()]
    [OutputType([string])]
    param()

    # 1. Canonical install-dirs candidates FIRST. The whole point of this
    #    helper is to AVOID the WSL/Cygwin/MSYS2 placeholder at
    #    `C:\Windows\System32\pwsh.exe` (which `Get-Command` happily
    #    returns on GitHub-hosted windows-latest if anything shadows the
    #    canonical install via PATH pollution / 32-bit System32 precedence).
    #    See actions/runner-images#12646 for the System32-shadowing bug.
    foreach ($cand in $script:PwshCandidates) {
        if ($cand -and (Test-Path -LiteralPath $cand)) {
            return $cand
        }
    }

    # 2. PATH lookup (Get-Command) — last-resort for operator-style
    #    installs at non-canonical paths. Filter out the System32
    #    WSL/Cygwin shadow.
    $pathHit = Get-Command pwsh.exe -ErrorAction SilentlyContinue
    if ($pathHit) {
        $src = $pathHit.Source
        $parent = Split-Path -Parent $src
        if ($parent -eq "$env:SystemRoot\System32" -or $parent -eq "$env:WinDir\System32") {
            # WSL/Cygwin shadow — ignore.
        } else {
            return $src
        }
    }

    return $null
}

# ---------------------------------------------------------------------------
# Find-BashLocation — return the first existing + runnable bash.exe.
# Returns $null if not found anywhere.
# ---------------------------------------------------------------------------
function Find-BashLocation {
    [CmdletBinding()]
    [OutputType([string])]
    param()

    # 1. Canonical install-dirs candidates FIRST. Avoid the WSL
    #    placeholder at `C:\Windows\System32\bash.exe` that
    #    `Get-Command` returns when Git Bash isn't first on PATH
    #    (System32 has 32-bit precedence per CreateProcess, see
    #    actions/runner-images#12646).
    foreach ($cand in $script:BashCandidates) {
        if ($cand -and (Test-Path -LiteralPath $cand)) {
            return $cand
        }
    }

    # 2. PATH lookup (Get-Command) — last-resort for operator-style
    #    installs at non-canonical paths. Filter out the System32
    #    WSL/Cygwin shadow.
    $pathHit = Get-Command bash.exe -ErrorAction SilentlyContinue
    if ($pathHit) {
        $src = $pathHit.Source
        $parent = Split-Path -Parent $src
        if ($parent -eq "$env:SystemRoot\System32" -or $parent -eq "$env:WinDir\System32") {
            # WSL/Cygwin shadow — ignore.
        } else {
            return $src
        }
    }

    return $null
}

# ---------------------------------------------------------------------------
# Test-PwshRunnable — does the given path actually run pwsh --version?
# ---------------------------------------------------------------------------
function Test-PwshRunnable {
    [CmdletBinding()]
    [OutputType([bool])]
    param([string]$Path)
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return $false }
    try {
        $null = & $Path --version 2>&1
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

# ---------------------------------------------------------------------------
# Test-BashRunnable — does the given path actually run bash --version?
# ---------------------------------------------------------------------------
function Test-BashRunnable {
    [CmdletBinding()]
    [OutputType([bool])]
    param([string]$Path)
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return $false }
    try {
        $null = & $Path --version 2>&1
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

# ---------------------------------------------------------------------------
# Get-PwshDir — return the directory containing pwsh.exe (for PATH forwarding).
# ---------------------------------------------------------------------------
function Get-PwshDir {
    [CmdletBinding()]
    [OutputType([string])]
    param([string]$PwshPath)
    if (-not $PwshPath) { return $null }
    return [System.IO.Path]::GetDirectoryName($PwshPath)
}

# ---------------------------------------------------------------------------
# Get-BashDir — return the directory containing bash.exe (for PATH forwarding).
# ---------------------------------------------------------------------------
function Get-BashDir {
    [CmdletBinding()]
    [OutputType([string])]
    param([string]$BashPath)
    if (-not $BashPath) { return $null }
    return [System.IO.Path]::GetDirectoryName($BashPath)
}

# ---------------------------------------------------------------------------
# Get-PwshVersion — return the pwsh --version string, or $null.
# ---------------------------------------------------------------------------
function Get-PwshVersion {
    [CmdletBinding()]
    [OutputType([string])]
    param([string]$Path)
    if (-not (Test-PwshRunnable -Path $Path)) { return $null }
    try {
        return (& $Path --version 2>&1 | Select-Object -First 1).ToString().Trim()
    } catch {
        return $null
    }
}

# ---------------------------------------------------------------------------
# Get-BashVersion — return the bash --version string, or $null.
# ---------------------------------------------------------------------------
function Get-BashVersion {
    [CmdletBinding()]
    [OutputType([string])]
    param([string]$Path)
    if (-not (Test-BashRunnable -Path $Path)) { return $null }
    try {
        return (& $Path --version 2>&1 | Select-Object -First 1).ToString().Trim()
    } catch {
        return $null
    }
}
