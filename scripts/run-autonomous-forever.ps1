param(
  [int]$SleepSeconds = 10,
  [int]$OpenAiTimeoutMs = 180000,
  [int]$OpenAiMaxRetries = 2,
  [int]$VerifyEvery = 10,
  [string]$StateRoot = "",
  [string]$Symbol = "",
  [string]$GoalMode = "",
  [string]$ResearchTargetId = "",
  [string]$ChartSymbol = "",
  [string]$ChartTimeframe = "",
  [string]$ChartType = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "runtime-json.ps1")

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
if ([string]::IsNullOrWhiteSpace($ResearchTargetId) -and [string]::IsNullOrWhiteSpace($Symbol)) {
  $ResearchTargetId = "qqq-120m-af"
}

function Get-ResearchTargetConfig {
  param([string]$TargetId)
  if ([string]::IsNullOrWhiteSpace($TargetId)) {
    return $null
  }
  $targetPath = Join-Path $ProjectRoot ("config\targets\{0}.json" -f $TargetId)
  if (-not (Test-Path -LiteralPath $targetPath)) {
    throw "Unable to load research target config: $targetPath"
  }
  return Get-Content -LiteralPath $targetPath -Raw | ConvertFrom-Json
}

$TargetConfig = Get-ResearchTargetConfig -TargetId $ResearchTargetId
$ConfiguredStateRoot = $StateRoot
if ([string]::IsNullOrWhiteSpace($ConfiguredStateRoot)) {
  if (-not [string]::IsNullOrWhiteSpace($ResearchTargetId)) {
    $StateRoot = Join-Path $ProjectRoot ("state\targets\{0}\pi-autoresearch" -f $ResearchTargetId)
  } else {
    $StateRoot = Join-Path $ProjectRoot "state\pi-autoresearch"
  }
} elseif ([System.IO.Path]::IsPathRooted($ConfiguredStateRoot)) {
  $StateRoot = [System.IO.Path]::GetFullPath($ConfiguredStateRoot)
} else {
  $StateRoot = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot $ConfiguredStateRoot))
}

if ($TargetConfig) {
  if ([string]::IsNullOrWhiteSpace($ChartSymbol)) {
    $ChartSymbol = [string]$TargetConfig.symbol
  }
  if ([string]::IsNullOrWhiteSpace($ChartTimeframe)) {
    $ChartTimeframe = [string]$TargetConfig.timeframe
  }
}

$RuntimeRoot = Join-Path $StateRoot "runtime"
$LogRoot = Join-Path $StateRoot "logs"
$StopFile = Join-Path $RuntimeRoot "STOP_AUTONOMOUS_LOOP"
$PidFile = Join-Path $RuntimeRoot "autonomous-loop.pid"
$HeartbeatFile = Join-Path $RuntimeRoot "autonomous-loop-heartbeat.json"
$LogFile = Join-Path $LogRoot ("autonomous-loop-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))

New-Item -ItemType Directory -Force -Path $RuntimeRoot, $LogRoot | Out-Null
& (Join-Path $PSScriptRoot "stop-af.ps1") -ProjectRoot $ProjectRoot -StateRoot $StateRoot -GraceSeconds 30 -Quiet

function Write-StaleHeartbeat {
  param(
    $Pid,
    [string]$Reason
  )
  Write-AtomicJson -LiteralPath $HeartbeatFile -Value @{
    pid = $Pid
    status = "stale"
    owner = "run-autonomous-forever"
    staleReason = $Reason
    lastCheckedAt = (Get-Date).ToUniversalTime().ToString("o")
    heartbeatPath = $HeartbeatFile
    pidPath = $PidFile
  }
}

if (Test-Path -LiteralPath $PidFile) {
  $existingPid = Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1
  [int]$existingPidValue = 0
  $hasValidPid = [int]::TryParse([string]$existingPid, [ref]$existingPidValue)
  if ($hasValidPid -and (Get-Process -Id $existingPidValue -ErrorAction SilentlyContinue)) {
    throw "Autonomous loop already appears to be running with PID $existingPidValue."
  }
  $staleReason = if ($hasValidPid) { "pid_not_running" } else { "pid_file_invalid" }
  $stalePid = if ($hasValidPid) { $existingPidValue } else { $null }
  Write-StaleHeartbeat -Pid $stalePid -Reason $staleReason
  Remove-Item -LiteralPath $PidFile -Force
}
if (Test-Path -LiteralPath $StopFile) {
  Remove-Item -LiteralPath $StopFile -Force
}

Set-Content -LiteralPath $PidFile -Value $PID -Encoding ASCII

$env:PINE_EVALUATION_EXECUTOR = "local-backtest"
$env:AF_STATE_ROOT = [string]$StateRoot
if (-not [string]::IsNullOrWhiteSpace($ResearchTargetId)) {
  $env:AF_RESEARCH_TARGET_ID = $ResearchTargetId
}
if (-not [string]::IsNullOrWhiteSpace($Symbol) -and -not [string]::IsNullOrWhiteSpace($ResearchTargetId)) {
  throw "Use either -Symbol or -ResearchTargetId, not both."
}
if (-not [string]::IsNullOrWhiteSpace($GoalMode)) {
  $env:AF_RESEARCH_GOAL_MODE = $GoalMode
}
if (-not [string]::IsNullOrWhiteSpace($ChartSymbol)) {
  $env:AF_CHART_SYMBOL = $ChartSymbol
}
if (-not [string]::IsNullOrWhiteSpace($ChartTimeframe)) {
  $env:AF_CHART_TIMEFRAME = $ChartTimeframe
}
if (-not [string]::IsNullOrWhiteSpace($ChartType)) {
  $env:AF_CHART_TYPE = $ChartType
}
$env:OPENAI_REQUEST_TIMEOUT_MS = [string]$OpenAiTimeoutMs
$env:OPENAI_MAX_RETRIES = [string]$OpenAiMaxRetries

function Write-LoopLog {
  param([string]$Message)
  $line = "[{0}] {1}" -f (Get-Date -Format "o"), $Message
  Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
}

function Invoke-Af {
  param([string[]]$Arguments)
  Push-Location $ProjectRoot
  $previousErrorActionPreference = $ErrorActionPreference
  try {
    $ErrorActionPreference = "Continue"
    & node "dist/cli/index.js" @Arguments 2>&1 | ForEach-Object {
      Add-Content -LiteralPath $LogFile -Value $_ -Encoding UTF8
    }
    return $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $previousErrorActionPreference
    Pop-Location
  }
}

function Get-LoopTelemetry {
  $proc = Get-Process -Id $PID -ErrorAction SilentlyContinue
  $os = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
  $totalBytes = if ($os) { [double]$os.TotalVisibleMemorySize * 1024 } else { 0 }
  $freeBytes = if ($os) { [double]$os.FreePhysicalMemory * 1024 } else { 0 }
  $rssBytes = if ($proc) { [double]$proc.WorkingSet64 } else { 0 }
  $privateBytes = if ($proc) { [double]$proc.PrivateMemorySize64 } else { 0 }
  $warnBytes = if ($totalBytes -gt 0) { [math]::Min([math]::Max($totalBytes * 0.10, 512MB), 2048MB) } else { 2048MB }
  $criticalBytes = if ($totalBytes -gt 0) { [math]::Min([math]::Max($totalBytes * 0.14, 768MB), 3072MB) } else { 3072MB }
  $pressure = if ($rssBytes -ge $criticalBytes) { "critical" } elseif ($rssBytes -ge $warnBytes) { "warning" } else { "ok" }
  return @{
    rssMB = [math]::Round($rssBytes / 1MB, 2)
    privateMB = [math]::Round($privateBytes / 1MB, 2)
    systemTotalMemoryMB = [math]::Round($totalBytes / 1MB, 2)
    systemFreeMemoryMB = [math]::Round($freeBytes / 1MB, 2)
    warningThresholdMB = [math]::Round($warnBytes / 1MB, 2)
    criticalThresholdMB = [math]::Round($criticalBytes / 1MB, 2)
    pressure = $pressure
  }
}

function Get-NodeTelemetry {
  $nodeTelemetryPath = Join-Path $RuntimeRoot "node-memory-telemetry.json"
  if (-not (Test-Path -LiteralPath $nodeTelemetryPath)) {
    return $null
  }
  try {
    return Get-Content -LiteralPath $nodeTelemetryPath -Raw | ConvertFrom-Json
  } catch {
    return $null
  }
}

$iteration = 0
$memoryWarningTimes = @()
Write-LoopLog "autonomous forever loop started; pid=$PID; project=$ProjectRoot; stateRoot=$StateRoot; symbol=$Symbol; goalMode=$env:AF_RESEARCH_GOAL_MODE; target=$env:AF_RESEARCH_TARGET_ID; chart=$($env:AF_CHART_SYMBOL):$($env:AF_CHART_TIMEFRAME); mode=local-only"
Write-LoopLog "stop file: $StopFile"

try {
  while ($true) {
    if (Test-Path -LiteralPath $StopFile) {
      Write-LoopLog "stop file detected; exiting"
      break
    }

    $iteration += 1
    $startedAt = Get-Date
    $memory = Get-LoopTelemetry
    Write-AtomicJson -LiteralPath $HeartbeatFile -Value @{
      pid = $PID
      iteration = $iteration
      status = "running"
      owner = "run-autonomous-forever"
      staleReason = $null
      lastCheckedAt = (Get-Date).ToUniversalTime().ToString("o")
      startedAt = $startedAt.ToUniversalTime().ToString("o")
      logFile = $LogFile
      stateRoot = $StateRoot
      researchSymbol = $Symbol
      goalMode = $env:AF_RESEARCH_GOAL_MODE
      researchTargetId = $env:AF_RESEARCH_TARGET_ID
      chartSymbol = $env:AF_CHART_SYMBOL
      chartTimeframe = $env:AF_CHART_TIMEFRAME
      currentTrainingMode = @{
        mechanism = "shared_af_autonomous_learning"
        targetId = $env:AF_RESEARCH_TARGET_ID
        symbol = $env:AF_CHART_SYMBOL
        timeframe = $env:AF_CHART_TIMEFRAME
        stateRoot = $StateRoot
        validationMode = "local_only"
      }
      memory = $memory
      nodeMemory = Get-NodeTelemetry
    }

    Write-LoopLog "iteration ${iteration}: run-autonomous-loop start"
    $runArguments = @("run-autonomous-loop", "--count", "1")
    if (-not [string]::IsNullOrWhiteSpace($ResearchTargetId)) {
      $runArguments += @("--target", [string]$ResearchTargetId)
    } elseif (-not [string]::IsNullOrWhiteSpace($Symbol)) {
      $runArguments += @("--symbol", [string]$Symbol)
    }
    if (-not [string]::IsNullOrWhiteSpace($GoalMode)) {
      $runArguments += @("--mode", [string]$GoalMode)
    }
    $runExit = Invoke-Af -Arguments $runArguments
    Write-LoopLog "iteration ${iteration}: run-autonomous-loop exit=$runExit"

    $memory = Get-LoopTelemetry
    if ($memory.pressure -ne "ok") {
      $memoryWarningTimes += (Get-Date)
      $cutoff = (Get-Date).AddSeconds(-120)
      $memoryWarningTimes = @($memoryWarningTimes | Where-Object { $_ -ge $cutoff })
      Write-LoopLog ("iteration ${iteration}: memory pressure={0}; rssMB={1}" -f $memory.pressure, $memory.rssMB)
    }
    $selfHealingActive = $memoryWarningTimes.Count -ge 5
    $effectiveVerifyEvery = if ($selfHealingActive) { [math]::Max($VerifyEvery, 20) } else { $VerifyEvery }
    $effectiveSleepSeconds = if ($selfHealingActive) { [math]::Max($SleepSeconds, [int][math]::Ceiling($SleepSeconds * 1.5)) } else { $SleepSeconds }

    if ($effectiveVerifyEvery -gt 0 -and (($iteration % $effectiveVerifyEvery) -eq 0) -and $memory.pressure -ne "critical") {
      Write-LoopLog "iteration ${iteration}: validate-ledger start"
      $validateStartedAt = Get-Date
      $ledgerExit = Invoke-Af -Arguments @("validate-ledger")
      $validateDurationSeconds = [math]::Round(((Get-Date) - $validateStartedAt).TotalSeconds, 3)
      Write-LoopLog "iteration ${iteration}: validate-ledger exit=$ledgerExit durationSeconds=$validateDurationSeconds"

      Write-LoopLog "iteration ${iteration}: rebuild-indexes --verify start"
      $rebuildStartedAt = Get-Date
      $indexExit = Invoke-Af -Arguments @("rebuild-indexes", "--verify")
      $rebuildDurationSeconds = [math]::Round(((Get-Date) - $rebuildStartedAt).TotalSeconds, 3)
      Write-LoopLog "iteration ${iteration}: rebuild-indexes --verify exit=$indexExit durationSeconds=$rebuildDurationSeconds"
    } else {
      $ledgerExit = $null
      $indexExit = $null
      $validateDurationSeconds = $null
      $rebuildDurationSeconds = $null
      if ($memory.pressure -eq "critical") {
        Write-LoopLog "iteration ${iteration}: full validation skipped due to critical memory pressure"
      }
    }

    $completedAt = Get-Date
    Write-AtomicJson -LiteralPath $HeartbeatFile -Value @{
      pid = $PID
      iteration = $iteration
      status = "sleeping"
      owner = "run-autonomous-forever"
      staleReason = $null
      lastCheckedAt = (Get-Date).ToUniversalTime().ToString("o")
      lastRunExit = $runExit
      completedAt = $completedAt.ToUniversalTime().ToString("o")
      durationSeconds = [math]::Round(($completedAt - $startedAt).TotalSeconds, 3)
      logFile = $LogFile
      stateRoot = $StateRoot
      researchSymbol = $Symbol
      goalMode = $env:AF_RESEARCH_GOAL_MODE
      researchTargetId = $env:AF_RESEARCH_TARGET_ID
      chartSymbol = $env:AF_CHART_SYMBOL
      chartTimeframe = $env:AF_CHART_TIMEFRAME
      currentTrainingMode = @{
        mechanism = "shared_af_autonomous_learning"
        targetId = $env:AF_RESEARCH_TARGET_ID
        symbol = $env:AF_CHART_SYMBOL
        timeframe = $env:AF_CHART_TIMEFRAME
        stateRoot = $StateRoot
        validationMode = "local_only"
      }
      memory = $memory
      nodeMemory = Get-NodeTelemetry
      verifyEvery = $effectiveVerifyEvery
      selfHealingActive = $selfHealingActive
      lastLedgerExit = $ledgerExit
      lastIndexExit = $indexExit
      lastValidateDurationSeconds = $validateDurationSeconds
      lastRebuildDurationSeconds = $rebuildDurationSeconds
    }

    Start-Sleep -Seconds $effectiveSleepSeconds
  }
} catch {
  Write-LoopLog ("fatal error: {0}" -f $_.Exception.Message)
  Write-AtomicJson -LiteralPath $HeartbeatFile -Value @{
    pid = $PID
    iteration = $iteration
    status = "failed"
    owner = "run-autonomous-forever"
    staleReason = $null
    lastCheckedAt = (Get-Date).ToUniversalTime().ToString("o")
    error = $_.Exception.Message
    logFile = $LogFile
  }
  throw
} finally {
  if (Test-Path -LiteralPath $PidFile) {
    Remove-Item -LiteralPath $PidFile -Force
  }
  Write-LoopLog "autonomous forever loop stopped"
}
