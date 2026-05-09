param(
  [int]$CalibrationBudget = 1,
  [int]$SleepSeconds = 10,
  [switch]$EnableTradingViewCalibration,
  [string]$ResearchTargetId = "qqq-120m-af",
  [string]$StateRoot = ""
)

$ErrorActionPreference = "Continue"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
if ([string]::IsNullOrWhiteSpace($StateRoot)) {
  $StateRoot = Join-Path $ProjectRoot ("state/targets/{0}/pi-autoresearch" -f $ResearchTargetId)
} elseif ([System.IO.Path]::IsPathRooted($StateRoot)) {
  $StateRoot = [System.IO.Path]::GetFullPath($StateRoot)
} else {
  $StateRoot = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot $StateRoot))
}
$TargetConfigPath = Join-Path $ProjectRoot ("config/targets/{0}.json" -f $ResearchTargetId)
$TargetConfig = if (Test-Path -LiteralPath $TargetConfigPath) {
  Get-Content -LiteralPath $TargetConfigPath -Raw | ConvertFrom-Json
} else {
  $null
}
$RuntimeRoot = Join-Path $StateRoot "runtime"
$LogRoot = Join-Path $StateRoot "logs"
$PidPath = Join-Path $RuntimeRoot "autonomous-loop.pid"
$StopPath = Join-Path $RuntimeRoot "STOP_AUTONOMOUS_LOOP"
$HeartbeatPath = Join-Path $RuntimeRoot "autonomous-loop-heartbeat.json"
$LogFile = Join-Path $LogRoot ("codex-supervised-loop-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))

New-Item -ItemType Directory -Force -Path $RuntimeRoot, $LogRoot | Out-Null
& (Join-Path $PSScriptRoot "stop-af.ps1") -ProjectRoot $ProjectRoot -StateRoot $StateRoot -GraceSeconds 30 -Quiet
Remove-Item -LiteralPath $StopPath -Force -ErrorAction SilentlyContinue

function Write-StaleHeartbeat {
  param(
    $Pid,
    [string]$Reason
  )
  [pscustomobject]@{
    pid = $Pid
    status = "stale"
    owner = "codex-supervised-loop"
    staleReason = $Reason
    lastCheckedAt = (Get-Date).ToUniversalTime().ToString("o")
    heartbeatPath = $HeartbeatPath
    pidPath = $PidPath
  } | ConvertTo-Json -Compress | Set-Content -LiteralPath $HeartbeatPath -Encoding UTF8
}

if (Test-Path -LiteralPath $PidPath) {
  $existingPid = Get-Content -LiteralPath $PidPath -ErrorAction SilentlyContinue | Select-Object -First 1
  [int]$existingPidValue = 0
  $hasValidPid = [int]::TryParse([string]$existingPid, [ref]$existingPidValue)
  if ($hasValidPid -and (Get-Process -Id $existingPidValue -ErrorAction SilentlyContinue)) {
    throw "Autonomous loop already appears to be running with PID $existingPidValue."
  }
  $staleReason = if ($hasValidPid) { "pid_not_running" } else { "pid_file_invalid" }
  $stalePid = if ($hasValidPid) { $existingPidValue } else { $null }
  Write-StaleHeartbeat -Pid $stalePid -Reason $staleReason
  Remove-Item -LiteralPath $PidPath -Force
}

Set-Content -LiteralPath $PidPath -Value $PID -Encoding UTF8

Push-Location $ProjectRoot
try {
  $AutoProcessCalibration = [bool]$EnableTradingViewCalibration
  $AutoProcessCalibrationText = if ($AutoProcessCalibration) { "true" } else { "false" }

  $env:PINE_EVALUATION_EXECUTOR = "local-backtest"
  $env:AF_STATE_ROOT = [string]$StateRoot
  $env:AF_RESEARCH_TARGET_ID = [string]$ResearchTargetId
  if ($TargetConfig) {
    $env:TRADINGVIEW_CHART_SYMBOL = [string]$TargetConfig.symbol
    $env:TRADINGVIEW_CHART_TIMEFRAME = [string]$TargetConfig.timeframe
  }
  $env:AF_AUTO_PROCESS_CALIBRATION = $AutoProcessCalibrationText
  $env:OPENAI_REQUEST_TIMEOUT_MS = "180000"
  $env:OPENAI_MAX_RETRIES = "2"

  Add-Content -LiteralPath $LogFile -Value "[$(Get-Date -Format o)] codex supervised loop started pid=$PID target=$ResearchTargetId stateRoot=$StateRoot chart=$($env:TRADINGVIEW_CHART_SYMBOL):$($env:TRADINGVIEW_CHART_TIMEFRAME) autoProcessCalibration=$AutoProcessCalibrationText"
  $iteration = 0

  while ($true) {
    if (Test-Path -LiteralPath $StopPath) {
      Add-Content -LiteralPath $LogFile -Value "[$(Get-Date -Format o)] stop file detected; exiting"
      break
    }

    $iteration += 1
    $startedAt = Get-Date
    Add-Content -LiteralPath $LogFile -Value "[$($startedAt.ToString('o'))] iteration ${iteration}: run-autonomous-loop start"
    & node dist/cli/index.js run-autonomous-loop --target $ResearchTargetId --count 1 --auto-process-calibration $AutoProcessCalibrationText --calibration-budget $CalibrationBudget >> $LogFile 2>&1
    $exitCode = $LASTEXITCODE
    $duration = [Math]::Round(((Get-Date) - $startedAt).TotalSeconds, 3)

    [pscustomobject]@{
      pid = $PID
      status = "sleeping"
      supervisor = "codex"
      owner = "codex-supervised-loop"
      staleReason = $null
      lastCheckedAt = (Get-Date).ToUniversalTime().ToString("o")
      iteration = $iteration
      generatedAt = (Get-Date).ToUniversalTime().ToString("o")
      lastRunExit = $exitCode
      durationSeconds = $duration
      autoProcessCalibration = $AutoProcessCalibration
      calibrationBudget = $CalibrationBudget
      logFile = $LogFile
      stateRoot = $StateRoot
      researchTargetId = $ResearchTargetId
      chartSymbol = $env:TRADINGVIEW_CHART_SYMBOL
      chartTimeframe = $env:TRADINGVIEW_CHART_TIMEFRAME
      currentTrainingMode = @{
        mechanism = "shared_af_autonomous_learning"
        targetId = $ResearchTargetId
        symbol = $env:TRADINGVIEW_CHART_SYMBOL
        timeframe = $env:TRADINGVIEW_CHART_TIMEFRAME
        stateRoot = $StateRoot
      }
    } | ConvertTo-Json -Compress | Set-Content -LiteralPath $HeartbeatPath -Encoding UTF8

    Add-Content -LiteralPath $LogFile -Value "[$(Get-Date -Format o)] iteration ${iteration}: run-autonomous-loop exit=$exitCode durationSeconds=$duration"
    if (Test-Path -LiteralPath $StopPath) {
      Add-Content -LiteralPath $LogFile -Value "[$(Get-Date -Format o)] stop file detected after iteration; exiting"
      break
    }

    Start-Sleep -Seconds $SleepSeconds
  }
} finally {
  Pop-Location
  Remove-Item -LiteralPath $PidPath -Force -ErrorAction SilentlyContinue
  Add-Content -LiteralPath $LogFile -Value "[$(Get-Date -Format o)] codex supervised loop stopped"
}
