# External Indicator Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port every safe importable indicator formula from the four audited repositories into the canonical FeatureSpec engine, deduplicate equivalent implementations, and support arbitrary registered-series transforms on completed daily, weekly, and monthly bars.

**Architecture:** External repositories provide formula/provenance records; calculations run in local pure Python code. A semantic registry maps aliases to canonical features and separates scalar OHLCV, multi-output, profile/order-flow, session, and research-label contracts. Series references are resampled and as-of aligned before calculation, so VIX, ETFs, gold, DXY, target symbols, and US/JP/KR 2Y/10Y/20Y rates all use the same transform path.

**Tech Stack:** Python 3.10, Pydantic v2, NumPy/Pandas-compatible tuple calculators, pytest/Hypothesis, Ruff, mypy, FastAPI dashboard.

---

## File map

- Create `core/features/series.py` for `TimeFrame`, `SeriesRef`, `FeatureTransform`, completed-bar resampling, and transform expressions.
- Modify `core/features/contracts.py` for provenance, semantic identity, output metadata, data contracts, and `1w`/`1mo`.
- Modify `core/features/alignment.py` for timezone-aware completed-bar and `available_at` alignment.
- Create `core/features/provenance.py` for the four source records, SPDX policy, and excluded operational symbols.
- Create `core/features/catalog.py` for canonical definitions, aliases, variants, rate IDs, and catalog search.
- Modify `core/features/calculators.py` for deterministic scalar and multi-output indicator dispatch.
- Create `core/features/specialized.py` for profile, order-flow, session, and research-label contracts.
- Modify `core/features/registry.py`, `strategy_ir/schema.py`, and `core/backtest/engine.py` for deduplicated lookup and series-aware backtests.
- Create tests `tests/core/test_feature_provenance.py`, `test_feature_series.py`, `test_imported_indicator_catalog.py`, `test_extended_feature_calculators.py`, `test_specialized_features.py`, and `test_series_feature_backtest.py`; update existing feature and Strategy IR tests.
- Modify `dashboard/app.py`, `dashboard/service.py`, `dashboard/static/index.html`, `dashboard/static/app.js`, `dashboard/static/styles.css`, and `tests/dashboard/test_api.py`/`test_static_assets.py` for the Korean catalog panel.
- Modify `README.md`, `docs/operations/feature-registry.md`, and `docs/operations/run-generation.md`; create `docs/operations/external-indicator-verification.md`.

## Imported inventory

The catalog covers moving averages/smoothing (SMA, EMA, WMA, TMA, HMA, DEMA, TEMA, VWMA, KAMA, VIDYA, Wilder, McGinley, zero-lag EMA, FAMA, Guppy), momentum (RSI, Stochastic, Stoch RSI, Williams %R, ROC, Momentum, CMO, RVI, RSX, MACD, CCI, TRIX, Ultimate Oscillator, TSI, Connors RSI, Schaff, Vortex, DTI, Laguerre RSI, SMI, Qstick), trend (DMI, ADX, Aroon, Parabolic SAR, Supertrend, Ichimoku, regression, TSF, slope, fractals), volatility/range (TR, ATR, normalized ATR, Bollinger, Keltner, Donchian, standard deviation, historical volatility, Chaikin volatility, Ulcer, Mass, Garman-Klass, Parkinson), volume/flow (OBV, VWAP and anchored variants, ADL, CMF, MFI, volume oscillator/breakout/ROC, force index, ease of movement, volume delta, intensity, PVT, VW-MACD, Klinger, VFI, PVI, NVI), price action (typical/median price, pivots, ZigZag, Heikin-Ashi, Renko, candlestick patterns, support/resistance), cycles/statistics (Fisher, Hilbert transforms, DPO, fractal dimension, Kalman slope, Hurst, entropy, KL divergence, z-score, percentile, rolling moments, MAD, scaling, returns, fractional difference, CUSUM, triple barrier), market context, and specialized profile/order-flow/Wyckoff features. Duplicate names map to one identity; different formulas remain variants.

### Task 1: Freeze source provenance and licensing

**Files:** `core/features/provenance.py`, `tests/core/test_feature_provenance.py`, `docs/superpowers/specs/2026-09-02-external-indicator-integration-design.md`, `docs/operations/feature-registry.md`

- [ ] Write tests asserting the four repository names, audited SPDX decisions, and that `submit_order`, `place_order`, `MetaTrader5`, downloader, network, and plotting symbols are excluded.
- [ ] Run `python -m pytest tests/core/test_feature_provenance.py -q`; it must fail because the manifest is absent.
- [ ] Implement immutable `SourceRecord(repository, commit, spdx, implementation_policy, excluded_paths)` and `audited_indicator_sources()`; set pythonpine policy to `independent_reimplementation` and MIT/Apache sources to `derived` only where attribution is recorded.
- [ ] Run focused tests and `ruff check core/features/provenance.py tests/core/test_feature_provenance.py`; commit `docs: freeze external indicator provenance`.

### Task 2: Add universal series/timeframe contracts

**Files:** `core/features/series.py`, `core/features/contracts.py`, `core/features/alignment.py`, `strategy_ir/schema.py`, `tests/core/test_feature_series.py`, existing contract/schema tests

- [ ] Add failing tests for `SeriesRef("US20Y", "close", "1w")`, `FeatureTransform` expression generation, `1mo`, timezone rejection, and completed-bar-only resampling.
- [ ] Run the focused tests and verify failure.
- [ ] Implement with Python 3.10-compatible enums:

```python
from enum import Enum

class TimeFrame(str, Enum):
    MINUTE = "1m"
    FIVE_MINUTE = "5m"
    FIFTEEN_MINUTE = "15m"
    HOUR = "1h"
    DAY = "1d"
    WEEK = "1w"
    MONTH = "1mo"

class SeriesRef(BaseModel):
    series_id: str = Field(min_length=1)
    field: str = Field(default="close", min_length=1)
    timeframe: TimeFrame = TimeFrame.DAY
    lag_bars: int = Field(default=0, ge=0)

class FeatureTransform(BaseModel):
    series: SeriesRef
    calculator: str = Field(min_length=1)
    parameters: dict[str, int | float | str | bool] = Field(default_factory=dict)
```

  Extend FeatureSpec and FeatureRef timeframe validation to `1w` and `1mo`. Resampling groups by exchange timezone/calendar and emits only closed bars. `align_as_of` uses `available_at` and rejects naive timestamps.
- [ ] Run `python -m pytest tests/core/test_feature_series.py tests/core/test_feature_contracts.py tests/strategy_ir/test_schema.py -q`; commit `feat: add series-aware timeframe contracts`.

### Task 3: Implement semantic catalog and deduplication

**Files:** `core/features/catalog.py`, `core/features/contracts.py`, `core/features/registry.py`, `tests/core/test_imported_indicator_catalog.py`, `tests/core/test_feature_catalog.py`

- [ ] Write failing tests asserting RSI aliases resolve to one canonical ID, Wilder and EMA RSI remain different IDs, all nine rate IDs exist, and the catalog exposes source/license/contract metadata.
- [ ] Run the focused tests and verify failure.
- [ ] Add defaulted `canonical_id`, `aliases`, `source_repositories`, `source_licenses`, `data_contract`, `output_name`, and `duplicate_group` fields to FeatureSpec. Hash normalized calculator, inputs, parameters, timeframe, lag, output, formula, warmup, and missing policy.
- [ ] Implement `imported_feature_catalog()`, `resolve()`, `search()`, `duplicates()`, and `rate_series_ids()`. Make registry registration reject duplicate semantic IDs while allowing aliases.
- [ ] Run catalog tests and `ruff check core/features/catalog.py core/features/registry.py`; commit `feat: add canonical indicator catalog and deduplication`.

### Task 4: Port deterministic indicator calculators

**Files:** `core/features/calculators.py`, `tests/core/test_extended_feature_calculators.py`

- [ ] Write reference-vector and property tests before production changes. Cover every inventory family, exact warmup/None behavior, constant-series denominators, multi-output bands/channels, and deterministic repeatability.
- [ ] Run `python -m pytest tests/core/test_extended_feature_calculators.py -q`; verify unsupported-calculator failures.
- [ ] Implement shared rolling/Wilder/weighted/EMA/price-transform primitives and one dispatch branch per canonical calculator. Multi-output indicators use `output_name`; all branches consume only declared inputs and never import modules dynamically.
- [ ] Run `python -m pytest tests/core/test_extended_feature_calculators.py tests/core/test_feature_calculators.py -q`, `ruff check core/features/calculators.py tests/core/test_extended_feature_calculators.py`, and `python -m mypy core/features/calculators.py`; commit `feat: implement imported indicator calculators`.

### Task 5: Isolate specialized data contracts

**Files:** `core/features/specialized.py`, `tests/core/test_specialized_features.py`

- [ ] Write failing tests proving profile indicators require profile observations, order-flow indicators require tick/aggregated order-flow observations, session indicators require session metadata, and order functions are unsupported.
- [ ] Run the focused tests and verify failure.
- [ ] Implement immutable `ProfileObservation`, `OrderFlowObservation`, and `SessionObservation`; calculate volume/TPO profile, aggregated/tick order flow, Weis-Wyckoff, session features, and research labels only under matching contracts. Reject research labels in live execution.
- [ ] Run tests and Ruff; commit `feat: isolate specialized indicator data contracts`.

### Task 6: Connect transforms to Strategy IR and backtests

**Files:** `core/backtest/engine.py`, `strategy_ir/schema.py`, `tests/core/test_series_feature_backtest.py`, `tests/core/test_signal_backtest.py`

- [ ] Write failing tests for weekly RSI on US10Y, monthly MACD on KR20Y, cross-asset correlation, late `available_at`, and combined FeatureRef/spec lag.
- [ ] Run focused tests and verify failure.
- [ ] Resolve each `SeriesRef` before `_feature_values`: resample closed bars, align as-of, calculate the registered canonical feature, and apply declared lags. Preserve supplied-value fast path and reject missing/unregistered/length-mismatched features.
- [ ] Run backtest and signal regression tests; commit `feat: calculate as-of series transforms in backtests`.

### Task 7: Expose the catalog in the Korean dashboard and docs

**Files:** `dashboard/app.py`, `dashboard/service.py`, `dashboard/static/index.html`, `dashboard/static/app.js`, `dashboard/static/styles.css`, `tests/dashboard/test_api.py`, `tests/dashboard/test_static_assets.py`, `README.md`, operations docs

- [ ] Write failing API/static tests for `/api/features/catalog`, canonical ID, aliases, source/license, verification state, data contract, and `1w`/`1mo` labels.
- [ ] Run the dashboard tests and verify failure.
- [ ] Implement a sanitized catalog endpoint and Korean panel showing `가져옴`, `중복 통합`, `검증 완료`, `격리`, and required data. Render expressions such as `US10Y · 1주봉 · RSI(14)`. Never return keys, account IDs, raw data, or paths.
- [ ] Document Codex Desktop selection syntax, optional rates, registration gates, and quarantined functions. Run dashboard tests; commit `feat: expose imported indicator catalog in dashboard`.

### Task 8: Full verification and evidence

**Files:** `docs/operations/external-indicator-verification.md`

- [ ] Run `python -m pytest -q`, `ruff check .`, and `python -m mypy .`; all must pass.
- [ ] Run `rg -n "submit_order|place_order|MetaTrader5|requests\.|api[_-]?key|app.?secret|access[_-]?token" core strategy_ir dashboard runtime research docs README.md`; operational symbols must be absent from feature modules and secret values must not appear.
- [ ] Record exact canonical, alias, variant, specialized, quarantined, and failed counts plus source commits and test commands, excluding credentials, account identifiers, raw data, and temp paths.
- [ ] Commit `test: record external indicator verification`.

## Completion criteria

All four sources are represented; every safe formula is canonical or an explicit variant; duplicate aliases resolve once; the nine rates support every transform on `1d`/`1w`/`1mo`; as-of alignment prevents future leakage; specialized data cannot be misapplied; existing paper/live gates remain unchanged; Korean dashboard/docs explain use; pytest, Ruff, and mypy pass.
