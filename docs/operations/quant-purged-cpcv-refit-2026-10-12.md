# Purged CPCV — explicit opt-in parameter refit (2026-10-12)

## Behavior

- Adds `orchestration.purged_cpcv.run_purged_cpcv` and an opt-in path through `GenerationPipeline.run`, `EvaluationService.run`, the JSON worker protocol and immutable attempt Evidence.
- Default `cpcv_label_end_indices=None` means **NOT MEASURED**. It does not run silently and does not invent label availability. Caller must supply an inclusive label-end sample index for **each unique market timestamp**, plus nonnegative `cpcv_embargo_bars`.
- Current configuration defaults to four chronological blocks and two held-out blocks per combination: 6 purged folds, 12 held-out block observations and 3 CPCV paths. Group configurations requiring over 28 combinations are denied to limit resource usage.
- Every split purges training label intervals that overlap test label intervals, applies embargo after each test label interval, and **refits candidate selection** from a predeclared, data-blind native-indicator Strategy IR cohort on surviving train segments. Separate training runs across discontinuous gaps prevent bridging missing labels. Its selected strategy is frozen **before** test scoring.
- Each held-out test group is evaluated as a distinct backtest with fresh equity, only market observations through the group's final timestamp for indicator warmup, and no orders before that group's start. Training and OOS scores are never used interchangeably.
- Deterministic bipartite incidence edge coloring assigns each held-out (fold, group) to exactly one reconstructed path. Each path contains every chronological market block exactly once. It compounds isolated block returns for path P&L; it does not create a single continuous position carrying across groups.
- New opt-in attempt Evidence includes folds, selected candidate identities, explicit train/test sample positions, block dates/returns, reconstructed paths, dataset hash, label-end-index digest, embargo count and `sealed_oos_evaluated=false`. No prior Evidence is modified.

## Limits and exclusions

- **RETROSPECTIVE:** Some CPCV folds train on dates *after* an earlier held-out test block, as intended for combinatorial resampling. The report explicitly states `chronological_train_only=false`. Strict chronological WFA is a different existing layer.
- This is a **refit of parameter/strategy selection**, not an ML estimator that can be retrained on each fold. The source parent and candidate hypotheses are predeclared; their independent historical origin cannot be proven.
- No external registered features with unverified historical release lag and no Bayesian optimization with unverified prior observations. Research data zone must be development.
- Featureless Strategy IR price indicators are causal but not a substitute for vendor point-in-time provenance. The result is **not** independent blinded/sealed OOS, a signed Champion gate, portfolio eligibility, or real order authorization.
- The opt-in label index is currently available to direct EvaluationService users; the public GPT batch workflow intentionally does **not** accept an invented label horizon. Extending its schema requires a vetted label timing provider/contract.
- Model-selection statistical confidence intervals, trial correlation, true label lifetime provenance, independent CPCV reference implementation review and realistic transaction-price calibration remain outstanding.

## Tests

- Independent exact-once bipartite test incidence oracle for N/k = 3/1, 4/2, 5/2, 6/2, 6/3 and 8/4.
- Synthetic 16-bar refit and 3-path compounding, train/test group overlap checks, test-only price mutation cannot change its same-fold train decision.
- Real EvaluationService queued worker request roundtrip, CPCV result persistence and immutable attempt Evidence.
- Missing label metadata or negative embargo fail closed; default research remains unchanged.
