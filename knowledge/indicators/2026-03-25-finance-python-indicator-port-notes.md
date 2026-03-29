# Finance-Python indicator port notes

- Source repository: [alpha-miner/Finance-Python](https://github.com/alpha-miner/Finance-Python)
- Review date: 2026-03-25
- Local inspection path: `C:\Users\hanji\AppData\Local\Temp\Finance-Python-alpha-miner-a84bdb2f-01c8-499e-98b1-d44153e050dd`

## Where the indicator code exists

- `PyFin/Analysis/TechnicalAnalysis/__init__.py`
- `PyFin/Analysis/TechnicalAnalysis/StatelessTechnicalAnalysers.pyx`
- `PyFin/Analysis/TechnicalAnalysis/StatefulTechnicalAnalysers.pyx`
- `PyFin/Math/Accumulators/StatelessAccumulators.pyx`
- `PyFin/Math/Accumulators/StatefulAccumulators.pyx`

The repository does contain real indicator code, but most of it is implemented as Cython extensions instead of plain Python modules.

## Indicators and formulas confirmed

- `XAverage`
  - Recursive EMA.
  - Seed with the first observed value.
  - Recurrence: `average += alpha * (value - average)`, `alpha = 2 / (window + 1)`.
- `MACD`
  - `XAverage(short_window) - XAverage(long_window)`.
- `MovingRSI`
  - Built from positive and negative difference averages.
  - Returns `100 * pos_avg / (pos_avg - neg_avg)`.
  - Returns `50` when the denominator is zero.
- `MovingCorrelation`
  - Rolling Pearson correlation.
  - Returns `0.0` for full windows with zero denominator.
- `SimpleReturn`
  - `current / previous - 1`.
  - Returns `NaN` when the previous value is zero.
- `LogReturn`
  - `log(current / previous)`.
  - Returns `NaN` when the previous value is zero.

## Objective usability assessment

- Formula quality: usable.
  - The formulas are internally consistent and backed by repo tests such as:
    - `PyFin/tests/Math/Accumulators/testStatefulAccumulators.py`
- Direct dependency fit for this project: poor.
  - The implementation is Cython-heavy.
  - It does not drop into our current `pandas.Series -> pandas.Series` indicator registry without an adapter.
  - Local build verification failed in the current environment because the extension build path could not start:
    - `python setup.py build_ext --inplace`
    - failure: `ModuleNotFoundError: No module named 'setuptools'`

That means the repo is a good formula reference, but not a practical direct import for the current autoresearch stack.

## What was ported into this project

Ported into:
- `src/finance_autoresearch/strategy/indicator_registry.py`
- `src/finance_autoresearch/strategy/base_contract.py`

Added indicators:
- `xaverage`
- `macd`
- `macd_signal`
- `macd_hist`
- `rolling_corr`
- `simple_return`
- `log_return`

Adjusted existing indicator behavior:
- `rsi` now returns `50.0` on flat windows after warmup, matching the external repo's neutral-denominator convention.

## Porting judgment

- Worth porting:
  - `XAverage`, `MACD`, correlation, return series
  - reason: straightforward formulas, low integration risk, directly useful for strategy mutation
- Not worth porting as-is right now:
  - the broader Cython accumulator framework
  - reason: higher complexity than the current project needs, weak fit with the single-file strategy mutation model
