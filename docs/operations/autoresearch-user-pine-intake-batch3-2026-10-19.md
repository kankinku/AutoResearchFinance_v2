# User Pine intake batch 3 — dollar risk and strategy frameworks

Scope: Q05/Q11/Q12, feature-library preparation only. Earlier G350 ledger and trade permissions unchanged.

## Source analysis
| Source | License | Role | Disposition |
|---|---|---|---|
| adolgov, `Stop loss and Take Profit in $$ example`, Pine v4 | MPL-2.0 header | SMA 14/28 crossing, cash-priced exit for signed quantity, point value, tick size | PARTIAL_PRIMITIVE_ADAPTED; strategy parity not claimed |
| `3Commas Bot / Bj Bot`, Pine v5 | Header not established in supplied material | Multiple MA options, ATR stops/trailing and R:R exits, session filters, reversal, alert payloads | REVIEW_ONLY; order and webhook behavior require licensing, execution modeling |
| Daveatt `BEST Strategy Template`, Pine v4 | MPL-2.0 header | External 1/-1/2/-2 signal input, pyramid and risk controls, stop/target variants | REVIEW_ONLY; external signal binding needed |
| mks17 `Oscillator Evaluator`, Pine v4 | MPL-2.0 header | RSI + stochastic blended oscillators, alternative entry/exit methods; very high pyramiding setting | REVIEW_ONLY; multiple oscillator interpretation and fill semantics needed |

## Implemented

`core/features/pine_cash_risk.py` is an independent deterministic calculation primitive. Converts cash-denominated loss/profit budgets into integer tick counts and corresponding stop and target prices for signed position quantity, contract point value and minimum tick. It rejects zero/invalid inputs and budgets smaller than one tick; it does not submit orders. The original Pine expression computes floating tick distances; this implementation intentionally floors to executable whole ticks and is **not bitwise or execution equivalent**.

No external Pine source is checked in and no simulator, protected backtester, order/risk gateway, StrategyIR schema, or runtime registration is modified. For reproducibility, source material was user-supplied inline and in conversation attachments; provenance requires separate archived review when approved.

## Tests & remaining gaps

Unit tests check long/short symmetry, tick budget limits, invalid input rejection. Actual TradingView broker emulator parity and full-sample QQQ backtest NOT RUN. Intrabar stop/target precedence, gap fills, price tick rounding, commissions, currency conversions and dynamic position sizing remain unsupported by this primitive. The new module is not available to LLM candidates until explicit typed IR and registry integration and relevant safety review.

Next: controlled source hash and license review; implement typed non-order feature registration, then execution semantics in an isolated test runner, not the protected live path.
