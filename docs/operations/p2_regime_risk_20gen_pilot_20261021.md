# Quant AutoResearch P2 — opt-in regime, ATR sizing and risk-gated parent promotion

**Date:** 2026-10-21 · **Branch:** `feat/quant-parent-portfolio-20261021`

## Scope and immutable boundary

- Original G1–G452 academic evidence is immutable; none of the commands below extends the production session or changes its original StrategyIR schema.
- Frozen source dataset: QQQ 2020-01-02 to 2025-12-31; dev/non-PIT only. **No retrospective result is a sealed independent OOS approval, and no live orders are enabled.**
- All opt-in paths default to OFF. Original P1 parent selector's selection hash with no P2 risk budget remains unchanged (`7fcbddf806facdfe3a43cfe857c01ba49d6042b6bfa34c4d6d72a41004ab0883`).
- No GPT-per-generation inference has been added. Cloned research cohorts still use `DETERMINISTIC_GPT_DESIGNED_POLICY_NOT_PER_GENERATION_LLM`.

## Implemented

1. `core/backtest/p2_policy.py` introduces typed `P2ResearchPolicy`, first-match regime `RegimeRoute` with a conditional entry and position-size cap, `ATRVolatilitySizing` with bounded target volatility, plus `ChildRiskBudget`, risk-assessment helpers.
2. `BacktestRequest.p2_policy` optionally activates single-asset execution using only completed close signals for route evaluation and ATR sizing, filling at the **following bar open** with the canonical backtest costs. A portfolio route's first matching market regime takes precedence; an unmatched route does NOT authorize a new position. Previous legacy paths remain unchanged. New policy + historical IR hash jointly identify P2 backtest outcomes.
3. Unsupported cases fail closed: P2 policy without StrategyIR, unrecognized ATR indicator, invalid condition references or operands, and multi-symbol P2 policy are explicitly blocked. Regime routing currently changes **entry rule and position size**, not per-regime exit policy; avoid claiming a full multi-strategy DSL.
4. `AcademicMCPCheckpointService(child_risk_budget=ChildRiskBudget(...),parent_portfolio_v2=True)` adds an opt-in risk budget at **P1 counted/S7 parent candidate promotion** after candidate replay. For counted candidates, the parent MDD comes from the signed prior selection and is cross-checked with the original lineage. For S7 candidates the source counted generation metrics are used. Failed candidates are removed from parent shortlist; if no eligible candidates remain, selection **raises**, rather than silently falling back. Each accepted/rejected decision is auditable. Without a budget, no serialized P1 candidate fields, rank output, or selected parent hash change.
5. `scripts/audit_parent_portfolio_v2.py --p2-risk` verifies on an isolated SQLite clone and stores an ignored report under `state/moon-http/fresh-20261021/p2-parent-risk-audit-v1.json`.
6. `scripts/run_p1_ab20_mixed_parent.py --arm risk` runs a separate 20-generation clone under the same pinned G452 data and same cost model.

## P2 audited risk shortlist

- Explicit pilot gate: child MDD **≤30%**, child-parent MDD increase **≤15 percentage points**, at least **30 closed trades**. These are **research control values**, not tuned live-trading guarantees.
- One source G452 clone audit: 18 counted + 12 S7 candidates considered, 27 passed replay/economic checks prior to risk filtering, **3 were rejected on P2 risk**. Remaining Pareto parent sources: **G192, G431, G68**. The first simulated parent pick G68 had matching frozen StrategyIR and full-fill replay hash; clone original evidence digest unchanged.
- The parent candidate gate **does not** apply to the just-created child strategy before its official counted generation is committed. This boundary is crucial for interpreting the pilot.

## 20-generation development comparison, each arm G453–G472

| Metric | Original S7 selector | P1 mixed parents | P2 risk-filtered parents |
|---|---:|---:|---:|
| Completed counted generations | 20 | 20 | 20 |
| Mean development return | +18.185% | +30.972% | +39.775% |
| Median development return | -2.071% | +45.801% | +48.690% |
| Positive generation returns | 10 | 14 | 13 |
| Mean MDD | **28.211%** | 38.370% | **38.514% (worse)** |
| Median MDD | 25.604% | 36.122% | 36.285% |
| Child generations with MDD >30% | **7/20** | 16/20 | **17/20** |
| Distinct parent sources | 1 | 3 | 3 |
| Parent source distribution | G4×20 | G68×7, G248×7, G192×6 | G68×7, G192×7, G431×6 |
| Candidate attempt signatures | 1,017 | 1,150 | 1,275 |
| Preflight rejected | 997 | 1,130 | 1,255 |
| Parent-candidate P2 risk rejections | n/a | n/a | 43 across the 20 selection checkpoints |

The risk-filter cohort had a higher mean **development** return but did **not** reduce average child MDD or the rate of high-drawdown children. Moreover, attempted candidate evaluations differ, so return differences cannot be attributed causally to the new selection policy. None of these runs has independent OOS validation.

All three copied runs are `472/472 COMPLETED`, with 472 S7 reports each, continuous generation evidence hashes, independent SQLite stores and `PRAGMA integrity_check=ok`. Original academic research remained `452/452`, SQLite integrity `ok`.

## Artifacts / replication

- `state/moon-http/fresh-20261021/p1-ab20-mixed-s7-20261021/{baseline,mixed,risk}/result.json`
- `state/moon-http/fresh-20261021/p2-parent-risk-audit-v1.json`
- Source: `.venv/bin/python -m scripts.audit_parent_portfolio_v2 --p2-risk`
- Cloned risk arm: `.venv/bin/python -m scripts.run_p1_ab20_mixed_parent --arm risk`
- Regression: `tests/core/test_p2_policy_execution.py`, pre-existing backtester/golden baseline tests, P1 parent selection tests.

## Next gate before P2 is complete

**Add a costed pre-commit child risk gate.** After a proposed strategy mutation is generated, replay its complete signal, fills and MDD vs its selected parent and a hard absolute risk threshold. If it breaches the predeclared cap, reject it *before creating immutable generation Evidence*. Log rejection with evidence hash and reason. The director must propose a revised structure or an explicitly documented risk-approved variation; never silently resize/truncate historic trades or hide rejected candidates. Integrate regime-specific exits and first-class conditional expressions only after separate proof of causal consistency, and compare equal actual backtest budgets over multiple experiment seeds and a fresh sealed OOS. Do not promote to live or paper orders on current evidence.
