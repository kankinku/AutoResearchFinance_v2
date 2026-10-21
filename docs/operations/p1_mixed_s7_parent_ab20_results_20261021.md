# Quant AutoResearch P1 mixed S7 + counted-parent integration and 20/20 clone pilot

**Run date:** 2026-10-21 (Asia/Seoul). **Code branch:** `feat/quant-parent-portfolio-20261021`. **Not independent OOS, not live, not per-generation GPT-autonomous**. This is a deterministic GPT-designed candidate policy with original QQQ 2020-01-02..2025-12-31 REUSED_DEVELOPMENT_NON_PIT historical data and identical academic cost execution.

## Implementation

- Opt-in `AcademicMCPCheckpointService(parent_portfolio_v2=True)` now combines (a) cost/close-trade and hash replay of **18** direct counted generation StrategyIR candidates with (b) S7 **12** strongest coarse successor candidates, each of which undergoes *full independent replay* using `replay_counted_s7_child`, including equity, costs, original S7 hash, effective trading change and legacy economic/risk gate via `choose_development_parent`.
- Cheap S7 scores only shortlist: none may be inherited solely because its stored coarse equity claims a profit.
- Replayed S7 child candidates are normalized to the same `parent_quality` and **computed real effective signals**, then submitted to the same 2-objective return-versus-drawdown Pareto filter and independently hashed pinned parent selection as counted parents.
- Existing source-kind `COUNTED_S7_CHILD` verification/materialization is reused, preserving the stronger legacy lineage proof.
- This was an **opt-in** path: the ordinary gateway service and original production cohort runner retain the previous selector by default.
- A new `scripts/run_p1_ab20_mixed_parent.py` clones the original three SQLite database files via `sqlite3.backup`, verifies the ledger G452 head, and runs each of `baseline` / `mixed` arms separately, 20 new counted generations each (G453..G472). A manifest pins the baseline input. Each arm has its own SQLite store and plan-signature logs. The script supports `--resume` after interrupted committed checkpoints without repeating completed generations.

## Replayed original evidence
- Source research ledger count: **452**, unchanged before and after.
- Source G452 head: `e620bfecb8bd5359731834d87064c13c1a3a32337da1d946a3f132cf9d79b337`.
- Both clone arms reached `472/472 COMPLETED`, with exactly **472 original+new stored S7 reports**, verified previous_evidence_hash chain for new generations, original head unchanged, broker orders disabled and independent OOS approval false.
- Source database and all six three-per-arm SQLite databases passed `PRAGMA integrity_check`.

## 20-generation experimental results

| Measured metric | Old S7 selector baseline | New mixed Pareto parents |
|---|---:|---:|
| Counted generations completed | 20 | 20 |
| Positive total return generations | 10 | 14 |
| **Mean in-sample total return** | **+18.19%** | **+30.97%** |
| **Median in-sample total return** | −2.07% | +45.80% |
| **Mean in-sample maximum drawdown** | **28.21%** | **38.37%** (worse) |
| Median drawdown | 25.60% | 36.12% (worse) |
| Best new generation return | +126.70% | +126.70% |
| Number of distinct parent sources | 1 | **3** |
| Parent source counts | G4: 20 | G68: 7; G248: 7; G192: 6 |
| Source kinds selected | COUNTED_S7_CHILD: 20 | COUNTED_GENERATION: 20 |
| Unique candidate attempt signatures | 1,017 | 1,150 |
| Preflight rejected candidates | 997 | 1,130 |
| S7 successor replay shortlist | Old original logic | 12/12 replayed and passed legacy parent gates for every new generation, but no S7 candidate won the final mixed Pareto lane |

**Delta:** mean total return +12.79 percentage points, mean MDD **+10.16 percentage points worse**, additional 133 candidate evaluations (+13.1%). This comparison is NOT an equal-backtest-budget contest. Both arms used the same number of completed generations, dataset and costs, but differing candidate trials; hence we do not attribute the average return advantage causally to parent selection nor certify better risk-adjusted performance. The Pareto rank separates objectives but does not guarantee the mutated child will preserve the parent's risk.

## Failure and recovery

The mixed arm encountered one transient `sqlite3.OperationalError: disk I/O error` after committing G467, while the baseline arm was still writing on the same Windows-backed volume. Available disk space exceeded 200 GB. Both cloned SQLite DBs passed `PRAGMA quick_check`, mixed checkpoint at `G467/472, AWAITING_PLAN` and no original state corruption.
The separate-process `--resume` command continued **only G468..G472**, final mixed exited 0 with no duplicated generations, full S7 count and hash chain verified. The cause of that isolated I/O error is not conclusively diagnosed; storage pressure alone is not demonstrated.

## Artifact locations (ignored operational state, not GitHub)

`state/moon-http/fresh-20261021/p1-ab20-mixed-s7-20261021/baseline/result.json`
`state/moon-http/fresh-20261021/p1-ab20-mixed-s7-20261021/mixed/result.json`

Cloned DBs, attempt logs and source snapshot SHA256 manifests are stored in separate corresponding directories.

## Decisions and next gates

- **P1 functional (mixed selector, economic S7 gates, parent rotation, copy-on-write generation): PASS**.
- **P1 financial/risk superiority: NOT ESTABLISHED**: 20 paired counted generations insufficient for conclusive inference, drawdown worsened, test attempt budget unequal and data reused 452 prior times.
- **Before adopting as the default parent selector:** equalize candidate *backtest* evaluation budget (e.g. hard costed trial cap, replay counts, compute budget), add risk budget controls before committing child, run multiple seeds/paired tests, and test two-parent and S7 selection under synthetic cases. A S7 successor qualified for the pool but was never chosen as a final parent, so that mixed promotion path remains unexercised at runtime.
- **P2 next priority:** introduce representational variety (market regimes, position sizing, risk-adjusted child promotion) and log real model-derived reasoning if GPT autonomy is requested; do not claim this A/B addressed P2/P3/P4.
- **Keep original G452 permanently intact** and do not optimize on already inspected 2026 chronological holdout data.
