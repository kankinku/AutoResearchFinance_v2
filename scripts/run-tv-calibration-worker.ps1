param(
  [int]$SleepSeconds = 10,
  [int]$CalibrationBudget = 1,
  [int]$CalibrationTimeoutMs = 60000,
  [string]$PromotionVerificationExecutor = "tradingview-web-playwright",
  [string]$TradingViewWebCdpUrl = "http://127.0.0.1:9223",
  [string]$TradingViewWebChartUrl = "https://www.tradingview.com/chart/",
  [string]$StateRoot = "",
  [string]$ResearchTargetId = "",
  [string]$ChartSymbol = "",
  [string]$ChartTimeframe = "",
  [string]$ChartType = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "runtime-json.ps1")

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
if ([string]::IsNullOrWhiteSpace($ResearchTargetId)) {
  $ResearchTargetId = "qqq-120m-af"
}
$TargetConfigPath = Join-Path $ProjectRoot ("config\targets\{0}.json" -f $ResearchTargetId)
$TargetConfig = if (Test-Path -LiteralPath $TargetConfigPath) {
  Get-Content -LiteralPath $TargetConfigPath -Raw | ConvertFrom-Json
} else {
  $null
}
$ConfiguredStateRoot = $StateRoot
if ([string]::IsNullOrWhiteSpace($ConfiguredStateRoot)) {
  $StateRoot = Join-Path $ProjectRoot ("state\targets\{0}\pi-autoresearch" -f $ResearchTargetId)
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
$GlobalStopFile = Join-Path $RuntimeRoot "STOP_AUTONOMOUS_LOOP"
$WorkerStopFile = Join-Path $RuntimeRoot "STOP_TV_CALIBRATION_WORKER"
$PidFile = Join-Path $RuntimeRoot "tv-calibration-worker.pid"
$HeartbeatFile = Join-Path $RuntimeRoot "tv-calibration-worker-heartbeat.json"
$LogFile = Join-Path $LogRoot ("tv-calibration-worker-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))

New-Item -ItemType Directory -Force -Path $RuntimeRoot, $LogRoot | Out-Null

function Write-WorkerLog {
  param([string]$Message)
  $line = "[{0}] {1}" -f (Get-Date -Format "o"), $Message
  Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
}

function Write-WorkerHeartbeat {
  param(
    [int]$Iteration,
    [string]$Status,
    [Nullable[int]]$LastExitCode = $null,
    [Nullable[double]]$DurationSeconds = $null,
    [string]$ErrorMessage = $null
  )
  $payload = @{
    pid = $PID
    iteration = $Iteration
    status = $Status
    owner = "tv-calibration-worker"
    lastCheckedAt = (Get-Date).ToUniversalTime().ToString("o")
    logFile = $LogFile
    stateRoot = $StateRoot
    researchTargetId = $env:AF_RESEARCH_TARGET_ID
    chartSymbol = $env:TRADINGVIEW_CHART_SYMBOL
    chartTimeframe = $env:TRADINGVIEW_CHART_TIMEFRAME
    currentTrainingMode = @{
      targetId = $env:AF_RESEARCH_TARGET_ID
      symbol = $env:TRADINGVIEW_CHART_SYMBOL
      timeframe = $env:TRADINGVIEW_CHART_TIMEFRAME
      stateRoot = $StateRoot
    }
    calibrationBudget = $CalibrationBudget
    calibrationTimeoutMs = $CalibrationTimeoutMs
    promotionVerificationExecutor = $env:AF_PROMOTION_VERIFICATION_EXECUTOR
    tradingViewWebCdpUrl = $env:TRADINGVIEW_WEB_CDP_URL
  }
  if ($null -ne $LastExitCode) {
    $payload.lastExitCode = $LastExitCode
  }
  if ($null -ne $DurationSeconds) {
    $payload.durationSeconds = $DurationSeconds
  }
  if (-not [string]::IsNullOrWhiteSpace($ErrorMessage)) {
    $payload.error = $ErrorMessage
  }
  Write-AtomicJson -LiteralPath $HeartbeatFile -Value $payload
}

function Stop-StaleWorkerPid {
  if (-not (Test-Path -LiteralPath $PidFile)) {
    return
  }
  $existingPid = Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1
  [int]$existingPidValue = 0
  $hasValidPid = [int]::TryParse([string]$existingPid, [ref]$existingPidValue)
  if ($hasValidPid -and (Get-Process -Id $existingPidValue -ErrorAction SilentlyContinue)) {
    throw "TV calibration worker already appears to be running with PID $existingPidValue."
  }
  Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
}

function Invoke-CalibrationCommand {
  param([int]$Iteration)

  $process = New-Object System.Diagnostics.Process
  $process.StartInfo.FileName = "node.exe"
  $process.StartInfo.Arguments = "dist/cli/index.js process-tv-calibration-queue --max-candidates $CalibrationBudget"
  $process.StartInfo.WorkingDirectory = [string]$ProjectRoot
  $process.StartInfo.UseShellExecute = $false
  $process.StartInfo.RedirectStandardOutput = $true
  $process.StartInfo.RedirectStandardError = $true
  $process.StartInfo.CreateNoWindow = $true

  $started = $process.Start()
  if (-not $started) {
    Write-WorkerLog "iteration ${Iteration}: failed to start process-tv-calibration-queue"
    return -1
  }
  $stdoutTask = $process.StandardOutput.ReadToEndAsync()
  $stderrTask = $process.StandardError.ReadToEndAsync()

  $exited = $process.WaitForExit($CalibrationTimeoutMs)
  if (-not $exited) {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    Write-WorkerLog "iteration ${Iteration}: process-tv-calibration-queue timed out after ${CalibrationTimeoutMs}ms; child pid=$($process.Id)"
    return 124
  }
  $process.WaitForExit()

  if (-not [string]::IsNullOrEmpty($stdoutTask.Result)) {
    $stdoutTask.Result -split "`r?`n" | Where-Object { $_.Length -gt 0 } | ForEach-Object {
      Add-Content -LiteralPath $LogFile -Value $_ -Encoding UTF8
    }
  }
  if (-not [string]::IsNullOrEmpty($stderrTask.Result)) {
    $stderrTask.Result -split "`r?`n" | Where-Object { $_.Length -gt 0 } | ForEach-Object {
      Add-Content -LiteralPath $LogFile -Value $_ -Encoding UTF8
    }
  }
  return [int]$process.ExitCode
}

Stop-StaleWorkerPid
if (Test-Path -LiteralPath $WorkerStopFile) {
  Remove-Item -LiteralPath $WorkerStopFile -Force
}
Set-Content -LiteralPath $PidFile -Value $PID -Encoding ASCII

$env:PINE_EVALUATION_EXECUTOR = "local-backtest"
$env:AF_STATE_ROOT = [string]$StateRoot
if (-not [string]::IsNullOrWhiteSpace($ResearchTargetId)) {
  $env:AF_RESEARCH_TARGET_ID = $ResearchTargetId
}
if (-not [string]::IsNullOrWhiteSpace($ChartSymbol)) {
  $env:TRADINGVIEW_CHART_SYMBOL = $ChartSymbol
}
if (-not [string]::IsNullOrWhiteSpace($ChartTimeframe)) {
  $env:TRADINGVIEW_CHART_TIMEFRAME = $ChartTimeframe
}
if (-not [string]::IsNullOrWhiteSpace($ChartType)) {
  $env:TRADINGVIEW_CHART_TYPE = $ChartType
}
$env:AF_AUTO_PROCESS_CALIBRATION = "true"
$env:AF_CALIBRATION_BUDGET = [string]$CalibrationBudget
$env:AF_CALIBRATION_TIMEOUT_MS = [string]$CalibrationTimeoutMs
$env:AF_TV_CALIBRATION_MODE = "live"
if (-not [string]::IsNullOrWhiteSpace($PromotionVerificationExecutor)) {
  $env:AF_PROMOTION_VERIFICATION_EXECUTOR = $PromotionVerificationExecutor
}
if (-not [string]::IsNullOrWhiteSpace($TradingViewWebCdpUrl)) {
  $env:TRADINGVIEW_WEB_CDP_URL = $TradingViewWebCdpUrl
}
if (-not [string]::IsNullOrWhiteSpace($TradingViewWebChartUrl)) {
  $env:TRADINGVIEW_WEB_CHART_URL = $TradingViewWebChartUrl
}

$iteration = 0
$lastExitCode = $null
$lastDurationSeconds = $null
Write-WorkerLog "tv calibration worker started; pid=$PID; project=$ProjectRoot; stateRoot=$StateRoot; target=$env:AF_RESEARCH_TARGET_ID; chart=$($env:TRADINGVIEW_CHART_SYMBOL):$($env:TRADINGVIEW_CHART_TIMEFRAME); calibrationBudget=$CalibrationBudget; promotionVerificationExecutor=$env:AF_PROMOTION_VERIFICATION_EXECUTOR"
Write-WorkerLog "stop files: $GlobalStopFile / $WorkerStopFile"

try {
  while ($true) {
    if ((Test-Path -LiteralPath $GlobalStopFile) -or (Test-Path -LiteralPath $WorkerStopFile)) {
      Write-WorkerLog "stop file detected; exiting"
      break
    }

    $iteration += 1
    $startedAt = Get-Date
    Write-WorkerHeartbeat -Iteration $iteration -Status "running" -LastExitCode $lastExitCode -DurationSeconds $lastDurationSeconds
    Write-WorkerLog "iteration ${iteration}: process-tv-calibration-queue start"
    $exitCode = Invoke-CalibrationCommand -Iteration $iteration
    $durationSeconds = [math]::Round(((Get-Date) - $startedAt).TotalSeconds, 3)
    $lastExitCode = $exitCode
    $lastDurationSeconds = $durationSeconds
    Write-WorkerLog "iteration ${iteration}: process-tv-calibration-queue exit=$exitCode durationSeconds=$durationSeconds"
    Write-WorkerHeartbeat -Iteration $iteration -Status "sleeping" -LastExitCode $lastExitCode -DurationSeconds $lastDurationSeconds

    Start-Sleep -Seconds $SleepSeconds
  }
} catch {
  Write-WorkerLog ("fatal error: {0}" -f $_.Exception.Message)
  Write-WorkerHeartbeat -Iteration $iteration -Status "failed" -ErrorMessage $_.Exception.Message
  throw
} finally {
  Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
  Write-WorkerLog "tv calibration worker stopped"
}
