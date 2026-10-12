# Quant Autoresearch — 2026-10-13 continuation handoff

## Source of truth / safety

- Repository: `kankinku/AutoResearchFinance_v2`, branch `docs/mcp-phase3-5-1-state-inventory`.
- Runtime checkout: `/shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory`.
- Live ChatGPT endpoint: `https://project-moon.taild689f9.ts.net/quant/mcp` (OAuth-protected, unauthenticated HTTP 401 is expected).
- `orders_enabled=false`. Never permit live orders, promotion, sealed OOS access, gate relaxation, or bypassing immutable Evidence from the research worker.
- Strategy IR is source of truth; `docs/architecture/quant-autoresearch-architecture-v1.0.md` and protected evaluator/data paths are not to be modified casually.

## Eight-item roadmap / current acceptance

| # | Item | Evidence / current state | Next gate |
|---|---|---|---|
| P0-1 | Mixed adaptive QQQ smoke | Completed 3/3, 2 novel applied hypotheses, unique semantic hashes, no duplicates | Complete |
| P0-2 | Immutable Evidence trace | Validated generation-to-attempt reference, rejected gate trace, novelty, deduplication, no orders | Complete for exercised batches |
| P0-3 | 20-generation study | Completed 20/20; 41 unique evaluated candidates; 19 duplicate candidates skipped; 4 replanned/applied hypotheses; all REJECT | Interruption and *actual resume* acceptance still unverified (current worker has cancel/restart but no same-batch resume guarantee) |
| P1-4 | Structure evolution | Exit-threshold change and RSI combined entry tested; 10-generation smoke applied both | Broaden operator/indicator menu while preventing overfitting |
| P1-5 | Crossover / Rescue | Crossover live QQQ proof complete. Rescue implementation now stores strictly gate-qualified NEAR_MISS IR snapshots in immutable Evidence, rebuilds replayable candidates by matching complete run / evaluation attempt / comparison key / dataset / IR and semantic hashes, and offers last-resort EXIT crossover in adaptive mixed runs. Focused tests passed; operating Evidence currently has 87 REJECT and **zero real NEAR_MISS** | Run genuine NEAR_MISS operational acceptance before declaring complete; keep REJECT excluded |
| P1-6 | GPT per-generation research director | External GPT selected different IBS `strong_close` and SMA `golden_cross` hypotheses; both were actually evaluated and rejected. New optional predecessor run ID validation records GPT step lineage against immutable same-dataset Evidence | A fully automatic LLM-at-each-generation controller remains **not built**; design durable GPT checkpoint/intent handoff without local worker invoking LLM |
| P1-7 | Market data lineage & PIT | QQQ Tiingo raw 2020-01-02..2025-12-31, 1,508 bars; no duplicate/non-monotone timestamps, OHLC or negative volume anomalies; source is `revision_policy=latest`, raw/no verified corporate action reference | Acquire/reconcile independently PIT-valid source and verifiable split/dividend adjustments before OOS/performance certification |
| P2-8 | Integration UX & operations | OAuth MCP responds; preflight, batch status/report, per-generation Evidence connected. Fixed projection bug: legitimate completed 11/12 `SEARCH_SPACE_EXHAUSTED` was previously incorrectly flagged `INTEGRITY_ERROR`. Read-only projection now recognizes only final `NO_NEW_CANDIDATES` with no pending hypothesis | Post-deploy authenticated `get_research_evidence` returns OK; test interruption/recovery, Windows Docker host gate, 5-user workflow |

## Important research run records (immutable)

- 3 generations: `2d7e80aeb8a346f287408ae0219b54ea`; run `873fee00a0ff4365a2cfefe04782302a`.
- 20 generations: `a6cf8d419fa94791b750efdfec7c0d23`; 41/41 unique, all rejected.
- Structure smoke 10 generations: `72f2d4491ab64c0e80ba797aa1f56de3`; exit and RSI variants applied.
- Crossover request 12 generations: `9801e769bab54cb09e3cfdac3d5854e1`; completed 11/12 with search-space exhaustion, 10 unique evaluated.
- GPT-directed IBS attempt: run `86fb3257ee...` `strong_close`, 327 trades, CAGR -8.74%, annual trading criterion passes but rejected on other gates.
- GPT-directed SMA crossover attempt: run `9663645707ab48638b01404ce50872fc`, 35 trades, CAGR 17.49%, annual trade-count criterion fails (minimum full-year annual threshold 30).
- Results use development-only QQQ data and **do not imply out-of-sample profitability**. Comparisons between different strategy discovery histories do not prove a fair independent holdout.

## Current development changes / integration

- Evidence projection: recognize immutable legacy `COMPLETED` batch with contiguous generations and terminal `NO_NEW_CANDIDATES`, no pending hypothesis, as expected early exhaustion; remain fail-closed for incomplete or contradictory completion.
- GPT directed `run_research_step`: optional `previous_research_run_id` input for explicit across-run lineage; predecessor must be completed, checksum-verified and evaluated on the same market dataset; audit predecessor ID into next run Evidence settings. Never invoke a model from local workers. This is checkpoint lineage, **not** an autonomous model loop.
- Tests added for both positive and negative Evidence cases, and two externally authored linked research steps.
- Before release: run full pytest, Ruff, Mypy; push atomic commit; restart only Quant MCP while no research batch runs; confirm connected authenticated tools and no OAuth loss.

## Safe next actions (in priority order)

1. Refresh the ChatGPT connector's cached tool metadata so `run_research_step.previous_research_run_id` is exposed, then verify linked submission over authenticated MCP rather than only via the local dispatcher; GET of linked Evidence already works.
2. Rescue Evidence implementation exists and is test-verified; obtain a *genuine* NEAR_MISS under unchanged evaluator criteria, then accept the full run from evidence snapshot to reconstructed EXIT-combination and its recorded causal hypothesis. Synthetic tests must never be reported as a live near-miss result.
3. Introduce externally directed GPT checkpoint protocol (one proposal per verified generation, linked predecessor, typed intent, explicit fail-closed resume token). The existing detached `start_research_batch` is deterministic only; do not claim it already makes GPT calls.
4. Resolve PIT corporate-action data provenance and independent historical releases. No sealed OOS until that gate.
5. Complete resilience/host deployment/UX acceptance (restart, cancellation, interruption vs true resume, 5-users), preserving all state.
6. Update this document and test evidence each task/commit to carry work across ChatGPT sessions.

## Test results

- Focused Evidence/GPT integration tests: 21 passed.
- Static checks: Ruff pass; Mypy 192 source files pass.
- Initial full suite (before Rescue): 1,103 passed in 265.27s.
- **Rescue implementation full suite: 1,114 passed in 276.65s**, no failures (2026-10-13 KST); Ruff all PASS and Mypy 192 source files PASS.
- Rescue new tests prove qualified IR storage, immutable completed-run-only restoration, same dataset + comparison key, tampered hash/semantic reject, rejected/survivor/unvalidated exclusions, and a real executable structural crossover via a synthetic near-miss fixture. Operating Evidence status counts were **REJECT: 87, NEAR_MISS: 0**; no live Rescue hypothesis or profitability verified.
- Post-deploy Quant-only restart: success; protected MCP local and gateway return HTTP 401 without authorization; 2 OAuth client records retained; zero live orders.
- Authenticated connected `get_research_evidence`: status `OK` with existing legacy exhausted 11/12 recorded as `SEARCH_SPACE_EXHAUSTED`; no immutable event rewrites.
- Operating MCP dispatcher `run_research_step` predecessor-linked research: `064a8f1301704f138e9005e0151dd551` linked to `9663645707ab48638b01404ce50872fc`; one candidate evaluated and REJECT, orders disabled. Authenticated ChatGPT `get_research_evidence(research_run_id=...)` confirmed persisted predecessor link.
- Caveat: current connected ChatGPT client-side tool schema was cached without new optional `previous_research_run_id`, and rejected this new argument before sending it. Server schema and dispatcher are updated; refresh/reconnect plugin tool metadata in a new client session to expose the field directly. Do not claim the connected submission itself succeeded until refreshed.
