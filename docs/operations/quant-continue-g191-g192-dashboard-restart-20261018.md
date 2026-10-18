# 2026-10-18 — Moon academic monitor auto-start recovery and genuine GPT G191–G192

## Scope and boundaries

- Approved stage: **T4 (S4/S5)**, Q02/Q06/Q09/Q15/Q16/Q17/Q20: continue real authenticated ChatGPT MCP research with checkpointed plans, measured backtests, LLM-produced diagnoses, controlled S7 tests, and immutable evidence. T4 dashboard availability is an operations prerequisite. Not a manually optimized single QQQ strategy.
- Original +100 request: global 181→281. Earlier genuine G182–G190 = 9/100; this turn continued from **190/300**, completed **G191 and G192**: **global 192/300**, **11/100**, **89 remaining**. Session `2ba41aaeacd547319cfbf7e6f266ad11` is local 92/100, AWAITING_PLAN. Original 100-generation session retained.
- Existing `/quant` MCP URL/OAuth, ChatGPT MCP provider choice, canonical QQQ development dataset, historical evidence, and **orders_enabled=false** unchanged. PIT/independent OOS/economic alpha NOT approved or demonstrated.

## Academic monitor crash/restart repair

- Host Supervisor config already had `[program:quant-academic-monitor]`, `autostart=true`, `autorestart=true`, but launcher `scripts/run_quant_academic_monitor.sh` required source SHA `2251d493...`, while referenced worktree HEAD had moved to `b2a8df5...`; it exited before binding port 8085. The proxy stayed on 8085, making auth-protected page fail behind login.
- Repaired ONLY the monitor launch script in existing deployed operations worktree (`AutoResearchFinance_v2-phase3-5-1-inventory`) by pinning immutable clean dashboard checkout at `/shared/moon-workspace/AutoResearchFinance_v2-academic-dashboard-inheritance-20261017`, SHA `8e7d17ef4f66f3cda9a4cf42a4ce3c145a317e71`. Supervisor config already enabled auto-start and auto-restart. Research/OAuth service launcher existing unrelated uncommitted edit left untouched.
- Added pin/autostart regression test (`tests/runtime/test_academic_monitor_autostart_pin.py`): **2 PASS**. Ruff file **PASS**; Mypy file **PASS**; bash -n **PASS**. Source committed and pushed branch `fix/academic-dashboard-auto-restart-20261017`, SHA **`f0a4769`**.
- Real Supervisor `SIGHUP` reloaded configured processes: independently owned dashboard process bound to `127.0.0.1:8085`, research MCP remains `127.0.0.1:8787`, HTTP `/api/academic/overview` **200**, same-session evidence readable, public unauthenticated `/academic` **401**, `/quant/mcp` unauthenticated **401**, orders disabled.
- **NOT RUN:** Windows host operating-system reboot, Docker Desktop autostart after reboot, entire repository pytest suite, independent PIT/OOS/profit test. The dashboard automatically comes back with a running container/Supervisor; the research model does NOT automatically perform unprompted ChatGPT plan/diagnosis calls.

## Real GPT research added

| Global G | Costed development return | Full MDD | Closed trades | Exposure | S7 outcome |
|---|---:|---:|---:|---:|---|
| 191 | +53.9520% | 7.7818% | 33 | 32.626% | Vote-score exit <=0.64→0.38 lowered completion count from 33 to ~32; **RETURN_WORSE**, -2.0637 percentage points return, 2 retrospective drawdown windows worsened |
| 192 | +63.4794% | 7.6761% | 34 | 31.366% | Parkinson entry cap 0.000088→0.000065 under early-exit 0.80: **RETURN_WORSE**, development return -22.9114pp, 34→29 trades, 3 retrospective drawdown windows worsened |

- Both G191/192 are actual authenticated ChatGPT typed `submit_algorithm_plan` followed by GPT diagnosis grounded in supplied actual trade/decision IDs, then `submit_algorithm_diagnosis(require_signal_change=true)` and S7 stored evidence; not server-scripted fake generations. Global 191 original generation hash `86db509173415f61d49ef931f8e9b96f645f992bb10ac54b7d1f89bcca696cd6`, controlled S7 hash `2053a3179e2b933cb50ce9a84bfc54b5ebd19a8234a19af9e4983ed838a13fb8`.
- First staged G192 alternative (remove outer extra SMA gate) produced +63.4794% aggregate results but its diagnosis request failed before counting the generation (`TOOL_EXECUTION_FAILED`). Explicit `resume_algorithm_research` recovered 91 completed originals and reset to AWAITING_PLAN; then retried a distinct early-vote-exit plan and completed actual G192. **One failed interrupted attempt ≠ a generation**; all earlier counts and evidence preserved.
- Development QQQ costed buy-and-hold comparison earlier provided +187.7724% on same retrospective 2020–2025 sample; selected inherited strong parent +63.4794% / 7.6761% full MDD, **not a proven forward return**. Identical strategy aggregate metrics across interventions do not prove identical fill traces unless separately verified.

## Next frozen work and blockers

1. Complete session G193–G200 by authenticated GPT plan→S2 audit→diagnosis→S7; verify 100/100 local evidence. Current AWAITING_PLAN; not autonomous in a background worker.
2. Verify secure **cross-session selected-parent StrategyIR, canonical trace, memory and immutable hashes** inheritance before G201–G281. Starting a new session at baseline would break requested continuity; do not fake completion with provider-free scripted generations. Current target remainder 89 genuine generations.
3. Preserve original work order T4→external V01–V04 PIT/OOS as available→V06 paper-only→V07 independent GO/NO-GO. No third-party paid model API or trading/secret changes.

Note: Status ledger + this report live on the separate docs branch, intentionally not on the production-pinned service checkout. The file documents a completed current-turn intervention, not unattended scheduled follow-up.

## Addendum — genuine G193–G194 and uncounted G195 checkpoint interruption

This report's **latest** counted state supersedes the preceding G192 interim count: authenticated GPT MCP completed G193 and G194 through valid Plan→real S2 audit→LLM diagnostic with trade IDs→measured S7. **Current global 194/300, requested add-100 progress 13/100, remaining 87**. The original active session is local 94/100 (6 slots left), `AWAITING_PLAN`; all 94 immutable counted generations still present.

| Global generation | Real QQQ development total return | Full-period MDD | Closed trades | Exposure | Matched S7 comparison |
|---|---:|---:|---:|---:|---|
| G193 | +63.4794% | 7.6761% | 34 | 31.366% | Replace the SMA-confirmation gate with 252-day momentum under removed outer Parkinson filter: **RETURN_WORSE**, -1.8948 pp net return, 34→33 closed trades |
| G194 | +61.5846% | 6.6608% | 33 | 30.172% | Ablate the added 252-day momentum confirmation: **RETURN_BETTER**, +1.8948 pp net return, 33→34 trades, revealing a return-vs-MDD risk tradeoff |

- G193 original generation evidence SHA `871138cac034bc666895f0a7cf039010ace50ea6853702be1e649db860d34c91`.
- G194 original generation evidence SHA `c5750d8a73ff0129abc6504e10ae0c422d0f8644655714fd25ab330be2956618`, G194 S7 controlled-record SHA `b93ffbd79c4951cbcab8f64b81e5142e5662fcdb2a3e5e5597396f4fcbcb056c`.
- An attempted **G195 stage** adjusting vote-score exit to 0.70 obtained a measured S2 (+53.9520%, MDD 7.7818%, 33 trades), but its S7 proposal at a narrow 0.715 threshold failed with `TOOL_EXECUTION_FAILED`, flipping the checkpoint to `INTERRUPTED` before the generation could be committed. The explicit authenticated `resume_algorithm_research` call restored the checkpoint to `AWAITING_PLAN` at exactly **94/100** and retained prior hashes. G195 is **not counted**. The service currently treats certain failed S7 paths as interrupted rather than returning a clean structured no-op rejection; review needed before expecting unattended operation. The cause is not definitively diagnosed; further silent retries of the same failed proposal are not warranted.
- The dashboard remains Supervisor-managed and readable with `orders_enabled=false`. Cross-session lineage of the actual selected champion + verified negative learning is still unproven. Completing all remaining 87 via model-free synthetic loops would violate the requested GPT-driven research definition.

**Updated next work:** fix/readably classify S7 interruption without losing counted evidence, finish 6 GPT-validated generations to global 200, then establish authenticated carryover G201–G281. The auto-start monitor is complete, but automatic GPT research generation is NOT implemented or verified. No new orders or paid model API calls.
