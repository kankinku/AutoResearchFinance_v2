# Quant dashboard — current 100-generation live cohort wiring (2026-10-23 KST)

## Proven root cause

The dashboard did not display the new 100-generation run because scripts/fresh_research_dashboard.py pinned its STATE to the original fresh-20261021 research SQLite, already completed at G452/452. This was a **source-path mismatch**, not a broken 5-second JavaScript poll. Both 8081 fallback and 8082 original UI consumed this old snapshot function.

The running 100-generation study PID37928 actually writes to a different, isolated and verified research tree: state/moon-http/quant-moon-bounded-100-20261023/research/academic-gpt-checkpoints. Its target is G552, starting from an immutable copied G452, so the new experimental progress is completed minus 452 of 100, **not** completed minus 52. The old controller PID detector also failed to match the new bounded_100 launcher.

## Source fix and safety

1. Define an allowlisted, fixed active cohort directory. Prefer it for the dashboard snapshot only when present. Verify immutable start-manifest and cohort metadata identify target G552, start G452 and the same original source evidence SHA. Verify the copied history at G452 still matches the pinned source. Reject inconsistent data rather than switch to an unrelated study. Preserve the original G452 academic STATE and explicit snapshot(old_state) functionality.
2. Read SQLite exclusively with read-only URI mode and query_only; never update research counts, metadata or actual experiments from the dashboard. Expose source_kind and a Korean cohort label visibly identifying deterministic exploration rather than per-generation GPT.
3. Correct additional_completed/target to N/100 for the G453–G552 cohort. Make the primary progress card and bar show percent of **this new 100**, not the full G1–G552 lineage. Show the full lineage number alongside and keep the 5-second read-only GET status refresh.
4. Match the active research worker by precise bounded cohort wrapper command and cwd, not the old worker list. Keep main original dashboard HTML/CSS/JS and nginx protected routing intact. Only performance overlay extension changed.
5. Preserve sealed OOS, original G452, the earlier separate model-authored G453 clone, OAuth, public URL, broker order disabled and no API spend.

## Live operational evidence

- Before: existing 8082 API gave G452/452 COMPLETE while active cohort SQLite was already G467+. No live worker was shown.
- Restarted only dashboard PID40 (respawn PID39077) and fallback dashboard PID22 (respawn PID39187), preserving active research PID37928 and Moon /health HTTP 200.
- First fresh 8082 API gave G484/552 and **32/100** additional. Both 8081 and 8082 subsequently gave G488/552 with **36/100**, running PID true and proof_chain_ok true.
- Node browser DOM simulation using **actual served original JavaScript and real API** validated current progress **38/100**, original backtest **G490/552**, chart, summary, reference QQQ metrics, GET refresh and connection dialog.
- Local anonymous nginx protected routes /academic/ and /quant-research/ plus their API status endpoints remain 401; authenticated Windows browser UI was not separately viewed using user credentials. No passwords or tokens read/published.
- Regression fixture added with two synthetic post-G452 generations, checks clone/default selection, 2/100 progress, archived source preserved and manifest mismatch rejection.
- Scoped bridge/governance tests **13 PASS**; expanded dashboard/governance regression **51 PASS**; Python Ruff PASS, focused mypy PASS, JavaScript syntax and Node smoke PASS, diff whitespace PASS. Final broad Node VM/live API run verified **45/100** and **G497/552**. Full repository release gate not claimed. Full repository release gate not claimed.

## Interpretation and deployment limitations

Dashboard mirrors **genuinely committed, costed development-only backtests** from the currently running bounded rule-search controller. It does NOT prove 100 independent model-authored decisions, PIT data, independent OOS alpha, or executable live brokerage strategy. Progress is a time-stamped factual snapshot, not a claim that G552 has finished. Old Quant OAuth/MCP 404 remains a separate defect, unrelated to this dashboard's read-only current research view.

The authoritative dashboard is http://127.0.0.1:2999/academic/ (existing Basic Auth) with the HTTPS mirror https://project-moon.taild689f9.ts.net/quant-research/. Both continue to use nginx Basic Auth and their existing routes. No new credentials or redirects introduced.
