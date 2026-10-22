# Quant AutoResearch — P3 Diagnostic `next_intent` Pre-S7 Semantic Gate (2026-10-22)

## Contract and approved scope

- **Stage T4/P3**, Q02/Q06/Q08/Q09/Q17/Q18/Q20: prevent semantically redundant S7 hypotheses from consuming immutable research generations; preserve verified feedback across retry and resume.
- Existing user-approved order **V05 → T4 actual ChatGPT MCP 10→100 → V01–V04 PIT/OOS → V06 paper-only → V07 GO/NO-GO** is unchanged. This is T4 dependency, not a new product milestone.
- Opt-in existing `p3_semantic_preflight=True` only. Default authenticated MCP transport and fixed URL, OAuth, original G452 academic session/market data/parents, costs, P2 risk gates, sealed OOS, and trading OFF are unchanged. No model API call, external data, new strategy library or background runner was introduced.

## Engineering changes

- `research/llm/p3_diagnostic_preflight.py`: re-authenticate the evidence-linked `DiagnosticResponse`, compile each typed `next_intent` through the existing diagnostic gate, check symbolic scalar subset and DEVELOPMENT bar-by-bar entry/exit/regime vector equality against unchanged, audited inherited StrategyIR. Equal sampled signals only reject when risk policy is unchanged. All hypotheses must pass; sampled equality is **not** universal/OOS equivalence and does not predict profitability.
- `application/academic_checkpoint_service.py`: before the irreversible `RUNNING` or counted-generation commit, reject P3 diagnostic requests with semantically uninformative hypotheses. Keep original diagnosis checkpoint token and generation number. Persist an idempotent, content-hashed sidecar receipt bound to session, generation, checkpoint token hash, staged plan, original context/evidence hash, dataset, and typed diagnosis hash. Verify receipts when returning the next model diagnostic context, fail closed on any inconsistency. No alteration of S2/S7 measured ledgers.
- `research/llm/inherited_checkpoint_autopilot.py`: bounded model re-proposal at the **same** diagnosis checkpoint; suppress duplicate typed diagnosis payloads, retain hash-chain rejection receipts, reject any change to checkpoint identity, fail on budget exhaustion without counting a new generation; support explicit safe resume after rejection.
- `research/llm/p3_semantic_preflight.py`: type-only scalar local binding and typed signal-vector helper annotation; semantic comparison unchanged.

## Reproducible evidence and limits

- In `scripts/test_p3_semantic_clone_e2e.py`, clone G452 with SQLite backups. First two **plan** semantic rejects preserved (symbolic and development-vector equivalence); after valid planning, submit provably redundant appended EMA OR-exit `next_intent` twice and verify the same single persisted diagnostic rejection (no G453 commit or checkpoint-token change). Tampered stored rejection hash fails closed, then restored receipt permits distinct diagnosis and cloned G453 costed S2/S7. Original G452 head/data unchanged. Result: G453 dev return +9.6870%, MDD 23.9916%, not an investment or OOS finding. No actual independent GPT/API inference occurred.
- P3 diagnostic focused tests cover symbolic implication, sampled-only equality, changed signals, changed risk, bounded diagnosis retry, immutable counted-generation increments, exhaustion and explicit rejection resume. Integration tests are deterministic fixtures and cannot establish GPT autonomy.
- Stage/operation risk: this is a semantic **preflight**, not proof of realized trade changes or improvement. Real GPT/T4 10→100, multi-seed benchmarking, PIT-aware external data, independent prospective sealed OOS, and generalization remain **NOT VERIFIED**.

## Remaining gates

1. Connect existing authenticated ChatGPT/MCP to the enhanced opt-in research lane and verify real 10→100 complete generations with true model-led diagnostics and budget-equal random comparisons. No default OAuth re-registration.
2. Build restricted expression/regime typed DSL compiler only as required by documented Q05/Q10 gaps; no arbitrary model-generated Python execution.
3. Resolve inherited full repository mypy/larger full pytest release-gate failures before any deployment or merge. Do not confuse isolated G453 clone acceptance with production release readiness.

**Deployment**: developer worktree / feature branch only. No operational rollout and no new official counted generation.

## Validation

- Focused tests: 49 PASS; SQLite-clone end-to-end: PASS; unchanged G452 verified.
- Repository Ruff: PASS; P3 three-module mypy: PASS.
- Full mypy: FAIL, 41 pre-existing type errors in 13 files; full pytest: NOT RUN for this change.
- Live API, MCP generation, independent OOS, and deployment: NOT RUN.
