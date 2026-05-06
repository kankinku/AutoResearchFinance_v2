$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$HookDir = Join-Path $ProjectRoot ".git\hooks"
$HookPath = Join-Path $HookDir "post-commit"

if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot ".git"))) {
  throw "This directory is not a git repository: $ProjectRoot"
}

New-Item -ItemType Directory -Force -Path $HookDir | Out-Null

$HookLines = @(
  "#!/bin/sh",
  "set -eu",
  "",
  "if [ `"`${AF_SKIP_AUTO_PUSH:-}`"` = `"1`" ]; then",
  "  exit 0",
  "fi",
  "",
  "branch=`$(git branch --show-current)",
  "if [ -z `"`$branch`" ]; then",
  "  exit 0",
  "fi",
  "",
  "git push origin HEAD:`"`$branch`""
)

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($HookPath, (($HookLines -join "`n") + "`n"), $Utf8NoBom)

Write-Host "Installed auto-push post-commit hook at $HookPath"
