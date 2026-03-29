# Universe metadata and factor evaluation notes

- Source repositories:
  - [JerBouma/FinanceDatabase](https://github.com/JerBouma/FinanceDatabase)
  - [quantopian/alphalens](https://github.com/quantopian/alphalens)
- Review date: 2026-03-26

## What these repositories are actually useful for

- FinanceDatabase is useful for:
  - symbol master enrichment
  - country / exchange / market filters
  - sector / industry grouping
  - asset-class-aware universe definitions
- Alphalens is useful for:
  - factor evaluation workflow
  - grouped analysis
  - quantile turnover
  - rank autocorrelation
  - information-coefficient style diagnostics

## Metadata ideas worth keeping

- Maintain a light symbol master with fields like:
  - symbol
  - country
  - exchange
  - market
  - currency
  - sector
  - industry_group
  - industry
  - market_cap
  - identifiers when available
- Use metadata mainly for:
  - universe filtering
  - grouped diagnostics
  - exposure summaries
- Treat sector and industry labels as internal grouping tools.
- Do not market them as official taxonomy coverage.

## Factor evaluation ideas worth keeping

- Align factor values with forward returns before evaluation.
- Review factors by:
  - mean return by quantile
  - information coefficient
  - quantile turnover
  - factor rank autocorrelation
  - grouped breakdown by sector / industry / market
- Expose both:
  - quantiles
  - bins
- Keep zero-aware handling for centered or sign-sensitive signals.
- Track how much data gets dropped during evaluation.

## What fits this project now

- FinanceDatabase is a good reference for a future lightweight symbol master.
- Alphalens is a good reference for a future small internal factor evaluator.
- The best immediate use is conceptual:
  - better universe definitions
  - better grouped diagnostics
  - better factor-quality checks before strategy adoption

## What does not fit this project yet

- Do not add FinanceDatabase as a hard runtime dependency right now.
- Do not add Alphalens as a package dependency right now.
- Do not treat metadata quality as uniform.
  - Duplicate listings and missing identifiers need explicit handling.
- Do not hide factor-evaluation drops behind silent defaults.

## Project adaptation rules

- If a symbol master is added later, keep it reference-only at first.
- Prefer daily cross-sectional evaluation before any broader expansion.
- Keep grouped factor analysis read-only and diagnostic at first.
- If factor evaluation is implemented later, surface:
  - missing price drop rate
  - missing metadata drop rate
  - failed binning drop rate

## Source-backed caveats

- FinanceDatabase is metadata-first, not a price or fundamentals truth source.
- Its classification is a loose approximation and parts of the curation pipeline are manual or AI-assisted.
- Alphalens is still a strong workflow reference, but the latest release is old relative to the current repo activity.

## Sources

- FinanceDatabase repository:
  - https://github.com/JerBouma/FinanceDatabase
- FinanceDatabase equities loader:
  - https://github.com/JerBouma/FinanceDatabase/blob/main/financedatabase/Equities.py
- FinanceDatabase sample equity database:
  - https://github.com/JerBouma/FinanceDatabase/blob/main/database/equities.csv
- FinanceDatabase category taxonomy:
  - https://github.com/JerBouma/FinanceDatabase/blob/main/compression/categories/categories.json
- Alphalens repository:
  - https://github.com/quantopian/alphalens
- Alphalens README:
  - https://github.com/quantopian/alphalens/blob/master/README.rst
- Alphalens performance module:
  - https://github.com/quantopian/alphalens/blob/master/alphalens/performance.py
- Alphalens utilities:
  - https://github.com/quantopian/alphalens/blob/master/alphalens/utils.py
