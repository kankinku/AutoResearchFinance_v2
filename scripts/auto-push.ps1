param(
  [string]$Message = "chore: update workspace",
  [switch]$SkipValidation
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

Push-Location $ProjectRoot
try {
  if (-not (Test-Path -LiteralPath ".git")) {
    throw "This directory is not a git repository: $ProjectRoot"
  }

  if (-not $SkipValidation -and (Test-Path -LiteralPath "package.json")) {
    npm run typecheck
  }

  git add -A

  $status = git status --porcelain
  if (-not $status) {
    Write-Host "No changes to commit."
    exit 0
  }

  $previousSkipAutoPush = $env:AF_SKIP_AUTO_PUSH
  $env:AF_SKIP_AUTO_PUSH = "1"
  try {
    git commit -m $Message
  } finally {
    if ($null -eq $previousSkipAutoPush) {
      Remove-Item Env:\AF_SKIP_AUTO_PUSH -ErrorAction SilentlyContinue
    } else {
      $env:AF_SKIP_AUTO_PUSH = $previousSkipAutoPush
    }
  }

  git push origin HEAD:master
} finally {
  Pop-Location
}
