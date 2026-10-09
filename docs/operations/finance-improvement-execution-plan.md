# Quant Autoresearch — Implementation Plan & Progress

Updated: 2026-10-09. Canonical architecture remains `docs/architecture/quant-autoresearch-architecture-v1.0.md`; MCP operational authority remains `docs/operations/mcp-current-state.md`. This plan records targeted improvements without silently changing those contracts.

## Completion rules

- Start from a red test that demonstrates the bug or inadequacy, then implement and re-run the focused and full suite.
- Preserve `orders_enabled=false` on all research MCP calls; do not grant credentials or live-order capabilities.
- Preserve immutable historical Evidence and reference old runs by their original code/metric semantics; changing evaluator semantics is not a retroactive correction to old runs.
- Make each change in an atomic commit, with a concise numerical or behavioral release note.
- Distinguish "unit tests pass" from "real-world strategy efficacy proven". Do not claim sealed OOS PASS without independent, authorized data and a frozen selection policy.

## Work breakdown

| Task | Priority | Status | Dependencies | Acceptance criteria |
| --- | --- | --- | --- | --- |
| T-001 | P0 | DONE | none | Synthetic next-open/cost/IR golden fixture, baseline tests |
| T-002 | P1 | PARTIAL | T-001 | DONE core validation-to-evaluation protocol and neutral IR/core hash dependency; remaining imports/inversions and full DAG audit |
| T-003 | P1 | PARTIAL | T-001 | DONE pure generation context/record extraction and preserve historical Frontier; PENDING repair state-machine isolation and crash/queue parity |
| T-004 | P0 | PARTIAL | T-001 | DONE finite OHLCV, warmup, vendor-declared provenance/Parquet lineage and immutable quality audit; PENDING independent as-of verification, corporate action evidence, exchange session QA |
| T-005 | P0 | PARTIAL | T-001 | DONE trailing stop/regime gates; remaining risk policy assertions/edge cases |
| T-006 | P0 | PARTIAL | T-005 | DONE exposure from marked positions; remaining accounting/returns audit |
| T-007 | P0 | PARTIAL | T-004, T-006 | DONE native price-strategy cohort train-only selection/holdout with immutable audit; PENDING upstream fold-specific generation, external as-of features, final sealed OOS |
| T-008 | P0 | PARTIAL | T-007 | DONE cost-resilience sign, PBO/CPCV aligned finite inputs, within-workspace cumulative trials; PENDING independent DSR/PBO reference and all-workspace trial accounting |
| T-009 | P1 | PARTIAL | T-001 | DONE memory-bounded random search with type-aware unique sampling, execution-semantic dedup; PENDING Bayesian scalability, version-aware cache and cross-parent sourcing |
| T-010 | P1 | PARTIAL | T-008, T-009 | DONE canonical policy-driven allocation planner; PENDING execution of source-specific generators and lineage evidence |
| T-011 | P1 | PARTIAL | T-010 | DONE read-only immutable-evidence Frontier in director context; PENDING actual parent IR retrieval, Rescue and authorized champion flow |
| T-012 | P1 | PENDING | T-011 | Evidence-based director; bounded calls, diagnostics, reproducible A/B benchmark |
| T-013 | P1 | PENDING | T-012 | Full official SDK + queue/process/Docker ownership, Windows Host acceptance |
| T-014 | P0 | PENDING | T-013 | Independent historical data run, frozen holdout, OOS report, security/regression signoff |

## Immediate next implementation steps

1. T-004: Add data-source provenance, asset survivorship/corporate-action policy, point-in-time tests; ensure fold indicator calculations have a warmup window but cannot trade prior to test boundaries.
2. T-007: Per walk-forward split, perform parent-selection and fit using **only** permitted training data; freeze candidate before evaluating its next chronological window. Record all selection attempts for multiple-testing correction.
3. T-008: Audit DSR/PBO implementations against independent reference computations and distinguish temporal holdout from independently sealed OOS.
4. T-002/T-003: Execute behavior-preserving dependency and lifecycle decomposition in separate commits, only with parity fixtures and managed worker crash/recovery tests.
5. T-009 onward: Store strategy identity separately from experimental lineage, and connect dedup/cache/frontier while preserving immutable evidence provenance.

## Safety and test gates

For each commit: `.venv/bin/ruff check .`, `.venv/bin/mypy .`, and `.venv/bin/python -m pytest -q` using the pinned venv/lock. Host Docker validation is not replaceable by the Python stub tests. No published release/merge or live-trading activation is implied by local green tests.

## 2026-10-09 follow-up batch

- `3094c3e`: reject NaN and infinite OHLCV values at construction; 15 red tests became green.
- `a74cd52`: optionally forbid any warmup-history signals before `signal_start_at`.
- `f58e8eb`: preserve causal warmup in temporal folds and measure only test-window metrics. `selection_applied=false` is unchanged; this remains *candidate holdout evidence*, not full train-only selection.
- Follow-up robustness correction: negative-return strategies must never get positive cost-resilience merely from dividing two negative returns.

## Final implementation additions — 2026-10-09

- T-007: development-only frozen cohort train-selection and independently measured following period, separate immutable attempt Evidence; not a sealed-OOS promotion.
- T-008: PBO/CPCV finite/aligned inputs and accumulated per-workspace optimizer attempts, still an approximation.
- T-009/T-010: semantic candidate deduplication and policy-driven search *budget* allocation; actual 4-source generators and cache wiring not complete.
- T-011: immutable-Evidence-based Frontier context; candidate strategy IR materialization and Rescue/Champion integration not complete.
- T-002: core metric-view interface and neutral shared hashing. Packaging includes the new foundation module; source checkout with stale editable virtual environments requires environment refresh or repository-root `PYTHONPATH`.
- Full regression at final code HEAD `f570564`: 862 passed, Ruff PASS, Mypy 170 source files PASS with repository-root `PYTHONPATH` used for stale editable venv. No real Windows Docker or sealed OOS evaluated.

## Existing records

- Baseline and T-001: `docs/operations/finance-improvement-phase0-baseline.md`.
- T-005: `docs/operations/finance-improvement-phase2-risk.md`.
- T-006: `docs/operations/finance-improvement-phase2-exposure.md`.
- T-009: `docs/operations/finance-improvement-phase4-random-search.md`.

## 2026-10-09 implementation continuation

- `9e9cfa4` T-004: source-provenance contract with Parquet persistence, legacy hash compatibility, quality status and immutable run/attempt evidence. Vendor claims are *declared only*, not independently PIT-verified.
- `366cfc9` T-003/T-011: extract pure generation context/result handling, and preserve evidence-backed frontier winners when the live director prepares the next generation. Proposal/repair state machines still need isolation.
- `2342674` T-004: 24/7 intraday/daily/weekly missing-bar detection without synthetic fill; actual stock-market calendar reconciliation remains pending.
- `8aaf4c0` T-009: seeded type-aware, uniform unique random parameter search in O(input domain widths + selected budget) memory; lazy indexed sampling works for 2**70 parameter combinations. Bayesian optimization and versioned evaluation caching remain pending.

No runtime broker credentials, paper/live order flags, autonomous champion promotions, sealed holdout read or external Docker acceptance was authorized or performed in these commits.
