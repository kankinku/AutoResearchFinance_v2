param(
  [int]$CalibrationBudget = 1,
  [int]$SleepSeconds = 10
)

$ErrorActionPreference = "Continue"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$RuntimeRoot = Join-Path $ProjectRoot "state/pi-autoresearch/runtime"
$LogRoot = Join-Path $ProjectRoot "state/pi-autoresearch/logs"
$PidPath = Join-Path $RuntimeRoot "autonomous-loop.pid"
$StopPath = Join-Path $RuntimeRoot "STOP_AUTONOMOUS_LOOP"
$HeartbeatPath = Join-Path $RuntimeRoot "autonomous-loop-heartbeat.json"
$LogFile = Join-Path $LogRoot ("codex-supervised-loop-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))

New-Item -ItemType Directory -Force -Path $RuntimeRoot, $LogRoot | Out-Null
Remove-Item -LiteralPath $StopPath -Force -ErrorAction SilentlyContinue
Set-Content -LiteralPath $PidPath -Value $PID -Encoding UTF8

Push-Location $ProjectRoot
try {
  $env:PINE_EVALUATION_EXECUTOR = "local-backtest"
  $env:AF_AUTO_PROCESS_CALIBRATION = "true"
  $env:OPENAI_REQUEST_TIMEOUT_MS = "180000"
  $env:OPENAI_MAX_RETRIES = "2"

  Add-Content -LiteralPath $LogFile -Value "[$(Get-Date -Format o)] codex supervised loop started pid=$PID"
  $iteration = 0

  while ($true) {
    if (Test-Path -LiteralPath $StopPath) {
      Add-Content -LiteralPath $LogFile -Value "[$(Get-Date -Format o)] stop file detected; exiting"
      break
    }

    $iteration += 1
    $startedAt = Get-Date
    Add-Content -LiteralPath $LogFile -Value "[$($startedAt.ToString('o'))] iteration ${iteration}: run-autonomous-loop start"
    & node dist/cli/index.js run-autonomous-loop --count 1 --auto-process-calibration true --calibration-budget $CalibrationBudget >> $LogFile 2>&1
    $exitCode = $LASTEXITCODE
    $duration = [Math]::Round(((Get-Date) - $startedAt).TotalSeconds, 3)

    [pscustomobject]@{
      pid = $PID
      status = "sleeping"
      supervisor = "codex"
      iteration = $iteration
      generatedAt = (Get-Date).ToUniversalTime().ToString("o")
      lastRunExit = $exitCode
      durationSeconds = $duration
      autoProcessCalibration = $true
      calibrationBudget = $CalibrationBudget
      logFile = $LogFile
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
