# OpenClaw Setup

This project uses OpenClaw through checked-in PowerShell wrappers and one Python adapter.

## Required roles

- `router`
- `research`
- `critic`

Optional:

- `builder`

Role examples live in `config/openclaw.roles.example.yaml`.

## Health check

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check-openclaw.ps1 -RolesPath config/openclaw.roles.example.yaml
```

The script verifies that the required role blocks exist in the roles file. If you also want the message to include the configured gateway URL, pass `-GatewayUrl` or set `FINANCE_AUTORESEARCH_OPENCLAW_GATEWAY_URL`.

## Wrapper contract

The Python client calls these wrappers:

- `scripts/openclaw-mutate.ps1`
- `scripts/openclaw-analyze.ps1`

Both wrappers accept:

- `-AgentId`
- `-RequestJson`
- `-ResponseJson`

The request file contains the runtime envelope:

```json
{
  "task_kind": "mutation",
  "run_id": "run-001",
  "iteration": 7,
  "stage": "mutate_strategy",
  "idempotency_key": "run-001:7:mutate_strategy",
  "agent_id": "research",
  "target_path": "src/finance_autoresearch/strategy/mutable/strategy_candidate.py",
  "context": {},
  "expected_schema": "strategy_replacement"
}
```

The response file must contain one envelope:

```json
{
  "ok": true,
  "task_kind": "mutation",
  "idempotency_key": "run-001:7:mutate_strategy",
  "artifact": {},
  "error_type": null,
  "message": "ok",
  "retryable": false
}
```

## Stub mode

The checked-in wrappers support a stub mode so you can test the pipeline before wiring a real OpenClaw command.

For mutation:

```powershell
$env:FINANCE_AUTORESEARCH_OPENCLAW_MUTATE_RESPONSE_JSON = "C:\path\to\mutation-response.json"
```

For analysis:

```powershell
$env:FINANCE_AUTORESEARCH_OPENCLAW_ANALYZE_RESPONSE_JSON = "C:\path\to\analysis-response.json"
```

If the environment variable points to a JSON file, the wrapper copies that file to the requested response path and exits `0`.

If no stub file is configured, the wrapper writes a transport-failure envelope and exits non-zero. The Python client classifies that as retryable transport failure.

## Wiring a real OpenClaw command

Replace the stub block inside each PowerShell wrapper with your OpenClaw CLI or gateway call. Keep these rules unchanged:

- read only the request JSON file
- write only the response JSON file
- preserve `idempotency_key` exactly
- return `retryable = false` for schema failures
- do not write side-effect files outside the requested response path

## Checked-in schemas

- `schemas/supervisor-command.schema.json`
- `schemas/openclaw-mutation.schema.json`

The mutation schema is validated again by `patch_applier.py` before any strategy file is written.
