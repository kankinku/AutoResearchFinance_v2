# Train-only trial dependence diagnostic — 2026-10-12

## Goal and evidence boundary

This change estimates **descriptive correlation-matrix effective rank within a single comparable candidate cohort**. It does not assert independently calibrated DSR trial counts. It is an intermediate, observable step toward the next DSR calibration work.

Primary research background: Bailey & López de Prado, *The Deflated Sharpe Ratio* (Journal of Portfolio Management, 2014, https://doi.org/10.3905/jpm.2014.40.5.094). Correlation-matrix entropy effective rank is also documented in independent replications of Sharpe-ratio inference, but **the rank cannot automatically be substituted for the independent-test count in the expected-maximum DSR formula**. For example, two perfectly anticorrelated strategies yield rank one while their maximum Sharpe still reflects two opposite bets.

## Implementation

- `evaluation/trial_dependence.py`: correlation eigenspectrum entropy rank `exp(-sum(p * log(p)))` with `p=nonnegative_eigenvalues / sum(nonnegative_eigenvalues)`; also record mean absolute off-diagonal correlation and across-candidate dispersion of observed *per-observation* Sharpe values. All values describe a fixed cohort, not an independently fitted null distribution.
- Scope: all actually evaluated, aligned candidates from **the latest chronological training fold's prefix**, and **never the later test block**. Candidate generation still uses existing deterministic data-blind generators. Upstream parent selection independence is not independently established.
- Reject/mark unmeasurable for fewer than 2 candidates, fewer than 30 aligned return observations, malformed or negative-below-100% returns, non-finite data, constant or nearly constant returns, invalid covariance, over 128 candidates, or over 100,000 return points. No imputation, silently dropped bars or inferred data-release times.
- `GenerationPipelineResult.trial_dependence`: per-cohort `CohortDependenceReport`, status, effective_rank, average_absolute_correlation, observed_sharpe_dispersion, training_cutoff_at, method and `dsr_calibrated=false`.
- **Unsupported external features, feature release timestamps or unverifiable prior Bayesian observations** make this diagnostic `NOT_MEASURED_UNVERIFIED_TRAINING_INPUTS`; the pipeline does not recover by silently using full-period series.
- `orchestration/evaluation_runner.py` records the small summary (not raw return streams or any price rows) in immutable attempt Evidence, alongside the unchanged DSR `multiple_testing_trials` raw-count proxy.
- `memory/trial_inventory.py` exposes `trial_dependence_estimated_cohorts`, `trial_dependence_unmeasured_cohorts`, and at most ten observed summaries `trial_dependence_diagnostics_sample` through existing `get_research_brief.research_trial_inventory`. Each summary is labeled **TRAIN_ONLY_COHORT_NOT_GLOBAL_DSR**; validation rejects malformed measured metrics.
- **Global** `effective_independent_trials` remains **null**, `effective_trials_status=NOT_MEASURED`, `history_complete=false`. Historical 21 evaluation instances did not record a return-correlation matrix and cannot be retroactively reconstructed. No proof of coverage across hidden workspaces, independent markets, history/PIT correctness, or multiple-testing probability is claimed.

## Verification

- Independent deterministic anchors: identical return vectors have rank one; orthogonal vectors have rank two; partial correlation lies between. Perfect negative dependence deliberately does **not** become DSR-independent K.
- Numeric validity and maximum input boundaries, legacy null diagnostics, invalid Evidence denial, API read-only compatibility, train-only status for external features, unchanged diagnostics after editing prices strictly beyond last fold's training cutoff.
- Ruff/Mypy, full Pytest suite, GitHub remote HEAD parity, public OAuth health, actual connected ChatGPT MCP research brief reading required before marking release complete.

## Remaining steps after this release

1. Persist and validate a shared **aligned train-only research universe** spanning comparable generations, with stable timestamps, return-source/code/data/funnel versions, complete trial registry, and verified parent/hypothesis lineage. Avoid leaking sealed OOS.
2. Independently calibrate the **distribution of the maximum Sharpe** under dependence (e.g. fixed-seed Gaussian-copula Monte Carlo and independent reference with uncertainty diagnostics), with correct Sharpe variance and complete candidate coverage; measure the **effective independent DSR K** only with full sufficient evidence.
3. Keep any prospective calibrated K diagnostic separate from the existing DSR proxy until an independent acceptance gate passes; do not use either to auto-promote Champion or enable trading.
