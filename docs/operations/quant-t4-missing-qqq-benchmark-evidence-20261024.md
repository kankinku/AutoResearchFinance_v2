# Quant T4 — missing QQQ benchmark gate evidence (2026-10-24 KST)

## Stage / scope
- Stage: T4 read-only evaluation interpretation, Q04/Q09/Q20. Supports autonomous algorithm research; this is not individual QQQ strategy optimization.
- Source: original 20 questions and locked order V05 → T4 → V01–V04 → V06 → V07 unchanged.
- User value: distinguish *unmeasured* benchmark comparison from measured failure and avoid falsely diagnosing low investment returns while keeping the qualification gate fail-closed.
- Non-goals: rerun 100-generation batch, count fixed-intent repeat backtests as GPT, change thresholds, fabricate Nasdaq/QQQ data, alter OAuth/MCP, production 8787, sealed OOS, order capability or original research evidence.

## Observed evidence and root cause
- Separate fixed-intent deterministic job `817d3bbc200c4c66a60adc3b804b62b5`: 100/100 complete, 177 evaluated unique candidates, 177 rejected, 623 duplicate candidates skipped. No per-generation GPT hypothesis diagnosis; cannot count as genuine GPT autonomous generations.
- Candidates have `benchmark_dataset_hash=null`, `qqq_cagr_delta=null` and a failed QQQ gate with reason `qqq_target_not_met`. This is **not measured underperformance**.
- `orchestration/evaluation_runner.py` populates benchmark curves only when `series_data_path` points to a valid aligned research series (both QQQ and NASDAQ). The fixed-intent batch did not provide such a series. Existing fail-closed rejection is sound, but the reason is ambiguous/misleading.
- Other authenticated `start_algorithm_research` sessions use a separate costed QQQ buy-and-hold benchmark; do not infer their missing values or their completed-generation counts from this batch. Existing evidence remains immutable and unchanged.

## Exact implementation (isolated development branch)
- `evaluation/selector.py`: when QQQ delta target is configured and comparator missing, preserve gate FAIL and select `benchmark_not_measured`. When a comparator exists but below the threshold, preserve `qqq_target_not_met`. When the target is optional, no regression in pass logic.
- `tests/evaluation/test_benchmark_missing_gate.py`: new regression tests for missing comparator / configured target, and optional benchmark control.
- `tests/evaluation/test_selector.py`: explicit assertion for existing measured-underperformance example.
- `orchestration/evidence.py`: preserve the computed per-gate `reason` as a new field for **future immutable candidate Evidence**. Previously the candidate_evidence serializer dropped `GateDecision.reason`, making the root-cause diagnosis invisible to persisted reports; existing records must remain unmodified.
- `tests/orchestration/test_benchmark_gate_reason_evidence.py`: RED-to-GREEN proof of both `benchmark_not_measured` and genuinely measured `qqq_target_not_met` surviving serialization.
- No production runtime restart, no original GPT research session state edits, no sealed market data access. Existing 177 candidate records are not rewritten: new reason is emitted on future evaluations. Future batch preflight must supply separately sourced QQQ+NASDAQ aligned series if benchmark gates are required.

## Validation
- RED test before patch: 1 failed / 8 passed, confirming old ambiguous `qqq_target_not_met` reason.
- Additional RED evidence serializer tests: **2 failed**, demonstrating the current immutable candidate-evidence writer discards the reason entirely.
- GREEN scoped tests across selector, missing benchmark, evidence writer, evaluation runner and batch summary: **29 passed**.
- Ruff on changed Python files: **PASS**. Repository-wide Ruff: **PASS**.
- Mypy for modified `evaluation/selector.py` and `orchestration/evidence.py`: **PASS**.
- Moon configured validation profile could not start: `uv: command not found` (exit 127). Direct full Mypy reported **51 errors in 16 pre-existing, unmodified files** (e.g. `application/academic_checkpoint_service.py` and `scripts/*`); this broader check **FAILED**, and this task does not silently fix unrelated code.
- Full repository Pytest: **FAILED during collection (1 collection error, 59.47s)**. `tests/dashboard/test_academic_cohort_runner.py` imports a controller that requires an ignored local runtime `state/moon-http/fresh-20261021/session-id.txt` which is **not present in the isolated worktree**. No runtime secret/session files were copied or synthesized. This is an environmental test-collection dependency, not evidence of passing full-suite regression.
- Live smoke, economic/OOS validations: **NOT RUN**. No production deployment.

## Remaining dependencies / next locked work
1. Actual authenticated GPT/MCP T4 full AlgorithmPlan→S2 trace→GPT Diagnosis→S7→signed next-plan until independently verified 100 valid generations, not local fixed-intent 100 backtests. Its operator live checkpoints are concurrently advancing and must be read and claimed with fresh evidence only.
2. If repeating fixed-intent batch comparisons, register independent, aligned QQQ and NASDAQ benchmark series with actual vintage/source evidence; do not use missing curves, backfilled values or invent Nasdaq observations.
3. External PIT/OOS and market-data as-of dependencies remain BLOCKED; V06 paper and V07 final GO/NO-GO follow the frozen sequence.
