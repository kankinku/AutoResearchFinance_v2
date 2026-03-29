# OpenClaw Setup

This project uses OpenClaw through checked-in PowerShell wrappers and one Python adapter.

## Runtime entrypoints

The control surfaces all call the same runtime:

```powershell
uv run python -m finance_autoresearch start_pipeline
uv run python -m finance_autoresearch start_autoresearch
uv run python -m finance_autoresearch openclaw-control < request.json
```

The runtime loads `.env`, builds the supervisor, and forwards the same OpenClaw wrapper settings to worker subprocesses.

`uv` is still the preferred manual entrypoint for local development, but the OpenClaw control skill wrappers are no longer `uv`-only. They can also fall back to an installed `finance-autoresearch` CLI or `python -m finance_autoresearch` when `uv` is unavailable.

## Required environment

At minimum set:

```powershell
FINANCE_AUTORESEARCH_WORKSPACE_ROOT=.
FINANCE_AUTORESEARCH_STATE_DB_PATH=runtime/finance_autoresearch.db
FINANCE_AUTORESEARCH_MARKET_PACK_MODE=download
FINANCE_AUTORESEARCH_OUTPUT_LANGUAGE=en
FINANCE_AUTORESEARCH_OPENCLAW_ROLES_PATH=config/openclaw.roles.example.yaml
FINANCE_AUTORESEARCH_OPENCLAW_GATEWAY_URL=http://127.0.0.1:18789
FINANCE_AUTORESEARCH_OPENCLAW_HEALTHCHECK_SCRIPT=scripts/check-openclaw.ps1
FINANCE_AUTORESEARCH_OPENCLAW_MUTATE_SCRIPT=scripts/openclaw-mutate.ps1
FINANCE_AUTORESEARCH_OPENCLAW_ANALYZE_SCRIPT=scripts/openclaw-analyze.ps1
```

For local dry runs you can also set:

```powershell
FINANCE_AUTORESEARCH_MARKET_PACK_MODE=cached
FINANCE_AUTORESEARCH_TELEGRAM_REPORT_DRY_RUN=true
```

If you want separate language control for logs vs generated Markdown notes, see [output-language.md](C:\Users\hanji\Desktop\Finance\AutoResearchFinance_v2\.worktrees\finance-autoresearch-v1\docs\output-language.md).

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
  "context": {
    "family": "replace_indicator",
    "historical_risks": ["turbulence", "metadata"],
    "allowed_indicator_pool": ["atr", "rolling_std", "rsi"],
    "knowledge_evidence": [
      {
        "source_id": "knowledge/factors/2026-03-26-factor-catalog-draft.md",
        "title": "Factor catalog draft",
        "relevance_reason": "Factor catalog notes matched the current issue."
      }
    ],
    "artifact_mode": "prefer_genome",
    "artifact_capabilities": {
      "strategy_genome_v1": {
        "supports_true_regime_split": false,
        "direction_mode": "mirrored_long_short",
        "max_indicator_count": 4,
        "max_new_conditions": 2
      }
    },
    "allowed_artifact_kinds": ["strategy_genome_v1", "strategy_replacement"],
    "genome_shadow_mode": true
  },
  "expected_schema": "mutation_artifact"
}
```

Important current note:

- Mutation requests are dual-path.
- The preferred path is `strategy_genome_v1`.
- `strategy_replacement` remains a backward-compatible fallback.
- If `artifact_mode = prefer_raw`, the wrapper should favor returning `strategy_replacement`.

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

The mutation `artifact` can be either of these:

1. Raw replacement:

```json
{
  "kind": "strategy_replacement",
  "target_path": "src/finance_autoresearch/strategy/mutable/strategy_candidate.py",
  "hypothesis": "Tighten the volatility gate.",
  "change_summary": "Use a narrower ATR-aware entry path.",
  "full_file_contents": "...python source...",
  "expected_effects": ["Reduce churn during turbulence spikes."]
}
```

2. Structured genome:

```json
{
  "kind": "strategy_genome_v1",
  "target_path": "src/finance_autoresearch/strategy/mutable/strategy_candidate.py",
  "hypothesis": "Prefer a structured volatility-aware EMA candidate.",
  "change_summary": "Compile a genome artifact instead of taking raw source directly.",
  "expected_effects": ["Prefer deterministic compiler output."],
  "family_id": "replace_indicator",
  "rationale": "Keep the mutation path structured while preserving a raw fallback.",
  "regime_policy": "preserve_current_regime_model",
  "indicator_specs": [],
  "entry_clauses": [],
  "exit_clauses": [],
  "risk_clauses": [],
  "params": {},
  "shadow_strategy_replacement": {
    "kind": "strategy_replacement",
    "target_path": "src/finance_autoresearch/strategy/mutable/strategy_candidate.py",
    "hypothesis": "Optional raw comparison path.",
    "change_summary": "Shadow-only raw replacement for comparison.",
    "full_file_contents": "...python source...",
    "expected_effects": ["Do not execute directly when genome is accepted."]
  }
}
```

Current planner vocabulary that may appear in `historical_risks`, `knowledge_evidence`, or workspace refs includes:

- factor words:
  - `atr`
  - `rolling_std`
  - `rolling_corr`
  - `rolling_rank`
  - `rolling_quantile`
- risk / regime words:
  - `turbulence`
  - `covariance`
  - `vix`
  - `regime`
- metadata words:
  - `metadata`
  - `sector`
  - `industry`
  - `exchange`
  - `country`
  - `universe`

Treat these as research hints, not as permission to widen scope beyond the single mutable strategy file.

## Handler mode

The wrappers can dispatch to a real local handler script without editing the checked-in wrapper files.

For mutation:

```powershell
$env:FINANCE_AUTORESEARCH_OPENCLAW_MUTATE_HANDLER_PATH = "C:\path\to\mutation-handler.ps1"
```

For analysis:

```powershell
$env:FINANCE_AUTORESEARCH_OPENCLAW_ANALYZE_HANDLER_PATH = "C:\path\to\analysis-handler.ps1"
```

Each handler receives:

- `-AgentId`
- `-RequestJson`
- `-ResponseJson`

The handler must write exactly one response envelope to `-ResponseJson`.

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

Preferred order:

1. Keep the checked-in wrappers unchanged.
2. Point `*_HANDLER_PATH` at your real local OpenClaw command adapter.
3. Use `*_RESPONSE_JSON` only for stubbed local testing.

If you still choose to edit the wrappers directly, keep these rules unchanged:

- read only the request JSON file
- write only the response JSON file
- preserve `idempotency_key` exactly
- return `retryable = false` for schema failures
- do not write side-effect files outside the requested response path

## Reusable setup flow

1. Copy [.env.example](C:\Users\hanji\Desktop\Finance\AutoResearchFinance_v2\.worktrees\finance-autoresearch-v1\.env.example) to `.env`.
2. Fill Telegram and OpenClaw values.
3. Choose one wrapper mode:
   - real handler mode via `FINANCE_AUTORESEARCH_OPENCLAW_*_HANDLER_PATH`
   - stub mode via `FINANCE_AUTORESEARCH_OPENCLAW_*_RESPONSE_JSON`
4. Run the health check:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check-openclaw.ps1 -RolesPath config/openclaw.roles.example.yaml
```

5. Start the fixed-market pipeline:

```powershell
uv run python -m finance_autoresearch start_pipeline
```

6. Start autoresearch after the pipeline reaches `success`:

```powershell
uv run python -m finance_autoresearch start_autoresearch
```

## Checked-in schemas

- `schemas/supervisor-command.schema.json`
- `schemas/openclaw-mutation.schema.json`

The mutation schema now covers:

- `strategy_replacement`
- `strategy_genome_v1`
- optional `shadow_strategy_replacement` inside genome responses

The artifact is validated again by `patch_applier.py` before any strategy file is written.

## OpenClaw control skills

For installable OpenClaw `.skill` bundles that wrap `openclaw-control`, see [openclaw-skills.md](C:\Users\hanji\Desktop\Finance\AutoResearchFinance_v2\.worktrees\finance-autoresearch-v1\docs\openclaw-skills.md).
