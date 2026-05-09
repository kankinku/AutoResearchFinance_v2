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

This means the system uses one shared AF autonomous learning mechanism and selects a chart profile for the run. QQQ 2-hour is the default profile. BTC 15-minute training is selected with `--target btc-15m-af`, `AF_RESEARCH_TARGET_ID=btc-15m-af`, or the dashboard training mode selector. The selected profile controls symbol, timeframe, objective policy, and target-scoped state root.

Mechanism:

- `shared_af_autonomous_learning`: same loop, same scoring flow, same local-first validation flow.
- Training mode selection changes the chart profile and state partition, not the learning algorithm.

Configured targets:

- `qqq-120m-af`: `QQQ` `120m`, objective file `objective.qqq-120m.json`
- `btc-15m-af`: `BTCUSD` `15m`, objective file `objective.btc-15m.json`
- `qqq-60m-af-dryrun`: `QQQ` `60m`, objective file `objective.qqq-60m.json`

## Data Separation Finding

The code has target configuration files for QQQ 120m and BTC 15m. New default runtime state is target-scoped:

- `state/targets/qqq-120m-af/pi-autoresearch`
- `state/targets/btc-15m-af/pi-autoresearch`

The old shared root remains a legacy partition:

- `state/pi-autoresearch`

The current experiment ledger has 1,991 experiment records, and all inspected records are legacy untagged records:

- `targetId`: missing on 1,991 / 1,991 records
- `symbol/timeframe/goalMode`: missing on 1,991 / 1,991 records

This means the historical shared state cannot reliably prove target separation from ledger metadata alone. New execution uses target-scoped roots by default, and the legacy shared ledger is not mixed into current target status unless explicitly selected.

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

Status: implemented.

Actions:

- Add `currentTrainingMode` to `inspect-autonomous-state`.
- Surface target ID, symbol, timeframe, goal mode, research mode, objective policy, chart match status, and state partition status.
- Treat missing target tags as a visible warning, not an implicit success.
- Extend dashboard and system health report to show the same current mode block.
- Add a dashboard training mode selector backed by `/api/status?target=<targetId>`.

Acceptance criteria:

- A user can run one command and see whether the system is currently in `qqq-120m-af` or `btc-15m-af`.
- A user can select QQQ 120m or BTC 15m in the dashboard without changing the learning mechanism.
- If chart env and target config disagree, the report explicitly says so.
- If state root is legacy shared, the report says `legacy_shared_state_root`.

### Phase 2 - Enforce Target-Scoped Training State

Actions:

- Introduce recommended state roots:
  - `state/targets/qqq-120m-af/pi-autoresearch`
  - `state/targets/btc-15m-af/pi-autoresearch`
- Add start scripts or documented commands that always set both:
  - `AF_RESEARCH_TARGET_ID`
  - `AF_STATE_ROOT`
- Add a preflight guard that blocks target/chart mismatches.
- Ensure autonomous execution filters current status to the selected target and does not count legacy untagged records as current target records.

Acceptance criteria:

- New records are target-tagged.
- QQQ and BTC can be audited independently.
- `inspect-autonomous-state --target btc-15m-af` does not mix QQQ history into BTC status.

### Phase 3 - Migrate Or Quarantine Legacy Untagged Records

Actions:

- Use `migrate-legacy-experiments --target <targetId> --dry-run` to report untagged records.
- Use `migrate-legacy-experiments --target <targetId> --confirm` to append tagged copies into the target-scoped state root.
- Keep the original shared records in the `legacy_untagged` partition.

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

- Add a shared JSON write lock for commands that rebuild or update derived views.
- Keep atomic temp-file writes, but serialize the final rename per JSON file.

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
$env:AF_STATE_ROOT = "state\targets\btc-15m-af\pi-autoresearch"
$env:TRADINGVIEW_CHART_SYMBOL = "BTCUSD"
$env:TRADINGVIEW_CHART_TIMEFRAME = "15"
node dist/cli/index.js run-autonomous-loop --target btc-15m-af --count 1
```

For QQQ 120m with explicit separation:

```powershell
$env:AF_RESEARCH_TARGET_ID = "qqq-120m-af"
$env:AF_STATE_ROOT = "state\targets\qqq-120m-af\pi-autoresearch"
$env:TRADINGVIEW_CHART_SYMBOL = "QQQ"
$env:TRADINGVIEW_CHART_TIMEFRAME = "120"
node dist/cli/index.js run-autonomous-loop --target qqq-120m-af --count 1
```
