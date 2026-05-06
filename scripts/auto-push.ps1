param(
  [string]$Message = "chore: update workspace",
  [ValidateSet("auto", "small", "medium", "large", "hotfix")]
  [string]$TaskSize = "auto",
  [string]$BranchName = "",
  [string]$BaseBranch = "master",
  [string]$BranchPrefix = "codex",
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
  "strategies/indicators",
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

function Invoke-Native {
  param(
    [scriptblock]$Command,
    [string]$FailureMessage
  )

  & $Command
  if ($LASTEXITCODE -ne 0) {
    throw $FailureMessage
  }
}

function ConvertTo-BranchSlug {
  param([string]$Value)

  $slug = $Value.ToLowerInvariant()
  $slug = $slug -replace "^[a-z]+(\([^)]+\))?:\s*", ""
  $slug = $slug -replace "[^a-z0-9]+", "-"
  $slug = $slug.Trim("-")

  if ($slug.Length -gt 48) {
    $slug = $slug.Substring(0, 48).Trim("-")
  }

  if (-not $slug) {
    return "update-workspace"
  }

  return $slug
}

function Get-CommitType {
  param([string]$CommitMessage)

  if ($CommitMessage -match "^([a-z]+)(\([^)]+\))?:") {
    return $Matches[1]
  }

  return "task"
}

function New-AutomationBranchName {
  $type = Get-CommitType $Message
  $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
  $slug = ConvertTo-BranchSlug $Message
  return "$BranchPrefix/$type-$timestamp-$slug"
}

function Assert-SafeBranchName {
  param([string]$Name)

  if (-not $Name) {
    throw "Branch name cannot be empty."
  }

  if (
    $Name.StartsWith("/") -or
    $Name.EndsWith("/") -or
    $Name.EndsWith(".") -or
    $Name.Contains("..") -or
    $Name.Contains("@{") -or
    $Name.Contains("//") -or
    ($Name -match "[\s~^:?*\[\\]")
  ) {
    throw "Refusing unsafe branch name: $Name"
  }
}

function Get-StagedChangeStats {
  $files = @(git diff --cached --name-only)
  $numstat = @(git diff --cached --numstat)
  $lineDelta = 0

  foreach ($line in $numstat) {
    $parts = $line -split "`t"
    if ($parts.Count -ge 2) {
      if ($parts[0] -match "^\d+$") {
        $lineDelta += [int]$parts[0]
      }
      if ($parts[1] -match "^\d+$") {
        $lineDelta += [int]$parts[1]
      }
    }
  }

  return [pscustomobject]@{
    FileCount = $files.Count
    LineDelta = $lineDelta
  }
}

function Resolve-TaskSize {
  param(
    [string]$RequestedTaskSize,
    [pscustomobject]$Stats
  )

  if ($RequestedTaskSize -ne "auto") {
    return $RequestedTaskSize
  }

  if ($Stats.FileCount -le 3 -and $Stats.LineDelta -le 200) {
    return "small"
  }

  if ($Stats.FileCount -le 12 -and $Stats.LineDelta -le 1200) {
    return "medium"
  }

  return "large"
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
    Invoke-Native { npm run typecheck } "Validation failed: npm run typecheck"
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

  Invoke-Native { git add -- $pathspecs } "Failed to stage allowed pathspecs."

  $status = git status --porcelain
  $stagedStatus = git diff --cached --name-status
  if (-not $stagedStatus) {
    Write-Host "No changes to commit."
    exit 0
  }

  Write-Host "Staged changes:"
  git diff --cached --stat
  git diff --cached --name-status

  $stats = Get-StagedChangeStats
  $resolvedTaskSize = Resolve-TaskSize $TaskSize $stats
  $currentBranch = git branch --show-current
  $targetBranch = $currentBranch
  $useBranchWorkflow = $false

  if ($BranchName) {
    $targetBranch = $BranchName
    $useBranchWorkflow = $true
  } elseif ($currentBranch -ne $BaseBranch) {
    $targetBranch = $currentBranch
    $useBranchWorkflow = $true
  } elseif ($resolvedTaskSize -in @("medium", "large", "hotfix")) {
    $targetBranch = New-AutomationBranchName
    $useBranchWorkflow = $true
  } else {
    $targetBranch = $BaseBranch
  }

  Assert-SafeBranchName $targetBranch
  Write-Host "Task size: $resolvedTaskSize"
  Write-Host "Target branch: $targetBranch"

  if ($useBranchWorkflow -and $currentBranch -ne $targetBranch) {
    git show-ref --verify --quiet "refs/heads/$targetBranch"
    $branchExists = ($LASTEXITCODE -eq 0)

    if ($branchExists) {
      Invoke-Native { git switch $targetBranch } "Failed to switch to branch: $targetBranch"
    } else {
      Invoke-Native { git switch -c $targetBranch } "Failed to create branch: $targetBranch"
    }
  }

  $previousSkipAutoPush = $env:AF_SKIP_AUTO_PUSH
  $env:AF_SKIP_AUTO_PUSH = "1"
  try {
    Invoke-Native { git commit -m $Message } "Failed to create commit."
  } finally {
    if ($null -eq $previousSkipAutoPush) {
      Remove-Item Env:\AF_SKIP_AUTO_PUSH -ErrorAction SilentlyContinue
    } else {
      $env:AF_SKIP_AUTO_PUSH = $previousSkipAutoPush
    }
  }

  if ($useBranchWorkflow) {
    Invoke-Native { git push -u origin "HEAD:$targetBranch" } "Failed to push branch: $targetBranch"
  } else {
    Invoke-Native { git push origin "HEAD:$BaseBranch" } "Failed to push to $BaseBranch."
  }
} finally {
  Pop-Location
}
