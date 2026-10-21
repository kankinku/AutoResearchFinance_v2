# Quant fresh research dashboard — secured live restoration, 2026-10-21

## Confirmed live access

URL: https://project-moon.taild689f9.ts.net/quant-research/

Use HTTP Basic username **research** and retrieve the randomly generated password only in your own Windows PowerShell terminal:

    docker exec project-moon-local /bin/sh -lc 'cat /shared/moon-workspace/AutoResearchFinance_v2-fresh-research-20261021/state/moon-http/fresh-20261021/dashboard-auth/dashboard-login.txt'

Never paste this credential in ChatGPT, docs, commits or logs. The HTTPS host is the preexisting Tailscale Funnel hostname, not a new Docker-published Windows port.

## What was broken

Moon basic MCP port 2999 healthy; original Quant MCP port 8787 and route /quant/mcp missing; dashboard 8081 was not started or configured. Existing Streamlit dashboard.py reads obsolete state/champion.json, not current research gateway/cycles SQLite. Root new isolated research session G42/52 had stalled at G43 AWAITING_DIAGNOSIS after the prior Python worker disappeared on container restart. The dashboard is an independent read-only app, not a repair of authenticated Quant MCP or the research worker.

## Remediation

- New source scripts/fresh_research_dashboard.py: minimal HTTP server on **127.0.0.1:8081 ONLY**, no third-party runtime dependency, SQLite URI read-only + PRAGMA query_only=ON, pinned session state/moon-http/fresh-20261021/session-id.txt. No research write, restart, registration, orders, tokens or OOS.
- Read cycles.sqlite and gateway.sqlite: exact completed/target G, phase, latest return/MDD/trades/exposure, all generation table/chart, evidence SHA continuity, eligible highest-return strategy requiring >=30 closed trades, QQQ development price-only benchmark, historical generation wall duration and last end date.
- Browser reloads /api/status every **5 seconds**, no browser-only fake progress/ETA and NO claim that research worker is running. No POST API, no raw trade IDs/auth secrets/vendor data.
- New installed nginx route /shared/nginx/routes.d/35-fresh-quant-dashboard.conf, source deployment/moon/35-fresh-quant-dashboard.conf. Basic Auth on /quant-research/ and *all* children including API and JavaScript, reverse proxy only to backend loopback 8081. Existing Moon paths /mcp and /health and missing Quant MCP /quant/mcp remain untouched. TLS from existing Funnel.
- Secrets ignored by Git at state/moon-http/fresh-20261021/dashboard-auth: dashboard-login.txt root:root mode 0600; hashed .htpasswd root:www-data mode 0640, enclosing dir root:www-data 0750; auth and supervisor config never checked into Git.
- Per-app secondary supervisor process runs current dashboard independently, autostarts after child crash (verified). Persistent source startup hook installed in previous supervisor include path at /shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory/deployment/moon/quant-mcp.supervisor.conf, content contains ONLY fresh dashboard service. Source template deployment/moon/fresh-quant-dashboard.supervisor.conf. The container PID1 includes exactly that original path, so a next cold boot should load the dashboard, but **container restart not done and not verified**. Do not claim Docker-level boot restart validated.

## Observed checks

- nginx -t PASS; nginx -s reload applied.
- Direct loopback localhost:8081/health HTTP 200.
- Nginx /quant-research/, app.js, api/status, health valid Basic login: all HTTP 200.
- Nginx no login /quant-research/ and api/status: 401; invalid password 401.
- Public HTTPS unauthenticated GET /quant-research/: HTTP/2 401, verified certificate.
- Public HTTPS authenticated GET /quant-research/api/status: HTTP 200, real 42/52 completed, 42 rows, Evidence chain true at time of test.
- Dashboard subprocess was intentionally terminated in isolation, per-app Supervisor relaunched it (PID 662 -> 862), health again HTTP 200, no Moon process restart.
- Existing Moon /health 200; Quant MCP /quant/mcp 404 (not restored).
- 9 targeted pytest including governance PASS; Ruff PASS; Mypy PASS.
- Research currently G42 completed (additional 40/50); G43 plan staged; no active research controller. Earlier +100 generations request remains **not executed**. G4+ batch previously was deterministic GPT-designed rules, NOT independently GPT-written per generation. A proper model-backed pipeline must be separately restored before claiming true autonomous research. No original G350 records or OAuth changed.

## Status commands

- To check dashboard program in current Docker:
  supervisorctl -c /shared/moon-workspace/AutoResearchFinance_v2-fresh-research-20261021/state/moon-http/fresh-20261021/dashboard-auth/fresh-dashboard-supervisord.conf status
- Anonymous HTTPS check expected 401:
  curl -I https://project-moon.taild689f9.ts.net/quant-research/
- Internal only:
  curl -fsS http://127.0.0.1:8081/health

Potential later tasks: verify container cold-boot behavior during a scheduled maintenance window; restore separate Quant authenticated MCP only with original credential state and URL identity; safely finish G43 current diagnosis and 52 target before any audited +100 extension.
