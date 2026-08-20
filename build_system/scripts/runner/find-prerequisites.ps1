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
    ),
    [string[]]$PythonCandidates = @(
        'C:\Python312\python.exe',
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:USERPROFILE\scoop\apps\python\current\python.exe"
    )
)

# ---------------------------------------------------------------------------
# Find-PythonLocation — return the first existing + runnable python.exe.
# The PATH fallback filters out the WindowsApps Store App Execution Alias
# (AppData\Local\Microsoft\WindowsApps\python.exe), which exits 126 if
# Store Python is not installed but still takes precedence on PATH for
# `python3` in workflow bash steps. Probe canonical dirs first so a real
# install wins regardless of PATH order.
# ---------------------------------------------------------------------------
function Find-PythonLocation {
    [CmdletBinding()]
    [OutputType([string])]
    param()

    foreach ($cand in $script:PythonCandidates) {
        if ($cand -and (Test-Path -LiteralPath $cand)) {
            return $cand
        }
    }
    foreach ($exeName in @('python.exe', 'python3.exe')) {
        $pathHit = Get-Command $exeName -ErrorAction SilentlyContinue
        if ($pathHit -and $pathHit.Source -notlike '*\AppData\Local\Microsoft\WindowsApps\*') {
            return $pathHit.Source
        }
    }
    return $null
}

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
# Find-GitExe — return the git.exe that ships next to bash.exe.
# `git ls-remote` is the probe used by both the runner-setup
# (setup-prerequisites.ps1 §7) and the release-cn checkout step
# (release-cn.yml "Probe Gitee reachability"). On every supported
# install layout (Git for Windows MSI, scoop, choco, portable,
# winget), git.exe lives in the same bin/ directory as bash.exe OR
# one directory up in mingw64/bin/ (newer Git for Windows split the
# native binaries into mingw64/). We start from bash.exe to inherit
# the same probe logic, then expand to PATH search so an install
# where bash.exe and git.exe ended up in different bins still works.
#
# Returns $null on miss. Callers should treat that as a hard error,
# not a silent skip — git is required for the Gitee checkout.
# ---------------------------------------------------------------------------
function Find-GitExe {
    [CmdletBinding()]
    [OutputType([string])]
    param()

    # (0) Try the System32-free PATH lookup FIRST. This handles the
    #     common case where git is installed (via winget, choco, or
    #     manual add-to-PATH) but bash.exe somehow isn't — the Gitee
    #     checkout only needs git, not bash. Returns early.
    $pathHit = Get-Command git.exe -ErrorAction SilentlyContinue
    if ($pathHit) {
        $src = $pathHit.Source
        $parent = Split-Path -Parent $src
        if ($parent -ne "$env:SystemRoot\System32" -and $parent -ne "$env:WinDir\System32") {
            return $src
        }
    }

    # (1) Same-directory candidates relative to bash.exe's bin/.
    #     Covers Git for Windows MSI (mingw64 layout), scoop, choco,
    #     winget, and the older GfW layout where git.exe ships in bin/.
    $bashExe = Find-BashLocation
    if ($bashExe) {
        $bashDir = [System.IO.Path]::GetDirectoryName($bashExe)
        $gitRoot = [System.IO.Path]::GetDirectoryName($bashDir)
        $candidates = @(
            (Join-Path $bashDir     'git.exe'),              # MSI bin/, scoop, choco
            (Join-Path $bashDir     'mingw64\bin\git.exe'),  # newer MSI mingw64/
            (Join-Path $gitRoot     'mingw64\bin\git.exe'),  # if bash is in bin/, root is the install dir
            (Join-Path $gitRoot     'cmd\git.exe'),          # very old GfW placed git in cmd/
            (Join-Path $gitRoot     'libexec\git-core\git.exe') # pre-2.x source-tree layout
        )
        foreach ($c in $candidates) {
            if ($c -and (Test-Path -LiteralPath $c)) { return $c }
        }
    }

    return $null
}

# ---------------------------------------------------------------------------
# Test-PythonRunnable — does the given path actually run python --version?
# Explicitly refuses WindowsApps Store placeholder paths.
# ---------------------------------------------------------------------------
function Test-PythonRunnable {
    [CmdletBinding()]
    [OutputType([bool])]
    param([string]$Path)
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return $false }
    if ($Path -like '*\AppData\Local\Microsoft\WindowsApps\*') { return $false }
    try {
        $null = & $Path --version 2>&1
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

# ---------------------------------------------------------------------------
# Get-PythonDir — return the directory containing python.exe (for PATH forwarding).
# ---------------------------------------------------------------------------
function Get-PythonDir {
    [CmdletBinding()]
    [OutputType([string])]
    param([string]$PythonPath)
    if (-not $PythonPath) { return $null }
    return [System.IO.Path]::GetDirectoryName($PythonPath)
}

# ---------------------------------------------------------------------------
# Get-PythonVersion — return the python --version string, or $null.
# ---------------------------------------------------------------------------
function Get-PythonVersion {
    [CmdletBinding()]
    [OutputType([string])]
    param([string]$Path)
    if (-not (Test-PythonRunnable -Path $Path)) { return $null }
    try {
        return (& $Path --version 2>&1 | Select-Object -First 1).ToString().Trim()
    } catch {
        return $null
    }
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
