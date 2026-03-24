Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

param(
    [Parameter(Mandatory = $true)]
    [string]$AgentId,
    [Parameter(Mandatory = $true)]
    [string]$RequestJson,
    [Parameter(Mandatory = $true)]
    [string]$ResponseJson
)

try {
    $request = Get-Content $RequestJson -Raw | ConvertFrom-Json
    $stubPath = $env:FINANCE_AUTORESEARCH_OPENCLAW_MUTATE_RESPONSE_JSON

    if ($stubPath -and (Test-Path $stubPath)) {
        Copy-Item $stubPath $ResponseJson -Force
        Write-Output "[OK] Wrote stub mutation response for agent $AgentId"
        exit 0
    }

    $response = @{
        ok = $false
        task_kind = "mutation"
        idempotency_key = $request.idempotency_key
        artifact = $null
        error_type = "transport"
        message = "Mutation wrapper is not configured. Set FINANCE_AUTORESEARCH_OPENCLAW_MUTATE_RESPONSE_JSON or wire this script to your OpenClaw CLI."
        retryable = $true
    }

    $response | ConvertTo-Json -Depth 10 | Out-File $ResponseJson -Encoding utf8
    Write-Error "[X] Mutation wrapper is not configured."
    exit 1
}
catch {
    Write-Error "[X] Mutation wrapper failed: $_"
    exit 1
}
