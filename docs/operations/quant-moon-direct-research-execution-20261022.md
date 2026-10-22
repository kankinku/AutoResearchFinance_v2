# Moon direct Quant research — measured GPT-guided clone test (2026-10-22 KST)

## Executive finding / cause

The failure to make progress was **a control-path conflation**. The existing Quant OAuth MCP endpoint is absent (`/quant/mcp` HTTP 404 and localhost port 8787 down), **but the trusted Moon connector can execute the local Python academic checkpoint service and fully costed QQQ development backtester**. A working original Quant OAuth database is **not required for this particular execution path**.

Caution: `scripts/run_academic_autopilot.py --execution-mode mcp` only outputs `USE_EXISTING_CHATGPT_MCP_CONNECTOR` instructions, never invokes a model. The optional `--execution-mode openai-api` requires explicitly confirmed paid model calls. This run instead used **ChatGPT assistant-authored typed decisions submitted directly using Moon**. It is not a standalone unattended 10/100-generation model provider loop. Core T4 full proof remains incomplete.

## Scope and immutable boundary

- Read-only input: separate **development-only** academic G452/452 ledger under `state/moon-http/fresh-20261021/research/academic-gpt-checkpoints`; original last evidence hash `e620bfecb8bd5359731834d87064c13c1a3a32337da1d946a3f132cf9d79b337`.
- Clone: `state/moon-http/fresh-20261021/moon-invoked-live-g453-20261022/academic-gpt-checkpoints` via SQLite backup of `cycles.sqlite`, `gateway.sqlite`, `catalog-s6-v2.sqlite`. All 6 source/clone databases pass SQLite integrity checks.
- Same QQQ **1,508 daily reused development bars, 2020-01-02 through 2025-12-31**, dataset hash `f637bcf0a8098aa13ed1758308086e8bfb4c3ade264ecb003ae741095ba95f9e`. This is neither certified PIT nor sealed independent OOS.
- Frozen budget: max child MDD **30%**, max MDD increase **15 percentage points**, min **30 closed trades**; canonical next-open fill replay with transaction costs, S7 evidence, no live orders.
- Original main G452 count, evidence hash, and source DBs **unchanged**. Development clone is NOT the missing legacy G350+ operational lineage, and does not advance original official T4 via the connected Quant MCP.

## G453: actual ChatGPT-plan + canonical backtest + assistant diagnosis + real S7

**Prerequisite rejection:** author proposed adding OR exit `plan_regime <= 0.5` to audited G68 parent. P3 `DEVELOPMENT_SIGNAL_EQUIVALENCE` rejected it against 1,508 development bars. Generation did **not** advance; one tamper-evident `p3_semantic_rejections` row was retained.

**Accepted candidate H2:** retain G68 entry (plan_entry > 0.5 and previous_range_breakout > 0.5), and EMA bearish exit `ema_direction_20 <= 0.5`. Add one OR exit `plan_vote_score <= 0.25` to test whether strong consensus deterioration controls drawdown without the excessive churn previously seen at `<=0.5`. This is a genuine changed strategy/fill trace; model authored proposal and diagnostics in the present user-requested ChatGPT↔Moon interaction, not scripted generation fixtures.

| Metric (same development period, costed) | G68 audited parent | G453 measured child | Child minus parent |
| --- | ---: | ---: | ---: |
| Total return | **+60.6753%** | **+30.8578%** | **−29.8175 pp** |
| Max drawdown | **15.9543%** | **21.3961%** | **+5.4418 pp** |
| Closed trades | **35** | **45** | **+10** |
| Canonical fill events | **70** | **90** | **+20** |
| Market exposure | **45.4907%** | **43.4350%** | **−2.0557 pp** |

Child passed the unchanged P2 gate (MDD below 30%, increase below +15 pp, trades >=30). S2 sample losing trade `b820981b805d-T-000032` was approximately −650.54 net. The candidate's lower performance is consistent with premature exit and altered re-entry/position sizing, but causal inference and actual fee-vs-market decomposition were **not** established by these aggregate results.

**GPT diagnosis and S7 single-rule ablation:** remove only newly added `exit.conditions.1` while keeping original EMA exit and unchanged entry/costs/market. S7 reran controlled next-open engine and measured return **+60.6753%** compared with child **+30.8578%**, `total_return` delta **+29.8175 pp**, 70 vs 90 fills, status `DIRECTION_MATCHED_DEVELOPMENT_ONLY`. S7 measured total execution costs **753.8225** versus child **837.8051** development cash units, with changes in timing and position quantities. It does **not** prove every return difference is caused by fees; the total return difference includes changed market exposure/trade execution.

**Counted G453**: `453/453 COMPLETED` before the subsequent explicit extension. Evidence hash `09d92d53a2df013edaf2becc5b7e576288b76e42aeddcfb253f795798e91636b`, previous hash equals preserved source G452 `e620bfec...`; S7 report record hash `a0d65ead6800f7a06ead5625267e3db2ca0e83f758cb8cb20ce29b260e023158`. Signed local summary at `moon-invoked-live-g453-20261022/verified-g453-result.json`, manifest hash `1d8d86c2bc5995cdaa45a452436257f9641f5045a98af444b0650b1cca0643c4`. Local SQLite and decisions are ignored by Git and never pushed.

## G454: continued research and two genuinely rejected proposals

Extended same clone **G453/453 → target 454** (new planning checkpoint, no repeat/overwrite). Audited parent-selection rotation chose different **G192**: development return **+168.3699%**, MDD **26.0446%**, closed trades **36**, exposure **85.2785%**.

1. **H1:** add EMA-direction weakness exit to G192 reclaim strategy. Executed P2 precommit canonical replay: **MDD 36.94%** and **127 closed trades**, up from parent MDD 26.04%, 36 trades. **Rejected by max 30% MDD.** A stored `precommit_risk_rejections` row proves the fail-closed decision; **no G454 counted**.
2. **H2:** following rejection, preserve exit and add long-term `dual_sma_trend_50 > 0.5` entry confirmation to reduce G192's high exposure. The inherited S2 fill/decision auditor raised **`ResearchCatalogError: inherited fill has no valid close decision`** before risk evaluation. That error means the independently reconstructed decision trace failed to reconcile with a canonical fill; it **may indicate an auditor–engine parity gap for this particular mutated IR**, not proof that the entire backtest engine is broken. No candidate accepted, no G454 counted. Needs minimized deterministic reproduction and trace-index comparison before any fix, keeping protected canonical engine unchanged.

**Final persisted local clone state:** **453 / target 454**, `AWAITING_PLAN`; G453 immutable evidence preserved; one P3 semantic rejection, one P2 risk rejection, and two accepted G453 plan/diagnosis submission receipts. G454 is **blocked at a safe planning checkpoint**, not running in the background. Canonical source **452/452** is unchanged.

## Diagnosed engineering facts and next gates

- **Quant computation works through Moon**: candidate generation, schema/semantic checks, deterministic costed backtest and trace, diagnosis, S7, immutable evidence, safe resume. Earlier “can't run Quant until old OAuth restored” was too broad and wrong for this local workflow.
- **Actual missing piece for ongoing autonomous T4**: a model-driven repeated decision controller using an authorized model interface over this Moon-accessible service, with per-generation evidence-linked prompts/receipts and bounded retry/resume. Merely repeating deterministic controller candidates or injecting scripted fixture plans is not independently GPT-authored research.
- **Concrete newly surfaced issue:** `audit_inherited_decisions` rejects a G192+SMA-entry variation on fill/decision mismatch. Verify actual offending bar, market and decision timeline, distinguish unsupported combination from a real mismatch, and add regression coverage before changing any executable engine.
- Retain Q01–Q20 scope, V05 → T4 real 10/100 generations → V01–V04 PIT/OOS → V06 paper-only → V07 GO/NO-GO. No new OAuth, URL, secrets, credentials, Docker, live trading or independent OOS actions performed.

## Validation and non-goals

Original and clone SQLite integrity **PASS** (3/3 databases each); original G452 count/hash and clone G453 chain link **PASS**; G454 remains `AWAITING_PLAN`; no source changes. This is a completed **local bounded measured test**, **not** a connected original Quant MCP activation, fully autonomous model API experiment, new approved PIT data, or an economic production success claim.
