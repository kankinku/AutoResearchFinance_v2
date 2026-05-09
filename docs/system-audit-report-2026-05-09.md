# AF System Audit Report - 2026-05-09

## Executive Summary

Status: **주의(P1)**. Target selector, target-scoped state root, chart conflict guard, focused TypeScript/runtime validations are operating correctly, so QQQ 120m and BTC 15m modes can be selected through the same `shared_af_autonomous_learning` mechanism. However, the full `npm test` suite still has legacy shared-state assumptions, and TradingView E2E could not open the Pine editor within timeout, so external promotion readiness is not clear.

Cleanup/delete/confirm/migration commands were not executed. Only `cleanup-runtime --target tradingview-cache --dry-run` was run.

## Environment

| Item | Result |
| --- | --- |
| Branch | `codex/feat-target-state-partition-20260509` |
| HEAD | `2960259` |
| Node.js | `v22.21.0` |
| npm | `11.7.0` |
| Runtime stop | `scripts/stop-af.ps1` completed: `AF runtime is stopped for C:\Users\hanji\Desktop\AF` |
| Git status before report | Clean tracked tree on branch tracking origin |

## Training Mode

The system now treats QQQ 120m and BTC 15m as selectable chart profiles using the same learning mechanism, not as different learning mechanisms.

| Scenario | Result |
| --- | --- |
| Default inspect | PASS: `qqq-120m-af`, `QQQ`, `120`, `shared_af_autonomous_learning` |
| BTC inspect | PASS: `btc-15m-af`, `BTCUSD`, `15`, `shared_af_autonomous_learning` |
| State partition | PASS: both modes read target-scoped roots under `state\targets\<targetId>\pi-autoresearch` |
| Chart match | PASS: `chartMatchesTarget: true` for default QQQ and explicit BTC checks |
| Conflict guard | PASS: QQQ target with `TRADINGVIEW_CHART_SYMBOL=BTCUSD` exits with code `1` and reports the symbol conflict |
| Dashboard selector API | PASS: `/api/status?target=qqq-120m-af` and `/api/status?target=btc-15m-af` returned different selected chart profiles and state roots |

Observed mode payloads:

```json
{
  "qqq": {
    "targetId": "qqq-120m-af",
    "symbol": "QQQ",
    "timeframe": "120",
    "mechanism": "shared_af_autonomous_learning",
    "stateRoot": "C:\\Users\\hanji\\Desktop\\AF\\state\\targets\\qqq-120m-af\\pi-autoresearch"
  },
  "btc": {
    "targetId": "btc-15m-af",
    "symbol": "BTCUSD",
    "timeframe": "15",
    "mechanism": "shared_af_autonomous_learning",
    "stateRoot": "C:\\Users\\hanji\\Desktop\\AF\\state\\targets\\btc-15m-af\\pi-autoresearch"
  }
}
```

Dashboard returned `optionCount: 3`, which means one additional configured target is visible beyond the two user-facing assumptions in this audit plan. This is not a runtime blocker, but the UI should clearly label dry-run or non-primary targets.

## Runtime Health

`scripts/stop-af.ps1` was executed before diagnostics. After the stop, no AF autonomous loop or dashboard runtime was left running as an AF-owned Node process. Later browser/WebView processes seen after TradingView checks were Windows/WebView related and not a duplicate AF runtime.

`system-health-report` for the default target returned:

```json
{
  "currentTrainingMode": {
    "targetId": "qqq-120m-af",
    "symbol": "QQQ",
    "timeframe": "120",
    "mechanism": "shared_af_autonomous_learning",
    "statePartition": "target_scoped_state_root",
    "chartMatchesTarget": true
  },
  "heartbeat": {
    "status": "missing",
    "pid": null,
    "logFile": null
  }
}
```

The missing heartbeat is expected because the audit intentionally stopped the AF runtime before inspection.

## Data Integrity

Default target ledger validation passed with zero records and zero issues:

```json
{
  "experiments": 0,
  "candidates": 0,
  "taskBatches": 0,
  "issueCount": 0
}
```

`rebuild-indexes --verify` completed successfully for the default target and returned verification output.

Legacy shared state was inspected explicitly through `--state-root state\pi-autoresearch`. It remains isolated as legacy shared state and was not auto-mixed into the current target:

```json
{
  "statePartition": "legacy_shared_state_root",
  "ledgerTargetTagging": "legacy_untagged",
  "experimentRecordCount": 1991,
  "targetTaggedRecordCount": 0,
  "currentTargetRecordCount": 0,
  "untaggedRecordCount": 1991
}
```

Legacy ledger validation completed with one warning:

```json
{
  "severity": "warning",
  "scope": "candidate-dedup",
  "message": "Duplicate candidate source hash detected across ids: cand-2a5e6ffe, cand-51397d04, cand-9cbc4c5f, cand-a93778fa, cand-bbb67c15, cand-fdc1ae65"
}
```

Parallel `inspect-autonomous-state` was run three times concurrently. All three runs exited with code `0`, and no `EPERM rename` or derived-view write collision reproduced.

## Validation Results

| Check | Result |
| --- | --- |
| `npm run typecheck` | PASS |
| Focused Vitest suite | PASS: 7 files, 64 tests |
| `npm test` expanded validation | FAIL: 61 files total, 55 passed, 5 failed, 1 skipped; 297 passed, 12 failed, 2 skipped |
| TradingView E2E | FAIL: Pine editor open timeout after 15 seconds, hard reload recovery also timed out |

Focused Vitest command:

```powershell
npx vitest run tests/cli/runtime-config.test.ts tests/config/target-registry.test.ts tests/dashboard/data.test.ts tests/cli/ledger-commands.test.ts tests/state/ledger-validator.test.ts tests/state/index-builder.test.ts tests/utils/fs.test.ts
```

Focused tests passed and cover the recent target registry, dashboard status, ledger validation, index rebuild, and runtime config surfaces.

`npm test` failures are concentrated in tests that still expect legacy shared-state fixtures or pre-partition behavior:

| Area | Evidence |
| --- | --- |
| `tests/cli/monitor.test.ts` | Missing `state/pi-autoresearch/traces` |
| `tests/research/iteration.test.ts` | Missing legacy context/ledger files and one expected parent mismatch |
| `tests/research/research-knowledge.test.ts` | Expected `available`, received `none` |
| `tests/research/task-batch-runner.test.ts` | Missing legacy ledger files and one timeout |
| `tests/state/knowledge-catalog.test.ts` | Audit and migration expectations no longer align with current state |

TradingView E2E was first run exactly with `AF_ENABLE_TV_E2E=1` and failed immediately because `AF_TV_E2E_CANDIDATE_PATH` was required. It was rerun with `strategies\source\seed_primary.pine` as the candidate path and an explicit 120 second Vitest timeout. Both E2E tests then failed while opening the TradingView Pine editor.

Classification: **chart load / Pine editor timeout**. This is separated from local AF validation. Local typecheck and focused tests passed.

## Storage Optimization

Largest measured runtime/state paths:

| Path | Size | Files | Note |
| --- | ---: | ---: | --- |
| `state\pi-autoresearch` | 9326.62 MB | 8114 | Legacy shared state dominates disk usage |
| `state\pi-autoresearch\runtime` | 4455.93 MB | 2699 | Runtime artifacts under legacy state |
| `state\pi-autoresearch\runtime\tradingview-web-profile` | 4407.13 MB | 2683 | Manual cleanup candidate only; not deleted |
| `state\pi-autoresearch\artifacts` | 4207.53 MB | 2395 | Large legacy artifacts |
| `state\pi-autoresearch\logs` | 32.26 MB | 52 | Cleanup candidate if policy allows |
| `.omx\state` | 9.52 MB | 162 | Runtime state, should remain uncommitted |
| `state\targets` | 2.89 MB | 151 | Target-scoped state roots |
| `.omx\logs` | 0.45 MB | 44 | Runtime logs, should remain uncommitted |
| `artifacts\dashboard` | 0.14 MB | 39 | Dashboard artifacts/logs |

Dry-run cleanup result:

```json
{
  "target": "tradingview-cache",
  "dryRun": true,
  "candidateCount": 0,
  "deletedCount": 0,
  "deletedBytes": 0
}
```

No cleanup action was taken. `runtime/tradingview-web-profile` was not deleted and should stay a manual cleanup candidate with backup/session implications documented before any removal.

## Risks And Fix Plan

| Severity | Risk | Evidence | Recommended action |
| --- | --- | --- | --- |
| P1 | Full test suite still contains legacy shared-state assumptions | `npm test` failed in monitor, research, task batch, and knowledge catalog tests | Update test fixtures/helpers to resolve target-scoped roots by default, and explicitly opt into `state\pi-autoresearch` only for legacy tests |
| P1 | TradingView E2E cannot establish Pine editor readiness | Pine editor open timed out after 15 seconds, hard reload recovery also timed out | Add a preflight diagnostic for auth/session/chart readiness, preserve `tv_unavailable` or `chart_load_timeout` in readiness reports, and tune E2E timeouts separately from local tests |
| P2 | Legacy state consumes about 9.33 GB | `state\pi-autoresearch` size report | Keep as isolated legacy data, then design a reviewed archival or cleanup process with backup and explicit confirmation |
| P2 | Dashboard exposes three target options while audit assumptions mention two | Dashboard API returned `optionCount: 3` | Label dry-run/non-primary targets clearly or filter the selector to user-facing targets |
| P2 | Legacy ledger contains duplicate candidate source hashes | `validate-ledger --state-root state\pi-autoresearch` warning | Keep warning as non-blocking, then dedupe or annotate legacy records through an explicit migration command only |

## Commands Run

| Command | Result summary |
| --- | --- |
| `git status --short --branch` | Clean branch tracking origin before report |
| `powershell -ExecutionPolicy Bypass -File scripts/stop-af.ps1` | AF runtime stopped |
| `node --version`; `npm --version` | `v22.21.0`; `11.7.0` |
| `inspect-autonomous-state` | PASS: default QQQ 120m target-scoped mode |
| `inspect-autonomous-state --target btc-15m-af` | PASS: BTCUSD 15m target-scoped mode |
| `inspect-autonomous-state` with conflicting chart env | PASS: blocked with symbol conflict, exit code `1` |
| `dashboard --port 49221`; `/api/status?target=...` | PASS: QQQ/BTC selector API returned distinct chart profiles and roots |
| `system-health-report` | PASS: default mode visible, heartbeat missing as expected after stop |
| `validate-ledger` | PASS: default target zero issues |
| `rebuild-indexes --verify` | PASS |
| `inspect-autonomous-state --state-root state\pi-autoresearch` | PASS: legacy untagged records remain isolated |
| `validate-ledger --state-root state\pi-autoresearch` | PASS with one warning |
| Parallel `inspect-autonomous-state` x3 | PASS: all exit code `0`, no rename/write collision |
| Storage size scan | Completed, largest paths listed above |
| `cleanup-runtime --target tradingview-cache --dry-run` | PASS: dry-run only, zero candidates |
| `npm run typecheck` | PASS |
| Focused Vitest suite | PASS: 64 tests |
| `npm test` | FAIL: legacy fixture/state expectation failures |
| `AF_ENABLE_TV_E2E=1 npm run test:e2e:tradingview` | FAIL: missing required candidate path |
| TradingView E2E with candidate path and 120s timeout | FAIL: Pine editor open timeout |
