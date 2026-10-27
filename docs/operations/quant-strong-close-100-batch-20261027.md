# Quant Strong Close 100-generation parameter batch — 2026-10-27 KST

## Scope and identity
- Research intent: follow-up 100-generation fixed-plan local worker test after mean-reversion batches failed. Stage T4-BATCH-DURABILITY-OBSERVATION, Q06/Q08/Q09/Q15/Q16/Q17/Q20. It exercises batch durability and dashboard observability, **not** the required user-defined GPT self-directed research generation (which must include model diagnosis and a next-generation plan).
- Job `c45b54f01f794ce492503cc0d6ea4d4a`, evidence run `37810e8e1ca54b5493529acb4c690d00`.
- Parent: `strong_close`, IBS-based close-strength momentum; source `strategies/normalized/a98951ec1c6f11cf-7.json`.
- Inputs: `QQQ_2020-01-02_2025-12-31_raw.parquet`, historical 1508 development bars. `count=6`, `generations=100`, `method=random`, `seed=202610271`; controlled domains stop-loss 12 values, take-profit 11 values, position-size 8 values.
- Generated code is not dynamically revised each generation; adaptive replanning 0, model-invocation evidence 0. PIT/as-of quality UNVERIFIED, sealed independent OOS NOT_MEASURED, orders disabled.

## Verified outcome
- Started 2026-10-27 03:41:30.033 UTC, finished 03:48:16.670 UTC (12:48:16.670 KST).
- MCP `get_research_batch_status`: `COMPLETED`, 100/100 requested, no errors or early stop, no unexecuted generations, orders false.
- MCP `get_research_batch_report`: 452 distinct evaluated candidates, 148 skipped duplicates (out of 600 proposed); 99 generations with at least one evaluated candidate, one `NO_NEW_CANDIDATES`; promoted successors 0. Every one of 452 evaluated candidates rejected.
- Immutable evidence gate counts: fast 452 failures; full 452; robustness 452; validation 452. Failures overlap. This excludes strategy-quality approval.
- Best **scored generation representative**, G98: score 0.079076, development full CAGR -6.0143%, MDD 39.9904%, Sharpe -0.4547, 295 trades, exposure 80%, stop 4%, take profit 7%, rejected.
- Highest development CAGR among retrieved *generation representatives*, G22: CAGR -2.0634%, MDD 14.3874%, 306 trades, exposure 30%, stop 1.5%, take profit 3%, rejected. This is not asserted as the absolute highest CAGR across all individual candidate instances.

## Live dashboard and preservation
- Read-only `/api/research-batches/latest` polled every 5 seconds during actual execution, 80 JSON samples, 80 observed distinct-generation states, 0 HTTP/API errors. From RUNNING 2/100 to COMPLETED 100/100; final 100/100, evaluated 452, duplicates 148, failed 452, passed/promoted 0, checkpoint counts consistent.
- Separately cross-checked authenticated installed Quant tool and dashboard API after completion. Both report the same final values.
- Original GPT academic `/api/status` remained session `14626d55`, 83/100, phase `AWAITING_DIAGNOSIS`, proof chain OK. This bounded run is NOT claimed to have advanced GPT session 83→100.
- GPT academic cycles.sqlite SHA-256 still `4294635268f6d1cff867c081413730a1793edf808d00a864082447d6ccd34f0b`. Existing nginx `/academic/` anonymous access HTTP 401. OAuth, credential paths, sealed OOS, research data and trade permission unchanged.
- Detailed transient monitor samples `/tmp/quant-batch-100-dashboard-20261027.jsonl`; immutable server-side research run provides permanent proof.

## Interpretation and next
- Reliability objective passed: bounded 100/100 worker completion and live dashboard update.
- Economic/algorithm evolution objective FAILED/NOT TESTED: 452/452 rejected and zero GPT adaptive replan. Further tuning stop/target/exposure in this unchanged Strong Close signal is lower priority than actual GPT-driven algorithm-structure hypotheses and independent OOS/PIT/benchmark data validation.
- Frozen remaining project order remains V05→T4 true ChatGPT/MCP generational evolution→V01–V04→V06→V07. No change to success criterion or frozen permissions.
