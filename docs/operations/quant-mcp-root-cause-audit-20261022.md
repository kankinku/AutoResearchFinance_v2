# Quant MCP root-cause audit — 2026-10-22 KST

## Verified outage mechanism

**CONFIRMED:** the active Supervisor configuration has no `[program:quant-mcp]`, the loaded Nginx configuration has no `/quant/mcp` route, and nothing listens on `127.0.0.1:8787`. Moon's `2999/health` returns 200, but `2999/quant/mcp` returns 404. The existing Quant connector's `get_workspace_status` and `get_research_brief` return internal errors.

**Proven configuration drift:** PID1 Supervisor's include path targets the old `AutoResearchFinance_v2-phase3-5-1-inventory/deployment/moon/quant-mcp.supervisor.conf`. The actual included file, modified 2026-10-21 14:27 KST, explicitly states “Current original Quant source/OAuth absent; startup hook is dashboard-only.” It defines only `fresh-quant-dashboard` and `fresh-quant-original-ui`. Parsed effective programs are `nginx`, `project-moon`, and these two dashboards. In contrast, the current tracked source template `deployment/moon/quant-mcp.supervisor.conf` declares `quant-mcp` but is **not** the loaded file. Installing that source template unchanged is not a repair because its launcher target does not exist.

**Original artifacts missing on accessible mounts:** the old inventory directory has only partial `.venv/lib` and `deployment/moon`; no launcher, app code, research-state folder or runnable interpreter. Original OAuth approval-key, pinned public-base URL and `quant-oauth.sqlite` absent at expected paths. Exact filename search of accessible `/shared` and `/var/lib/project-moon` found none. It remains **unknown whether the original files exist in an unmounted Windows host path/backup**; permanent deletion and its actor/time cannot be inferred.

**Separate dashboard deployment:** active Nginx includes the 2026-10-21 dashboard route `35-fresh-quant-dashboard.conf` but not the original Quant `20-quant-autoresearch.conf`. Ports 8081/8082 are dashboards, not OAuth/MCP. The dashboard was restored, **not** the Quant service.

## Evidence chronology

- **2026-10-13:** documented actual Windows Docker container restart acceptance: Quant MCP unauthenticated local/gateway responses `401/401`, OAuth clients 2, Evidence events 163 and 10 preserved state fingerprints; therefore original service/auth state demonstrably existed then. Host full reboot or later worktree replacement not established. Source: `quant-windows-supervisor-restart-acceptance.md`.
- **2026-10-21 03:50 KST:** `fresh-quant-dashboard-connection-diagnosis-2026-10-21.md` already recorded missing original Quant service and separate development study; therefore disappearance **preceded** the afternoon dashboard replacement.
- **2026-10-21 14:27 KST:** deployed Supervisor include file modified to dashboard-only; time is file mtime, **not** deletion time or author.
- **2026-10-21 15:16 KST:** dashboard-only Nginx route modified/installed; protected Quant route absent.
- **2026-10-22:** present investigation reproduced every layer with read-only process inspection, `nginx -T`, Supervisor parser, HTTP probes, mounted filesystem and Git comparison.

## Architectural factors

1. `scripts/run_quant_moon_http.sh` derives the OAuth+research state path from `$ROOT/state/moon-http`. `.gitignore` excludes that tree and `.dockerignore` excludes state. Code checkout cannot reconstruct original issuer identity, data or hash chain. The separate Moon Docker named volume `/var/lib/project-moon` is **not** the old Quant state path; a worktree replacement or mount change is sufficient to orphan Quant state. Whether this occurred remains unknown.
2. PID1 Supervisor includes a **mutable file inside an old worktree**. Its filename stayed `quant-mcp.supervisor.conf` even when its only programs were dashboards, obscuring the dependency. No deployed, verified protected-route restoration path remained.
3. Starting the available Quant launcher without the old state can **create a new OAuth approval key and URL pin**. This would be a new identity, not restoration; therefore no launcher was run.
4. Separate research architecture issue: `scripts/run_academic_autopilot.py --execution-mode mcp` returns connector-use instructions instead of invoking a model itself. P3 injected autonomous caller requires explicitly approved API mode. Repaired connector availability is not alone proof of real iterative GPT 10→100.

## Safe recovery sequence — not executed

1. Find the original Windows-host/backup source, OAuth approval-key, URL pin, OAuth SQLite, official research SQLite/Parquet/Evidence and original verified runtime SHA. Inspect **existence, size and hashes only**; never disclose key contents.
2. Bind those original files together with exact previous issuer and signed research lineage; back them up without resetting. Official latest G after prior G350 history is **unverified**, while the currently accessible development-only G452 lineage is **not** a substitute.
3. Only after authenticity checks, deploy Quant backend under a stable distinct program and original source tree, and restore exact `/quant/mcp` route. Preserve Moon `/mcp` and the old Quant OAuth URL; do not re-register.
4. Validate Quant backend/proxy unauthorized HTTP 401, OAuth discovery 200, existing connected app's authenticated read tools, official generation/parent/evidence/data hashes, orders OFF and sealed OOS untouched. Then attempt true GPT-authored T4 10 generations and later 100.

**Conclusion:** immediate cause is **dashboard-only Supervisor + missing Quant Nginx route**, forced by or contemporaneous with **absence of authoritative runtime/auth state**. Exact reason the source/state became unavailable is **not established**. This audit changed no infrastructure, OAuth, source code or research state.
