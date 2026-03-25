param(
    [string]$RepositoryRoot = "",
    [string]$OutputRoot = (Join-Path ([System.IO.Path]::GetTempPath()) "finance-autoresearch-openclaw-skills"),
    [string]$OpenClawWorkspace = (Join-Path $HOME ".openclaw\workspace"),
    [switch]$SkipInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $RepositoryRoot) {
    $RepositoryRoot = Join-Path $PSScriptRoot ".."
}

function Resolve-AbsolutePath {
    param([string]$PathValue)

    $resolved = Resolve-Path -Path $PathValue -ErrorAction Stop
    return $resolved.Path
}

function Copy-RenderedSkillTree {
    param(
        [string]$SourceDir,
        [string]$DestinationDir,
        [hashtable]$Replacements
    )

    Copy-Item -Path $SourceDir -Destination $DestinationDir -Recurse -Force
    $files = Get-ChildItem -Path $DestinationDir -Recurse -File
    foreach ($file in $files) {
        $content = Get-Content -Path $file.FullName -Raw
        foreach ($key in $Replacements.Keys) {
            $content = $content.Replace($key, $Replacements[$key])
        }
        Set-Content -Path $file.FullName -Value $content -Encoding utf8
        if ($file.FullName.EndsWith(".template")) {
            $renamedPath = $file.FullName.Substring(0, $file.FullName.Length - ".template".Length)
            Move-Item -Path $file.FullName -Destination $renamedPath -Force
        }
    }
}

try {
    $repoRoot = Resolve-AbsolutePath -PathValue $RepositoryRoot
    $skillsSourceRoot = Join-Path $repoRoot "openclaw-skills"
    if (-not (Test-Path $skillsSourceRoot)) {
        throw "OpenClaw skill source directory is missing: $skillsSourceRoot"
    }

    New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
    if (-not $SkipInstall) {
        New-Item -ItemType Directory -Path $OpenClawWorkspace -Force | Out-Null
    }

    $stagingRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("finance-autoresearch-openclaw-stage-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $stagingRoot -Force | Out-Null

    $skills = @(
        "finance-autoresearch-control",
        "finance-autoresearch-status-polling"
    )
    $result = New-Object System.Collections.Generic.List[object]

    foreach ($skillName in $skills) {
        $sourceDir = Join-Path $skillsSourceRoot $skillName
        $skillStagingDir = Join-Path $stagingRoot $skillName
        $skillPackage = Join-Path $OutputRoot ($skillName + ".skill")
        $skillZip = Join-Path $OutputRoot ($skillName + ".zip")

        if (-not (Test-Path $sourceDir)) {
            throw "Missing skill source: $sourceDir"
        }

        Copy-RenderedSkillTree -SourceDir $sourceDir -DestinationDir $skillStagingDir -Replacements @{
            "__REPOSITORY_ROOT__" = $repoRoot
        }

        if (Test-Path $skillPackage) {
            Remove-Item -Path $skillPackage -Force
        }
        if (Test-Path $skillZip) {
            Remove-Item -Path $skillZip -Force
        }
        Compress-Archive -Path $skillStagingDir -DestinationPath $skillZip -Force
        Move-Item -Path $skillZip -Destination $skillPackage -Force

        $installedTo = $null
        if (-not $SkipInstall) {
            $installedTo = Join-Path $OpenClawWorkspace ($skillName + ".skill")
            Copy-Item -Path $skillPackage -Destination $installedTo -Force
        }

        $result.Add([pscustomobject]@{
            skill_name = $skillName
            package_path = $skillPackage
            installed_to = $installedTo
        }) | Out-Null
    }

    $result | ConvertTo-Json -Depth 10
}
catch {
    Write-Error $_
    exit 1
}
