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
| T-002 | P1 | PENDING | T-001 | Remove inversions in strategy_ir/core boundaries; public contracts unchanged |
| T-003 | P1 | PENDING | T-001 | Split 556-line autoresearch orchestration by phase; recovery/queue parity |
| T-004 | P0 | PENDING | T-001 | Point-in-time vendor data quality, warmup and missing-data contracts |
| T-005 | P0 | PARTIAL | T-001 | DONE trailing stop/regime gates; remaining risk policy assertions/edge cases |
| T-006 | P0 | PARTIAL | T-005 | DONE exposure from marked positions; remaining accounting/returns audit |
| T-007 | P0 | PENDING | T-004, T-006 | Proper train-only fit/selection, walk-forward and held-out gate; prevent OOS re-use |
| T-008 | P0 | PENDING | T-007 | Statistical definition validation (CSCV/CPCV/PBO/DSR), multiple-test accounting |
| T-009 | P1 | PARTIAL | T-001 | DONE unique random draws; remaining cross-parent semantic dedup and versioned evaluation cache |
| T-010 | P1 | PENDING | T-008, T-009 | Exploration/exploitation/crossover/rescue policy actually drives candidate sourcing |
| T-011 | P1 | PENDING | T-010 | Durable frontier, rescue, champion and evidence-linked hypotheses |
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

## Existing records

- Baseline and T-001: `docs/operations/finance-improvement-phase0-baseline.md`.
- T-005: `docs/operations/finance-improvement-phase2-risk.md`.
- T-006: `docs/operations/finance-improvement-phase2-exposure.md`.
- T-009: `docs/operations/finance-improvement-phase4-random-search.md`.
