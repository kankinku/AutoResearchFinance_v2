# Finance Autoresearch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working Python implementation of the finance autoresearch system described in the approved spec, including Supervisor control flow, automatic market-data pipeline, vectorbt evaluation, OpenClaw runtime integration, and CLI/Telegram/dashboard surfaces.

**Architecture:** Create a new root Python package named `finance_autoresearch` and keep `upstream-autoresearch/` read-only as a reference. The system centers on one SQLite-backed state store and one Supervisor service that controls a pipeline worker and an autoresearch worker. Only `src/finance_autoresearch/strategy/mutable/strategy_candidate.py` is LLM-editable; all other logic stays in fixed, testable modules.

**Tech Stack:** Python, uv, pytest, FastAPI, Typer, SQLAlchemy, Pydantic, pandas, pyarrow, vectorbt, yfinance, python-telegram-bot, PowerShell wrapper scripts for OpenClaw.

---

## File Map

### New root project files

- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `config/openclaw.roles.example.yaml`

### Source package

- Create: `src/finance_autoresearch/__init__.py`
- Create: `src/finance_autoresearch/__main__.py`
- Create: `src/finance_autoresearch/app.py`
- Create: `src/finance_autoresearch/settings.py`

### Supervisor and state

- Create: `src/finance_autoresearch/supervisor/service.py`
- Create: `src/finance_autoresearch/supervisor/command_gate.py`
- Create: `src/finance_autoresearch/supervisor/transition_guard.py`
- Create: `src/finance_autoresearch/supervisor/process_lock.py`
- Create: `src/finance_autoresearch/state/models.py`
- Create: `src/finance_autoresearch/state/repository.py`
- Create: `src/finance_autoresearch/state/sqlite_store.py`
- Create: `src/finance_autoresearch/state/outbox.py`

### Strategy and mutation boundary

- Create: `src/finance_autoresearch/strategy/base_contract.py`
- Create: `src/finance_autoresearch/strategy/indicator_registry.py`
- Create: `src/finance_autoresearch/strategy/regime_registry.py`
- Create: `src/finance_autoresearch/strategy/mutable/strategy_candidate.py`
- Create: `src/finance_autoresearch/mutation/openclaw_client.py`
- Create: `src/finance_autoresearch/mutation/prompt_builder.py`
- Create: `src/finance_autoresearch/mutation/patch_applier.py`
- Create: `src/finance_autoresearch/mutation/candidate_workspace.py`

### Data, backtest, and workers

- Create: `src/finance_autoresearch/backtest/data_loader.py`
- Create: `src/finance_autoresearch/backtest/harness.py`
- Create: `src/finance_autoresearch/backtest/evaluator.py`
- Create: `src/finance_autoresearch/backtest/analyzer.py`
- Create: `src/finance_autoresearch/backtest/scoring.py`
- Create: `src/finance_autoresearch/workers/pipeline_runner.py`
- Create: `src/finance_autoresearch/workers/autoresearch_runner.py`
- Create: `src/finance_autoresearch/workers/heartbeat.py`

### External surfaces and scripts

- Create: `src/finance_autoresearch/integrations/cli.py`
- Create: `src/finance_autoresearch/integrations/openclaw_control.py`
- Create: `src/finance_autoresearch/integrations/telegram_control.py`
- Create: `src/finance_autoresearch/integrations/telegram_report.py`
- Create: `src/finance_autoresearch/integrations/dashboard_api.py`
- Create: `scripts/check-openclaw.ps1`
- Create: `scripts/openclaw-mutate.ps1`
- Create: `scripts/openclaw-analyze.ps1`
- Create: `schemas/supervisor-command.schema.json`
- Create: `schemas/openclaw-mutation.schema.json`
- Create: `docs/openclaw-setup.md`

### Tests

- Create: `tests/conftest.py`
- Create: `tests/test_settings.py`
- Create: `tests/state/test_sqlite_store.py`
- Create: `tests/supervisor/test_service.py`
- Create: `tests/strategy/test_patch_applier.py`
- Create: `tests/backtest/test_data_loader.py`
- Create: `tests/backtest/test_harness.py`
- Create: `tests/backtest/test_evaluator.py`
- Create: `tests/workers/test_pipeline_runner.py`
- Create: `tests/workers/test_autoresearch_runner.py`
- Create: `tests/integrations/test_openclaw_client.py`
- Create: `tests/integrations/test_openclaw_control.py`
- Create: `tests/integrations/test_telegram_flows.py`
- Create: `tests/integrations/test_dashboard_api.py`

## Task 1: Bootstrap The Root Project

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `config/openclaw.roles.example.yaml`
- Create: `src/finance_autoresearch/__init__.py`
- Create: `src/finance_autoresearch/__main__.py`
- Create: `src/finance_autoresearch/settings.py`
- Test: `tests/test_settings.py`

- [ ] **Step 1: Write the failing settings test**

```python
def test_settings_load_defaults():
    settings = Settings()
    assert settings.project_id == "finance"
    assert settings.state_db_path.name == "finance_autoresearch.db"

def test_module_entrypoint_exists():
    import finance_autoresearch.__main__
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_settings.py -v`
Expected: FAIL with import or file-not-found errors

- [ ] **Step 3: Create project manifest and dependency list**

Add `pyproject.toml` with:
- runtime deps: `fastapi`, `uvicorn`, `typer`, `sqlalchemy`, `pydantic`, `pydantic-settings`, `pandas`, `pyarrow`, `numpy`, `vectorbt`, `yfinance`, `python-telegram-bot`
- test deps: `pytest`, `pytest-asyncio`, `httpx`
- package source root under `src/`

- [ ] **Step 4: Add base package and settings implementation**

```python
class Settings(BaseSettings):
    project_id: str = "finance"
    state_db_path: Path = Path("runtime/finance_autoresearch.db")
```

Add `src/finance_autoresearch/__main__.py` that delegates to the CLI/app entrypoint.

- [ ] **Step 5: Add `.gitignore` for runtime and local secrets**

Ignore:
- `.env`
- `.omx/`
- `runtime/`
- `data/market/raw/`
- `data/market/canonical/`
- `.pytest_cache/`

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_settings.py -v`
Expected: PASS

- [ ] **Step 7: Add checked-in OpenClaw example config**

Create:
- `.env.example` with placeholder Telegram and dashboard/OpenClaw settings
- `config/openclaw.roles.example.yaml` with `router`, `research`, `critic`, optional `builder`

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .gitignore .env.example config/openclaw.roles.example.yaml src/finance_autoresearch/__init__.py src/finance_autoresearch/__main__.py src/finance_autoresearch/settings.py tests/test_settings.py
git commit -m "feat: bootstrap finance autoresearch package"
```

## Task 2: Build SQLite State Store And Outbox

**Files:**
- Create: `src/finance_autoresearch/state/models.py`
- Create: `src/finance_autoresearch/state/repository.py`
- Create: `src/finance_autoresearch/state/sqlite_store.py`
- Create: `src/finance_autoresearch/state/outbox.py`
- Test: `tests/state/test_sqlite_store.py`

- [ ] **Step 1: Write failing repository tests**

```python
def test_store_initializes_default_project_state(store):
    state = store.get_status()
    assert state.project_state == "idle"
    assert state.pipeline_state == "idle"
    assert state.autoresearch_state == "idle"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/state/test_sqlite_store.py -v`
Expected: FAIL with missing store implementation

- [ ] **Step 3: Define persisted models**

Add tables for:
- project status
- command history
- run history
- experiment history
- analysis history
- outbox messages

- [ ] **Step 4: Implement repository API**

Include methods for:
- `get_status()`
- `record_command(...)`
- `set_status(...)`
- `append_outbox_event(...)`
- `mark_outbox_sent(...)`
- `set_active_run(...)`
- `set_current_stage(...)`
- `set_pending_command(...)`
- `record_heartbeat(...)`
- `set_candidate_revision(...)`
- `set_baseline_revision(...)`
- `set_recovery_marker(...)`

- [ ] **Step 5: Add repository tests for run/state bookkeeping**

Cover:
- `active_run_id`
- `current_stage`
- `pending_command`
- heartbeat timestamps
- candidate/baseline revisions
- recovery marker persistence

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/state/test_sqlite_store.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/finance_autoresearch/state tests/state/test_sqlite_store.py
git commit -m "feat: add sqlite state store and outbox"
```

## Task 3: Implement Supervisor Command State Machine

**Files:**
- Create: `src/finance_autoresearch/supervisor/command_gate.py`
- Create: `src/finance_autoresearch/supervisor/transition_guard.py`
- Create: `src/finance_autoresearch/supervisor/process_lock.py`
- Create: `src/finance_autoresearch/supervisor/service.py`
- Test: `tests/supervisor/test_service.py`

- [ ] **Step 1: Write failing transition tests**

```python
def test_start_pipeline_allowed_from_idle(supervisor):
    response = supervisor.handle({"command": "start_pipeline", ...})
    assert response["accepted"] is True
    assert response["pipeline_state"] == "running"

def test_start_autoresearch_rejects_without_successful_pipeline(supervisor):
    response = supervisor.handle({"command": "start_autoresearch", ...})
    assert response["accepted"] is False
```

- [ ] **Step 2: Add degraded recovery transition test**

```python
def test_start_pipeline_allowed_from_degraded(supervisor_in_degraded_state):
    response = supervisor_in_degraded_state.handle({"command": "start_pipeline", ...})
    assert response["accepted"] is True

def test_duplicate_start_autoresearch_is_rejected(active_supervisor):
    response = active_supervisor.handle({"command": "start_autoresearch", ...})
    assert response["accepted"] is False
```

- [ ] **Step 3: Add accepted `start_autoresearch` transition tests**

```python
def test_start_autoresearch_sets_active_running_when_pipeline_succeeded(supervisor_with_successful_pipeline):
    response = supervisor_with_successful_pipeline.handle({"command": "start_autoresearch", ...})
    assert response["accepted"] is True
    assert response["project_state"] == "active"
    assert response["autoresearch_state"] == "running"

def test_start_autoresearch_does_not_auto_run_pipeline(supervisor):
    response = supervisor.handle({"command": "start_autoresearch", ...})
    assert response["pipeline_state"] != "running"
```

- [ ] **Step 4: Run tests to verify failure**

Run: `uv run pytest tests/supervisor/test_service.py -v`
Expected: FAIL with missing Supervisor service

- [ ] **Step 5: Implement command validation and normalized responses**

Support:
- `start_pipeline`
- `start_autoresearch`
- `pause_autoresearch`
- `resume_autoresearch`
- `stop_autoresearch`
- `reset_project`
- `status`

- [ ] **Step 6: Implement pipeline-success gating and duplicate start rejection**

Encode:
- latest pipeline must be `success`
- duplicate active start rejects
- no implicit pipeline run on autoresearch start

- [ ] **Step 7: Implement stop semantics and pending command handling**

Encode:
- running stop -> pending stop until next stage boundary
- paused stop -> immediate success/idle transition

- [ ] **Step 8: Run supervisor tests**

Run: `uv run pytest tests/supervisor/test_service.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/finance_autoresearch/supervisor tests/supervisor/test_service.py
git commit -m "feat: add supervisor command state machine"
```

## Task 4: Build Strategy Contract And Mutation Guardrails

**Files:**
- Create: `src/finance_autoresearch/strategy/base_contract.py`
- Create: `src/finance_autoresearch/strategy/indicator_registry.py`
- Create: `src/finance_autoresearch/strategy/regime_registry.py`
- Create: `src/finance_autoresearch/strategy/mutable/strategy_candidate.py`
- Create: `src/finance_autoresearch/mutation/patch_applier.py`
- Test: `tests/strategy/test_patch_applier.py`

- [ ] **Step 1: Write failing patch guard tests**

```python
def test_patch_applier_rejects_forbidden_import():
    artifact = {"full_file_contents": "import os\n", ...}
    with pytest.raises(ValueError):
        apply_strategy_artifact(artifact)
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/strategy/test_patch_applier.py -v`
Expected: FAIL with missing patch applier

- [ ] **Step 3: Implement fixed strategy dataclasses and registries**

Define:
- `StrategyContext`
- `StrategyDefinition`
- EMA, SMA, RSI, ATR, rolling std
- EMA200 bull/bear classifier

- [ ] **Step 4: Add baseline mutable strategy candidate**

Implement a simple regime-aware EMA crossover strategy that satisfies the contract.

- [ ] **Step 5: Implement AST validation and file-length/import checks**

Reject:
- forbidden imports
- forbidden calls
- missing `build_strategy`
- multi-file targets

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/strategy/test_patch_applier.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/finance_autoresearch/strategy src/finance_autoresearch/mutation/patch_applier.py tests/strategy/test_patch_applier.py
git commit -m "feat: add strategy contract and mutation boundary"
```

## Task 5: Implement Automatic Market Data Pipeline

**Files:**
- Create: `src/finance_autoresearch/backtest/data_loader.py`
- Create: `src/finance_autoresearch/workers/pipeline_runner.py`
- Test: `tests/backtest/test_data_loader.py`
- Test: `tests/workers/test_pipeline_runner.py`

- [ ] **Step 1: Write failing canonicalization tests**

```python
def test_builds_canonical_market_pack(tmp_path):
    result = build_market_pack(cache_root=tmp_path)
    assert sorted(result.keys()) == [
        ("BTC-USD", "1d"),
        ("BTC-USD", "2h"),
        ("IWM", "1d"),
        ("IWM", "2h"),
        ("QQQ", "1d"),
        ("QQQ", "2h"),
    ]
```

- [ ] **Step 2: Write failing 2h timestamp policy tests**

```python
def test_equity_2h_bars_use_second_source_bar_close_timestamp():
    ...
```

- [ ] **Step 3: Run tests to verify failure**

Run: `uv run pytest tests/backtest/test_data_loader.py tests/workers/test_pipeline_runner.py -v`
Expected: FAIL

- [ ] **Step 4: Implement raw fetchers and canonical parquet writer**

Cover:
- `1d` fetch policy
- `1h` fetch policy
- QQQ/IWM regular-session filtering
- BTC-USD UTC right-labeled `2h` resample

- [ ] **Step 5: Implement pipeline worker preconditions**

Pipeline worker must:
- build market pack
- validate schema and history windows
- validate SQLite reachability and migrations
- create or validate accepted baseline snapshot
- validate OpenClaw health
- validate baseline strategy presence
- validate Telegram control credentials
- validate Telegram report credentials
- validate dashboard configuration

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/backtest/test_data_loader.py tests/workers/test_pipeline_runner.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/finance_autoresearch/backtest/data_loader.py src/finance_autoresearch/workers/pipeline_runner.py tests/backtest/test_data_loader.py tests/workers/test_pipeline_runner.py
git commit -m "feat: add automatic market data pipeline"
```

## Task 6: Implement Fixed Harness, Evaluator, And Analyzer

**Files:**
- Create: `src/finance_autoresearch/backtest/harness.py`
- Create: `src/finance_autoresearch/backtest/evaluator.py`
- Create: `src/finance_autoresearch/backtest/analyzer.py`
- Create: `src/finance_autoresearch/backtest/scoring.py`
- Test: `tests/backtest/test_harness.py`
- Test: `tests/backtest/test_evaluator.py`

- [ ] **Step 1: Write failing harness test**

```python
def test_harness_returns_per_combination_and_aggregate_metrics(sample_market_pack):
    results = run_backtests(sample_market_pack, strategy_module)
    assert "aggregate" in results
    assert ("QQQ", "1d") in results["combinations"]
```

- [ ] **Step 2: Write failing evaluator test**

```python
def test_evaluator_uses_even_count_median_for_score():
    score = evaluate_scores([1, 2, 3, 4, 5, 6])["score"]
    assert score == 3.5

def test_evaluator_zero_trade_defaults_profit_factor_and_guardrails():
    ...
```

- [ ] **Step 3: Add failing evaluator contract tests**

```python
def test_evaluator_uses_expected_annualization_map():
    ...

def test_evaluator_requires_50_bar_regime_window():
    ...

def test_evaluator_enforces_full_guardrail_set():
    ...
```

- [ ] **Step 4: Run tests to verify failure**

Run: `uv run pytest tests/backtest/test_harness.py tests/backtest/test_evaluator.py -v`
Expected: FAIL

- [ ] **Step 5: Implement deterministic vectorbt harness**

Return:
- split metrics
- regime slices
- per-combination bundles
- aggregate bundles

- [ ] **Step 6: Implement evaluator formulas and guardrails**

Pin:
- Sharpe
- Sortino
- turnover
- exposure
- drawdown convention
- finite metric set

- [ ] **Step 7: Implement structured analyzer output**

Generate:
- strengths
- weaknesses
- coverage gaps
- regime observations
- next-hypothesis hints

- [ ] **Step 8: Run tests**

Run: `uv run pytest tests/backtest/test_harness.py tests/backtest/test_evaluator.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/finance_autoresearch/backtest tests/backtest/test_harness.py tests/backtest/test_evaluator.py
git commit -m "feat: add fixed harness evaluator and analyzer"
```

## Task 7: Implement OpenClaw Adapter And Wrapper Contracts

**Files:**
- Create: `src/finance_autoresearch/mutation/openclaw_client.py`
- Create: `src/finance_autoresearch/mutation/prompt_builder.py`
- Create: `src/finance_autoresearch/mutation/candidate_workspace.py`
- Create: `scripts/check-openclaw.ps1`
- Create: `scripts/openclaw-mutate.ps1`
- Create: `scripts/openclaw-analyze.ps1`
- Create: `schemas/supervisor-command.schema.json`
- Create: `schemas/openclaw-mutation.schema.json`
- Create: `docs/openclaw-setup.md`
- Test: `tests/integrations/test_openclaw_client.py`

- [ ] **Step 1: Write failing wrapper envelope tests**

```python
def test_openclaw_client_retries_transport_failure_once(tmp_path):
    ...

def test_openclaw_client_retries_timeout_once(tmp_path):
    ...

def test_openclaw_client_does_not_retry_schema_failure(tmp_path):
    ...

def test_openclaw_client_preserves_idempotency_key(tmp_path):
    ...
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/integrations/test_openclaw_client.py -v`
Expected: FAIL

- [ ] **Step 3: Implement JSON schema files and wrapper request/response models**

Include:
- command schema
- mutation artifact schema
- wrapper request envelope
- wrapper response envelope

- [ ] **Step 4: Implement PowerShell wrappers and health check**

Support:
- role presence check for `router`, `research`, `critic`
- mutation/analyze request file flow
- transport failure normalization
- timeout classification
- retryable envelope handling

- [ ] **Step 5: Implement Python OpenClaw client**

Wrap:
- subprocess invocation
- timeout classification
- retry precedence
- artifact validation

- [ ] **Step 6: Add setup documentation**

Document:
- gateway port
- required roles
- env vars
- wrapper usage

- [ ] **Step 7: Run tests**

Run: `uv run pytest tests/integrations/test_openclaw_client.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/finance_autoresearch/mutation scripts schemas docs/openclaw-setup.md tests/integrations/test_openclaw_client.py
git commit -m "feat: add openclaw adapter and wrapper contracts"
```

## Task 8: Implement Autoresearch Worker Loop And Rollback

**Files:**
- Create: `src/finance_autoresearch/workers/autoresearch_runner.py`
- Create: `src/finance_autoresearch/workers/heartbeat.py`
- Modify: `src/finance_autoresearch/state/repository.py`
- Modify: `src/finance_autoresearch/supervisor/service.py`
- Test: `tests/workers/test_autoresearch_runner.py`

- [ ] **Step 1: Write failing iteration-loop tests**

```python
def test_autoresearch_runner_rolls_back_failed_candidate():
    result = runner.run_iteration(...)
    assert result.decision == "rollback"
    assert current_strategy_contents() == baseline_contents

def test_autoresearch_runner_keeps_only_when_score_beats_threshold():
    ...

def test_ties_are_not_kept():
    ...

def test_crash_is_recorded_as_crash_not_plain_rollback():
    ...
```

- [ ] **Step 2: Write failing stop-at-boundary test**

```python
def test_runner_honors_pending_stop_at_next_stage_boundary():
    ...
```

- [ ] **Step 3: Run tests to verify failure**

Run: `uv run pytest tests/workers/test_autoresearch_runner.py -v`
Expected: FAIL

- [ ] **Step 4: Add failing startup recovery tests**

```python
def test_recovery_marks_crash_recovered_and_emits_recovery_event():
    ...

def test_recovery_clears_active_run_stage_and_pending_command():
    ...

def test_recovery_marks_pipeline_running_as_failed_and_emits_pipeline_recovered_stale():
    ...

def test_recovery_marks_autoresearch_running_as_stale_and_emits_autoresearch_recovered_stale():
    ...
```

- [ ] **Step 5: Add failing start_autoresearch seed-baseline validation test**

```python
def test_start_autoresearch_rejects_invalid_seed_strategy(supervisor):
    response = supervisor.handle({"command": "start_autoresearch", ...})
    assert response["accepted"] is False
    assert response["project_state"] == "degraded"

def test_runner_stops_when_process_lock_is_lost():
    ...

def test_runner_fails_after_three_consecutive_crashes():
    ...
```

- [ ] **Step 6: Implement baseline capture, mutation, backtest, evaluation, analysis, keep/rollback**

Persist:
- run id
- iteration number
- hypothesis
- mutation summary
- decision

- [ ] **Step 7: Implement recovery, heartbeat handling, and Supervisor seed validation path**

Normalize:
- `crash_recovered`
- stale transitions
- baseline restore
- outbox recovery events
- `pipeline_recovered_stale`
- `autoresearch_recovered_stale`
- clear `active_run_id`
- clear `current_stage`
- clear `pending_command`
- process lock loss stop
- three-consecutive-crash failure threshold
- `start_autoresearch` seed compile/contract/backtest/guardrail rejection

- [ ] **Step 8: Run tests**

Run: `uv run pytest tests/workers/test_autoresearch_runner.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/finance_autoresearch/workers src/finance_autoresearch/state/repository.py src/finance_autoresearch/supervisor/service.py tests/workers/test_autoresearch_runner.py
git commit -m "feat: add autoresearch loop and rollback"
```

## Task 9: Implement CLI, Telegram, And Dashboard Surfaces

**Files:**
- Create: `src/finance_autoresearch/integrations/cli.py`
- Create: `src/finance_autoresearch/integrations/openclaw_control.py`
- Create: `src/finance_autoresearch/integrations/telegram_control.py`
- Create: `src/finance_autoresearch/integrations/telegram_report.py`
- Create: `src/finance_autoresearch/integrations/dashboard_api.py`
- Create: `src/finance_autoresearch/app.py`
- Test: `tests/integrations/test_openclaw_control.py`
- Test: `tests/integrations/test_telegram_flows.py`
- Test: `tests/integrations/test_dashboard_api.py`

- [ ] **Step 1: Write failing CLI status test**

```python
def test_cli_status_returns_normalized_response(runner):
    result = cli_app(["status"])
    assert result.exit_code == 0
    assert '"project_state"' in result.stdout
```

- [ ] **Step 2: Write failing OpenClaw control ingress tests**

```python
def test_openclaw_control_defaults_project_id_and_returns_normalized_status():
    ...

def test_openclaw_control_rejects_invalid_stdin_schema():
    ...

def test_python_module_openclaw_control_subprocess_exit_code_and_stdout():
    ...
```

- [ ] **Step 3: Write failing Telegram control/report tests**

```python
def test_control_command_creates_command_history_and_matches_cli_transition():
    ...

def test_report_sender_only_uses_outbox_messages():
    ...
```

- [ ] **Step 4: Write failing dashboard endpoint parity test**

```python
def test_dashboard_status_matches_supervisor_status(client):
    response = client.get("/status")
    assert response.status_code == 200
    assert response.json()["project_state"] == cli_status["project_state"]
```

- [ ] **Step 5: Run tests to verify failure**

Run: `uv run pytest tests/integrations/test_openclaw_control.py tests/integrations/test_telegram_flows.py tests/integrations/test_dashboard_api.py -v`
Expected: FAIL

- [ ] **Step 6: Implement Typer CLI and OpenClaw stdin/stdout control adapter**

Support:
- `status`
- `start_pipeline`
- `start_autoresearch`
- `pause_autoresearch`
- `resume_autoresearch`
- `stop_autoresearch`
- `reset_project`

- [ ] **Step 7: Implement Telegram control and report adapters**

Ensure:
- control adapter only forwards commands
- report adapter only drains outbox

- [ ] **Step 8: Implement FastAPI dashboard status endpoints**

Expose:
- `/status`
- `/history/commands`
- `/history/experiments`
- `/history/outbox`

- [ ] **Step 9: Run tests**

Run: `uv run pytest tests/integrations/test_openclaw_control.py tests/integrations/test_telegram_flows.py tests/integrations/test_dashboard_api.py -v`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add src/finance_autoresearch/integrations src/finance_autoresearch/app.py tests/integrations/test_openclaw_control.py tests/integrations/test_telegram_flows.py tests/integrations/test_dashboard_api.py
git commit -m "feat: add control and reporting surfaces"
```

## Task 10: Run End-To-End Verification

**Files:**
- Modify: `tests/conftest.py`
- Create: `tests/test_end_to_end.py`

- [ ] **Step 1: Write failing end-to-end smoke test**

```python
def test_pipeline_then_autoresearch_smoke_flow(app_fixture):
    ...
```

- [ ] **Step 2: Run test to verify failure**

Run: `uv run pytest tests/test_end_to_end.py -v`
Expected: FAIL

- [ ] **Step 3: Add shared fixtures and deterministic fake OpenClaw wrappers**

Support:
- fake data cache
- fake OpenClaw responses
- fake Telegram delivery sink

- [ ] **Step 4: Run focused suite**

Run: `uv run pytest tests/test_end_to_end.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -v`
Expected: PASS

- [ ] **Step 6: Run lint/type/build validation**

Run:
- `uv run pytest -v`
- `uv run python -m compileall src`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add tests/conftest.py tests/test_end_to_end.py
git commit -m "test: add end-to-end verification"
```
