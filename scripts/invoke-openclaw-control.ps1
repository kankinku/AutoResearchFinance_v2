param(
    [Parameter(Mandatory = $true)]
    [ValidateSet(
        "status",
        "start_pipeline",
        "start_autoresearch",
        "pause_autoresearch",
        "resume_autoresearch",
        "stop_autoresearch",
        "reset_project"
    )]
    [string]$Command,
    [string]$ProjectId = "finance",
    [string]$RequestedBy = "openclaw-skill",
    [string]$PayloadJson = "{}",
    [string]$RepositoryRoot = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $RepositoryRoot) {
    $RepositoryRoot = Join-Path $PSScriptRoot ".."
}

function Resolve-RepositoryRoot {
    param([string]$PathValue)

    $resolved = Resolve-Path -Path $PathValue -ErrorAction Stop
    return $resolved.Path
}

function ConvertTo-PayloadObject {
    param([string]$JsonText)

    if ([string]::IsNullOrWhiteSpace($JsonText)) {
        return [pscustomobject]@{}
    }

    try {
        $payload = $JsonText | ConvertFrom-Json
    }
    catch {
        throw "PayloadJson must be a JSON object string."
    }

    if ($null -eq $payload) {
        return [pscustomobject]@{}
    }

    return $payload
}

try {
    $repoRoot = Resolve-RepositoryRoot -PathValue $RepositoryRoot
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw "uv is not installed or not available on PATH."
    }

    $payload = ConvertTo-PayloadObject -JsonText $PayloadJson
    $request = [ordered]@{
        command = $Command
        project_id = $ProjectId
        source = "openclaw"
        requested_by = $RequestedBy
        requested_at = [DateTimeOffset]::UtcNow.ToString("o")
        payload = $payload
    }
    $requestJson = $request | ConvertTo-Json -Depth 10 -Compress

    Push-Location $repoRoot
    try {
        $requestJson | & uv run python -m finance_autoresearch openclaw-control
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }
    finally {
        Pop-Location
    }
}
catch {
    Write-Error $_
    exit 1
}
