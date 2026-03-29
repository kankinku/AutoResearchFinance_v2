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
    $candidateScore = $null
    $baselineScore = $null
    if ($request.context -and $request.context.candidate_evaluation) {
        $candidateScore = $request.context.candidate_evaluation.score
    }
    if ($request.context -and $request.context.baseline_evaluation) {
        $baselineScore = $request.context.baseline_evaluation.score
    }

    $summary = if ($null -ne $candidateScore -and $null -ne $baselineScore) {
        "Smoke-test analysis completed. candidate_score=$candidateScore baseline_score=$baselineScore"
    }
    else {
        'Smoke-test analysis completed.'
    }
    $pythonWriter = @'
import json
import pathlib
import sys

request_path = pathlib.Path(sys.argv[1])
response_path = pathlib.Path(sys.argv[2])
summary = sys.argv[3]

request = json.loads(request_path.read_text(encoding="utf-8-sig"))
payload = {
    "ok": True,
    "task_kind": "analysis",
    "idempotency_key": request["idempotency_key"],
    "artifact": {
        "strengths": ["Wrapper round-trip succeeded."],
        "weaknesses": ["This is a local smoke-test analysis handler, not a real research critic."],
        "coverage_gaps": ["Replace with a real OpenClaw analysis handler for production use."],
        "regime_observations": ["No regime-specific qualitative review was generated in smoke-test mode."],
        "next_hypothesis_hints": ["Wire a real analysis handler after transport validation."],
        "summary": summary,
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

    $pythonWriter | python - $RequestJson $ResponseJson $summary
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
    exit 0
}
catch {
    Write-Error "[X] Local analysis handler failed: $_"
    exit 1
}
