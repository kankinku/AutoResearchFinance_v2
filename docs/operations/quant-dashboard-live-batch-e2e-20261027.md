# Quant bounded batch / dashboard live-refresh E2E — 2026-10-27

## Scope and acceptance
Stage: T4-DASHBOARD-BATCH-LIVE-SMOKE, Q06/Q08/Q09/Q15–Q17/Q20. Goal: verify real *running* bounded research generations appear in the newly deployed read-only dashboard API and finish in a coherent final status. This is not GPT-authored multi-step evolutionary research, does not change product scope, and does not authorize trading. Existing V05→T4→V01–V04→V06→V07 remains the product sequence.

## Execution
- Batch/job: `317e9ce793814ab1b132d92fbda2b940`, research run `6527f57ff32545feb6ce3af28ca70ca9`.
- Requested 10; status `COMPLETED` at `2026-10-27T03:37:30.026505+00:00` (12:37:30 KST). `stopped_early=false`, `error_code=null`, `unexecuted=0`, `orders_enabled=false`.
- `mean_reversion` fixed-parameter search, 8 proposals per generation, deterministic random seed 20261028; new parameter grid variation to exercise the worker and the dashboard, not for performance-optimization claims.
- Validity: historical 2020–2025 QQQ development bars, PIT/as-of corporate-action proof unverified, sealed OOS not measured; these are not investment OOS results. Actual model adaptive replanning 0 generations.
- Results: 70 unique evaluated candidates, 10 duplicates skipped, all 70 rejected, 0 successful promotions, 0 duplicate-only generations; gate evidence showed 70 annual-trade-count and 70 validation failures, 68 robustness failures. Counts overlap.

## Actual live web status evidence
- New dashboard endpoint `http://127.0.0.1:8082/api/research-batches/latest` checked with `Cache-Control: no-store` about every two seconds during the real batch. Raw compact source sample file (ephemeral only): `/tmp/quant-batch-dashboard-live-20261027.jsonl`.
- 13 HTTP 200 samples all in the correct newly created batch. Observed live progression: 3/10 (22 candidates) -> 4/10 (30) -> 5/10 (38) -> 6/10 (45) -> 7/10 (51) -> 8/10 (56) -> 9/10 (63) -> `COMPLETED` 10/10 (70). **Eight distinct generation-count states**, 0 query errors. At each sample `checkpoints_consistent=true`.
- Final web API output matched MCP batch-status and final batch report: id exact, 10/10, evaluated 70, duplicate 10, rejected 70, promotion 0. Stored generation history and completed count match.
- Existing GPT academic API source still session `14626d55`, 83/100, proof chain valid; existing `cycles.sqlite` sha256 unchanged versus before live experiment: `4294635268f6d1cff867c081413730a1793edf808d00a864082447d6ccd34f0b`.
- Nginx unauthenticated `/academic/` returned 401; OAuth and orders untouched.

## Verification and limits
- Browser DOM polling fixture exercise (2/10 -> 10/10) PASS (`node tests/dashboard/bounded_batch_browser_smoke.cjs`). Relevant Python regression test subset 5 PASS. Dashboard service was already deployed and needed no code change or restart in this step.
- Real HTTP back-end status changes are confirmed; actual end-user authenticated browser UI rendering was **NOT RUN**. Do not claim the real DOM displayed transitions without observing it.
- This verifies correct monitoring, not generation-by-generation model autonomy or realized strategy improvement. The existing academic GPT checkpoint remains `AWAITING_DIAGNOSIS` despite the independent bounded batch completing.

## Next
Investigate the actual LLM plan -> backtest -> failure-diagnosis -> next-generation plan/parent promotion flow under the frozen T4 goal. Keep independent OOS/PIT and live trading blocked until their respective conditions are met.
