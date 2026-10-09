# T-004/T-007: explicit out-of-sample signal boundary

`BacktestRequest.signal_start_at` is an optional aware datetime, defaulting to `None` to preserve existing backtests. When set, the simulator may calculate indicators on all earlier history, but must not issue entry signals before that timestamp; any resulting orders still fill no earlier than the *next* bar open. It applies to single- and multi-symbol portfolios. A naive timestamp is rejected.

This is an execution primitive **only**: it does not independently validate a research strategy. Every validation fold must additionally prevent parameter selection on its future test rows, and must explicitly record whether this happened. Existing `selection_applied=false` indicates that no train-only strategy selection has taken place.

The tests in `tests/core/test_backtest_warmup_boundary.py` start with a three-bar SMA, prohibit all training-window trades, and confirm test-window signals use earlier history without future candles. Existing default execution invariants remain frozen by `test_backtest_golden_baseline.py`.
