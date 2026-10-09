# Finance improvement — executed Strategy IR gates (T-005 partial)

This change deliberately alters backtest results **only** for strategies that declare active `regime_filters` or a positive `trailing_stop_pct`; the behavior of strategies without these options remains covered by `test_backtest_golden_baseline.py`.

## Confirmed semantics

- `regime_filters`: all *enabled* conditions must hold at the **completed signal bar close** before placing a new buy for the next open. An absent list or only disabled filters imposes no restriction. Existing holdings can still exit when the regime turns false; regime rules never block exits.
- `trailing_stop_pct`: positive percentage drop from the greatest **observed completed close** since a given long position's entry, with the entry fill price as its starting reference. No intrabar maximum, implied intrabar stop fill, or same-bar execution is assumed; sell is queued for the **next available bar open**.
- Each symbol maintains its own peak. The peak is reset whenever that symbol's position is closed and initialized on a subsequent entry. Value `0` and `None` disable trailing exits.
- Preexisting fixed stop loss and take profit continue to act on completed bar closes and fill on the next available bar open.
- Fields `risk_appetite` and `loss_tolerance_pct` are **evaluation metadata** and must not be represented as order-level risk controls without an explicit implementation contract.

## Regression evidence

`tests/core/test_strategy_risk_execution.py` covers single-symbol and multi-symbol regime eligibility, trailing exits, disabled gates, reset after re-entry, and noninterference with ordinary exits. Test-first reproduction: four failing tests against the old engine (one more test added before patch, also previously unsupported). See signed Git history for implementation and baseline golden tests.

## Remaining work

- Verify strategy feature reference errors fail closed with an actionable message.
- Validate regime signal timing against `available_at` for macro features; avoid forward-looking regime data.
- Introduce separately versioned, realistic intrabar stop/limit semantics only after independent OHLC fill-policy tests. The close-confirmed next-open model is intentional and must not be silently changed.
