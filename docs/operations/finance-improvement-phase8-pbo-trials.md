# T-008 partial — finite aligned returns and accumulated optimization trials

- CSCV PBO now refuses candidate histories with unequal observation counts instead of silently truncating the longer ones. The caller must explicitly align common timestamps *before* supplying return arrays. NaN/Inf return values fail closed in both PBO and CPCV calculation; incomparable or corrupt histories must not produce success-shaped scores.
- `GenerationPipeline.run(prior_trials=...)` now supplies a cumulative trial count to its DSR approximation. `run_local_evaluation` reads prior attempt Evidence and counts the stored evaluated candidate records, then adds the current unique evaluated candidates. This is a **conservative within-workspace estimate**, not the number of every abandoned/unpersisted manual optimization trial or a guarantee of a fully unbiased DSR.
- `multiple_testing_trials` is included in immutable attempt execution metadata and local evaluation output to make the magnitude of the correction visible. Full-history attempts and cross-workspace search must not be silently treated as independent research.

Versioning warning: DSR scores change for subsequent research in an existing state directory, and historic scores are preserved. This does not yet constitute independent statistical reference validation for DSR/PBO, nor sealed OOS promotion.
