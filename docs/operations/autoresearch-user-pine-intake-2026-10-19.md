# User-provided Pine files — first actual component adaptation

Scope: Q05/Q11/Q12 / S9. This is **feature-library preparation**, not a new strategy generation, trading deployment, or TradingView parity certification.

| Uploaded source | Type | Header | Upload SHA-256 | Status |
|---|---|---|---|---|
| Buyers & Sellers Profile + Dynamic S/R, © Zeiierman | Pine v6 indicator | CC BY-NC-SA 4.0 | `76a3059c22ffb756376c4764827556659c3c8702d76a0139806db5b290a8cc66` | REVIEW_REQUIRED: noncommercial/share-alike scope; no code imported |
| Shaakuni Liquidity Levels & Order Blocks 1.4.0, © Shaakuni | Pine v6 indicator | MPL-2.0 | `54dabcd62a87df46e0b248ef290ccf3f1346d4b2f5f49ec72b6c68148e703f78` | **PARTIAL_FEATURE_ADAPTED**: past-completed day/week high, low, EQ only |
| Wyckoff [theUltimator5] | Pine v6 indicator | No explicit license header found in upload | `b2911d7eeef036ef476615fbda127ae10d8041cd6da469a4ede546c62be77b59` | PERMISSION_REVIEW_REQUIRED: no code imported |

## Implemented

`core/features/pine_liquidity_levels.py`: streaming prior completed daily/weekly high, low and 50% midpoint from exchange-local, time-ordered bars. Non-lookahead convention: changes visible at the first bar of the **following** completed day/week, and the current day's partial prices never contaminate prior-level features. Includes credit and MPL-2.0 attribution.

Important limitations: **Not registered** in dynamic Feature Registry or StrategyIR. Does not implement OB detection, live sweep/break display, weekend `timenow` roll logic, sessions/DST normalization or Pine plotting. ISO week key assumes pre-aligned session dates; Pine's timeframe boundaries may differ on non-standard assets. Full source code **not reproduced** in the repository. No signal/trade parity, backtest or OOS tests were executed. The three inputs were user-provided and are not the earlier N01–N10 strategies.

## Verification

Target tests: `tests/core/test_pine_liquidity_levels.py` and existing `tests/strategy_ir/test_pine_source_gate.py`: 5 PASS. Target Ruff PASS and diff whitespace check PASS. Full suite, live MCP and trading NOT RUN. Research ledger remains G350 and real orders disabled.

## Next gate

Before claiming the files are strategy candidates, identify specific causal features and decision rules, confirm licensing and implement a typed FeatureRef/registry binding plus PIT and trading-replay parity checks on independently obtained OHLCV data. In particular, the original indicators do not declare `strategy.entry/exit` orders.
