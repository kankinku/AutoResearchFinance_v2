# T-004/T-007: explicit out-of-sample signal boundary

`BacktestRequest.signal_start_at` is an optional aware datetime, defaulting to `None` to preserve existing backtests. When set, the simulator may calculate indicators on all earlier history, but must not issue entry signals before that timestamp; any resulting orders still fill no earlier than the *next* bar open. It applies to single- and multi-symbol portfolios. A naive timestamp is rejected.

This is an execution primitive **only**: it does not independently validate a research strategy. Every validation fold must additionally prevent parameter selection on its future test rows, and must explicitly record whether this happened. Existing `selection_applied=false` indicates that no train-only strategy selection has taken place.

The tests in `tests/core/test_backtest_warmup_boundary.py` start with a three-bar SMA, prohibit all training-window trades, and confirm test-window signals use earlier history without future candles. Existing default execution invariants remain frozen by `test_backtest_golden_baseline.py`.

## Fold integration (follow-up)

`GenerationPipeline._temporal_holdout_evidence()` now creates a prefix containing only bars at or before the fold test end. Calculators use the prefix for causal indicator warmup while `signal_start_at` blocks trading based on prior training bars. The resulting equity, trades, exposure, turnover, performance and benchmark comparison are restricted to the test timestamps. `warmup_history_used=true` records this behavior, while `selection_applied=false` remains explicit: the strategy was **not** reoptimized exclusively on each fold's training window.

The targeted tests verify a 3-bar SMA can trade inside a 3-bar test window using earlier causal history, and changing later candles does not change this fold's result. This does **not** satisfy independent walk-forward strategy selection or Sealed OOS verification, which remain pending.
