# PowerShell 5.1+; run on the actual Windows Docker Desktop host.
# Default is read-only. -RestartContainer explicitly interrupts the entire Moon container.
[CmdletBinding()]
param(
    [string] $Container = "project-moon-local",
    [string] $ContainerRepo = "/shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory",
    [switch] $RestartContainer
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-Exit {
    param([string] $Label)
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed (exit code $LASTEXITCODE). No PASS may be claimed."
    }
}

function Read-ContainerProbe {
    param([string] $Path, [string] $Stage)
    $exe = "$ContainerRepo/.venv/bin/python"
    $result = & docker exec -w $ContainerRepo $Container $exe -m scripts.verify_quant_moon_restart $Stage --moon-state "$ContainerRepo/state/moon-http" --baseline $Path
    Assert-Exit "state-$Stage"
    $payload = ($result | Out-String) | ConvertFrom-Json
    if ($Stage -eq "before" -and $payload.status -ne "BASELINE_CAPTURED") {
        throw "Pre-restart baseline capture did not pass."
    }
    if ($Stage -eq "after" -and $payload.status -ne "PASS") {
        throw "Post-restart persistent identity comparison failed."
    }
    return $payload
}

try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Windows Docker CLI not installed or not accessible."
    }
    $osType = (& docker info --format '{{.OSType}}' | Out-String).Trim()
    Assert-Exit "docker-info"
    if ($osType -ne "linux") {
        throw "Docker Desktop must use Linux containers, got '$osType'."
    }
    $running = (& docker inspect --format '{{.State.Running}}' $Container | Out-String).Trim()
    Assert-Exit "docker-inspect"
    if ($running -ne "true") {
        throw "Expected Moon container is not running."
    }
    $restartPolicy = (& docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' $Container | Out-String).Trim()
    Assert-Exit "docker-restart-policy"
    Write-Output "CONTAINER=$Container"
    Write-Output "LINUX_ENGINE=PASS"
    Write-Output "DOCKER_RESTART_POLICY=$restartPolicy"
    if ($restartPolicy -notin @("always", "unless-stopped")) {
        Write-Output "WINDOWS_HOST_AUTOBOOT_ACCEPTANCE=PENDING_RESTART_POLICY"
    }
    if (-not $RestartContainer) {
        Write-Output "WINDOWS_DOCKER_RESTART=NOT_EXECUTED"
        Write-Output "ACTION=Use -RestartContainer only during an approved Moon maintenance window."
        exit 0
    }

    # Linux verifier refuses a restart baseline while any research batch is active.
    $timestamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssfffZ")
    $baseline = "$ContainerRepo/state/moon-http/research/system/restart-acceptance/windows-$timestamp.json"
    $before = Read-ContainerProbe -Path $baseline -Stage "before"
    Write-Output "PRE_RESTART_STATE=PASS"
    Write-Output "OAUTH_CLIENTS=$($before.oauth_clients)"
    Write-Output "EVIDENCE_EVENTS=$($before.evidence_events)"

    # Explicit operator opt-in. No docker rm, compose down -v or image rebuild.
    & docker restart $Container | Out-Null
    Assert-Exit "docker-restart"
    $ready = $false
    for ($n = 0; $n -lt 30; $n++) {
        Start-Sleep -Seconds 2
        $live = (& docker inspect --format '{{.State.Running}}' $Container 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or $live -ne "true") { continue }
        $local = (& docker exec $Container curl -s -o /dev/null -w '%{http_code}' --max-time 4 http://127.0.0.1:8787/mcp 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) { continue }
        $gateway = (& docker exec $Container curl -s -o /dev/null -w '%{http_code}' --max-time 4 http://127.0.0.1:2999/quant/mcp 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) { continue }
        if ($local -eq "401" -and $gateway -eq "401") {
            $ready = $true
            break
        }
    }
    if (-not $ready) {
        throw "Local and gateway MCP unauthorized health probes did not recover to 401."
    }
    Write-Output "LOCAL_MCP_UNAUTHORIZED=401"
    Write-Output "GATEWAY_MCP_UNAUTHORIZED=401"
    $after = Read-ContainerProbe -Path $baseline -Stage "after"
    Write-Output "PERSISTED_STATE_CHECKS=$($after.checks)"
    Write-Output "OAUTH_CLIENTS_AFTER=$($after.oauth_clients)"
    Write-Output "EVIDENCE_EVENTS_AFTER=$($after.evidence_events)"
    Write-Output "WINDOWS_DOCKER_RESTART=PASS"
    Write-Output "HOST_REBOOT_ACCEPTANCE=NOT_TESTED"
    if ($restartPolicy -notin @("always", "unless-stopped")) {
        Write-Output "HOST_AUTOSTART_POLICY=REQUIRES_CONFIGURATION"
    }
    exit 0
}
catch {
    # No secret, OAuth keys, sqlite rows or internal file dumps.
    Write-Output "WINDOWS_DOCKER_RESTART=BLOCKED"
    Write-Output "REASON=$($_.Exception.Message)"
    exit 2
}
