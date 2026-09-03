param(
    [string]$StateDir = "state",
    [string]$EnvFile = ".env",
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8080
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = (Get-Command python).Source
$Arguments = @(
    "-m", "runtime.dashboard_supervisor",
    "--project-root", $ProjectRoot,
    "--state-dir", $StateDir,
    "--env-file", $EnvFile,
    "--host", $BindHost,
    "--port", $Port
)

Start-Process -FilePath $Python -ArgumentList $Arguments -WorkingDirectory $ProjectRoot -WindowStyle Hidden
Write-Output "Paper dashboard supervisor started: http://$BindHost`:$Port/"
