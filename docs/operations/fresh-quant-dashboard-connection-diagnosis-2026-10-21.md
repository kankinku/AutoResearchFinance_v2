# Fresh Quant dashboard connectivity — midrun operational diagnosis (2026-10-21 KST)

## Observed actual environment (read-only)

While user-requested *additional 50 new independent generations* continue on fresh session `3eb928535edd4a3c90eea0e937e67973` (new G3~G52 after existing G1~G2):

- `http://127.0.0.1:2999/health` HTTP 200: **Moon only**, not Quant.
- `http://127.0.0.1:2999/quant/mcp` HTTP **404**: existing Quant ingress missing.
- `http://127.0.0.1:8787/health` **connection refused**, no Quant backend listener.
- `http://127.0.0.1:8081/` **connection refused**, no dashboard listener or exposed Docker port mapping.
- Runtime process `.venv/bin/python -u state/tools/fresh_batch_controller_20261021.py --max-new 34` is **running** independently, persisting study to private academic SQLite; it does **not** start a web service, dashboard, nor authenticated remote MCP. As of **2026-10-21 03:50 KST read-only checkpoint**, committed **G32/52** (30/50 additional), phase `RUNNING`, no orders and no independent OOS, hash chain PASS.
- Effective nginx configuration includes `/shared/nginx/routes.d/*.conf`, but `/shared/nginx/routes.d/` has **zero** installed Quant routes. Supervisor's included path remains pinned to `/shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory/deployment/moon/quant-mcp.supervisor.conf`; that original runtime folder now contains only `.venv` and corresponding old Supervisor config is unavailable. No `/shared/moon-services` Quant startup hook.
- A checked-in root `dashboard.py` Streamlit application **exists**, but loads `STATE_DIR = repo/state` and traditional `mode.json`, `champion.json`, `frontier.json`; it **does not directly consume** `state/moon-http/fresh-20261021/research/academic-gpt-checkpoints` (new canonical session G3+ Evidence). Launching that app unchanged would show stale/wrong state rather than automatic connection. `runtime/dashboard_supervisor.py` also targets separate local `8080` paper CLI; it does not configure a live new Quant MCP dashboard or forward HTTP access.
- Old operational docs `docs/operations/quant-moon-fixed-url-oauth.md` distinguish manual backend `nohup scripts/run_quant_moon_http.sh` and future Supervisor-image rebuild *not validated*; there is **no proven startup wiring** for the new separate G1~G52 session. The original Quant OAuth SQLite and original keys remain unavailable; do not regenerate silently.

## Key distinction

**Local research working does not imply dashboard or MCP connection working.** This is a deployment / backend / data adapter integration gap, not evidence of a user changing Docker. The research run has its own SQLite but no continuously served HTTP dashboard bridge. We neglected to provision a working dashboard for the newly isolated session.

## Midrun evidence snapshot 2026-10-21 03:50 KST

- New session count **G32/52**, additional **30/50**.
- Additional G3–G32 average strategy total return **+7.8285%**, average full-sample MDD **31.3573%**, positive **16/30**, negative/nonpositive **14/30**.
- Overall G1–G32 average return **+11.2096%**, MDD **30.8025%**, positive **18/32**.
- Max raw return G6 **+95.5479%**, but **8** closed trades and **43.9780%** MDD: **insufficient-for-review**, not a valid champion.
- Best of 30+ closed-trade *counted generations* remains G2 **+68.2234%**, MDD **20.1421%**, **71** trades, exposure **55.6366%**; QQQ development price-only costed buy-and-hold **+187.7724%**. G32 last return **−12.5669%**, MDD **13.2980%**, 123 trades, exposure **8.1565%**.
- Existing new-session Evidence chain `previous_evidence_hash` verified all G1–G32; execution `orders_enabled=false`, independent OOS `false`, authenticated real GPT model connection `false`.
- **Important truth in progress log:** G1–G3 locally GPT-authored; G4+ batch controller is explicitly `DETERMINISTIC_GPT_DESIGNED_POLICY_NOT_PER_GENERATION_LLM` (fixed rule search that submits programmatic typed plan and diagnosis). These generations are real canonical costed simulator/S7 Evidence but **NOT 30 independent GPT decisions and not verification of GPT autonomy**. Do not say "50 GPT-directed generations" unless model calls explicitly proven.

## Safe dashboard remediation requirements (not completed)

1. Define a read-only **current session Evidence adapter** that fetches from `AcademicMCPCheckpointService.get(session_id)` and separate S7 reports rather than old dashboard `state/champion.json`. Fields: latest target/current, state/heartbeat, elapsed average/ETA, per-generation returns and MDD, 30+trades strategy eligibility, exposure, costs, QQQ buy-and-hold, parent strategy hash, S7 result, missing GPT authorization, proof head.
2. Start a separate localhost-only HTTP/UI service under an audited process supervisor and persist startup hook in correct mounted path. Do not manipulate existing active research batch or reset its SQLite.
3. For Windows browser access, Docker port mapping must exist OR use already verified access-controlled nginx path; never publish SQLite/OAuth or no-auth dashboard through Tailscale Funnel. Preserve original URL and OAuth identity; do not replace protected `/quant/mcp` with an unauthenticated proxy.
4. Validate real browser URL/HTTP response, updated generation values, auth, and automatic process restart. Until those are verified, **dashboard remains NOT_CONNECTED**.
5. For true GPT autonomy, restore verified model-tool loop using existing credentials or an explicitly separate authenticated endpoint; deterministic rule generation does not satisfy original 20Q goal.

**State:** diagnosis complete; dashboard not repaired. Current research batch running. Recheck latest Evidence and no actual future completion promises.
