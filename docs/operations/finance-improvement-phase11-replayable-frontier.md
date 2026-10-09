# T-011 partial — replayable Frontier parent Strategy IR from immutable Evidence

Prior to this change the research director could see historically eligible Frontier hashes and scores but there was no trustworthy way to reconstruct a winning Strategy IR from them: candidate lineage and evaluation results were decoupled. A future parent could not be recompiled or deliberately mutated from its Frontier record.

New evaluation attempts now attach serialized canonical `StrategyIR` and `strategy_ir_hash` **only** to candidates whose observed research funnel status is `SURVIVOR`, `FRONTIER`, `CHAMPION_CANDIDATE` or `CHAMPION`. `REJECT` and `NEAR_MISS` attempts remain metadata-only; their strategies cannot be silently promoted as an eligible Frontier parent. The attempt payload stays append-only in `EvidenceStore` with its original integrity checks.

`memory.evidence_frontier.frontier_parents(state_dir)` reconstructs only the highest-scoring eligible candidate per family with a matching IR content hash and a model-valid canonical Strategy IR; hash mismatches or invalid/missing snapshots fail closed. Existing immutable attempts that predate this change remain readable and result in no executable parent when their IR snapshots are absent. The director's compact `frontier_summary` continues to show only hash/score/status metadata, not full raw market rows or any Sealed OOS record.

**Scope boundary:** This introduces a real replayable parent source but does not yet trigger automatic Frontier/Crossover/Rescue execution, does not independently authorize survivor-to-champion transitions, does not replace the active parent in the live loop, and does not prove strategy profitability or independence of the upstream hypothesis. T-011 remains PARTIAL until parent materialization is wired to audited source-specific execution and the authorization workflow.

Tests check exact canonical IR hash capture, missing legacy IR, rejection of tampered IR hashes and Near Miss strategies.
