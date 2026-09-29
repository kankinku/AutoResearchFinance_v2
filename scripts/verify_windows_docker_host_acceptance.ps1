param(
    [Parameter(Mandatory = $true)]
    [string]$RepoPath,
    [string]$RemoteBranch = "feat/autoresearch-runtime-mcp-sdk",
    [string]$Image = "quant-autoresearch-worker:local"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Require-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "HOST_BLOCKED: required command not found: $Name"
    }
}

function Invoke-Native {
    param([string]$Command, [string[]]$Arguments = @())
    $output = @(& $Command @Arguments 2>&1 | ForEach-Object { $_.ToString() })
    if ($LASTEXITCODE -ne 0) {
        $joined = $output -join [Environment]::NewLine
        throw "COMMAND_FAILED: $Command $($Arguments -join ' ') | exit=$LASTEXITCODE | $joined"
    }
    return $output
}

function Convert-LastJson {
    param([string[]]$Output)
    $candidates = @($Output | Where-Object { $_.TrimStart().StartsWith("{") })
    if ($candidates.Count -eq 0) {
        throw "JSON_PARSE_FAILED: no JSON payload found"
    }
    return ($candidates[-1] | ConvertFrom-Json)
}

$repo = (Resolve-Path -LiteralPath $RepoPath).Path
Push-Location $repo

$report = [ordered]@{
    schema_version = 1
    status = "RUNNING"
    remote_branch = $RemoteBranch
    image = $Image
    started_at = (Get-Date).ToString("o")
    host = [ordered]@{}
    git = [ordered]@{}
    steps = [ordered]@{}
    error = $null
}
$reportPath = $null

function Save-Report {
    if ($script:reportPath) {
        $script:report | ConvertTo-Json -Depth 16 |
            Set-Content -LiteralPath $script:reportPath -Encoding UTF8
    }
}

function Invoke-Step {
    param([string]$Name, [string]$Command, [string[]]$Arguments = @())
    $output = @(Invoke-Native -Command $Command -Arguments $Arguments)
    $script:report.steps[$Name] = [ordered]@{
        status = "PASS"
        command = "$Command $($Arguments -join ' ')"
        output = $output
    }
    Save-Report
    return $output
}

function Invoke-JsonStep {
    param(
        [string]$Name,
        [string[]]$Arguments,
        [string]$ExpectedStatus
    )
    $output = @(Invoke-Native -Command "uv" -Arguments $Arguments)
    $payload = Convert-LastJson -Output $output
    if ($payload.status -ne $ExpectedStatus) {
        throw "ASSERTION_FAILED: $Name status expected $ExpectedStatus but got $($payload.status)"
    }
    if ($payload.orders_enabled -ne $false) {
        throw "ASSERTION_FAILED: $Name orders_enabled must be false"
    }
    $script:report.steps[$Name] = [ordered]@{
        status = "PASS"
        command = "uv $($Arguments -join ' ')"
        payload = $payload
        output = $output
    }
    Save-Report
    return $payload
}

try {
    if ($env:OS -ne "Windows_NT") {
        throw "HOST_BLOCKED: real Windows host required"
    }

    Require-Command "git"
    Require-Command "uv"
    Require-Command "docker"

    $dirtyBefore = @(Invoke-Native "git" @("status", "--porcelain=v1"))
    if ($dirtyBefore.Count -gt 0) {
        throw "HOST_BLOCKED: working tree must be clean before acceptance"
    }

    Invoke-Native "git" @("fetch", "--prune", "origin") | Out-Null
    $localHead = (@(Invoke-Native "git" @("rev-parse", "HEAD"))[-1]).Trim()
    $remoteHead = (@(Invoke-Native "git" @("rev-parse", "origin/$RemoteBranch"))[-1]).Trim()
    if ($localHead -ne $remoteHead) {
        throw "HOST_BLOCKED: local HEAD $localHead does not match origin/$RemoteBranch $remoteHead"
    }

    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $acceptanceRoot = Join-Path $repo "state\windows-docker-host-acceptance\$stamp"
    New-Item -ItemType Directory -Force -Path $acceptanceRoot | Out-Null
    $reportPath = Join-Path $acceptanceRoot "report.json"

    $report.git = [ordered]@{
        clean_before = $true
        local_head = $localHead
        remote_head = $remoteHead
    }
    Save-Report

    Invoke-Step "host_uv_sync" "uv" @("sync", "--locked", "--extra", "dev") | Out-Null
    Invoke-Step "host_python" "uv" @("run", "--locked", "--extra", "dev", "python", "-c", "import sys; print(sys.version)") | Out-Null
    Invoke-Step "host_docker_version" "docker" @("version") | Out-Null

    $dockerInfo = @(Invoke-Step "host_docker_info" "docker" @("info", "--format", "{{.OSType}}|{{.OperatingSystem}}|{{.ServerVersion}}"))
    $parts = $dockerInfo[-1] -split "\|", 3
    if ($parts.Count -ne 3 -or $parts[0] -ne "linux") {
        throw "HOST_BLOCKED: Docker Desktop Linux engine required"
    }
    $report.host = [ordered]@{
        os = $env:OS
        powershell = $PSVersionTable.PSVersion.ToString()
        docker_os_type = $parts[0]
        docker_operating_system = $parts[1]
        docker_server_version = $parts[2]
    }
    Save-Report

    $common = @("run", "--locked", "--extra", "dev", "python", "scripts/verify_docker_evaluation.py", "--project-root", ".")

    Invoke-JsonStep "step1_static_build_contract" ($common + @("--image", $Image, "--check-build-context")) "STATIC_READY" | Out-Null
    Invoke-JsonStep "step2_image_build" ($common + @("--image", $Image, "--build-image", "--check-only")) "READY" | Out-Null
    Invoke-JsonStep "step3_single_job_evidence" ($common + @("--state-dir", (Join-Path $acceptanceRoot "single"), "--image", $Image, "--prepare-fixture")) "PASS" | Out-Null
    Invoke-JsonStep "step4_timeout_cleanup" ($common + @("--state-dir", (Join-Path $acceptanceRoot "timeout"), "--image", $Image, "--verify-timeout", "--timeout-seconds", "0.5")) "PASS" | Out-Null
    Invoke-JsonStep "step5_retry_exhaustion" ($common + @("--state-dir", (Join-Path $acceptanceRoot "retry"), "--image", $Image, "--verify-retry-exhaustion", "--timeout-seconds", "0.5", "--max-retries", "2")) "PASS" | Out-Null
    Invoke-JsonStep "step6_controller_restart" ($common + @("--state-dir", (Join-Path $acceptanceRoot "controller-restart"), "--image", $Image, "--verify-controller-restart")) "PASS" | Out-Null

    Invoke-Step "step7_ruff" "uv" @("run", "--locked", "--extra", "dev", "ruff", "check", ".") | Out-Null
    Invoke-Step "step7_mypy" "uv" @("run", "--locked", "--extra", "dev", "mypy", ".") | Out-Null
    Invoke-Step "step7_pytest" "uv" @("run", "--locked", "--extra", "dev", "python", "-m", "pytest", "-q") | Out-Null

    Invoke-JsonStep "step8_mcp_sdk" @(
        "run", "--locked", "--extra", "dev", "python", "scripts/verify_mcp_sdk_runtime.py",
        "--project-root", ".", "--state-dir", (Join-Path $acceptanceRoot "mcp-sdk")
    ) "PASS" | Out-Null

    Invoke-JsonStep "step8_mcp_manual_rollback" @(
        "run", "--locked", "--extra", "dev", "python", "scripts/verify_mcp_runtime.py",
        "--project-root", ".", "--state-dir", (Join-Path $acceptanceRoot "mcp-manual")
    ) "PASS" | Out-Null

    $dirtyAfter = @(Invoke-Native "git" @("status", "--porcelain=v1"))
    if ($dirtyAfter.Count -gt 0) {
        throw "ASSERTION_FAILED: acceptance changed tracked or unignored repository state"
    }

    $report.git.clean_after = $true
    $report.status = "PASS"
    $report.ended_at = (Get-Date).ToString("o")
    Save-Report

    Write-Host "WINDOWS_DOCKER_HOST_ACCEPTANCE=PASS"
    Write-Host "HEAD=$localHead"
    Write-Host "REPORT=$reportPath"
    exit 0
}
catch {
    $message = $_.Exception.Message
    $report.status = if ($message.StartsWith("HOST_BLOCKED:")) { "BLOCKED" } else { "FAIL" }
    $report.error = $message
    $report.ended_at = (Get-Date).ToString("o")
    Save-Report
    Write-Host "WINDOWS_DOCKER_HOST_ACCEPTANCE=$($report.status)"
    Write-Host "ERROR=$message"
    if ($reportPath) {
        Write-Host "REPORT=$reportPath"
    }
    exit 1
}
finally {
    Pop-Location
}
