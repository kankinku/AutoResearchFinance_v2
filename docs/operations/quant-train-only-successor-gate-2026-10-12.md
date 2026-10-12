# Train-only successor gate — 2026-10-12

## Problem verified

The walk-forward fold evaluator generated and ranked candidate strategies using *only its training window*, but the batch successor helper later ranked the entire evaluated candidate cohort using full-period robustness/holdout scores. This gave later test returns an influence over which alternative strategy advanced to the next generation. Existing next-generation IR Evidence checks prevent forgery, but do not on their own make that ranking train-only.

## Narrow change

- The default next-parent selection uses **the last chronological train-only fold's previously frozen selected_candidate_hash**. It must be a member of that fold's generated candidate hashes, have train_end_at strictly before test_start_at and exist in the actual evaluated candidate cohort.
- Holdout/full-period funnel gates still may **veto** the frozen choice for exploratory progression; they cannot replace it with a higher-scoring competing test candidate. If the train-only choice is rejected, absent from the evaluated cohort, or train-only selection status is not EVALUATED, there is **no successor**.
- No silently substituting a winner for unsupported external feature inputs, or Bayesian search with unverified prior observations. Candidate snapshots continue to be saved only when the existing eligibility gates approve them.
- Successful evaluation returns successor_selection_basis=LATEST_TRAIN_ONLY_FOLD and the latest fold training end timestamp. The metadata preserves successor_selection_upstream_verified=false: the parent strategy's origin is still not independently known to be train-only.
- This is a conservative *exploratory successor selection* guard, NOT an independent OOS verification, an approved Champion or validation that the original user-provided strategy was never tuned on historical test data.
- The current fold design is chronological walk-forward. The CPCV/CSCV diagnostics remain retrospective and are not used for the frozen successor decision. A fully independent sealed OOS and independently verified source/feature provenance remain future work.

## Regression focus

- Manipulating full-period candidate scores cannot change a valid training-selected successor.
- Rejecting that exact frozen train winner cannot cause a fallback to another full-period/holdout winner.
- Altering candles strictly after the final training-fold cutoff does not change the selected successor.
- An unverified or unsupported train-only selection cannot name a successor.
- Existing eligibility and immutable Evidence checks remain required.
