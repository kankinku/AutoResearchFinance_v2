# Quant T4 — GPT generations G87–G93 evidence audit (2026-10-27)

Stage T4 (Q02/Q05/Q06/Q07/Q08/Q09/Q14/Q15/Q17/Q20). After an explicit request to continue G87–G93, the first current GPT MCP read already returned **93/100 AWAITING_PLAN**; these completed records existed before new submissions in this turn. Accordingly we **did not submit duplicate plans/diagnoses or mutate the academic session**. The provenance of the concurrent advancement is not independently attributed to this chat.

## Real checkpoint verification

- Session `14626d55fb2b461faa485df911920071`; completed 93/100, next G94 AWAITING_PLAN. Existing OAuth/MCP and orders=false, independent_oos_approved=false. Server `real_model_connection_verified=false`: authenticated checkpoint accepts GPT-authored submissions, but no independent model-provider invocation attestation.
- Seven **distinct** G87–G93 recorded generations, each with an evidence hash, actual analysis, inherited intent, and one S7 experiment hypothesis. Read-only gateway SQLite `PRAGMA integrity_check=ok`; exactly 7 rows in `experiment_reports` and 7 in `generation_timings` for this range; each S7 report contains one experiment. No change to original research state was necessary.
- G87: inherited replay-verified G60, changed exit to EMA direction-off, development return +60.38%, MDD 17.91% vs G60 +66.65%, MDD 10.33%.
- G88: inherited replay-verified G79; RSI>45 regime, development return +188.86%, MDD 22.67% vs parent +197.81%, MDD 23.10%. Lower MDD but lower return.
- G89: replay-verified newly counted **G88** strategy selected as parent; changed exit to EMA-off; development +74.89%, MDD 28.04%, worse than G88 +188.86%, MDD 22.67%. This is genuine cross-generation parent inheritance, **not evidence of improved final alpha**.
- G90: replay-verified G60, developmental return +112.47%, MDD 17.45% vs G60 +66.65%, MDD 10.33%; return rises while risk worsens.
- G91: replay-verified G79, high ADX exclusion return +182.40%, MDD 26.66% vs parent +197.81%, MDD 23.10%, both worse.
- G92: replay-verified G88, RSI cap return +185.99%, MDD 23.02% vs parent +188.86%, MDD 22.67%, both worse.
- G93: replay-verified G60, ADX<37 cap return +54.03%, MDD 13.63% vs parent +66.65%, MDD 10.33%, both worse. Its record notes an equivalent-effective-signal proposal was rejected before a genuine execution change was accepted.

**Interpretation:** Development-only, repeated 2020–2025 QQQ sample. Market condition, as-of/PIT, cost/model selection bias, independent sealed 2026 OOS, and real trading remain unapproved/unproven. A strategy that is picked as a parent need not dominate; lineage selection/replay is not an unconditional economic success. This completed interval is not evidence that unattended 100-generation model orchestration runs indefinitely, because server model invocation attestation remains false.

## Next gate

The existing GPT checkpoint is **G94 AWAITING_PLAN**, with a replay-verified G79 parent offered. Continue original typed GPT plan→S2 execution difference→audit→GPT diagnosis→S7 controlled comparison→lineage evidence; avoid reverting to deterministic batch generation counts, changing validation gates, or rewriting the previous results.
