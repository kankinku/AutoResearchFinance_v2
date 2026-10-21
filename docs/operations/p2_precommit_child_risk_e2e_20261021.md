# P2 — Pre-commit Child Risk Gate, E2E verification (2026-10-21)

**Branch:** `feat/quant-parent-portfolio-20261021`. **Status:** implemented and tested on clones; production G452 not extended. Data is QQQ 2020–2025 *development/non-PIT*, not independent OOS, not paper/live trading. Research controller is deterministic GPT-designed policy, **not** a fresh GPT reasoning call per generation.

## Root cause addressed

The previous P2 candidate-parent promotion screen `ChildRiskBudget` was applied **only when picking a future parent**. It did not prevent a mutation of that parent from being committed as a new generation at >30% MDD. The 20-generation risk-selection-only pilot had 17/20 newly committed children with MDD above 30%, mean MDD 38.51%.

## Newly implemented gateway

- Optional `AcademicMCPCheckpointService(precommit_child_risk_budget=..., parent_portfolio_v2=True)`; **off by default**. Non-P2 original research and P1 parent selection remain unchanged.
- After canonical ResearchIntent mutation and duplicate rejection, **before changing stage from AWAITING_PLAN to AWAITING_DIAGNOSIS**, replay both selected parent and proposed child using the same costed S2 `audit_inherited_decisions`, including next-opening fills, fees, exposure and equity curve.
- Calculate actual child-vs-parent MDD and closed-trade count via `assess_child_risk` and the explicitly selected `ChildRiskBudget`. A disapproved child does not consume planning token, insert generation timing, stage diagnosis or commit any new counted generation. It raises the retryable `P2_PRECOMMIT_RISK_REJECTED` error.
- A failed candidate writes an **idempotent, hash-verified rejection** to `gateway.sqlite.precommit_risk_rejections`, binding session/generation, hashed request and token, previous immutable evidence, selected parent, parent and child strategy hashes, costed equity hashes, S2 decision audit hash, dataset, cost policy, risk thresholds, measured drawdown/trades and source scope. The audit row is durable even though a retryable error is returned. Duplicate submission cannot create another row for the same proposal.
- A passing candidate carries **`p2_precommit_approved`** in its pinned `plan_json`, within `plan_digest`. `_materialize_inherited` replays that evidence, independently checks risk and source hashes before any counted S2 diagnosis can progress. A mismatched/tampered proof fails closed. A pending plan with no approved proof cannot be accepted by a service with the flag enabled.
- Reuse original StrategyIR schema, closed-trade and cost accounting, original S7 evaluation, and immutable G452 evidence. Does not introduce unconstrained execution or broker orders.

## Clone E2E verification

Command: `.venv/bin/python -m scripts.test_clone_g453_p2_precommit_risk`

Two **separately cloned**, isolated academic-gateway SQLite research sessions from the original G452 state:

1. **Rejection** fixture: predeclared max child MDD 0%, max increase 0pp, min 30 closed trades. The controller's valid candidate registered a fully costed child MDD **24.60%** vs parent **15.95%**, 45 closed trades. It was rejected with `P2_PRECOMMIT_RISK_REJECTED` **before** G453; stage remained `AWAITING_PLAN`, same token, `completed_generations=452`, no pending plan, no G453 timing row. Retry of identical intent was rejected, the single rejection persisted and its hash `c358a89cfe6adfe207b9c8009fe7d00365a4ccb45623150a372c11dee81aac04` matched.
2. **Acceptance** fixture: max MDD 100%, max increase 100pp, min 1 closed trade, verifies approval/hashing mechanics only (NOT a recommended real risk limit). Deterministic controller generated, audited and committed G453 at **+73.03%** development return, **27.91%** MDD and **103** closed trades. Correct S2 and S7 completion, full approved precommit proof in pending stage, committed generation evidence hash `b2bba3ba47ad27371d015d6f2d0c10bda90de232947664e3b81e0504ebc7d5d9`, and S7 report hash.
3. Original G452 session untouched, with original academic chain digest constant throughout. No broker orders or OOS approval.

E2E record (ignored runtime data): `state/moon-http/fresh-20261021/p2-precommit-child-risk-e2e.json`; content hash `13d7c12cacadf57c35fbeea1bcf978870053fef39ddbd032e08777e35ebd8c77`.

**Interpretation:** This establishes correctness of the development gateway state-machine guard and evidence persistence, **not** improved profitability or proof that practical 30% MDD caps will leave enough distinct, risk-compliant candidates to fill 20 generations. A realistic-budget A/B is next and may hit genuine `EXHAUSTED_TYPED_PLAN_POOL`, which should be reported rather than bypassed.

## Next gates

- Exercise a **realistic precommit budget** (e.g. 30% child MDD, +15pp parent-relative, >=30 closed trades) in a bounded clone, preserving rejected candidates and measuring valid-trial scarcity.
- Add a separate adversarial test for fabricated `plan_json` approved-risk proof after the stage is signed; fail closed even if an attacker recomputes the plain content hash.
- Integrate child rejection feedback into **new GPT hypothesis generation**, expanding the typed DSL rather than silently rerolling a static finite list.
- Fixed equal **candidate backtest** budget, multi-seed development comparison, then never-reused prospective OOS/PIT data. Current experiments are all development-only.
