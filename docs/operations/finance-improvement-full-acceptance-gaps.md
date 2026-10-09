# Remaining full-acceptance prerequisites — 2026-10-09

This is a **blocking-criteria register**, not a declaration that all T-001…T-014 work has passed.

## Currently verified

- Golden execution, close-confirmed trailing exits, regime entry filters, actual portfolio exposure, finite OHLCV, and loss-aware stress scoring are covered by regression tests.
- Development walk-forward reports now identify a fixed cohort winner using *only* training-window returns and test it on the subsequent window. External-feature cohorts are explicitly not eligible for this report. Candidate-level legacy holdout and cohort-selection evidence remain distinguishable.
- Deduplication uses an executable Strategy IR hash separate from candidate lineage; earlier attempt records remain immutable.
- PBO/CPCV reject unaligned/nonfinite returns; DSR approximate multiple-trial adjustment includes earlier attempts recorded in this workspace.
- Research source budgets read canonical policy; immutable evidence-backed Frontier context is available to the AI research director, without raw OOS or credentials.
- MCP order permissions remain disabled, and no user capital/order action is authorized by the completed unit tests.

## Critical incomplete work — software

1. **T-002/T-003:** safely untangle core/IR dependencies and split the 556-line research lifecycle without changing the official SDK/queue/worker ABI; crash/retry/recovery parity tests required.
2. **T-004:** require vendor provenance, as-of revisions, delisting/survivorship policy, split/dividend/corporate-action adjustment, missing data / exchange-calendar QA. Current synthetic bars cannot prove any vendor quality.
3. **T-007/T-008:** upstream per-fold strategy *generation* must also be training-only; existing fixed-cohort selection does not erase prior search leakage. Validate DSR/PBO formulas against independent references, account for all trials across workspaces, add purging/embargo for overlapping-label methods.
4. **T-009/T-010:** attach version-aware on-disk experiment cache to real worker execution, materialize Frontier/Rescue/Crossover/Explore candidate sources and report actual source-specific attempts rather than allocated budgets.
5. **T-011/T-012:** persist candidate Strategy IR snapshots for future parents; route rescue and champion requests through audited explicit state transitions, and benchmark bounded AI proposals/repairs against unchanged local baselines.
6. **T-013/T-014:** complete official MCP + Docker acceptance on the Windows/Docker host, independent signed promotion gate and blinded Sealed OOS pass/fail. Do not label a strategy promotable merely because its development funnel says SURVIVOR.

## External acceptance inputs presently unavailable in this worktree

- `docker` CLI and `codex` executable are not present on the examined Moon Linux host; independent Windows Docker Desktop acceptance has not been executed here.
- No historical market-data Parquet or sealed-OOS dataset was located within the examined project worktree. The current worktree contains only synthetic fixtures and repo configuration.
- No signed, independently measured production-quality OOS results or realized investment performance can be asserted from unit tests.

## Exit criteria for genuinely declaring full completion

For each of T-002 through T-014: independently reviewed code, failing-before/passing-after contract tests, immutable evidence and atomic commits; full pytest+Ruff+Mypy PASS; developer fixture benchmarking; Windows Docker worker acceptance including restart/retry; market-data provenance and corporate-actions checks; true training-only research including feature release time; separate authorized validation and one-time Sealed OOS; human-authorized champion gate; negative tests proving research and MCP cannot order or inspect sealed rows.

Until all those conditions are met, overall status remains **PARTIAL**, irrespective of regression test count.
