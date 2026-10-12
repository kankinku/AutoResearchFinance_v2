# Conditional DSR trial-count calibration — 2026-10-12

## Scope

This implements a **train-only, single-cohort Gaussian Sharpe-Z null calibration**, not a globally authorized or audited DSR effective independent trial count.

The previously deployed empirical per-cohort return correlation matrix is created on the last chronological training-fold prefix, with later/test returns excluded and external feature-release timing unsupported. The matrix is used transiently and not written to Evidence or exposed through GPT.

## Null calculation

- Eigendecompose the empirical candidate correlation matrix; clip numerical negative eigenvalues after PSD validation.
- With a documented fixed RNG seed (20261012), simulate 4096 correlated standard-normal **asymptotic Sharpe Z** vectors. Take the maximum candidate score on each draw, then compute the mean and **Monte Carlo-only** ±1.96 SE interval.
- Map the observed mean and its Monte Carlo-only bounds onto an IID Gaussian *equivalent trial count* `K`. The IID reference uses direct deterministic numerical integration of `E[max(Z_1,...,Z_K)]` for i.i.d. standard normals. It is **not** a measure of the number of independent historical experiments, real-world DSR family-wise error, or calibrated multiple-testing correction.
- Even perfectly negatively correlated 2-candidate scores can have IID-equivalent K > 2, though correlation entropy effective rank = 1. Tests independently check `E[max(Z1,Z2)]=1/sqrt(pi)`, `E[max(Z,-Z)]=sqrt(2/pi)`, equal vectors, fixed-seed reproducibility and CI intervals.
- The 95% reported interval is **conditional** on the estimated training correlation; it omits matrix-estimation error, temporal dependence, non-Gaussian return tails, optimizer selection, strategy migration, and missing trials. It is not a full confidence interval for genuine DSR K.

## Data and safety

- The `CohortDependenceReport` now carries `null_max_sharpe_z_mean`, `null_max_sharpe_z_ci95`, `iid_equivalent_trials_estimate`, `iid_equivalent_trials_ci95`, `null_monte_carlo_draws=4096`, and `null_model=GAUSSIAN_SHARPE_Z_EMPIRICAL_TRAIN_CORRELATION`.
- The immutable attempt Evidence already records a small serialized `trial_dependence` dictionary. No additional MCP tools, OAuth schema, DB migrations, raw price disclosures, live orders or sealed OOS actions.
- Existing `get_research_brief.research_trial_inventory` adds `trial_null_calibration_cohorts`, `trial_null_unmeasured_cohorts`, and per-cohort null estimates (last 10). Historical no-calibration attempts remain **unmeasured**, not filled by imputation.
- New Evidence validation denies incomplete, nonfinite, reversed or incorrectly attributed calibration intervals. `global_dsr_approved=false`, `effective_independent_trials=null`, `effective_trials_status=NOT_MEASURED` and `history_complete=false` are invariant.
- The currently displayed existing DSR score remains on its historical **raw candidate count IID proxy**, not the new local Gaussian-null K. A measured local proxy must never silently be used for strategy promotion.

## Next scientific acceptance

1. Freeze a comparable research-universe manifest spanning candidate generations and explicit workspaces, including actual train-only timestamps, source fingerprints, candidate semantic identities and completeness of all attempted trials.
2. Independently cross-check correlated Studentized-Sharpe maximum distributions, including time-series autocorrelation, resampling under market null and covariance estimation error. Calibrate confidence intervals against independent reference implementation and large simulations.
3. Only after a full independent evidence gate, consider an explicitly versioned replacement of old trial-count DSR proxies. Do not enable trading or automatically promote Frontier/Champion.
