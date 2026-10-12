# Observed trial inventory — safe MVP handoff (2026-10-12)

## Purpose and boundary

- The existing immutable `EvidenceStore` is the only verified source for candidate **evaluation rows**. New projections read it without mutating the journal.
- `memory.trial_inventory.research_trial_inventory((state_a, state_b, ...))` combines explicitly provided workspace *state* roots and verifies checksums before accounting. It does **not** discover all user computers, previous exports or external provider records; a complete global history cannot be asserted.
- Exact mirrored run journals count once; conflicting or partial mirror copies fail closed. Different research runs with matching manifest `comparison_key` can be **grouped**, but manifest equality is not independent confirmation of provenance, historical release timing or PIT data.
- `candidate_evaluation_instances` counts all observed immutable attempt candidate rows, including failed/fallback attempts. `finalized_candidate_instances` counts only completed attempt records referenced by final generation events. `nonfinal_candidate_instances` covers the remainder. Duplicate-prevented proposals recorded in generation `duplicate_skipped` are separate from *evaluated* candidate rows.
- `unique_candidate_hashes_global` and per-manifest-group counts use lineage/proposal identity, not independent hypothesis trials.
- New attempt candidate snapshots include `semantic_strategy_hash` derived from executable Strategy IR, excluding metadata and ancestry; `unique_semantic_strategy_hashes_global` is **NULL**, not guessed, if any candidate record lacks it (e.g. legacy immutable Evidence). The original Evidence journal is never retroactively rewritten.
- `effective_independent_trials: null`, `history_complete: false` and `effective_trials_status: NOT_MEASURED` remain explicit. DSR effective trial counts require independently validated provenance, coverage and candidate-dependence calibration; this feature cannot authorize strategy promotion.
- A legacy generation without `duplicate_skipped` makes the total skipped count `null`; it is not reported as zero. `UNVERIFIED_EVALUATOR` attempts remain explicitly identified.

## Existing MCP integration

- The existing `get_research_brief` response adds `research_trial_inventory` scoped **only** to its authorized server state directory. Existing MCP tool names, parameter schemas, OAuth configuration and endpoints are unchanged; arbitrary client-supplied state paths are **not** allowed.
- To audit a second workspace, an operator must intentionally pass its state root to the Python read-only inventory function. GPT's general brief does not imply or assert that the other workspace was included.
- Existing `get_research_evidence` payload contract is unchanged, so historical clients and read-only dashboard/CLI output remain compatible.

## Regression acceptance

- Checksum-verified two-workspace aggregation, finalized vs nonfinal attempts, retries, duplicate hashes, scope isolation and unscoped events.
- Exact-mirror deduplication; conflicting/partial mirrors and corrupt journals fail closed; missing directory reads create no new files.
- Legacy skipped and missing semantic identities stay unmeasured; two different lineage candidate hashes with the same semantic hash deduplicate at the executable-strategy level.
- ChatGPT research brief remains read-only and includes new scoped counts; newly evaluated candidates write the semantic identity in immutable Evidence.
- No new real research jobs, market-data changes, sealed OOS access, trade orders or promotions as part of deployment.
