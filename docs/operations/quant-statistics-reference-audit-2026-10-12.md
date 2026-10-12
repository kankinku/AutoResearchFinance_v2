# DSR · PBO · CPCV — reference and leakage audit (2026-10-12)

## Scope and reference basis

- Bailey & López de Prado, *The Deflated Sharpe Ratio* (2014): https://doi.org/10.3905/jpm.2014.40.5.094
- Bailey et al., *The Probability of Backtest Overfitting* (2015): https://escholarship.org/uc/item/4w1110bb
- López de Prado, *Advances in Financial Machine Learning*, CPCV and purge/embargo methods; noncanonical independent public implementation: https://github.com/landtml/purgedcv
- **No benchmark return history or validation source is altered by this audit.** No sealed-OOS access or brokerage action is authorized.

## Actual defects corrected

1. **DSR frequency mismatch:** the evaluation engine's Sharpe is annualized but its observed return count is in bars. The old calculation compared annualized Sharpe directly to a per-observation normal selection threshold, distorting the reported DSR.
2. **DSR null threshold:** corrected to a documented independent normal-trial *proxy* (expected maximum normal Sharpe using Euler-Mascheroni weighted quantiles and null standard deviation 1/sqrt(T-1)). Converts annualized Sharpe back to per-observation units and uses observed return skew and Pearson kurtosis in the DSR denominator when enough nonconstant samples exist. Annualization-unit invariance is tested independently.
3. **CSCV-PBO symmetry:** the default 4/2 split is retained. Non-even or unequal train/test partitions are now rejected rather than returned as a canonical PBO score. The fixed cohort is ranked by *compounded log returns* (not an independently fit Sharpe-optimized cohort).
4. **CPCV naming accuracy:** the original cpcv_return_scores simply compounded returns in held-out group combinations for a fixed strategy without retraining, purging, embargo, or path reconstruction. The pipeline now calls group_holdout_return_scores. The old name remains a compatibility alias, but these values must **not** be called independent CPCV paths.
5. **Purging/embargo reusable splitter:** cpcv_splits accepts explicit per-observation inclusive label-end indices and an optional nonnegative number of embargo bars, and removes overlapping train label intervals before a caller fits a model. Defaults preserve the old split contract. Independent synthetic interval checks validate the exclusion behavior.

## Honest provenance in new Evidence

Each new candidate Evidence record adds:
- `dsr_methodology`: SAMPLE_MOMENTS_IID_TRIAL_PROXY or NORMAL_IID_TRIAL_PROXY (or NOT_MEASURED).
- `pbo_methodology`: CSCV_LOG_RETURN_RANK_NO_REFIT or NOT_MEASURED.
- `stability_methodology`: UNPURGED_FIXED_STRATEGY_GROUP_DIAGNOSTIC (or NOT_MEASURED).
- `cpcv_full_paths`: NOT_MEASURED.

These fields are **methodology warnings, not independently signed statistical validation**. The independence and completeness of total effective trials cannot be verified across unrelated workspaces. Fixed-cohort CSCV ranking does not prove a real fold-specific optimizer was refit. Purging + embargo on a splitter does not imply a model was fitted or OOS predictions reconstructed. Existing immutable Evidence remains unchanged.

## Remaining work

- Authoritative per-trial registry across runs/workspaces, dependence-aware effective multiple testing, and empirical cross-trial Sharpe dispersion.
- Independent statistical library cross-check with pinned reference outputs for full DSR and PBO alternatives (including Sharpe-based cohort selection), and reasoned confidence intervals.
- Full CPCV fitting for every purged fold using known label time horizons and source-release delays, with exactly-once chronological out-of-sample path assembly and non-double-counting checks.
- Separate data-provider Point-in-Time, corporate-action and exchange-calendar verification; signed one-time sealed-OOS validation and human-gated promotion.
