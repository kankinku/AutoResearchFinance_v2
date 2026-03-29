# Qlib alpha factor research notes

- Source repository: [microsoft/qlib](https://github.com/microsoft/qlib)
- Review date: 2026-03-26

## What the repository is actually useful for

- Qlib is most useful here as a reference for:
  - dataset layout
  - factor-expression design
  - OHLCV-derived feature families
- The strongest reusable idea is not the full platform.
- The strongest reusable idea is:
  - keep raw market data simple
  - derive many research features lazily from expressions

## Data and feature structure worth copying conceptually

- Separate market data into:
  - calendars
  - instruments
  - features
- Treat OHLCV as the canonical base layer.
- Generate research factors from the base layer instead of storing every derived column.
- Keep feature engineering separate from model or strategy packaging.

## Factor families worth remembering

- Alpha158-style families suggest these research directions:
  - normalized price features
  - rolling mean / std
  - rolling rank / quantile
  - rolling max / min
  - rolling correlation
  - slope / rsquare / residual-style trend diagnostics
  - VWAP-aware features when data is available
- These are good future candidates for:
  - factor catalog expansion
  - prescreen diagnostics
  - strategy genome feature primitives

## What fits this project now

- Treat Qlib as a feature-research reference, not a dependency.
- Good near-term uses:
  - define a future factor catalog around OHLCV-derived expressions
  - keep calendar and instrument snapshots explicit
  - add a data-health check before feature generation
- Good low-risk future factor ideas:
  - rolling rank
  - rolling quantile
  - trend slope
  - trend fit quality
  - residual-style deviation from local trend

## What does not fit this project yet

- Do not import the full Qlib stack into the current harness.
- Do not inherit Qlib label definitions blindly.
  - Their examples are market-specific and not aligned to this project's keep/rollback loop.
- Do not treat the public Yahoo-backed example dataset as authoritative.
- Do not couple the current backtest path to Qlib storage assumptions.

## Project adaptation rules

- Keep SQLite and the current harness as the operational core.
- Use Qlib only as:
  - factor family inspiration
  - data layout inspiration
  - validation checklist inspiration
- If a future factor catalog is added, start from a small OHLCV-only subset.
- If calendar and instrument metadata are added, keep them outside the mutable strategy file.

## Source-backed caveats

- Qlib's official dataset availability is currently limited.
- The README and docs warn about Yahoo data quality and update caveats.
- The main branch is active development and can differ from stable package behavior.

## Sources

- Repository:
  - https://github.com/microsoft/qlib
- Data docs:
  - https://qlib.readthedocs.io/en/v0.8.1/component/data.html
- Alpha handler:
  - https://github.com/microsoft/qlib/blob/main/qlib/contrib/data/handler.py
- Alpha loader:
  - https://github.com/microsoft/qlib/blob/main/qlib/contrib/data/loader.py
