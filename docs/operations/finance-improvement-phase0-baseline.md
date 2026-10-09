# Finance Improvement — Phase 0 reproducibility baseline

Snapshot: `4b48073` (2026-10-02) on `docs/mcp-phase3-5-1-state-inventory`.
This document supplements but does **not** replace `docs/architecture/quant-autoresearch-architecture-v1.0.md` or `docs/operations/mcp-current-state.md`.

## Invariants preserved across changes

- Strategy IR remains the source of truth; downstream Python is only an execution artifact.
- No MCP order/credential/live activation tools; research `orders_enabled=false`.
- Current publicly advertised MCP tool names and input schemas remain compatible.
- Immutable evidence, queue ownership, strategy/data hashes, and persisted experiments remain intact.
- Market-data zones (development, validation, sealed OOS) do not merge.
- Signal at completed bar `t` is filled no earlier than the next bar open `t+1`.

## Executable goldens

`tests/core/test_backtest_golden_baseline.py` freezes:

1. Strategy IR JSON round trip preserves output.
2. Next-open order chronology, buy/sell quantities, per-fill costs, and equity curve.
3. Identical inputs preserve all BacktestResult fields and curve digest.

The synthetic example starts at 1,000 cash, opens at 50, closes at 60, exits at 70, and charges 8 basis points per side. Expected equity: `(1000.0, 1199.04, 1397.760896)`.

Prior full-repository baseline before this addition: `802 passed`, Ruff PASS, Mypy PASS (165 files), on the same head. This is a regression/contract baseline **not** validation of market-data quality or external OOS performance.

## Outstanding acceptance boundaries

- External Windows Docker Engine acceptance is pending.
- No authentic research Parquet files or completed sealed-OOS evaluation records are present in this worktree.
- Every change to financial semantics requires a new failing regression test and a release note explaining any expected behavioral difference.
