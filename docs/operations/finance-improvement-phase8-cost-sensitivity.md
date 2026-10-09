# T-008 (partial): robustness cost sensitivity sign correction

The former `robust_statistics` computed `clamp_unit(stressed_return / base_return)` for any nonzero base return. This incorrectly assigned 100% cost resilience to a strategy whose original -10% loss deteriorated to -20% under higher trading costs (ratio +2). That is mathematically a ratio, but not a valid *resilience* reward.

For a nonpositive baseline return, cost resilience is now zero. Positive baseline returns preserve the existing ratio and cap. Insufficient-evidence semantics (`base_return=0`) remain unchanged. Other DSR/PBO/CSCV logic is not modified by this correction.

This is a **score semantics change** and historical candidate scores must be compared with the original evaluation code/manifest, not silently overwritten. `tests/evaluation/test_robustness.py` now includes the loss-deterioration counterexample and a positive-return control.

Still outstanding: independently audit DSR annualization and moments, full number of optimization trials, PBO cohort construction, purged folds, and sealed OOS data access.
