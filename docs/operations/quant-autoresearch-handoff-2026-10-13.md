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
| P1-6 | GPT per-generation research director | Durable external GPT checkpoint workflow implemented: start/get/submit tools with atomic token CAS, immutable predecessor Evidence lineage, frozen dataset and gate floors, fail-closed interruption; synthetic two-generation integration PASS | Verify authenticated real QQQ two-step research; no unattended server-side GPT calls are implemented |
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

## Rescue release acceptance (2026-10-13 KST)

- Commit `4a3dd368d12e92d7d1315dbbbd9e33d1f1ad748f` pushed to `docs/mcp-phase3-5-1-state-inventory`.
- Full `pytest`: **1,114 passed**; Ruff all pass; Mypy **192** source files pass; Git worktree clean after commit.
- Restarted only `integrations.chatgpt_mcp_http` with zero running/queued research batches. Both local and proxy MCP endpoints recovered from short startup 502 to expected unauthenticated **401**. Existing **2 OAuth clients** retained.
- Authenticated connector: `get_workspace_status` reported `READY`, `get_research_evidence` reported `OK`, **10 runs**, `orders_enabled=false`. Historical research candidate statuses remain **87 REJECT and zero genuine NEAR_MISS**; no realized Rescue promotion claimed.
- Rescue new operational implementation is deployed; only *synthetic isolated tests* verified the rescue mutation path. Next hard gate: evaluate a **real, evaluator-labeled** NEAR_MISS and verify its fully recorded subsequent rescue application without changing evaluator acceptance thresholds or touching sealed OOS.

## P1-6 GPT-guided checkpoint protocol (2026-10-13 KST)

- Implementation: `application/gpt_guided_research_service.py` exposes a **durable, explicitly externally directed** session journal in `state/.../system/gpt-guided-sessions.sqlite`. Client-facing `start_guided_research`, `get_guided_research`, `submit_guided_generation` tools added only to ChatGPT MCP plane; legacy public API retained.
- State progression: `AWAITING_GPT` -> atomic token-claimed `EXECUTING` -> `AWAITING_GPT` (new one-time token) or `COMPLETED`, with interruption fail-closed. No automatic local LLM calls. External ChatGPT must choose next typed ResearchIntent and call submit **each generation**.
- Session pins original market Parquet file hash, dataset identity, development zone, method, count, random seed progression and acceptance thresholds. No subsequent proposal may override them; floor is canonical policy (30 full trades, 30 annual trades, >= 0.10 QQQ CAGR delta). Inputs must be canonical project files, model operations validated as Strategy IR.
- Before next generation, prior completed immutable Evidence research_run_id is passed to existing `ChatDirectedResearchService`. Result generation, attempt identity and all candidate dataset hashes are reconciled against immutable verified Evidence before checkpoint is committed. Checkpoint surfaces bounded failed gate names, not raw market rows or sealed OOS data.
- Concurrent duplicate/stale tokens are rejected by SQLite conditional update. Failed evaluator marks session `INTERRUPTED`, with no silent retry; ambiguity after hard process failure requires operational reconciliation (remaining P2 work).
- Verification complete: **1,120 full Pytest PASSED in 271.56s**; Ruff PASS; Mypy 193 source files PASS. Six new guided protocol tests verify two-step GPT direction, checkpoint continuation across instances, stale-token blocking, data mutation refusal, policy floor protection and evaluator-failure interruption. SDK, stdio, OAuth audit, launcher tests updated for 21 advertised MCP tools.
- **Scope limitation:** this is a client-controlled research director protocol. The server does **not** initiate an LLM call or orchestrate ChatGPT in the background; such unattended scheduling cannot be claimed. The development dataset is not independent sealed OOS; no strategy profitability claim.
- Next: GitHub push, restart Quant-only MCP with zero running batches, authenticate tool discovery and execute a real QQQ 2-generation GPT-directed Paper demonstration without changing gates. Record whether live connector input schema is refreshed; do not claim a QQQ generation run unless actual immutable Evidence exists.

## P1-6 release & real QQQ acceptance (2026-10-13 KST)

- Source commit `e778de2c72a046179e0d6614c3425cf99e648aad` pushed to `docs/mcp-phase3-5-1-state-inventory`; clean worktree. Quant-only MCP restarted after zero active batches, OAuth local/gateway both returned expected unauthorized 401, and authenticated connected `get_workspace_status=READY`, `get_research_evidence=OK`, `orders_enabled=false`.
- Genuine development QQQ 2-step directed session ID `6f67cec0337b4975ab5d855ff1383f7d`, requested 2 generations. Start created no Evidence and status `AWAITING_GPT`; each step required a fresh token. First explicit hypothesis `mean_reversion` ran and recorded `research_run_id=f03fda972deb4769b4a7ab14152efff4`; failures: annual_trade_count, fast, full, qqq_cagr_delta, robustness, validation.
- GPT chose structurally different, registered `strong_close` IBS strategy for the second generation based on failures; completed `research_run_id=50342555ae6046cc9328eb013202a070`. Failed gates: fast, full, qqq_cagr_delta, robustness, validation; annual_trade_count did not fail. Session status `COMPLETED` 2/2, checkpoint token consumed, `orders_enabled=false`, verified previous Evidence link. Connected authenticated `get_research_evidence` confirmed completed 2nd run, prior-run ID and 0% candidate pass rate.
- No independent sealed OOS, positive-return claim, true causal attribution or order activity. The GPT director is **externally driven by client calls**; a model was not autonomously invoked in the server process. Existing ChatGPT connection may cache previous 18-tool plugin schema, so end-to-end **new tool direct call through the ChatGPT plugin** requires tool metadata refresh; acceptance was through the operating Moon dispatcher with authenticated connected Evidence re-read.
- Remaining: source-aware semantic deduplication across externally directed generations; safe reconciliation for ambiguous crashes (current status stays INTERRUPTED); plug-in metadata refresh acceptance; PIT-quality market source verification and UX/host testing. Never silently replay a checkpoint after partial evaluation.
