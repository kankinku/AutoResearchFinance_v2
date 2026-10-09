# T-009 — semantic strategy deduplication in local research

`candidate_hash` remains a lineage/proposal identifier and is never rewritten. `semantic_strategy_hash` hashes the actual executable Strategy IR fields independently of display ID, family label, parent IDs, generation number, provenance and researcher mutation history. The GenerationPipeline now removes equivalent generated candidates before fast/full/stress evaluations; deduplication retains the first representative and its lineage, leaving input JSON and candidate result schemas unchanged. The legacy `deduplicate_candidates(..., semantic=False)` remains compatible.

Execution-level identity is not an environment or experiment identity. Never reuse a result across different market data, instrument universes, cost models, code versions, or optimizer seeds solely because the semantic strategy hash matches. The existing ExperimentManifest hash must continue protecting cross-run caching.

Tests compare two strategies with distinct lineage and identical risk/signals, verify risk mutations produce different fingerprints, confirm legacy behavior, and assert that the pipeline runs only one backtest set for duplicate parameter points.

Remaining T-009: environment-sensitive cache use at the evaluation worker, provenance-aware dedup reporting, cross-parent cohort sourcing, and historical comparison using original candidate hashes.
