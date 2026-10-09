# Finance improvement — no-replacement random parameter sampling (T-009 partial)

`mutation.parameter.random_search()` previously sampled **with replacement** whenever the requested number of candidates exceeded the finite grid size, including a domainless search producing many identical `{}` points. Identical inputs produced repeated backtests and artificially inflated experiment counts.

New contract: `count` is a maximum evaluation budget, not a guarantee of distinct candidates. Each call samples without replacement from unique parameter combinations, respecting the existing seed. Repeated values within a parameter domain are deduplicated before sampling. `random_search((), count=8)` now produces only the single baseline `{}`; `count=0` produces no points. When the grid has fewer combinations than the requested count, the actual candidate count is smaller.

The change preserves candidate and manifest schema, and leaves Grid and Bayesian sampling untouched. It does not yet deduplicate *semantically equivalent strategies from different parent paths*, which is a distinct next-stage task. Experiment count/comparison for historical runs with replacement is not directly equivalent after this change.

Tests: `tests/mutation/test_parameter_search.py` covers deterministic unique sampling, repeated input values, and domainless search; `tests/orchestration/test_evaluation_runner.py` verifies the pipeline's actual candidate count and Evidence ledger count.
