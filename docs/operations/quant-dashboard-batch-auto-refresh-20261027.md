# Quant dashboard bounded-batch auto-refresh — 2026-10-27

Stage: T4-DASHBOARD-BATCH-BRIDGE. Traces Q06/Q08/Q09/Q15/Q16/Q17/Q20. The approved V05→T4→V01–V04→V06→V07 sequence remains unchanged.

## Cause
The original dashboard tracked the GPT academic checkpoint by a pinned session ID. Its five-second poll could not display another job's `gpt-research-batches.sqlite` generations. This was not a poll-timer failure.

## Fix
A separate, read-only GET `/api/research-batches/latest` now reads the bounded-worker `batches` and `generation_history` tables. The new status/graph area polls every five seconds independently. It displays measured generation counts, candidate evaluations, duplicates, failures and promotions, while the original GPT research chart and research engine remain unchanged. The new view explicitly says parameter-search generations are not independently GPT-authored generations. No permissions, orders, OAuth, research evidence or OOS access changed.

## Verification
- Tests written first; selected pytest suite 26 PASS, Ruff PASS, changed-source mypy PASS, Node JavaScript syntax PASS.
- Node DOM polling smoke: 2/10 -> 10/10 PASS; tested source API responses via SQLite fixture and HTTP handler.
- Only read-only dashboard PID changed on deployment (29 -> 721). Existing 8081 dashboard and Quant MCP processes were not restarted.
- Operational HTTP before/after: `/api/research-batches/latest` 404 -> 200; response latest batch `76fc91dd8b2e4769b1a4b961454ad2ba`, 10/10 complete, 68 evaluated, 12 duplicates, 68 rejected, zero promoted. Source checkpoint consistency true.
- Source SQLite hashes were identical before and after deploy; public nginx anonymous `/academic/` HTTP 401. Authenticated Quant MCP status tool still confirms 10/10 COMPLETE, orders OFF.

## Limits and next
Actual logged-in user browser was not visually inspected. Auto-update transition was exercised with fixture and JS DOM, not a new live worker. No new investment-performance/OOS/PIT claims. Resume planned T4 GPT-directed end-to-end evolution and preserve existing evidence.

## Source and deployment
- Implementation commit `1328c9a`, branch `feat/quant-parent-portfolio-20261021`, pushed to origin successfully; source deployed in active read-only 8082 process.
