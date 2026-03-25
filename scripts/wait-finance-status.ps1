param(
    [string]$ProjectId = "finance",
    [string]$RequestedBy = "openclaw-status-polling",
    [string]$ProjectState,
    [string]$PipelineState,
    [string]$AutoresearchState,
    [int]$TimeoutSeconds = 600,
    [int]$PollIntervalSeconds = 5,
    [switch]$StopOnTerminalFailure,
    [string]$RepositoryRoot = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $RepositoryRoot) {
    $RepositoryRoot = Join-Path $PSScriptRoot ".."
}

function Test-StateMatch {
    param(
        [pscustomobject]$Status,
        [string]$ExpectedProjectState,
        [string]$ExpectedPipelineState,
        [string]$ExpectedAutoresearchState
    )

    if ($ExpectedProjectState -and $Status.project_state -ne $ExpectedProjectState) {
        return $false
    }
    if ($ExpectedPipelineState -and $Status.pipeline_state -ne $ExpectedPipelineState) {
        return $false
    }
    if ($ExpectedAutoresearchState -and $Status.autoresearch_state -ne $ExpectedAutoresearchState) {
        return $false
    }
    return $true
}

function Test-TerminalFailure {
    param(
        [pscustomobject]$Status,
        [string]$ExpectedProjectState,
        [string]$ExpectedPipelineState,
        [string]$ExpectedAutoresearchState
    )

    if ($ExpectedProjectState -and $ExpectedProjectState -ne "degraded" -and $Status.project_state -eq "degraded") {
        return $true
    }
    if ($ExpectedPipelineState -eq "success" -and $Status.pipeline_state -eq "failed") {
        return $true
    }
    if ($ExpectedAutoresearchState -eq "success" -and $Status.autoresearch_state -in @("failed", "stale")) {
        return $true
    }
    return $false
}

try {
    $invokeScript = Join-Path $PSScriptRoot "invoke-openclaw-control.ps1"
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
    $effectiveStopOnFailure = $StopOnTerminalFailure.IsPresent

    while ([DateTimeOffset]::UtcNow -lt $deadline) {
        $rawStatus = & $invokeScript -Command "status" -ProjectId $ProjectId -RequestedBy $RequestedBy -RepositoryRoot $RepositoryRoot
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }

        $status = $rawStatus | ConvertFrom-Json
        if (-not $status.accepted) {
            throw "status command was rejected: $($status.message)"
        }

        if (Test-StateMatch -Status $status -ExpectedProjectState $ProjectState -ExpectedPipelineState $PipelineState -ExpectedAutoresearchState $AutoresearchState) {
            $status | ConvertTo-Json -Depth 10 -Compress
            exit 0
        }

        if ($effectiveStopOnFailure -and (Test-TerminalFailure -Status $status -ExpectedProjectState $ProjectState -ExpectedPipelineState $PipelineState -ExpectedAutoresearchState $AutoresearchState)) {
            $status | ConvertTo-Json -Depth 10 -Compress
            exit 2
        }

        Start-Sleep -Seconds $PollIntervalSeconds
    }

    $timeoutStatus = & $invokeScript -Command "status" -ProjectId $ProjectId -RequestedBy $RequestedBy -RepositoryRoot $RepositoryRoot
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
    $timeoutStatus
    exit 1
}
catch {
    Write-Error $_
    exit 1
}
