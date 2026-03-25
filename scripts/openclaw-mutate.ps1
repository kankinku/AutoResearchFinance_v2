param(
    [Parameter(Mandatory = $true)]
    [string]$AgentId,
    [Parameter(Mandatory = $true)]
    [string]$RequestJson,
    [Parameter(Mandatory = $true)]
    [string]$ResponseJson
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

try {
    $request = Get-Content $RequestJson -Raw | ConvertFrom-Json
    $handlerPath = $env:FINANCE_AUTORESEARCH_OPENCLAW_MUTATE_HANDLER_PATH
    $stubPath = $env:FINANCE_AUTORESEARCH_OPENCLAW_MUTATE_RESPONSE_JSON

    if ($handlerPath) {
        if (-not (Test-Path $handlerPath)) {
            Write-Error "[X] Mutation handler not found: $handlerPath"
            exit 1
        }

        & $handlerPath -AgentId $AgentId -RequestJson $RequestJson -ResponseJson $ResponseJson
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
        if (-not (Test-Path $ResponseJson)) {
            Write-Error "[X] Mutation handler did not create a response file."
            exit 1
        }
        exit 0
    }

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
