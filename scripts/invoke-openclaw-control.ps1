param(
    [Parameter(Mandatory = $true)]
    [ValidateSet(
        "status",
        "start_pipeline",
        "start_autoresearch",
        "pause_autoresearch",
        "resume_autoresearch",
        "stop_autoresearch",
        "reset_project"
    )]
    [string]$Command,
    [string]$ProjectId = "finance",
    [string]$RequestedBy = "openclaw-skill",
    [string]$PayloadJson = "",
    [string]$PayloadPath = "",
    [string]$RepositoryRoot = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-FinanceAutoresearchRepository {
    param([string]$CandidatePath)

    if ([string]::IsNullOrWhiteSpace($CandidatePath)) {
        return $false
    }

    try {
        $resolved = (Resolve-Path -Path $CandidatePath -ErrorAction Stop).Path
    }
    catch {
        return $false
    }

    $pyprojectPath = Join-Path $resolved "pyproject.toml"
    $packagePath = Join-Path $resolved "src\finance_autoresearch\__init__.py"
    return (Test-Path $pyprojectPath) -and (Test-Path $packagePath)
}

function Find-FinanceAutoresearchRepository {
    param([string]$ExplicitRepositoryRoot)

    $candidates = New-Object System.Collections.Generic.List[string]
    if (-not [string]::IsNullOrWhiteSpace($ExplicitRepositoryRoot)) {
        $candidates.Add($ExplicitRepositoryRoot) | Out-Null
    }
    if (-not [string]::IsNullOrWhiteSpace($env:FINANCE_AUTORESEARCH_REPOSITORY_ROOT)) {
        $candidates.Add($env:FINANCE_AUTORESEARCH_REPOSITORY_ROOT) | Out-Null
    }
    if (-not [string]::IsNullOrWhiteSpace($PSScriptRoot)) {
        $candidates.Add((Join-Path $PSScriptRoot "..")) | Out-Null
    }

    $cursor = (Get-Location).Path
    while (-not [string]::IsNullOrWhiteSpace($cursor)) {
        $candidates.Add($cursor) | Out-Null
        $parent = Split-Path -Path $cursor -Parent
        if ([string]::IsNullOrWhiteSpace($parent) -or $parent -eq $cursor) {
            break
        }
        $cursor = $parent
    }

    foreach ($candidate in $candidates) {
        if (Test-FinanceAutoresearchRepository -CandidatePath $candidate) {
            return (Resolve-Path -Path $candidate -ErrorAction Stop).Path
        }
    }

    return $null
}

function Get-PayloadJsonText {
    param(
        [string]$JsonText,
        [string]$JsonPath
    )

    if (-not [string]::IsNullOrWhiteSpace($JsonText) -and -not [string]::IsNullOrWhiteSpace($JsonPath)) {
        throw "Use either PayloadJson or PayloadPath, not both."
    }

    if (-not [string]::IsNullOrWhiteSpace($JsonPath)) {
        if (-not (Test-Path -Path $JsonPath)) {
            throw "PayloadPath was not found: $JsonPath"
        }
        return Get-Content -Path $JsonPath -Raw
    }

    return $JsonText
}

function Test-JsonObjectValue {
    param([object]$Value)

    if ($null -eq $Value) {
        return $true
    }

    if ($Value -is [pscustomobject]) {
        return $true
    }

    if ($Value -is [System.Collections.IDictionary]) {
        return $true
    }

    return $false
}

function ConvertTo-PayloadObject {
    param([string]$JsonText)

    if ([string]::IsNullOrWhiteSpace($JsonText)) {
        return [pscustomobject]@{}
    }

    try {
        $payload = $JsonText | ConvertFrom-Json
    }
    catch {
        throw "PayloadJson must be a JSON object string."
    }

    if ($null -eq $payload) {
        return [pscustomobject]@{}
    }

    if (-not (Test-JsonObjectValue -Value $payload)) {
        throw "PayloadJson must resolve to a JSON object."
    }

    return $payload
}

function Get-PreferredWorkingDirectory {
    param([string]$ResolvedRepositoryRoot)

    if (-not [string]::IsNullOrWhiteSpace($ResolvedRepositoryRoot)) {
        return $ResolvedRepositoryRoot
    }

    return (Get-Location).Path
}

function Resolve-CommandInvocation {
    param([string]$ResolvedRepositoryRoot)

    $workingDirectory = Get-PreferredWorkingDirectory -ResolvedRepositoryRoot $ResolvedRepositoryRoot

    if ($ResolvedRepositoryRoot -and (Get-Command uv -ErrorAction SilentlyContinue)) {
        return [pscustomobject]@{
            executable = "uv"
            arguments = @("run", "python", "-m", "finance_autoresearch", "openclaw-control")
            working_directory = $ResolvedRepositoryRoot
            prepend_pythonpath = $false
        }
    }

    if (Get-Command finance-autoresearch -ErrorAction SilentlyContinue) {
        return [pscustomobject]@{
            executable = "finance-autoresearch"
            arguments = @("openclaw-control")
            working_directory = $workingDirectory
            prepend_pythonpath = $false
        }
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        return [pscustomobject]@{
            executable = "python"
            arguments = @("-m", "finance_autoresearch", "openclaw-control")
            working_directory = $workingDirectory
            prepend_pythonpath = -not [string]::IsNullOrWhiteSpace($ResolvedRepositoryRoot)
        }
    }

    if (Get-Command py -ErrorAction SilentlyContinue) {
        return [pscustomobject]@{
            executable = "py"
            arguments = @("-m", "finance_autoresearch", "openclaw-control")
            working_directory = $workingDirectory
            prepend_pythonpath = -not [string]::IsNullOrWhiteSpace($ResolvedRepositoryRoot)
        }
    }

    throw "Could not find a usable runner. Install uv or ensure finance-autoresearch/python is on PATH."
}

try {
    $repoRoot = Find-FinanceAutoresearchRepository -ExplicitRepositoryRoot $RepositoryRoot
    $payloadJsonText = Get-PayloadJsonText -JsonText $PayloadJson -JsonPath $PayloadPath
    $payload = ConvertTo-PayloadObject -JsonText $payloadJsonText
    $request = [ordered]@{
        command = $Command
        project_id = $ProjectId
        source = "openclaw"
        requested_by = $RequestedBy
        requested_at = [DateTimeOffset]::UtcNow.ToString("o")
        payload = $payload
    }
    $requestJson = $request | ConvertTo-Json -Depth 10 -Compress
    $requestJsonPath = [System.IO.Path]::GetTempFileName()
    $invocation = Resolve-CommandInvocation -ResolvedRepositoryRoot $repoRoot

    $previousPythonPath = $env:PYTHONPATH
    if ($invocation.prepend_pythonpath -and $repoRoot) {
        $srcPath = Join-Path $repoRoot "src"
        if ([string]::IsNullOrWhiteSpace($previousPythonPath)) {
            $env:PYTHONPATH = $srcPath
        }
        else {
            $env:PYTHONPATH = "$srcPath;$previousPythonPath"
        }
    }

    Push-Location $invocation.working_directory
    try {
        Set-Content -Path $requestJsonPath -Value $requestJson -Encoding utf8
        & $invocation.executable @($invocation.arguments) "--request-json-path" $requestJsonPath
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }
    finally {
        Pop-Location
        Remove-Item -Path $requestJsonPath -ErrorAction SilentlyContinue
        if ($null -eq $previousPythonPath) {
            Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
        }
        else {
            $env:PYTHONPATH = $previousPythonPath
        }
    }
}
catch {
    Write-Error $_
    exit 1
}
