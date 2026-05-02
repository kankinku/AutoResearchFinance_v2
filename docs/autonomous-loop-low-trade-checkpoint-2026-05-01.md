# Autonomous Loop Low-Trade Checkpoint - 2026-05-01

## Current Saved Approach

This checkpoint preserves the current focused low-trade stagnation strategy before the next improvement pass.

## Active Mechanism

- Run mode: local-first autonomous loop.
- TradingView: excluded from active decision making while unavailable.
- Breakout mode: `exploration_breakout`.
- Outcome memory window: recent breakout candidates are grouped by route.
- Suppression: routes repeatedly missing the OOS trade floor are placed in `suppressedRoutes`.
- Preference: routes with eligible breakout evidence are placed in `preferredRoutes`.
- Sparse signal: repeated sparse OOS profiles such as `31/7`, `7/1`, and `3/1` add `sparse_oos_trade_cluster`.
- Best current breakout evidence: `cand-f80d7394` on `time_boxed_event_rotation`.

## Current Route State

- Preferred route: `time_boxed_event_rotation`.
- Suppressed routes:
  - `momentum_continuation_pullback`
  - `mean_reversion_reentry`
  - `volatility_compression_release`
  - `event_reclaim_reversal`
- Repair fallback: when all alternate routes are suppressed, stay on `time_boxed_event_rotation` but forbid the failed sparse implementation.

## Observed Problem

The route-selection mechanism works, but recent candidates still repeat the `31 trades / 7 OOS trades` profile inside `time_boxed_event_rotation`.

Recent status before this checkpoint:
- Recent 12 local candidates: 11 at `31/7`, 1 at `2/1`.
- Recent eligible candidates: 0.
- The bottleneck has moved from route selection to route-internal implementation diversity.

## Next Improvement Direction

Add a stronger time-boxed route variant policy:
- Escalate after repeated `31/7` on `time_boxed_event_rotation`.
- Force deterministic route-internal variants instead of generic prompt advice.
- Explicitly ban the last sparse implementation shape.
- Require broader post-event participation, zero or low cooldown, and simple time exits.
- Use a variant ladder so repeated failures trigger a materially different skeleton.

## Improvement Pass 2

After the first variant run, the loop produced another `31/7` candidate even though it followed the broad event-window title and shape. The root cause was route-internal: the generated script still used sparse AF milestone events and stacked `entryPass` filters.

Implemented follow-up controls:
- Force `eventFloorBars` default 4 or 5 and early bull/bear events before L1/L2/L3 milestones.
- Forbid L1/L2/L3, candidate, strong, or confirmed events as the only time-boxed event source.
- Limit `entryPass` to `primaryEntryTrigger` plus at most one lightweight risk-off exclusion.
- Add preflight blocking codes for old sparse implementations:
  - `time_boxed_sparse_event_source`
  - `time_boxed_entry_overfiltered`

Dry-run result:
- Active route remains `time_boxed_event_rotation`.
- Preferred route remains `time_boxed_event_rotation`.
- Dominant sparse pattern remains `31/7`.
- Current variant escalated to `thresholdless_event_age_rotation`.
- The old sparse candidate `cand-69526792` is now blocked by preflight before local evaluation.

## Improvement Pass 3

After Pass 2, the loop correctly blocked sparse `time_boxed_event_rotation` candidates, but generation still spent most of the mutation phase before preflight and then timed out while asking the LLM for repair.

Implemented deterministic preflight normalization:
- If `time_boxed_sparse_event_source` or `time_boxed_entry_overfiltered` is detected under `breakoutVariantDirective`, patch the generated Pine before calling LLM repair.
- Inject `eventFloorBars = input.int(4, ...)`.
- Inject `bullEventFloor`, `bearEventFloor`, `earlyBullEvent`, and `earlyBearEvent`.
- Prefer early events in `bullEventRaw` and `bearEventRaw`.
- Collapse overfiltered `entryPass` to `primaryEntryTrigger and not riskOff`.
- Re-run preflight immediately and skip slow LLM repair if the deterministic fix clears the block.

Verification:
- `cand-69526792` initially blocks on `time_boxed_sparse_event_source` and `time_boxed_entry_overfiltered`.
- After deterministic normalization, blocking issues are `[]`.

## Improvement Pass 4

The next run proved that the deterministic repair path worked operationally, but the evaluated candidate still produced `31/7`. Source inspection showed the dense event floor was created but the actual entry window still used sparse aliases or delayed windows:
- `bullEarlyEvent = newBullL1 or newBullCandidate ...`
- `bearEarlyEvent = newBearL1 or newBearCandidate ...`
- `bullEventAge >= eventFloorBars`
- `bearEventAge >= eventFloorBars`

Implemented stronger normalization:
- Detect sparse `bullEarlyEvent`/`bearEarlyEvent` or `bullEventSource`/`bearEventSource` aliases when they feed `primaryEntryTrigger`.
- Replace those aliases with `earlyBullEvent` and `earlyBearEvent`.
- Detect delayed time-box windows using `age >= eventFloorBars`.
- Remove the lower age bound so windows open from age 0 and only cap the upper window.

Verification:
- `cand-14f8749e` now blocks on `time_boxed_sparse_event_source`.
- Deterministic repair rewrites `bullEarlyEvent = earlyBullEvent`, `bearEarlyEvent = earlyBearEvent`, and clears all blocking issues.

## Improvement Pass 5

The old dist loop still reached `time_boxed_sparse_event_source` after deterministic repair, so the issue is now treated as an incomplete source rewrite rather than a prompt-only problem.

Implemented stronger deterministic fallback:
- Handle typed generated assignments such as `bool bullEarlyEvent = ...`, `int bullEventRaw = ...`, and typed age/window booleans.
- If a time-boxed candidate still has noncanonical event windows, force the entry path onto dense canonical windows:
  - `bullEventAge = ta.barssince(earlyBullEvent)`
  - `bearEventAge = ta.barssince(earlyBearEvent)`
  - `bullAgeActive = not na(bullEventAge) and bullEventAge <= bullContinueWindow`
  - `bearAgeActive = not na(bearEventAge) and bearEventAge <= bearReboundWindow`
  - `primaryEntryTrigger = postBullEventWindow or postBearReboundWindow`
- Add missing `bullContinueWindow`/`bearReboundWindow` inputs when generated code omits them.
- If blocking issues still remain after deterministic repair, persist a runtime artifact with the repaired Pine source so the next diagnosis is source-backed instead of inferred from trace codes only.

Verification:
- Added regression coverage for typed sparse aliases and noncanonical windows.
- `npm run typecheck`, `npm test`, `npm run build`, `validate-ledger`, and `rebuild-indexes --verify` pass.

## Improvement Pass 6

The first successful post-repair candidate (`cand-02f8e219`) reached local evaluation, but still scored `31 total / 7 OOS`. Source inspection showed the Pine had dense time-boxed entry and `maxHoldBars`, but the local simulator ignored those route-specific inputs and continued to simulate only the fixed AF seed event model.

Implemented local simulator route support:
- Parse optional `eventFloorBars`, `eventWindowBars`, `maxHoldBars`, `bullContinueWindow`, and `bearReboundWindow` inputs without making them AF compatibility requirements.
- When `eventFloorBars` is present, simulate dense early bull/bear event-floor windows directly in the JS local backtest.
- Apply `maxHoldBars` as a real time exit in local simulation.
- Use time-boxed entry ranks high enough to make replacement logic reachable under the existing `replaceMinRank` input.
- Treat `holdBars` as an alias for `maxHoldBars`, and enable route-aware simulation when `eventWindowBars` or `holdBars` is present even if `eventFloorBars` is omitted.
- Parse simple numeric route constants such as `maxHoldBars = 10` when the LLM emits a constant instead of an `input.int(...)`.

Verification:
- Re-simulating `cand-02f8e219` through the updated local simulator parses the route inputs and changes the result from the old `31` trades profile to `1345` trades.
- Re-simulating `cand-cd40f065` through the updated local simulator parses `eventWindowBars=4` and `holdBars=8`, changing the result from the old `31` trades profile to `313` trades.
- Re-simulating `cand-62059948` through the updated local simulator parses constant `maxHoldBars=10`, changing the result from the old `31` trades profile to `911` trades.
- Targeted tests pass for local-backtest config/simulator, preflight repair, and autonomous loop regression coverage.
- `npm run typecheck`, `npm run build`, `validate-ledger`, and `rebuild-indexes --verify` pass.

## Improvement Pass 7

The next live loop confirmed that the broad direction was working: `cand-f7398180` became `local_candidate_eligible` with high trade count. However, the preceding generated route shape (`cand-5cf470ad`) still evaluated as `31/7` because it expressed the route with `rotationWindowEnd`, `windowBars`, and `holdBars1..4` instead of the explicit optional route names.

Implemented rotation-window route support:
- Parse `entryWindowBars`, `windowBars`, and `rotationWindowBars` as `eventWindowBars` aliases.
- Parse conditional rank windows such as `windowBars = finalBullEvent >= 4 ? 5 : ...` by taking the generated branch maximum.
- Parse `holdBars1..4` constants and map the maximum value to `maxHoldBars`.
- During deterministic time-boxed preflight repair, support `entrySignal`-based rotation windows by inserting canonical `primaryEntryTrigger`/`entryPass` and redirecting `if entrySignal ...` to `if entryPass ...`.
- Add regression tests for parser/simulator route awareness and sparse `entrySignal` repair.

Verification:
- `cand-5cf470ad` now parses `eventWindowBars=5`, `maxHoldBars=10`, and re-simulates at `327` trades instead of the old `31`.
- `cand-eb5c0c9f` now parses `maxHoldBars=6` and re-simulates at `811` trades instead of the old `31`.
- `cand-f7398180` now parses `entryWindowBars=4`, `maxHoldBars=18`, and re-simulates at `313` trades.
- Targeted tests pass for local-backtest config/simulator, preflight repair, and autonomous loop regression coverage.
- Full `npm run typecheck`, full `npm test`, `npm run build`, `validate-ledger`, and `rebuild-indexes --verify` pass.

Final deployment note:
- Live restarted candidates `cand-b8e26ed1` and `cand-97e78627` both reached `local_candidate_eligible` after deterministic sparse-source repair.
- `cand-b8e26ed1` parses `eventFloorBars=5`, `eventWindowBars=6`, `maxHoldBars=10`, `bullContinueWindow=14`, and `bearReboundWindow=14`, and re-simulates at `1691` trades.
- `cand-97e78627` parses `eventFloorBars=4`, `eventWindowBars=8`, `maxHoldBars=10`, `bullContinueWindow=14`, and `bearReboundWindow=14`, and re-simulates at `1814` trades.
- Added a final preflight ordering fix so deterministic repair inserts event floors before early events, window inputs before age-window usage, and routes `entrySignal` entry blocks through canonical `entryPass`.
- Final verification again passed `npm run typecheck`, full `npm test`, `npm run build`, `validate-ledger`, and `rebuild-indexes --verify`.
- Final restarted loop generated `cand-8cfb97d5`, applied deterministic sparse-source repair, and recorded it as `local_candidate_eligible`; it parses `eventFloorBars=4`, `eventWindowBars=9`, `maxHoldBars=12`, `bullContinueWindow=14`, and `bearReboundWindow=14`, and re-simulates at `1688` trades.
