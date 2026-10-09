# Finance improvement — capital exposure calculation (T-006 partial)

Prior bug: `orchestration/pipeline.py` supplied `exposure = closed_trade_count / number_of_equity_points`. This measured *trade frequency*, not the amount of capital invested or time exposed to the market. Long hold-to-maturity strategies could report 0% exposure; frequent trading strategies could report larger exposure despite being mostly flat.

## Replacement definition

`Metrics.exposure` now receives the arithmetic mean, across every available portfolio equity timestamp, of **gross long marked market value / total marked equity**. Opens and sells fill at their timestamp's market open; the remaining position is valued at that timestamp's close. For unequal multi-symbol calendars, the last available close is carried forward solely for marking outstanding holdings. This is not a margin/leverage or intrabar time-at-risk metric.

The API shape and the field name do not change, but numerical results **will change** for almost all strategies. Old experiment outputs and new outputs must not be compared using the exposure field without honoring evaluator/code version and the manifest comparison key. Market data, holdings, trade history, and equity must come from the same evaluation run.

Tests: `tests/orchestration/test_exposure_accounting.py` covers no position, full/partial portfolio ownership, and actual `GenerationPipeline._evaluate` integration. The independently calculated four-bar fixture is 0%, 100%, 100%, 50%, with an average of 62.5% exposure.

Remaining risk-model work: explicitly version the metric contract if used by external analytics, and extend separate tests for leverage/short borrow when support is added (currently IR/backtest is long-only).
