# Quant AutoResearch — P3 Post-Commit S7 Receipt Reconciliation (2026-10-22)

## Approval boundary / scope lock

- **Stage**: existing T4/P3 interruption-recovery dependency, Q02/Q06/Q08/Q15/Q17/Q20. Frozen delivery order **V05 → T4 (real GPT/MCP 10→100 cycles) → V01–V04 (PIT/OOS) → V06 paper-only → V07 GO/NO-GO** remains unchanged.
- **User value**: an interrupted foreground inherited GPT experiment must not silently lose its S7 result, duplicate an immutable counted generation, or give the next LLM an unverified S7 report.
- **Limits**: P3 model-proposal runner and tests only. Default MCP/URL/OAuth/provider modes, canonical StrategyIR, protected core, existing G452 research lineage, dataset/market evidence, OOS and broker execution are not modified. No new ChatGPT/paid provider call, new generation, real trading, or backend daemon is part of this task.

## Implemented behavior

1. The P3 audit retains *chain-verified* receipt metadata on explicit JSONL resume; new receipts are tracked only after flush + fsync.
2. At opt-in runner startup, when the last receipt states a generation was **counted** but its S7 receipt was not written, reconcile only that exact latest counted generation. The canonical `evaluate_experiments` API is idempotent for hash-verified stored reports. Validate generation identity, original evidence hash, previous evidence-chain link, hypothesis result completeness; then append exactly one S7 receipt.
3. If an S7 receipt already exists, reconstruct the current stored report and compare context hash, proposal/report hash, result class and source generation hash. Do not append a second S7 receipt or rerun a model request.
4. Forward the verified S7 feedback to the next planning context on continued runs; expose `reconciled_s7_generations`, `verified_existing_s7_receipts` and `new_generations` separately. Reconciliation alone never counts as a new research generation.
5. Fail closed on evidence mismatch, unsupported phase (including RUNNING), nonresearch order/OOS flags, wrong audit session or structurally ambiguous terminal checkpoint. A crash **between immutable generation commit and DIAGNOSIS receipt flush** is intentionally not automatically reconciled: require operator-level canonical reconciliation, rather than infer an unproven GPT diagnosis from a PLAN receipt.

## Reproduction and tests

- Added interruption-before-S7 and interruption-after-S7-persistence receipt tests, plus crash-after-receipt-fsync, contradictory evidence/report hash, and two-generation verified feedback inheritance tests.
- P3 unit suite: **12 passed**. Related P3/transport/MCP-policy/scope-lock regression suite: **42 passed**.
- Target file Ruff: **PASS**. Target P3 source mypy: **PASS**.
- P3 isolated SQLite-clone E2E: **PASS** using a scripted provider; clone G453 and S7 evidence verified, original G452 remained unchanged. Clone child +73.0338% development return and 27.9092% MDD do NOT demonstrate independent GPT reasoning or OOS performance.
- Full repository Ruff: **PASS**. Full repository mypy: **FAIL (110 errors in 14 previously existing files; no reported error in changed P3 runner)**. Full pytest: **INTERRUPTED after 300-second timeout at approximately 29%; no failure markers printed up to that point, full-suite PASS NOT VERIFIED**.
- Existing normal P3 flow, P2 constraints and mocked provider tests retain the "mock != autonomous GPT" distinction.

## Open gates / next work

1. Full pytest requires longer independent integration validation; the 300-second run stopped at roughly 29%. Isolated clone E2E passed.
2. Fix pre-existing repository-wide mypy failures as a separately scoped task; do not claim release gate PASS while these remain.
3. P3 next: pre-S7 candidate `next_intent` semantic signal nonredundancy checking plus informative signed feedback; restrict to typed, non-executable StrategyIR and test on clone. Real user-authorized GPT/MCP 10→100 research remains the frozen T4 priority, blocked where OAuth/service/data access is unavailable.
4. True PIT, unseen prospective OOS, multi-seed economic superiority and unattended GPT model calls remain **NOT VERIFIED**.

**Deployment**: development worktree only, not merged into operating Quant MCP, not applied to production G452 state.
