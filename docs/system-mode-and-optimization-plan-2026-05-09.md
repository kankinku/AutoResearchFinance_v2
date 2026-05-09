# AF System Mode And Optimization Plan - 2026-05-09

## Current Training Mode

Current default execution mode is:

- Target: `qqq-120m-af`
- Market/timeframe: `QQQ` `120m`
- Strategy family: `AF`
- Goal mode: `improve`
- Research mode: `continuous_improvement`
- Primary executor: local AF backtest
- External calibration: TradingView optional queue
- Current chart environment: `TRADINGVIEW_CHART_SYMBOL=QQQ`, `TRADINGVIEW_CHART_TIMEFRAME=120`

This means the system is currently configured for the QQQ 2-hour model by default. It is not currently configured to run the separate BTC 15-minute target unless the command explicitly sets `--target btc-15m-af`, `--symbol BTCUSD`, or `AF_RESEARCH_TARGET_ID=btc-15m-af` with a matching state root.

Configured targets:

- `qqq-120m-af`: `QQQ` `120m`, objective file `objective.qqq-120m.json`
- `btc-15m-af`: `BTCUSD` `15m`, objective file `objective.btc-15m.json`
- `qqq-60m-af-dryrun`: `QQQ` `60m`, objective file `objective.qqq-60m.json`

## Data Separation Finding

The code has target configuration files for QQQ 120m and BTC 15m, but the current default state root is shared:

- `state/pi-autoresearch`

The current experiment ledger has 1,991 experiment records, and all inspected records are legacy untagged records:

- `targetId`: missing on 1,991 / 1,991 records
- `symbol/timeframe/goalMode`: missing on 1,991 / 1,991 records

This means the current historical state cannot reliably prove target separation from ledger metadata alone. Newer execution paths can resolve target context at runtime, but the persisted records need target tags and preferably target-scoped state roots before QQQ and BTC histories can be treated as cleanly separated training datasets.

## Storage And File Optimization Findings

Current state footprint is approximately 9.78 GB:

- `state/pi-autoresearch/runtime`: about 4.67 GB
- `state/pi-autoresearch/artifacts`: about 4.41 GB
- `state/pi-autoresearch/ledger`: about 345 MB

Largest observed runtime component:

- `state/pi-autoresearch/runtime/tradingview-web-profile`: about 4.4 GB

Largest artifact pattern:

- `state/pi-autoresearch/artifacts/desktop-runs/pi-loop-backtest-*.json`
- many files are roughly 6.5 MB each

Operational findings:

- Ledger validation is currently passing with 0 errors and 1 duplicate-source warning.
- TradingView health is currently unavailable.
- Latest strong local candidate `cand-deb83b0a` is quarantined because external TV verification failed with `tv_surface_failure`.
- Parallel read/inspect commands can still collide on derived view writes, observed as an `EPERM rename` during concurrent diagnostics.

## Improvement Plan

### Phase 1 - Make Mode Explicit Everywhere

Status: partially implemented.

Actions:

- Add `currentTrainingMode` to `inspect-autonomous-state`.
- Surface target ID, symbol, timeframe, goal mode, research mode, objective policy, chart match status, and state partition status.
- Treat missing target tags as a visible warning, not an implicit success.
- Extend dashboard and system health report to show the same current mode block.

Acceptance criteria:

- A user can run one command and see whether the system is currently in `qqq-120m-af` or `btc-15m-af`.
- If chart env and target config disagree, the report explicitly says so.
- If state root is shared, the report says `shared_state_root`.

### Phase 2 - Enforce Target-Scoped Training State

Actions:

- Introduce recommended state roots:
  - `state/pi-autoresearch/targets/qqq-120m-af`
  - `state/pi-autoresearch/targets/btc-15m-af`
- Add start scripts or documented commands that always set both:
  - `AF_RESEARCH_TARGET_ID`
  - `AF_STATE_ROOT`
- Add a preflight guard that blocks BTC runs in a QQQ state root and QQQ runs in a BTC state root unless an explicit override is used.
- Ensure every new experiment, candidate, calibration, problem, repair, and head event record includes `targetId`, `symbol`, `timeframe`, `goalMode`, and `goalProfileId`.

Acceptance criteria:

- New records are target-tagged.
- QQQ and BTC can be audited independently.
- `inspect-autonomous-state --target btc-15m-af` does not mix QQQ history into BTC status.

### Phase 3 - Migrate Or Quarantine Legacy Untagged Records

Actions:

- Write a dry-run migration report that classifies legacy records by available evidence:
  - candidate path/spec objective
  - objective artifact symbol/timeframe
  - chart target metadata inside artifact bundles
  - run timestamp and known environment
- Only auto-tag records with high-confidence evidence.
- Keep ambiguous records in a `legacy_untagged` partition.

Acceptance criteria:

- No record is silently assigned to QQQ or BTC without evidence.
- Reports continue to include legacy records only when explicitly requested.

### Phase 4 - Runtime And Artifact Cleanup

Actions:

- Use existing `cleanup-runtime --target tradingview-cache --confirm` for allowlisted browser caches only.
- Add retention policy for `desktop-runs` artifacts:
  - keep full artifacts for promoted, verified, frontier, and recent candidates
  - compact or archive failed/duplicate/low-value runs
  - never delete without a dry-run report first
- Compress or summarize large backtest artifacts older than the active review window.

Acceptance criteria:

- Runtime footprint drops materially without deleting session/login files.
- Artifact cleanup report lists candidate ID, decision, size, and retention reason.
- Ledger validation passes after cleanup.

### Phase 5 - View Write Serialization

Actions:

- Add a shared derived-view write lock for commands that rebuild or update `state/pi-autoresearch/views`.
- Make read-only inspect commands avoid rebuilding derived views unless requested with `--refresh`.
- Retry atomic rename on Windows `EPERM` for known transient file-lock cases.

Acceptance criteria:

- Running multiple inspect commands in parallel does not fail with `EPERM rename`.
- Dashboard reads do not race with index rebuild writes.

### Phase 6 - TradingView Verification Recovery

Actions:

- Repair current `tv_surface_failure` path before treating local candidates as promotion-ready.
- Add a small health-check command that verifies browser/CDP/profile/chart state before queue processing.
- Re-run external verification for `cand-deb83b0a` after TV health is available.

Acceptance criteria:

- TV health is `healthy` before calibration processing.
- Strong local candidates either become verified or receive actionable failure reasons.

## Recommended Immediate Commands

For current QQQ 120m mode:

```powershell
node dist/cli/index.js inspect-autonomous-state
node dist/cli/index.js system-health-report
```

For BTC 15m with explicit separation:

```powershell
$env:AF_RESEARCH_TARGET_ID = "btc-15m-af"
$env:AF_STATE_ROOT = "state\pi-autoresearch\targets\btc-15m-af"
$env:TRADINGVIEW_CHART_SYMBOL = "BTCUSD"
$env:TRADINGVIEW_CHART_TIMEFRAME = "15"
node dist/cli/index.js run-autonomous-loop --target btc-15m-af --count 1
```

For QQQ 120m with explicit separation:

```powershell
$env:AF_RESEARCH_TARGET_ID = "qqq-120m-af"
$env:AF_STATE_ROOT = "state\pi-autoresearch\targets\qqq-120m-af"
$env:TRADINGVIEW_CHART_SYMBOL = "QQQ"
$env:TRADINGVIEW_CHART_TIMEFRAME = "120"
node dist/cli/index.js run-autonomous-loop --target qqq-120m-af --count 1
```
