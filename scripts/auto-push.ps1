param(
  [string]$Message = "chore: update workspace",
  [switch]$SkipValidation,
  [switch]$IncludeResearchArtifacts,
  [string[]]$ExtraPath = @()
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

$DefaultPathspecs = @(
  "AGENTS.md",
  ".gitignore",
  ".env.example",
  "package.json",
  "package-lock.json",
  "tsconfig.json",
  "tsconfig.build.json",
  "vitest.config.ts",
  "program.finance.md",
  "src",
  "tests",
  "scripts",
  "docs",
  "config"
)

$ResearchArtifactPathspecs = @(
  "strategies/candidates",
  "strategies/specs",
  "strategies/source",
  "state/pi-autoresearch/ledger",
  "state/pi-autoresearch/taxonomy",
  "state/pi-autoresearch/views",
  "state/pi-autoresearch/artifacts/results"
)

$BlockedPathPrefixes = @(
  ".env",
  ".omx",
  "artifacts/autonomous-run",
  "artifacts/dashboard",
  "dist",
  "node_modules",
  "state/pi-autoresearch/logs",
  "state/pi-autoresearch/runtime",
  "state/pi-autoresearch/traces"
)

function Normalize-GitPath {
  param([string]$Pathspec)
  return ($Pathspec -replace "\\", "/").TrimStart("./")
}

function Assert-AllowedPathspec {
  param([string]$Pathspec)
  $normalized = Normalize-GitPath $Pathspec
  if (-not $normalized -or $normalized.Contains("..")) {
    throw "Refusing unsafe pathspec: $Pathspec"
  }
  foreach ($blockedPrefix in $BlockedPathPrefixes) {
    if ($normalized -eq $blockedPrefix -or $normalized.StartsWith("$blockedPrefix/")) {
      throw "Refusing blocked runtime/local pathspec: $Pathspec"
    }
  }
}

Push-Location $ProjectRoot
try {
  if (-not (Test-Path -LiteralPath ".git")) {
    throw "This directory is not a git repository: $ProjectRoot"
  }

  $preExistingStaged = git diff --cached --name-only
  if ($preExistingStaged) {
    throw "Refusing to commit because files are already staged. Unstage or commit them first."
  }

  if (-not $SkipValidation -and (Test-Path -LiteralPath "package.json")) {
    npm run typecheck
  }

  $pathspecs = @($DefaultPathspecs)
  if ($IncludeResearchArtifacts) {
    $pathspecs += $ResearchArtifactPathspecs
  }
  if ($ExtraPath.Count -gt 0) {
    foreach ($pathspec in $ExtraPath) {
      Assert-AllowedPathspec $pathspec
    }
    $pathspecs += $ExtraPath
  }

  git add -- $pathspecs

  $status = git status --porcelain
  $stagedStatus = git diff --cached --name-status
  if (-not $stagedStatus) {
    Write-Host "No changes to commit."
    exit 0
  }

  Write-Host "Staged changes:"
  git diff --cached --stat
  git diff --cached --name-status

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
