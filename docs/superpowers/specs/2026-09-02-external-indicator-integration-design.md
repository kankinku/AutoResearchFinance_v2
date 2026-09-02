# External Indicator Integration Design

## Decision

Use the repository's canonical deterministic `FeatureSpec` engine. The four audited repositories are formula and provenance sources, not runtime dependencies. Keep one implementation per semantic signature, preserve aliases and source evidence, and retain explicit variants when smoothing, warmup, output, or missing-data behavior differs.

`pythonpine` is treated as AGPL-3.0 because its repository LICENSE conflicts with package metadata. Its code is not vendored; formulas are independently reimplemented. No order, account, network, downloader, or plotting code enters the feature engine.

## Expression and data contracts

Every series can receive every registered transform:

```text
<series_id>.<field>@<timeframe>:<calculator>(<sorted parameters>):lag=<bars>
```

Examples:

```text
US10Y.close@1d:rsi(period=14):lag=0
US20Y.close@1w:rsi(period=14):lag=0
KR20Y.close@1mo:macd(fast_period=12,slow_period=26):lag=1
QQQ.close@1d:rolling_correlation(period=60,series=SPY.close):lag=0
```

Timeframes are `1m`, `5m`, `15m`, `1h`, `1d`, `1w`, and `1mo`. Higher-timeframe values are usable only after the source bar closes and `available_at` is no later than the target bar timestamp.

Optional rate identifiers are `US2Y`, `US10Y`, `US20Y`, `JP2Y`, `JP10Y`, `JP20Y`, `KR2Y`, `KR10Y`, and `KR20Y`. They are never automatically required by a strategy.

Feature data contracts are `scalar`, `ohlcv`, `profile`, `order_flow`, `session`, and `research_label`. Profile/order-flow features reject daily OHLCV-only inputs; research labels are unavailable to live execution.

## Semantic identity and registration

The canonical key contains calculator, input roles, normalized parameters, timeframe, lag, output name, data contract, normalized formula, warmup policy, and missing-data policy. Aliases and source ordering do not affect the key. Registration requires schema, reference-vector, historical, no-future-leak, alignment, missing-data, reproducibility, resource, and safety checks to pass.

## Safety boundary

Calculators are pure functions over supplied observations. They cannot read files, access the network, access secrets or accounts, call order APIs, or mutate protected core directories. Existing paper/live approval and emergency-stop gates remain outside the indicator registry.

## Review gate

This document controls `docs/superpowers/plans/2026-09-02-external-indicator-integration.md`. After the user reviews this design, implementation follows the plan's test-first task boundaries.
