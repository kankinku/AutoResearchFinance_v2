# P0-6 — PIT metadata gate and independent QQQ benchmark (research-only)

## Isolation and rollback

- New feature branch: `feat/p0-pit-benchmark-gate-v1`.
- Pinned P0-5 parent: `d4c8b66da7f4bef2ca56dcf671d7952cc0cd3669`.
- Preserved developer branch: `feat/p0-indicator-research-engine-v1`.
- Preserved operational rollback baseline:
  `docs/mcp-phase3-5-1-state-inventory` at `4a7423327dfec940fd497f970c6db69ef42e95bc`.
- No production engine, broker, sealed OOS, Champion, MCP endpoint or
  deployment changes. **Do not merge** this branch without independently
  executing validation and reviewing the underlying data supplier claims.

## Scope

`research.indicator_engine.benchmark_pit` has two separate research functions.

1. `audit_pit_metadata(dataset, evidence, session_opens)` refuses
   latest-revision feeds, missing as-of source metadata, incomplete bar
   evidence, missing adjusted-price action lineage, mismatched bar times,
   future-dated publication, and post-opening vintage capture. Each
   claimed historical session open must precede the corresponding
   completed bar; each bar's release and captured vintage must precede
   the **next** session open before the price can inform the next trade.
   Session open timestamps must come from a separately validated exchange
   calendar. Merely supplying fabricated timestamps is NOT certification.
2. `compare_independent_qqq(strategy_report, strategy_dataset,
   benchmark_dataset)` requires distinct source identifiers and distinct
   dataset identities, development-zone QQQ daily bars, exactly aligned
   completed-bar timestamps, identical price adjustment policies,
   strategy-result binding, and a positive finite equity curve.
   The benchmark invests the strategy's initial amount at the **first**
   benchmark opening price, paying the P0-5 model's same 1 bp commission,
   2 bps spread and 5 bps slippage before taking exposure. It then
   marks its units to each close. Terminal equity excludes an assumed
   liquidation/sell fee, just as the strategy's terminal report is marked.
   Strategy/benchmark return spread is a difference in *realized model
   price-path cumulative returns*, not risk-adjusted or verified alpha.

The source-id check is necessary but not sufficient to establish
independence: an independent, independently audited external provider
must later corroborate lineage and prices. All outputs explicitly retain
`NON_PIT_DEVELOPMENT_COMPARISON`, `verified_alpha=false`,
`independently_verified_benchmark=false`, `candidate_promotable=false`,
`broker_executable=false`, and `out_of_sample_approved=false`.

Even a successful `audit_pit_metadata` yields
`METADATA_CONSISTENT_NOT_CERTIFIED`. It does not independently verify
historical snapshots, exchange market-open tables, exchange actions,
vendor release metadata or investable market universe. `latest` QQQ
2020–2025 development data used in earlier P0-5 experiments therefore
cannot pass this audit. No authenticated, separate QQQ price series has
yet been supplied; no independent economic result is reported here.

## Validation acceptance required before merge

Run from the isolated feature checkout:

```bash
python -m pytest -q -p no:cacheprovider tests/research/test_academic_benchmark_pit.py
python -m pytest -q -p no:cacheprovider tests/research
ruff check .
mypy .
python -m pytest -q -p no:cacheprovider
```

Acceptance includes future-price/future-publication perturbations, data
source identity, as-of corporate actions and archived source vintages,
dates from a trusted NYSE session calendar, realistic independent QQQ
price ingestion, fee and return reconciliation, and true signed/
immutable third-party audit evidence. Tests using synthetic fixtures
prove only contract behavior, not real historical PIT integrity.

### Development environment limitation — 2026-10-14

Moon host MCP command/directory access returned
`UNAVAILABLE / Connection failed` repeatedly. A direct GitHub connector
was used solely for isolated source branch creation and feature commits.
The source and tests are pushed for **inspection but unexecuted** as of
this record; no Ruff, Mypy, pytest or QQQ dataset benchmark run is
claimed. Repeat the validation suite above in the actual Moon worktree
before considering this change reviewed or complete. No merge authorized.
