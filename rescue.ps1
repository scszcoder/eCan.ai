$repoRoot = "C:\Users\songc\PycharmProjects\eCan.ai"
$commitMap = Join-Path $repoRoot ".git\filter-repo\commit-map"

Get-Content $commitMap | ForEach-Object {
    $parts = $_.Split(" ", [System.StringSplitOptions]::RemoveEmptyEntries)
    if ($parts.Count -eq 2 -and $parts[0] -match '^[0-9a-f]{40}$') {
        $oldSha = $parts[0]
        $info   = git -C $repoRoot show --quiet --date=iso --pretty="format:%h | %cI | %s" $oldSha
        if ($info -match '2025-11-28') {      # adjust date or add other filters
            $branch = "rescue-" + $oldSha.Substring(0,8)
            git -C $repoRoot branch $branch $oldSha | Out-Null 2>&1
            Write-Host "$branch -> $info"
        }
    }
}