# Finance Autoresearch Design

Status: Draft for user review
Date: 2026-03-24
Audience: Human builder, coding agents, OpenClaw workers

## 1. Executive Target

Build a local-first finance research system inspired by karpathy/autoresearch, but adapted for vectorbt strategy search.

The system must:

- accept control commands only through a single Supervisor
- let LLMs modify only one mutable strategy file
- run repeatable backtests against a fixed evaluation harness
- analyze results after evaluation, including strengths, weaknesses, missing coverage, and likely next improvements
- keep or roll back a candidate automatically based on fixed guardrails
- repeat in code via a controlled loop
- use OpenClaw authenticated agents as the mutation and analysis LLM runtime

The system must not:

- let Telegram, Dashboard, OpenClaw, or CLI control workers directly
- let the LLM edit the evaluator, state store, or supervisor logic
- spread strategy mutations across many files
- mix control messages with report notifications

This document defines the destination clearly enough that a coding agent should be able to implement the first working version without inventing major architecture.

## 2. Source Pattern To Preserve

The upstream reference is:

- [README.md](C:\Users\hanji\Desktop\Finance\AutoResearchFinance_v2\upstream-autoresearch\README.md)
- [program.md](C:\Users\hanji\Desktop\Finance\AutoResearchFinance_v2\upstream-autoresearch\program.md)
- [train.py](C:\Users\hanji\Desktop\Finance\AutoResearchFinance_v2\upstream-autoresearch\train.py)
- [prepare.py](C:\Users\hanji\Desktop\Finance\AutoResearchFinance_v2\upstream-autoresearch\prepare.py)

The upstream invariants that must survive the port are:

1. There is one mutable experiment target.
2. There is one fixed evaluation harness.
3. The system runs a keep-or-discard loop automatically.

The mapping for this project is:

- upstream `program.md` -> finance mutation policy and research org instructions
- upstream mutable `train.py` -> mutable strategy candidate file
- upstream fixed `prepare.py` -> fixed finance data and evaluation harness
- upstream `val_bpb` loop -> backtest score plus strengths and weaknesses analysis

## 3. North Star Definition

This section describes the final architecture target.

V1 implementation scope is narrower and is defined by the acceptance criteria in section 24.

The final architecture target is that a user can do the following:

1. Start autoresearch from CLI, control Telegram, or OpenClaw.
2. The command is forwarded to Supervisor.
3. Supervisor confirms the system is allowed to run.
4. Supervisor starts the autoresearch worker.
5. The worker asks an OpenClaw agent to propose a strategy mutation.
6. Only the mutable strategy file changes.
7. The fixed harness runs a vectorbt backtest.
8. The system evaluates the result numerically.
9. The system analyzes the result narratively and structurally.
10. The system decides keep or rollback automatically.
11. The state store records the latest truth.
12. Report Telegram receives a notification.
13. Dashboard shows the same state without owning any control.
14. The loop continues until Supervisor stops, pauses, or rejects continuation.

## 4. Scope

## In Scope

- local single-machine orchestration
- Supervisor as the only control owner
- single state store
- pipeline worker and autoresearch worker
- OpenClaw-backed mutation and analysis
- vectorbt backtest harness
- strategy-only mutation boundary
- strengths and weaknesses analysis after evaluation
- automatic keep or rollback decision
- repeat loop in code
- read-only dashboard surface
- control Telegram and report Telegram adapters
- CLI command surface

## Out of Scope For First Version

- distributed execution
- multi-user tenancy
- many mutable strategy files
- live trading
- broker integration
- automatic secret provisioning
- autonomous edits to indicator registry or evaluator
- fully styled dashboard frontend

## 5. Assumptions

- The first version runs on Windows and must avoid Unix-only assumptions.
- Python is the implementation language.
- SQLite is sufficient for the first state store.
- vectorbt is the backtest engine.
- market data is auto-downloaded and cached locally by the pipeline in the first version.
- V1 uses Yahoo Finance via `yfinance` as the default no-auth data source for `QQQ`, `IWM`, and `BTC-USD`.
- Telegram control, Telegram report, and dashboard integrations must be working end-to-end in V1, even if the dashboard UI remains minimal.
- OpenClaw is already installed and has authenticated models available.
- The initial deployment target is one workspace, one project, one active autoresearch run at a time.

### 5.1 Fixed V1 Backtest Target

The first implementation must support exactly one canonical market pack and one canonical execution model.

Market pack contract:

- symbols: `QQQ`, `IWM`, `BTC-USD`
- timeframes: `1d`, `2h`
- fixed evaluation combinations:
  - `QQQ / 1d`
  - `QQQ / 2h`
  - `IWM / 1d`
  - `IWM / 2h`
  - `BTC-USD / 1d`
  - `BTC-USD / 2h`

Acquisition contract:

- provider: `yfinance`
- raw cache directory: `data/market/raw/`
- canonical cache directory: `data/market/canonical/`
- `1d` fetch policy:
  - `interval = 1d`
  - `period = 10y`
  - `auto_adjust = false`
  - `actions = false`
  - `repair = true`
  - `prepost = false`
- `1h` fetch policy for `2h` generation:
  - `interval = 1h`
  - `period = 730d`
  - `auto_adjust = false`
  - `actions = false`
  - `repair = true`
  - `prepost = false`
- raw timestamps remain in provider-local exchange time until session filtering and resampling complete
- canonical timestamps are converted to UTC immediately before cache write
- `1d` data is downloaded directly from the provider
- `2h` data is created by downloading `1h` bars and resampling locally to `2h`
- `QQQ` and `IWM` intraday session policy:
  - keep only regular-session bars in `America/New_York`
  - do not synthesize missing bars
  - build `2h` bars by grouping consecutive regular-session `1h` bars inside the same trading day
  - drop any final unpaired session tail bar that cannot form a full `2h` bucket
  - canonical `2h` timestamp equals the close timestamp of the second source bar in the pair, converted to UTC
- `BTC-USD` intraday session policy:
  - keep all provider bars
  - build `2h` bars by UTC-even-hour resampling with `closed = right` and `label = right`
  - canonical `2h` timestamp equals the right-edge bucket close timestamp in UTC
- pipeline owns download, refresh, normalization, and cache validation
- the operator is never expected to hand-create CSV files

Canonical schema contract:

- required columns: `timestamp`, `open`, `high`, `low`, `close`, `volume`, `symbol`, `timeframe`
- timezone: UTC
- sort order: ascending by `timestamp`
- duplicate timestamps per `symbol + timeframe`: reject
- missing required columns: reject
- all canonical files are stored as one file per combination at `data/market/canonical/{symbol}_{timeframe}.parquet`

Split contract:

- all splits are rolling and anchored to the latest fully closed bar available at pipeline runtime
- `1d` combinations require at least 1,825 calendar days of canonical history
- `1d` split windows:
  - in-sample: latest 1,095 days before validation
  - validation: latest 365 days before out-of-sample
  - out-of-sample: latest 365 days
- `2h` combinations require at least 540 calendar days of canonical history after filtering and resampling
- `2h` split windows:
  - in-sample: latest 270 days before validation
  - validation: latest 135 days before out-of-sample
  - out-of-sample: latest 135 days
- if any fixed combination fails the minimum history requirement, the pipeline fails and autoresearch cannot start

Execution contract:

- engine: `vectorbt.Portfolio.from_signals`
- execution price: `close`
- long entries and short entries are both allowed
- if a strategy does not emit short signals, short arrays remain all false
- initial cash: `100_000`
- fees per side: `0.001`
- slippage per side: `0.0005`
- leverage: `1.0`
- accumulation: disabled
- backtests run independently per fixed combination and are aggregated only after per-combination metrics are computed
- execution frequency matches the canonical timeframe for each combination

This contract is intentionally rigid for the first version. Generalized universe selection is a later feature.

## 6. Primary Design Decision

Use a single mutable strategy file.

The only LLM-editable file is:

`src/finance_autoresearch/strategy/mutable/strategy_candidate.py`

Why this is the correct choice:

- it preserves the cleanest part of upstream autoresearch
- it makes rollback trivial
- it makes mutation review obvious
- it prevents silent architecture drift
- it lets the evaluator and supervisor stay trustworthy

Alternatives rejected:

- DSL or JSON strategy spec: safer but too restrictive for indicator composition and regime-specific logic
- multi-file strategy package: flexible but weakens control and rollback boundaries

## 7. Required Repository Shape

```text
docs/
  superpowers/
    specs/
      2026-03-24-finance-autoresearch-design.md

src/
  finance_autoresearch/
    app.py
    settings.py

    supervisor/
      service.py
      command_gate.py
      transition_guard.py
      process_lock.py

    state/
      models.py
      repository.py
      sqlite_store.py
      outbox.py

    workers/
      pipeline_runner.py
      autoresearch_runner.py
      heartbeat.py

    mutation/
      openclaw_client.py
      prompt_builder.py
      patch_applier.py
      candidate_workspace.py

    strategy/
      base_contract.py
      indicator_registry.py
      regime_registry.py
      mutable/
        strategy_candidate.py

    backtest/
      data_loader.py
      harness.py
      evaluator.py
      analyzer.py
      scoring.py

    integrations/
      cli.py
      openclaw_control.py
      telegram_control.py
      telegram_report.py
      dashboard_api.py

tests/
  ...
```

This structure is not optional. It is the default target structure for implementation unless a later spec amends it.

## 8. Control Model

There is exactly one control owner: Supervisor.

Valid control surfaces:

- CLI
- control Telegram
- OpenClaw control entry
- dashboard action endpoint

All control surfaces do only this:

1. validate incoming command shape
2. forward command to Supervisor
3. return the Supervisor response

They do not:

- spawn workers directly
- mutate state directly
- send reports directly
- decide keep or rollback

Report Telegram is notification-only.

Dashboard is read-only except for explicit command forwarding endpoints that still go through Supervisor.

## 9. Workers

Two worker classes exist.

### Pipeline Worker

Purpose:

- prepare or validate data dependencies
- refresh cached datasets if configured
- run fixed preconditions
- record pipeline success or failure

It does not:

- change strategy code
- own run state transitions beyond reporting progress
- accept direct commands from outside Supervisor

V1 pipeline success contract:

- canonical cached datasets exist for all six fixed combinations
- all six cached datasets pass schema and minimum-history validation
- SQLite store is reachable and migrations are applied
- mutable strategy file exists
- accepted baseline snapshot file exists or is created
- OpenClaw gateway is reachable and required agent mappings resolve
- Telegram control and report credentials load successfully
- dashboard server configuration validates successfully

V1 pipeline orchestration rules:

- pipeline and autoresearch do not run concurrently
- `start_autoresearch` must reject execution if the latest pipeline result is not `success`
- `start_autoresearch` does not auto-run pipeline in V1
- the operator must call `start_pipeline` first and wait for `pipeline_state = success`

### Autoresearch Worker

Purpose:

- execute the research loop
- call OpenClaw agents for hypothesis, mutation, and analysis
- run backtests
- evaluate results
- analyze strengths and weaknesses
- trigger keep or rollback
- continue while Supervisor allows continuation

It does not:

- own system-wide command authority
- bypass the state store
- mutate files outside the allowed strategy boundary

## 10. State Model

State must exist in one place only.

Recommended storage:

- SQLite database for durable structured state
- optional JSON export for dashboard reads or debugging

Required top-level states:

- project_state: `idle | active | paused | degraded`
- pipeline_state: `idle | running | success | failed`
- autoresearch_state: `idle | running | paused | success | failed | stale`

Required autoresearch stages:

1. `hypothesis`
2. `mutate_strategy`
3. `run_backtest`
4. `evaluate_results`
5. `analyze_results`
6. `decide_keep_or_rollback`
7. `repeat_or_stop`

Important rule:

- status is user-facing state
- stage is internal progress inside the current run

Required persisted concepts:

- current project status
- active run id
- worker heartbeat timestamps
- latest command and command result
- latest experiment result
- latest analysis result
- current candidate revision
- current accepted baseline revision
- outbox messages waiting for report delivery
- recovery marker for interrupted iterations

## 11. Supervisor State Transitions

Supervisor must reject invalid transitions.

V1 transition rules:

- `start_pipeline` allowed only when `project_state == idle`
- `start_pipeline` is also allowed when `project_state == degraded`; this is the only command besides `reset_project` that may exit a degraded state
- `start_pipeline` sets `project_state = active` and `pipeline_state = running`
- successful pipeline completion sets `pipeline_state = success`; if autoresearch is not running then `autoresearch_state = idle` and `project_state = idle`
- failed pipeline completion sets `pipeline_state = failed` and `project_state = degraded`
- `start_autoresearch` allowed only when `project_state == idle` and latest pipeline result is `success`
- accepted `start_autoresearch` first validates the repository seed baseline
- if the seed baseline fails compile, contract validation, backtest, or guardrails, `start_autoresearch` is rejected, `autoresearch_state = failed`, and `project_state = degraded`
- if the seed baseline is valid, `start_autoresearch` sets `project_state = active` and `autoresearch_state = running`
- `pause_autoresearch` allowed only when `autoresearch_state == running`; it sets `project_state = paused` and `autoresearch_state = paused`
- `resume_autoresearch` allowed only when `project_state == paused` and `autoresearch_state == paused`; it sets `project_state = active` and `autoresearch_state = running`
- `stop_autoresearch` allowed only when `autoresearch_state in {running, paused}`
- if `stop_autoresearch` is accepted while `autoresearch_state == running`, Supervisor sets `pending_command = "stop_autoresearch"` and the worker exits at the next stage boundary; after the worker stops cleanly it sets `autoresearch_state = success`, `project_state = idle`, and `pending_command = null`
- if `stop_autoresearch` is accepted while `autoresearch_state == paused`, Supervisor stops the run immediately and sets `autoresearch_state = success`, `project_state = idle`, `pending_command = null`, and `active_run_id = null`
- `reset_project` allowed only when `project_state in {idle, degraded}`; it clears transient run state but preserves the accepted baseline
- direct worker start without Supervisor is always rejected
- `active -> active` on duplicate start commands is rejected and must return `accepted = false`
- if the autoresearch loop exits because the repeat gate declines continuation without error, `autoresearch_state = success` and `project_state = idle`
- if the autoresearch loop exits because the crash threshold is exceeded, `autoresearch_state = failed` and `project_state = degraded`

If a worker heartbeat is stale:

- stale pipeline heartbeat:
  - Supervisor sets `pipeline_state = failed`
  - Supervisor sets `project_state = degraded`
  - report outbox gets a pipeline stale event
  - no strategy rollback occurs
- stale autoresearch heartbeat:
  - Supervisor sets `autoresearch_state = stale`
  - Supervisor sets `project_state = degraded`
  - report outbox gets an autoresearch stale event
  - the current candidate is rolled back to the accepted baseline

## 12. Command Contract

Every command forwarded to Supervisor must have a normalized shape.

```python
{
    "command": "start_autoresearch" | "pause_autoresearch" | "resume_autoresearch" | "stop_autoresearch" | "start_pipeline" | "reset_project" | "status",
    "project_id": str | None,
    "source": "cli" | "telegram_control" | "openclaw" | "dashboard",
    "requested_by": str,
    "requested_at": str,
    "payload": dict,
}
```

Supervisor responses must also be normalized.

```python
{
    "accepted": bool,
    "project_state": str,
    "pipeline_state": str,
    "autoresearch_state": str,
    "pending_command": str | None,
    "message": str,
    "run_id": str | None,
}
```

## 13. OpenClaw Integration

OpenClaw is the LLM execution runtime.

The system must not assume raw provider SDK usage as the primary path.

Required adapter:

`src/finance_autoresearch/mutation/openclaw_client.py`

Responsibilities:

- inspect configured agent identities if needed
- send mutation requests to an assigned OpenClaw agent
- send analysis requests to an assigned OpenClaw agent
- return structured outputs
- record failures cleanly

Recommended stage mapping:

- `research` agent: stage 1 hypothesis plus stage 2 mutation
- `critic` agent: stage 5 strengths and weaknesses analysis
- optional `builder` agent: patch sanity review before applying edits

V1 required OpenClaw roles:

- required:
  - `router`
  - `research`
  - `critic`
- optional:
  - `builder`

Required constraint:

OpenClaw output must be converted into structured artifacts before use. Do not let free-form text directly drive state transitions.

V1 checked-in OpenClaw support artifacts:

- `docs/openclaw-setup.md`
- `.env.example`
- `config/openclaw.roles.example.yaml`
- `scripts/check-openclaw.ps1`
- `scripts/openclaw-mutate.ps1`
- `scripts/openclaw-analyze.ps1`
- `schemas/supervisor-command.schema.json`
- `schemas/openclaw-mutation.schema.json`

V1 control ingress protocol:

- `openclaw_control.py` is a local command adapter, not a direct worker entrypoint
- the only allowed V1 control command is:
  - `python -m finance_autoresearch openclaw-control`
- input transport:
  - one JSON command document on `stdin`
  - schema: `schemas/supervisor-command.schema.json`
  - `project_id` is allowed but optional; if omitted, default to `finance`
- output transport:
  - one JSON Supervisor response document on `stdout`
  - schema identical to the Supervisor response contract in section 12
- exit code rules:
  - `0` when Supervisor returns a valid response, including rejected commands
  - non-zero only for malformed JSON, schema failure, or local process failure
- only the OpenClaw router role is allowed to invoke this adapter in V1

V1 mutation and analysis runtime protocol:

- `openclaw_client.py` must call checked-in wrapper scripts instead of embedding provider SDK logic in worker code
- required wrapper interfaces:
  - `scripts/openclaw-mutate.ps1 --agent-id <id> --request-json <path> --response-json <path>`
  - `scripts/openclaw-analyze.ps1 --agent-id <id> --request-json <path> --response-json <path>`
- wrapper request and response payloads are file-based JSON only
- wrappers may log to `stdout` and `stderr`, but they may not emit side-effect files outside the requested response path
- timeout rules:
  - mutation: 180 seconds
  - analysis: 120 seconds
- retry rules:
  - one retry after 2-second backoff for transport or process-launch failure
  - one retry after 2-second backoff for timeout failure
  - zero retries for schema validation failure or rejected structured output
- idempotency key:
  - every runtime request must carry `{run_id}:{iteration}:{stage}`
- separation rule:
  - `openclaw_control.py` handles human-originated control ingress only
  - `openclaw_client.py` handles mutation and analysis runtime only

V1 wrapper request envelope:

```python
{
    "task_kind": "mutation" | "analysis",
    "run_id": str,
    "iteration": int,
    "stage": str,
    "idempotency_key": str,
    "agent_id": str,
    "target_path": str | None,
    "context": dict,
    "expected_schema": "strategy_replacement" | "analysis_artifact",
}
```

V1 wrapper response envelope:

```python
{
    "ok": bool,
    "task_kind": "mutation" | "analysis",
    "idempotency_key": str,
    "artifact": dict | None,
    "error_type": "transport" | "schema" | "model" | "timeout" | None,
    "message": str,
    "retryable": bool,
}
```

Wrapper validation rules:

- `artifact` is required when `ok == true`
- `error_type` and `message` are required when `ok == false`
- `retryable` must be `false` for `schema` failures
- `idempotency_key` in the response must match the request exactly
- retry precedence:
  - the client retries only when `error_type in {"transport", "timeout"}` and `retryable == true`
  - if no envelope is produced because the process launch failed, the client synthesizes `error_type = "transport"` and retries once
  - if the process exceeds timeout and no envelope is produced, the client synthesizes `error_type = "timeout"` plus `retryable = true` and retries once
  - if the wrapper exits non-zero, writes malformed JSON, writes only a partial response file, or exits before producing any response envelope, the client classifies the attempt as `transport`
  - `retryable = false` always wins, even if `error_type` is otherwise retryable

V1 mutation artifact schema:

```python
{
    "kind": "strategy_replacement",
    "target_path": "src/finance_autoresearch/strategy/mutable/strategy_candidate.py",
    "hypothesis": str,
    "change_summary": str,
    "full_file_contents": str,
    "expected_effects": [str, ...],
}
```

V1 analysis artifact schema:

```python
{
    "strengths": [str, ...],
    "weaknesses": [str, ...],
    "coverage_gaps": [str, ...],
    "regime_observations": [str, ...],
    "next_hypothesis_hints": [str, ...],
    "summary": str,
}
```

`patch_applier.py` must accept only the `strategy_replacement` envelope and must reject diffs, shell instructions, or multi-file edits.

## 14. Strategy Mutation Boundary

The LLM may modify only:

`src/finance_autoresearch/strategy/mutable/strategy_candidate.py`

That file may contain:

- strategy parameters
- indicator composition using read-only registries
- entry conditions
- exit conditions
- regime-dependent branching
- lightweight helper functions local to the strategy file

That file must not:

- open network connections
- write files
- mutate state store records
- call Telegram or dashboard code
- modify evaluator logic
- import unsafe modules just to bypass constraints

The file must implement a fixed contract from `base_contract.py`.

Required contract:

```python
@dataclass
class StrategyContext:
    open: pd.Series
    high: pd.Series
    low: pd.Series
    close: pd.Series
    volume: pd.Series
    symbol: str
    timeframe: str
    indicators: IndicatorRegistry
    regimes: RegimeRegistry

@dataclass
class StrategyDefinition:
    long_entries: pd.Series
    long_exits: pd.Series
    short_entries: pd.Series
    short_exits: pd.Series
    regime: pd.Series
    params: dict[str, int | float | bool | str]
    diagnostics: dict[str, pd.Series | int | float | str]

def build_strategy(context: StrategyContext) -> StrategyDefinition: ...
```

The types above are fixed for V1 and must not be reinvented during implementation.

Enforcement is mandatory before import or backtest:

1. validate the OpenClaw response against the mutation artifact schema
2. verify `target_path` matches the one allowed mutable file exactly
3. parse the candidate file with Python AST
4. enforce an import allowlist
5. enforce a forbidden-call blacklist
6. require a top-level `build_strategy` function
7. require `py_compile` success
8. reject files longer than 400 lines

V1 import allowlist:

- `math`
- `numpy`
- `pandas`
- `typing`
- `dataclasses`
- project-local imports from `finance_autoresearch.strategy.base_contract`
- project-local imports from `finance_autoresearch.strategy.indicator_registry`
- project-local imports from `finance_autoresearch.strategy.regime_registry`

V1 forbidden imports and calls:

- `os`
- `sys`
- `subprocess`
- `pathlib`
- `socket`
- `requests`
- `httpx`
- `shutil`
- `tempfile`
- `open`
- `eval`
- `exec`
- `compile`
- `__import__`

## 15. Read-Only Registries

`indicator_registry.py` contains approved indicator implementations.

`regime_registry.py` contains approved regime classification logic.

These registries are read-only for the LLM.

V1 fixed indicator registry API:

- `ema(series: pd.Series, window: int) -> pd.Series`
- `sma(series: pd.Series, window: int) -> pd.Series`
- `rsi(close: pd.Series, window: int = 14) -> pd.Series`
- `atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series`
- `rolling_std(series: pd.Series, window: int) -> pd.Series`

V1 fixed regime registry API:

- `classify_ema200_regime(close: pd.Series) -> pd.Series`
- `is_bull(close: pd.Series) -> pd.Series`
- `is_bear(close: pd.Series) -> pd.Series`

V1 canonical evaluator regime classifier:

- function name: `classify_ema200_regime`
- module path: `finance_autoresearch.strategy.regime_registry`
- input: `close: pd.Series`
- output: `pd.Series` containing only `bull` or `bear`
- rule:
  - `bull` when `close > EMA(close, 200)`
  - `bear` when `close <= EMA(close, 200)`

The fixed harness, evaluator, analyzer, and guardrails must use this exact classifier for regime-sliced metrics in V1.

This design intentionally allows the mutable strategy file to combine trusted building blocks instead of rewriting them.

Examples of allowed composition:

- EMA crossover plus RSI filter
- separate bull and bear branches
- volatility filter gating
- parameter shifts by regime

Examples of forbidden mutation:

- replacing the registry implementation
- editing vectorbt harness internals
- changing the scoring formula from the mutable file

## 16. Backtest Harness

`harness.py` must be the fixed execution layer around vectorbt.

Responsibilities:

- load the fixed six-combination market pack from the canonical loader
- call the current strategy contract
- run vectorbt backtests per symbol and timeframe combination
- return normalized raw results plus aggregate rollups

Normalized raw results should include at least:

- total return
- CAGR
- Sharpe
- Sortino if available
- max drawdown
- win rate
- profit factor
- turnover
- trade count
- exposure
- regime-specific summary slices
- per-combination metric bundles keyed by `symbol` and `timeframe`
- aggregate metric bundles across the full six-combination pack

The harness must be deterministic given the same inputs and candidate code.

The harness must compute metrics for each fixed split separately for every fixed combination:

- in-sample
- validation
- out-of-sample

The harness must also compute regime-sliced out-of-sample metrics for every fixed combination for at least:

- bull regime
- bear regime

## 17. Evaluation

`evaluator.py` is the numeric decision layer.

It converts raw backtest output into:

- score
- guardrail checks
- keep candidate decision input

Required behavior:

- produce one fixed numeric score
- keep the scoring formula outside the mutable file
- treat guardrail violations as first-class signals, not footnotes

V1 metric conventions:

- annualization factors:
  - `QQQ / 1d`: `252`
  - `IWM / 1d`: `252`
  - `BTC-USD / 1d`: `365`
  - `QQQ / 2h`: `756`
  - `IWM / 2h`: `756`
  - `BTC-USD / 2h`: `4380`
- `risk_free_rate = 0.0`
- Sharpe formula:
  - `bar_returns` are computed as `portfolio_value.pct_change().fillna(0.0)` on the split-local equity curve
  - `mean(bar_returns) / std(bar_returns) * sqrt(annualization_factor)`
  - if `std(bar_returns) == 0`, return `0.0`
- Sortino formula:
  - `bar_returns` use the same source as Sharpe
  - `downside_returns = min(bar_returns, 0.0)` elementwise
  - `downside_std = sqrt(mean(downside_returns ** 2))`
  - `mean(bar_returns) / downside_std * sqrt(annualization_factor)`
  - if downside deviation is `0`, return `0.0`
- zero-trade handling:
  - `total_return = 0.0`
  - `cagr = 0.0`
  - `sharpe = 0.0`
  - `sortino = 0.0`
  - `win_rate = 0.0`
  - `profit_factor = 0.0`
  - `trade_count = 0`
  - `turnover = 0.0`
  - `exposure = 0.0`
- non-zero-trade infinity normalization:
  - if gross loss is `0` and gross profit is `> 0`, set `profit_factor = 999.0`
- turnover formula:
  - `entry_count = executed_long_entry_count + executed_short_entry_count`
  - `exit_count = executed_long_exit_count + executed_short_exit_count`
  - `split_years = split_bar_count / annualization_factor`
  - `turnover = (entry_count + exit_count) / max(split_years, 1 / annualization_factor)`
- exposure formula:
  - `exposure = bars_with_non_zero_position / total_bars_in_split`
- drawdown convention:
  - `max_drawdown` is stored as a positive fraction in `[0.0, 1.0]`
- a regime window is considered to exist only when the out-of-sample split contains at least `50` bars for that regime label

V1 fixed scoring rule:

- `score = median(out_of_sample_sharpe across the six fixed combinations)`
- for six values, median means:
  - sort ascending
  - take the 3rd and 4th values
  - return their arithmetic mean

V1 fixed guardrails:

- every fixed combination must produce finite values for:
  - `out_of_sample_total_return`
  - `out_of_sample_cagr`
  - `out_of_sample_sharpe`
  - `out_of_sample_sortino`
  - `out_of_sample_max_drawdown`
  - `out_of_sample_win_rate`
  - `out_of_sample_profit_factor`
  - `out_of_sample_turnover`
  - `out_of_sample_trade_count`
  - `out_of_sample_exposure`
- at least four of the six fixed combinations must have `out_of_sample_trade_count >= 20`
- no fixed combination may have `out_of_sample_max_drawdown > 0.35`
- mean out-of-sample turnover across the six fixed combinations must be `<= 12.0`
- each symbol (`QQQ`, `IWM`, `BTC-USD`) must have non-zero out-of-sample exposure in at least one timeframe
- for each symbol, if both bull and bear regime windows exist across that symbol's out-of-sample combinations, at least one timeframe for that symbol must show non-zero bull exposure and at least one timeframe for that symbol must show non-zero bear exposure

V1 tie-breakers for reporting only:

1. higher mean out-of-sample total return across the six fixed combinations
2. lower worst-combination out-of-sample max drawdown
3. lower mean out-of-sample turnover across the six fixed combinations

Tie-breakers do not override the keep threshold below.

Output shape:

```python
{
    "score": float,
    "metrics": {...},
    "guardrails_passed": bool,
    "guardrail_failures": [str, ...],
}
```

## 18. Analysis Stage

`analyzer.py` is the required stage after numeric evaluation.

Purpose:

- explain what improved
- explain what got worse
- identify missing coverage
- identify likely reasons for failure or success
- produce targeted hints for the next hypothesis

This is not optional commentary. It is a structured artifact that feeds the next loop.

Required output shape:

```python
{
    "strengths": [str, ...],
    "weaknesses": [str, ...],
    "coverage_gaps": [str, ...],
    "regime_observations": [str, ...],
    "next_hypothesis_hints": [str, ...],
    "summary": str,
}
```

## 19. Keep Or Rollback Decision

The keep or rollback rule must live outside the mutable file.

Decision outcomes:

- `keep`
- `rollback`
- `crash`

Baseline initialization rule:

- when autoresearch starts, the system must first evaluate the repository seed `strategy_candidate.py`
- that seed result becomes the accepted baseline before any mutation iteration begins
- if the seed result fails compile, contract validation, backtest execution, or guardrails, the run does not start and the system enters `project_state = degraded` plus `autoresearch_state = failed`

V1 keep threshold:

- keep only if `candidate_score >= baseline_score + 0.05`
- ties are not kept
- guardrail improvements alone do not override a score delta below `0.05`

Keep when:

- score meets the keep threshold
- guardrails pass
- candidate compiles and backtests successfully

Rollback when:

- score is below the keep threshold
- guardrails fail
- the strategy contract breaks
- the patch touches forbidden files

Crash when:

- syntax error
- import error
- runtime error
- backtest execution failure

Crash handling rule:

- crash always triggers immediate rollback to the accepted baseline
- the crashed candidate is recorded in iteration history but never left as the working strategy file

Rollback must restore the last accepted strategy candidate exactly.

## 20. Loop Model

The autoresearch worker owns the internal repeat loop, but only under Supervisor approval.

Reference loop:

```python
while supervisor.allows_continue(run_id):
    run_hypothesis_stage()
    run_mutation_stage()
    run_backtest_stage()
    run_evaluation_stage()
    run_analysis_stage()
    run_keep_or_rollback_stage()
    run_repeat_gate_stage()
```

The repeat loop must stop when:

- Supervisor receives a stop command
- project moves to `paused`
- project moves to `degraded`
- repeated crashes exceed threshold
- process lock is lost

V1 repeated crash threshold:

- three consecutive crashes in the same run

## 20.1 Recovery Contract

Recovery behavior is fixed for V1.

On process startup:

1. if an iteration was in progress and not marked complete, mark it as `crash_recovered`
2. restore the accepted baseline contents into the mutable strategy file
3. clear the active process lock
4. if `pipeline_state == running`, set `pipeline_state = failed`
5. if `autoresearch_state in {running, paused}`, set `autoresearch_state = stale`
6. if step 4 or step 5 changed state, set `project_state = degraded`
7. if `project_state` was already `degraded`, preserve it
8. if no recovery failure was detected, preserve the last terminal states instead of forcing `idle`
9. set `active_run_id = null`
10. set `current_stage = null`
11. set `pending_command = null`
12. preserve the latest completed experiment result and latest completed analysis artifact

Recovery event rule:

- if startup recovery changes `pipeline_state` from `running` to `failed`, enqueue one `pipeline_recovered_stale` outbox event
- if startup recovery changes `autoresearch_state` from `running` or `paused` to `stale`, enqueue one `autoresearch_recovered_stale` outbox event
- these recovery events are emitted exactly once per recovery pass

Recovery exit rule:

- a recovered `degraded` or `stale` state remains visible until `reset_project` is called or a fresh `start_pipeline` run succeeds

V1 does not attempt mid-iteration resume.

Outbox delivery semantics:

- delivery is at-least-once
- each message has a unique id
- adapters mark `sent_at` only after confirmed delivery
- unsent messages remain pending across restart

## 21. Report Surface

Report Telegram is notification-only.

It consumes outbox messages such as:

- autoresearch started
- candidate crashed
- candidate kept
- candidate rolled back
- worker stale
- project paused
- project resumed

The report adapter must not infer system state. It only formats and sends already persisted events.

## 22. Dashboard Surface

Dashboard is read-only by default.

It shows:

- current project state
- current pipeline state
- current autoresearch state
- current stage
- latest accepted baseline metrics
- latest candidate metrics
- latest strengths and weaknesses analysis
- recent command history
- recent notification history

If the dashboard exposes action buttons later, those actions still call Supervisor through the same command contract.

## 23. Logging And Traceability

Every experiment iteration must persist:

- run id
- iteration number
- candidate revision id
- baseline revision id
- hypothesis text
- mutation summary
- backtest metrics
- analysis output
- final decision
- timestamps

This is required for debugging and human review.

## 24. Acceptance Criteria

The first working version is done when all of the following are true:

1. A single command can start autoresearch through Supervisor.
2. Only one autoresearch run can be active at a time.
3. The mutable strategy file is the only LLM-edited file.
4. The pipeline can auto-download, normalize, and cache all six fixed combinations according to the fetch policy in section 5.1.
5. The fixed harness runs vectorbt backtests for all six fixed combinations across all three fixed splits.
6. The fixed harness emits per-combination metrics and aggregate metrics, including bull and bear out-of-sample slices.
7. Evaluation produces a numeric score and guardrail result using the metric conventions in section 17.
8. Analysis produces structured strengths, weaknesses, coverage gaps, regime observations, and next-hypothesis hints.
9. Keep and rollback both work, and rollback restores the accepted baseline file contents exactly.
10. State is persisted and recoverable after process restart without erasing `degraded` or `stale` truth.
11. CLI, OpenClaw control ingress, and control Telegram can all query the same consistent status from Supervisor.
12. Report outbox records events and report Telegram sends those events without inferring state on its own.
13. OpenClaw is used through the adapter and wrapper protocol, not scattered shell calls.
14. `scripts/check-openclaw.ps1` exits `0` and confirms that all required OpenClaw roles resolve before `start_autoresearch` is allowed.
15. A `status` command sent through `python -m finance_autoresearch openclaw-control` returns a valid normalized Supervisor response on `stdout` with exit code `0`.
16. A control Telegram `start_pipeline` command reaches Supervisor, creates a command-history record, and produces the same state transition as the CLI path.
17. A report event created by a successful pipeline run is delivered through report Telegram without any direct worker-to-Telegram call.
18. The dashboard status endpoint returns the same `project_state`, `pipeline_state`, `autoresearch_state`, and `run_id` values as the CLI `status` command for the same moment.
19. OpenClaw setup documentation, example role mapping, and health-check scripts are checked in for reuse.

## 25. Recommended Build Order

Build in this order:

1. state models plus SQLite store
2. Supervisor command handling and process lock
3. strategy contract plus mutable candidate boundary
4. fixed data loader plus vectorbt harness
5. evaluator and analyzer
6. rollback mechanics
7. OpenClaw adapter
8. autoresearch loop
9. CLI surface
10. Telegram and dashboard adapters

Do not start with Telegram or dashboard.

## 26. Risks

- If the mutable boundary is not enforced strongly, the system will drift into uncontrolled edits.
- If state lives in more than one place, control surfaces will disagree.
- If analysis is only free-form text, the next loop will become noisy and unstable.
- If keep or rollback criteria are fuzzy, the system will preserve bad strategies.
- If OpenClaw calls are embedded directly in workers without an adapter, later changes will be expensive.

## 27. Decision Log

1. Keep the upstream single-mutable-target pattern.
Reason: it is the cleanest control boundary.

2. Use SQLite as the first state store.
Reason: durable, simple, local-first, enough for one-machine orchestration.

3. Separate status from stage.
Reason: user-facing state and internal progress are different concerns.

4. Make analysis a required stage after evaluation.
Reason: the user explicitly wants strengths and weaknesses discovery before later loop stages.

5. Make OpenClaw the LLM runtime through one adapter.
Reason: authenticated model reuse and clean separation from provider details.

6. Keep dashboard read-only.
Reason: it prevents split-brain control behavior.

7. Keep Telegram split into control and report surfaces.
Reason: command traffic and notification traffic should not share behavior or permissions.

8. Require explicit pipeline success before autoresearch start.
Reason: it removes cold-start ambiguity and keeps command flow simple.

9. Use `classify_ema200_regime` as the fixed V1 bull and bear evaluator.
Reason: regime-sliced metrics must be reproducible across implementations.

10. Treat pipeline stale and autoresearch stale as different failures.
Reason: only autoresearch stale affects the mutable strategy baseline.

## 28. Implementation Brief For Coding Agents

Build exactly this:

- a Python package named `finance_autoresearch`
- one Supervisor service with strict command gating
- one SQLite-backed state store
- one mutable strategy candidate file and no other LLM-editable source
- one fixed vectorbt harness
- one evaluator and one analyzer
- one OpenClaw adapter
- one autoresearch loop with keep or rollback

Avoid inventing:

- extra services
- extra state stores
- multi-agent orchestration outside OpenClaw adapter calls
- multiple mutable strategy files
- direct control from dashboard or Telegram to workers

If something is unclear during implementation, prefer preserving the control boundary over adding flexibility.

## 29. User Review Gate

This spec should be reviewed by the user before implementation planning starts.
