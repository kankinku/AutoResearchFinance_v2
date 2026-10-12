# Quant finance execution boundaries — 2026-10-12

Purpose: make abnormal cost-model or capital inputs fail explicitly, and prevent nonsensical zero-share buys from consuming research cash.

## Confirmed implementation

- Cost-model commission, spread and slippage rates must be finite and nonnegative. Per-trade notional, stress multiplier and calculated cost components/total also must be finite.
- Backtest initial capital must be finite and strictly positive; cost stress multiplier finite and nonnegative. These checks occur before simulation state can be modified.
- In both single-symbol and multi-symbol next-open execution, an entry with total buy cost greater than or equal to the planned notional **does not execute**. The strategy's available cash is preserved, and no zero-unit fill is written.
- A sell whose cost exceeds or exhausts its proceeds fails the research run rather than silently creating impossible negative cash.
- Ordinary buy execution/accounting remains unchanged: budget is debited from cash, shares = (budget - fee) / next open price, trade ledger notional = shares * fill price, and marked equity includes remaining cash. Existing frozen golden baseline remains the reference.

## Validation

- A 110% commission synthetic fixture is refused without burning initial cash (single- and two-symbol portfolios).
- A 10bp commission fixture reconciles mathematically to 999.0 remaining marked equity from 1,000.0 initial capital and flat prices in both portfolios.
- NaN/Inf/-Inf initial cash, multiplier, notional and rate inputs are denied. Numeric overflow in calculated costs is denied.
- No change to market-data hashes, sealed OOS permissions, actual broker orders or promotion gate thresholds.
- These are **synthetic execution accounting checks**, not empirical calibration of real broker fills or liquidity/market impact. Independent train-only leak checks and statistical validation are separate follow-up tasks.


## Risk policy audit

- The execution engine treats a daily loss at or above the configured limit as a stop/reduce trigger. The post-evaluation risk reporter now counts **equality as a breach** with the same small floating-point tolerance. For a 100 → 98 → 99 → 95 equity series with a 2% limit, the 2.00% and 4.04% losses are both violations (two breaches), not one.
- Risk reports reject nonfinite equity and non-positive equity; time-based risk reports also require timezone-aware, strictly increasing timestamps. This prevents silently reporting 'compliant' on NaN/Inf or unchronological sequences.
- The risk evaluator reports violations, but does not execute orders. No broker configuration, Sealed OOS access, or promotion thresholds were changed.
