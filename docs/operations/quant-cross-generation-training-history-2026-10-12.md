# Cross-generation training return alignment — 2026-10-12

## What changed

1. The development-market research evaluator records only **training-prefix equity returns** for every generated candidate that passed the existing chronological train-only selection eligibility checks. The new internal `TrainingTrace` contains timezone-aware return timestamps, all semantic strategy IDs (including rejected candidates), the dataset hash, calendar, timeframe, and aligned return observations. No prices, market source dump, protected Sealed OOS data, external feature series or credentials are exported.
2. `TrainingTraceStore` writes an SHA-256 content-addressed immutable JSON artifact under the **runtime state** `system/training-traces/`. Repeated identical writes are idempotent. Readers never create files. Missing, corrupt, oversized, malformed, altered or symlinked artifacts fail closed. Original immutable Evidence attempts only contain `training_trace_ref` rather than the returns.
3. `research_trial_inventory`, already used by `get_research_brief`, can aggregate these traces across explicitly selected, checksum-verified Evidence workspace journals. A scope is eligible for comparable training alignment **only** if it shares an identical verified manifest comparison hash (including data hash, data zone, code and engine policy). Trace metadata must match the manifest and every candidate ID must match its immutable attempt snapshot.
4. The alignment is a **common chronological prefix**, never pairwise deletion, forward-fill, intersection with silent gaps, or extrapolation after the shortest training cutoff. Short histories (<30 observations), differences in timebase/market source, conflicting repeated strategy semantics, missing trace references and candidate count overflow all produce explicit incomplete/incomparable statuses.
5. Executable-strategy duplicates are counted as evaluated attempts, but appear only once in the dependence-correlation cohort if their common-prefix returns are identical. The combined cohort diagnostic reuses the existing correlation matrix effective rank and 4,096-seed Gaussian Sharpe-Z null reference; its local IID-equivalent count is clearly **not** an approved global DSR correction.

## Read-only operator evidence

Existing MCP `get_research_brief.research_trial_inventory` adds:
- `cross_generation_aligned_scopes` and `cross_generation_incomplete_scopes`
- `cross_generation_training_history` list of at most 32 manifest-scoped summaries, with status, observation count, evaluated and unique semantic candidate counts, exact training cutoff and **conditional** Gaussian-null equivalent K when available
- `cross_generation_scope = EXPLICIT_MANIFEST_MATCH_TRAIN_ONLY_NOT_GLOBAL_DSR`

No new MCP tool, input schema or OAuth behavior is required. Raw return vectors are never added to MCP summary. The original protected market data files and historic immutable Evidence records are left untouched.

## Cautions and limitations

- `history_complete=false` and `effective_independent_trials=null` remain fixed. A missing old trace or unknown external workspace is never interpreted as zero attempts. The currently deployed operating Evidence predates training-return snapshots, so the old research runs remain unmeasured.
- A matching manifest and train-prefix alignment does **not** prove that the **initial parent strategy, past hypotheses, earlier model selection or data vendor revisions** were independently point-in-time valid.
- The cross-generation correlation matrix pools observations of strategies that may have been discovered after the historical training cutoff, so this is retrospective diagnostic information only. No Champion promotion, Sealed OOS evaluation, statistical certification or brokerage authorization changes.
- Store contains strategy-generated derived training returns as runtime research artifacts. It must remain ignored from Git, inaccessible to public client filesystem operations, and subject to the same backup/secrecy rules as other private research state.
- The next rigorous gate is an auditable chronological trial/parent lineage registry with actual source-release timestamps and cross-validated Monte Carlo error including finite-sample estimation uncertainty; independent DSR null-distribution calibration is not achieved here.

## Acceptance checks

- Integrity: tampering, symlinks, missing blob, impossible values and invalid references fail closed.
- Alignment: two compatible attempts with different training cutoffs align on the shorter contiguous prefix; exact duplicate executable strategies do not inflate dimensionality; conflicting executable-return values are rejected.
- Segregation: mismatched version/manifests cannot pool; any missing history blocks a partial result from being labeled complete.
- Actual evaluation: generated Evidence includes the content-addressed trace reference, return source and candidate semantics; the summary returns no raw vectors.
- Existing Ruff, Mypy and complete pytest; safe Git push, paused-run Quant-only restart and actual authenticated ChatGPT MCP `get_research_brief` read required before marking deployed.
