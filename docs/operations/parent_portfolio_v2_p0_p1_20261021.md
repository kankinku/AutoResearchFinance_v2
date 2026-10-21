# Quant AutoResearch — P0 / P1 parent portfolio implementation, 2026-10-21

## Baseline / immutable boundary
- Original worktree session: `G452/452`, development QQQ 2020-01-02..2025-12-31, 1,508 bars.
- G248 +170.1955%, MDD 33.4829% development; G431 +156.0622%, MDD 26.0446%.
- The original 452 generations are NEVER rewritten. Changes belong to branch `feat/quant-parent-portfolio-20261021`; the operator did not extend the research session or place broker orders.
- New selection mode **defaults off**: `AcademicMCPCheckpointService(..., parent_portfolio_v2=True)` only when explicitly instantiated in a new/isolated development session. Existing production operator and public MCP server continue on their original selection mode until separate opt-in wiring and testing.

## P0 measured root cause (not a guess)
1. **448/452** recorded generations shared source G4 for their counted inherited parent. G5, G248, G452 pinned selection all source G4, same successor StrategyIR hash `624231a0...`.
2. The original parent selector considers *S7 successors*, not the independently counted G248 StrategyIR itself. Thus a directly successful generation is not automatically eligible for inheritable parents. Policy requires a replayed successor to beat its preceding child, >=30 closed trades, MDD gate. DO NOT silently relax these gates.
3. Bootstrap first sorts coarse S7 outcomes, replays only `coarse[:16]`; at G452 those audited candidate source generations are `[4,5,7,8,9,10,11,12,13,96,97,98,101,102,103,104]`. G248 is missing from these candidate origins.
4. 452 source StrategyIR identities differ, but recorded entry structures only 33, exit structures 22, regime-filter structures 1, risk structures 1, parent lineages effectively anchored to G4.
5. Of 981 candidate attempts in controller progress log, 530 preflight rejected: 327 duplicate effective signals, 136 insufficient closed trades, 67 other contract/validation errors. This does not mean 530 finalized generations failed.

## P1 development changes (implemented)
- `research/llm/parent_portfolio_v2.py`: preselects up to 18 distinct recorded candidate signals across development return, Calmar, and lower MDD; rejects <30 trades, >=50% drawdown, weak exposure, or low development return. Stored score is used ONLY for cheap shortlist.
- For each shortlisted candidate, `AcademicMCPCheckpointService._choose_counted_generation_portfolio` reconstructs original typed plan and counted StrategyIR, then replays its immutable signed S2 audit, full costed trades, closed trade count, measured return and MDD. S7 sidecar provenance hash is also checked.
- Selection uses the **non-dominated Pareto frontier** (return up / drawdown down), then different return, return-vs-risk, defensive objectives. Deterministic rotation across independent verified effective signals is evidence-hash pinned. A candidate failing the replay gate is never promoted.
- New `source_kind=COUNTED_GENERATION` handled by the existing gateway's verification and StrategyIR materialization path without changing old S7-child or legacy lineage protocols.
- Enabling parent_portfolio_v2 is **explicit**, default false. This is research-development only, **NOT a new GPT-per-generation autonomy system**, not OOS certification and not live order capability.

## P1 clone dry-run (no production writes)
- `python -m scripts.audit_parent_portfolio_v2` clones 3 SQLite DBs with SQLite backup, executes selection, pins/replays in temporary DB, compares production evidence digest before/after, writes an ignored JSON evidence report.
- G452 clone shortlist included G248, G192, G431. Eighteen shortlisted strategies had signed S2, S7 and costed fill/metric replay verified. Pareto multi-objective lanes selected source generations `[248,192,68]`; first simulated next generation G453 selected the defensive G68 lane and full replay succeeded.
- This **is not a new committed G453 generation** and should not be labeled 453/453. Original session stays 452/452.
- Unit tests: `tests/research/test_parent_portfolio_v2.py`. Existing selection test suite keeps original defaults unchanged.
- Some older archived integration tests rely on `/shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory/state/moon-http/research/audits/phase1-20261017-1950/snapshot-manifest.json`; those fail in this worktree because the historical external snapshot is absent. This is a fixture installation issue, not a pass.

## P1 isolated counted generation end-to-end — PASS

- Harness: `.venv/bin/python -m scripts.test_clone_g453_parent_portfolio_v2`.
- Cloned all 3 original SQLite files via backup API, validated DBs, extended **clone** from G452 to G454 (2 generations), reused the production deterministic GPT-designed policy but routed its entire service connection and progress log to the cloned session.
- Pinned full-fill replay of defensive G68 for counted G453: development return **+73.0338%**, MDD **27.9092%**, 103 closed trades, complete S2/S7 evidence.
- Pinned full-fill replay of return leader G248 for counted G454: development return **+27.9604%**, MDD **41.5825%**, 208 closed trades, complete S2/S7 evidence.
- The transition **G68 → G248** was verified from `inherited_parent.source_generation`, signed parent selection hash, full-fill child StrategyIR, the prior generation's evidence-hash link, and independent stored S7 reports for each.
- Clone completed `454/454`, exactly 454 experiment reports (counted G1..G454).
- Production retained **452/452** generations with identical full original evidence-chain digest `e27c586ccda974438ca7d3ae7c0c2471e935bdaef1aa8dcf446eab1103a8fdf9`; production sqlite integrity check OK.
- Full cloned trace/result summary was saved separately at `state/moon-http/fresh-20261021/p1-g453-g454-clone-e2e-result.json`.
- The clone test is NOT live trading, actual GPT reasoning per generation, sealed independent OOS, or evidence of improved return. It uses the same reused DEVELOPMENT_NON_PIT sample as G452.
- A first single-generation harness attempt committed G453 successfully but its final assertion expected `latest_controlled_experiments` in the closed-session GET response; fixed the harness to audit the persisted S7 report DB. The corrected two-generation run exited 0.

## Remaining gates BEFORE approving new academic batches
1. Clone G453/G454 end-to-end counted generation was **completed**; next is opt-in wiring for a *new* isolated campaign, with an explicit immutable configuration flag; keep the original production controller default unchanged.
2. Integrate S7 successor candidates alongside direct counted candidate portfolio, avoid using observed 2026 holdout in selection; baseline (existing S7) and new path must remain comparable.
3. Broaden StrategyIR/risk/regime and actual GPT planning log (P2/P3): not implemented.
4. Independent multi-vendor PIT audit, prospective sealed OOS (P4): not implemented.
5. Run 20→50→100 clean A/B generational tests with fixed backtest budget and fixed data split (P5): not started.

## Safeguards
- Existing session `G452/452` evidence hash and counts preserved.
- No OOS used for candidate optimization; latest Yahoo 2026 holdout is *spent* and remains separate.
- No reduction of fill, cost or risk-review gate.
- New parent lane exploration does not establish profitability, nor authorize broker orders.
