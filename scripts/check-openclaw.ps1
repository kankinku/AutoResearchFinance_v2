param(
    [Parameter(Mandatory = $true)]
    [string]$RolesPath,
    [string]$GatewayUrl
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

try {
    if (-not (Test-Path $RolesPath)) {
        Write-Error "[X] Roles file not found: $RolesPath"
        exit 1
    }

    $content = Get-Content $RolesPath -Raw
    $requiredRoles = @("router", "research", "critic")
    foreach ($role in $requiredRoles) {
        if ($content -notmatch "(?m)^\s*${role}:\s*$") {
            Write-Error "[X] Missing required role block: $role"
            exit 1
        }
    }

    $mutateHandler = $env:FINANCE_AUTORESEARCH_OPENCLAW_MUTATE_HANDLER_PATH
    $analyzeHandler = $env:FINANCE_AUTORESEARCH_OPENCLAW_ANALYZE_HANDLER_PATH
    $mutateStub = $env:FINANCE_AUTORESEARCH_OPENCLAW_MUTATE_RESPONSE_JSON
    $analyzeStub = $env:FINANCE_AUTORESEARCH_OPENCLAW_ANALYZE_RESPONSE_JSON

    if ($mutateHandler) {
        if (-not (Test-Path $mutateHandler)) {
            Write-Error "[X] Mutation handler not found: $mutateHandler"
            exit 1
        }
    }
    elseif (-not ($mutateStub -and (Test-Path $mutateStub))) {
        Write-Error "[X] Mutation wrapper is not configured. Set FINANCE_AUTORESEARCH_OPENCLAW_MUTATE_HANDLER_PATH or FINANCE_AUTORESEARCH_OPENCLAW_MUTATE_RESPONSE_JSON."
        exit 1
    }

    if ($analyzeHandler) {
        if (-not (Test-Path $analyzeHandler)) {
            Write-Error "[X] Analysis handler not found: $analyzeHandler"
            exit 1
        }
    }
    elseif (-not ($analyzeStub -and (Test-Path $analyzeStub))) {
        Write-Error "[X] Analysis wrapper is not configured. Set FINANCE_AUTORESEARCH_OPENCLAW_ANALYZE_HANDLER_PATH or FINANCE_AUTORESEARCH_OPENCLAW_ANALYZE_RESPONSE_JSON."
        exit 1
    }

    if (-not $GatewayUrl) {
        $GatewayUrl = $env:FINANCE_AUTORESEARCH_OPENCLAW_GATEWAY_URL
    }

    if ($GatewayUrl) {
        Write-Output "[OK] OpenClaw roles and wrapper configuration resolved. Gateway: $GatewayUrl"
    }
    else {
        Write-Output "[OK] OpenClaw roles and wrapper configuration resolved."
    }
    exit 0
}
catch {
    Write-Error "[X] OpenClaw health check failed: $_"
    exit 1
}
