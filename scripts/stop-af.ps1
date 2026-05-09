param(
  [string]$ProjectRoot = "",
  [string]$StateRoot = "",
  [int]$GraceSeconds = 30,
  [switch]$NoForce,
  [switch]$Quiet
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
  $ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
} elseif ([System.IO.Path]::IsPathRooted($ProjectRoot)) {
  $ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
} else {
  $ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $ProjectRoot))
}

if ([string]::IsNullOrWhiteSpace($StateRoot)) {
  $StateRoot = Join-Path $ProjectRoot "state\targets\qqq-120m-af\pi-autoresearch"
} elseif ([System.IO.Path]::IsPathRooted($StateRoot)) {
  $StateRoot = [System.IO.Path]::GetFullPath($StateRoot)
} else {
  $StateRoot = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot $StateRoot))
}

$RuntimeRoot = Join-Path $StateRoot "runtime"
$StopFile = Join-Path $RuntimeRoot "STOP_AUTONOMOUS_LOOP"
$WorkerStopFile = Join-Path $RuntimeRoot "STOP_TV_CALIBRATION_WORKER"
$PidFiles = @(
  (Join-Path $RuntimeRoot "autonomous-loop.pid"),
  (Join-Path $RuntimeRoot "tv-calibration-worker.pid")
)

function Write-StopAfLog {
  param([string]$Message)
  if (-not $Quiet.IsPresent) {
    Write-Host $Message
  }
}

function Test-IsAfCommandLine {
  param([string]$CommandLine)
  if ([string]::IsNullOrWhiteSpace($CommandLine)) {
    return $false
  }

  $normalizedRoot = $ProjectRoot.TrimEnd('\')
  if ($CommandLine.IndexOf($normalizedRoot, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
    return $false
  }

  $needles = @(
    "dist/cli/index.js",
    "dist\cli\index.js",
    "src/cli/index.ts",
    "src\cli\index.ts",
    "run-autonomous-forever.ps1",
    "codex-supervised-loop.ps1",
    "run-tv-calibration-worker.ps1",
    "scripts/stop-af.ps1",
    "scripts\stop-af.ps1"
  )
  foreach ($needle in $needles) {
    if ($CommandLine.IndexOf($needle, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
      return $true
    }
  }

  return $false
}

function Get-AfProcesses {
  Get-CimInstance Win32_Process |
    Where-Object {
      $_.ProcessId -ne $PID -and (Test-IsAfCommandLine -CommandLine $_.CommandLine)
    } |
    Sort-Object ProcessId
}

function Test-IsAfProcessId {
  param([int]$ProcessId)
  $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
  return ($process -and (Test-IsAfCommandLine -CommandLine $process.CommandLine))
}

function Remove-StalePidFiles {
  foreach ($pidFile in $PidFiles) {
    if (-not (Test-Path -LiteralPath $pidFile)) {
      continue
    }

    $pidRaw = Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    [int]$pidValue = 0
    $hasValidPid = [int]::TryParse([string]$pidRaw, [ref]$pidValue)
    if (-not $hasValidPid) {
      Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
      Write-StopAfLog "removed invalid pid file: $pidFile"
      continue
    }

    $running = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
    if (-not $running -or -not (Test-IsAfProcessId -ProcessId $pidValue)) {
      Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
      Write-StopAfLog "removed stale pid file: $pidFile"
    }
  }
}

New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
New-Item -ItemType File -Force -Path $StopFile | Out-Null
New-Item -ItemType File -Force -Path $WorkerStopFile | Out-Null

$initialProcesses = @(Get-AfProcesses)
if ($initialProcesses.Count -gt 0) {
  Write-StopAfLog "requested AF shutdown for $($initialProcesses.Count) process(es)"
}

if ($GraceSeconds -gt 0 -and $initialProcesses.Count -gt 0) {
  $deadline = (Get-Date).AddSeconds($GraceSeconds)
  do {
    Start-Sleep -Seconds 1
    $remaining = @(Get-AfProcesses)
  } while ($remaining.Count -gt 0 -and (Get-Date) -lt $deadline)
} else {
  $remaining = @(Get-AfProcesses)
}

if ($remaining.Count -gt 0 -and -not $NoForce.IsPresent) {
  foreach ($process in $remaining) {
    Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    Write-StopAfLog "stopped AF process pid=$($process.ProcessId) name=$($process.Name)"
  }
  Start-Sleep -Milliseconds 300
}

Remove-StalePidFiles

$finalProcesses = @(Get-AfProcesses)
if ($finalProcesses.Count -gt 0) {
  $ids = ($finalProcesses | ForEach-Object { $_.ProcessId }) -join ", "
  throw "AF process(es) still running after stop request: $ids"
}

Write-StopAfLog "AF runtime is stopped for $ProjectRoot"
