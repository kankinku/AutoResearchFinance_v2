param(
    [Parameter(Mandatory = $true)]
    [string]$AgentId,
    [Parameter(Mandatory = $true)]
    [string]$RequestJson,
    [Parameter(Mandatory = $true)]
    [string]$ResponseJson
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

try {
    $request = Get-Content $RequestJson -Raw | ConvertFrom-Json
    $repoRoot = Split-Path -Parent $PSScriptRoot
    $candidatePath = Join-Path $repoRoot 'src\finance_autoresearch\strategy\mutable\strategy_candidate.py'
    $candidateSource = Get-Content $candidatePath -Raw
    $hypothesis = if ($request.context.hypothesis) {
        [string]$request.context.hypothesis
    }
    else {
        'Keep current validated baseline strategy.'
    }

    $pythonWriter = @'
import json
import pathlib
import sys

request_path = pathlib.Path(sys.argv[1])
response_path = pathlib.Path(sys.argv[2])
candidate_path = pathlib.Path(sys.argv[3])
hypothesis = sys.argv[4]

request = json.loads(request_path.read_text(encoding="utf-8-sig"))
candidate_source = candidate_path.read_text(encoding="utf-8")
payload = {
    "ok": True,
    "task_kind": "mutation",
    "idempotency_key": request["idempotency_key"],
    "artifact": {
        "kind": "strategy_replacement",
        "target_path": "src/finance_autoresearch/strategy/mutable/strategy_candidate.py",
        "hypothesis": hypothesis,
        "change_summary": "Local handler returned the current validated strategy candidate for smoke-test execution.",
        "full_file_contents": candidate_source,
        "expected_effects": [
            "Preserves a schema-valid candidate so the autoresearch pipeline can run end-to-end."
        ],
    },
    "error_type": None,
    "message": "ok",
    "retryable": False,
}
response_path.write_text(
    json.dumps(payload, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
'@

    $pythonWriter | python - $RequestJson $ResponseJson $candidatePath $hypothesis
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
    exit 0
}
catch {
    Write-Error "[X] Local mutation handler failed: $_"
    exit 1
}
