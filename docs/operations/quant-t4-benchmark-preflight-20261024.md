# Quant T4 — required QQQ benchmark preflight (2026-10-24 KST)

## Stage and product boundaries
- T4 / Q04 Q09 Q17 Q20: block pointless fixed-intent backtests when their explicitly required QQQ comparison is unavailable.
- Frozen sequence remains V05 → T4 actual GPT 10/100 → V01–V04 external PIT/OOS → V06 paper-only → V07 GO/NO-GO.
- Fixed-intent 100/100 job 817d3bbc... ran 177 rejected candidates with benchmark_dataset_hash=null and qqq_cagr_delta=null. It is not 100 actual GPT-authored diagnostic generations.
- Historical G452/G552, actual GPT checkpoint, OAuth/MCP fixed URL, OOS isolation, and order-disabled safety are not altered.

## Before and after
- Before: when min_qqq_cagr_delta=0 and series_data_path was omitted, batch preflight returned READY_WITH_WARNINGS. All QQQ gates then failed without any measured comparator.
- After: for an explicitly configured QQQ excess CAGR target, missing series is BENCHMARK_SERIES_REQUIRED before any DB/job creation. A series missing QQQ/NASDAQ, a required as-of value, or positive prices is BENCHMARK_SERIES_INCOMPLETE.
- Use the identical _benchmark_data development-zone as-of comparison path from orchestration/evaluation_runner.py, with no imputed Nasdaq prices or synthetic substitute.
- min_qqq_cagr_delta=None still permits exploratory backtests without benchmark. Verified supplied development series permit queued work but DO NOT establish PIT/OOS accuracy.
- Tests: new tests/integrations/test_batch_benchmark_preflight.py and correction of existing research batch fixture to include the already available series.parquet when QQQ comparison is requested. Legacy 177 decisions are never modified.

## Tests and release state
- TDD RED: missing-series and incomplete-NASDAQ cases failed before production fix; late-as-of fixture was corrected after its series-ordering contract error.
- Scoped integration tests for benchmark preflight, detached batch execution and resume: **30 passed** (133.28s).
- Previous benchmark gate serialization + scope governance tests: **15 passed** (3.36s), total 45 scoped cases passed.
- Repository Ruff: **PASS**. Modified batch service Mypy: **PASS**. `git diff --check`: **PASS**.
- Broader full Mypy/Pytest: **NOT RUN this increment**. Prior worktree baseline documented 51 existing errors in 16 untouched files and full Pytest collection failure caused by the missing ignored `state/moon-http/fresh-20261021/session-id.txt`; no production or historical state files were copied to manufacture a PASS. `uv` is absent.
- Operation/deployment: NOT RUN; this is a separate development branch only.

## Next approved step
Finish actual authenticated GPT T4 cycles with GPT-authored plan → costed S2 trade evidence → independent model-authored diagnosis → S7 control → justified next-plan and signed parent genealogy. Avoid concurrent checkpoint conflict and never attribute deterministic 100 fixed-intent generations to the GPT.
Obtain audited benchmark series and separate V01–V04 PIT/OOS evidence before profitability claims.
