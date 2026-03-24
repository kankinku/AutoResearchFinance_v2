Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

param(
    [Parameter(Mandatory = $true)]
    [string]$RolesPath,
    [string]$GatewayUrl
)

try {
    if (-not (Test-Path $RolesPath)) {
        Write-Error "[X] Roles file not found: $RolesPath"
        exit 1
    }

    $content = Get-Content $RolesPath -Raw
    $requiredRoles = @("router", "research", "critic")
    foreach ($role in $requiredRoles) {
        if ($content -notmatch "(?m)^\s+$role:\s*$") {
            Write-Error "[X] Missing required role block: $role"
            exit 1
        }
    }

    if (-not $GatewayUrl) {
        $GatewayUrl = $env:FINANCE_AUTORESEARCH_OPENCLAW_GATEWAY_URL
    }

    if ($GatewayUrl) {
        Write-Output "[OK] OpenClaw roles resolved. Gateway: $GatewayUrl"
    }
    else {
        Write-Output "[OK] OpenClaw roles resolved."
    }
    exit 0
}
catch {
    Write-Error "[X] OpenClaw health check failed: $_"
    exit 1
}
