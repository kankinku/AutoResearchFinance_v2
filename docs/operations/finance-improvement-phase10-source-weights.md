# T-010 partial — policy-driven search source budgets

The `allocate_sources` planner now reads `research/policy.yaml` (or an explicit validated `SearchPolicy` / ratio map) rather than silently applying hard-coded ratios. Every source weight must be finite and nonnegative; all four fractions must sum to one. Candidate slots are assigned using floor + largest remainder with seeded reproducible tie-breaking. Existing legacy callers still receive the default policy layout.

**Status is planning-only.** This module does not implement the separate exploit/explore/crossover/rescue candidate generators or read candidate lineages from the persisted frontier. Allocated slots are *budgets*, not proof that those sources actually executed. Subsequent work must connect real source-generated candidates and audit lineage before claiming the search is policy-driven end to end.
