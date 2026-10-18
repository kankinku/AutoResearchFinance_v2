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
