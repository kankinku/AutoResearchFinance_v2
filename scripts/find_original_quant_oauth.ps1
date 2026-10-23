#requires -Version 5.1
# Read-only ORIGINAL Quant OAuth state locator for the Windows Docker host.
# No OAuth/key contents, URL values or database rows are ever read or printed.
[CmdletBinding()]
param(
    [string] $Container = "project-moon-local",
    [string[]] $SearchRoots = @(),
    [ValidateRange(1, 20)]
    [int] $MaxDepth = 10,
    [ValidateRange(100, 100000)]
    [int] $MaxDirectories = 20000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Add-ExistingRoot {
    param(
        [System.Collections.Generic.List[string]] $Roots,
        [string] $Candidate
    )
    if ([string]::IsNullOrWhiteSpace($Candidate)) { return }
    try {
        $resolved = (Resolve-Path -LiteralPath $Candidate -ErrorAction Stop).Path
        if ((Test-Path -LiteralPath $resolved -PathType Container) -and
            -not $Roots.Contains($resolved)) {
            $Roots.Add($resolved)
        }
    } catch {
        # Nonexistent historical folders are not recreated or substituted.
    }
}

function Read-DockerBindRoots {
    param([string] $ContainerName)
    $result = [System.Collections.Generic.List[string]]::new()
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        return $result
    }
    try {
        $mountJson = (& docker inspect --format '{{json .Mounts}}' $ContainerName 2>$null |
            Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or -not $mountJson) { return $result }
        $mounts = ConvertFrom-Json -InputObject $mountJson
        foreach ($mount in @($mounts)) {
            # Do not mistake the Moon's separate /var/lib/project-moon identity
            # for Quant's original state. Only use a real Windows bind mount.
            if ($mount.Type -ne "bind" -or $mount.Destination -ne "/shared") { continue }
            if (-not (Test-Path -LiteralPath $mount.Source -PathType Container)) { continue }
            Add-ExistingRoot -Roots $result -Candidate $mount.Source
            $parent = Split-Path -Path $mount.Source -Parent
            Add-ExistingRoot -Roots $result -Candidate $parent
        }
    } catch {
        # Missing host Docker state is a BLOCKED result, never permission to
        # create a new OAuth client or start a new container.
    }
    return $result
}

function Inspect-StateRoot {
    param([System.IO.DirectoryInfo] $MoonHttp)
    if ($null -eq $MoonHttp.Parent -or $MoonHttp.Parent.Name -ne "state") {
        return $null
    }
    $key = Join-Path $MoonHttp.FullName "oauth/approval-key"
    $pin = Join-Path $MoonHttp.FullName "oauth/public-base-url"
    $db = Join-Path $MoonHttp.FullName "research/oauth/quant-oauth.sqlite"
    $items = @($key, $pin, $db)
    $exists = @()
    foreach ($item in $items) {
        $exists += [bool](Test-Path -LiteralPath $item -PathType Leaf)
    }
    $count = @($exists | Where-Object { $_ }).Count
    if ($count -eq 0) { return $null }
    return [pscustomobject]@{
        StateRoot = $MoonHttp.FullName
        ApprovalKeyPresent = $exists[0]
        PinnedUrlPresent = $exists[1]
        OAuthDatabasePresent = $exists[2]
        Status = if ($count -eq 3) {
            "CANDIDATE_TRIPLET_PRESENT_UNVERIFIED"
        } else {
            "PARTIAL_IDENTITY_DO_NOT_START"
        }
    }
}

# Host inspection never performs docker exec/start/restart, never creates files
# or directories, and never reads key material or issuer URL text.
$roots = [System.Collections.Generic.List[string]]::new()
foreach ($requested in $SearchRoots) {
    Add-ExistingRoot -Roots $roots -Candidate $requested
}
foreach ($found in (Read-DockerBindRoots -ContainerName $Container)) {
    Add-ExistingRoot -Roots $roots -Candidate $found
}
if ($roots.Count -eq 0) {
    Write-Output "STATUS=BLOCKED_NO_ACCESSIBLE_HOST_SEARCH_ROOT"
    Write-Output "ACTION=Supply -SearchRoots with an existing historical Quant project or backup directory."
    exit 2
}

$skip = @(".git", ".venv", "node_modules", "__pycache__", ".cache",
          ".pytest_cache", "site-packages", "pytest-of-root")
$queue = [System.Collections.Generic.Queue[object]]::new()
foreach ($root in $roots) {
    $queue.Enqueue([pscustomobject]@{ Path = $root; Depth = 0 })
}
$seen = [System.Collections.Generic.HashSet[string]]::new(
    [System.StringComparer]::OrdinalIgnoreCase)
$foundStates = [System.Collections.Generic.List[object]]::new()
$visited = 0
while ($queue.Count -gt 0 -and $visited -lt $MaxDirectories) {
    $entry = $queue.Dequeue()
    if (-not $seen.Add($entry.Path)) { continue }
    $visited++
    $dir = Get-Item -LiteralPath $entry.Path -ErrorAction SilentlyContinue
    if ($null -eq $dir -or -not $dir.PSIsContainer) { continue }
    if ($dir.Name -eq "moon-http") {
        $candidate = Inspect-StateRoot -MoonHttp $dir
        if ($null -ne $candidate) { $foundStates.Add($candidate) }
        continue
    }
    if ($entry.Depth -ge $MaxDepth) { continue }
    foreach ($child in @(Get-ChildItem -LiteralPath $entry.Path -Directory -Force -ErrorAction SilentlyContinue)) {
        if (($child.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -or
            $child.Name -in $skip) { continue }
        $queue.Enqueue([pscustomobject]@{
            Path = $child.FullName
            Depth = $entry.Depth + 1
        })
    }
}

foreach ($candidate in $foundStates) {
    # Output only state-root path and boolean presence indicators, NOT secrets.
    Write-Output "STATUS=$($candidate.Status)"
    Write-Output "STATE_ROOT=$($candidate.StateRoot)"
    Write-Output "APPROVAL_KEY_PRESENT=$($candidate.ApprovalKeyPresent)"
    Write-Output "PUBLIC_URL_PIN_PRESENT=$($candidate.PinnedUrlPresent)"
    Write-Output "OAUTH_DB_PRESENT=$($candidate.OAuthDatabasePresent)"
    Write-Output "ACTION=Verify original issuer/client/DB provenance before any restore; do not rotate OAuth."
}
Write-Output "SCANNED_DIRECTORIES=$visited"
if ($queue.Count -gt 0) {
    Write-Output "STATUS=INCOMPLETE_SCAN_INCREASE_MAXDIRECTORIES"
    exit 3
}
if ($foundStates.Count -eq 0) {
    Write-Output "STATUS=BLOCKED_ORIGINAL_QUANT_OAUTH_NOT_FOUND"
    Write-Output "ACTION=Check additional original Windows disks and offline backups using -SearchRoots."
    exit 2
}
if (@($foundStates | Where-Object { $_.Status -eq "CANDIDATE_TRIPLET_PRESENT_UNVERIFIED" }).Count -eq 0) {
    Write-Output "STATUS=BLOCKED_ONLY_PARTIAL_IDENTITIES"
    exit 2
}
Write-Output "STATUS=CANDIDATE_FOUND_NOT_RESTORED"
exit 0
