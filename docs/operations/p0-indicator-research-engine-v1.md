# P0 Indicator Research Engine v1.0 — staged implementation

## Branch protection and rollback

- Original branch: `docs/mcp-phase3-5-1-state-inventory`; frozen and pushed
  baseline commit: `4a7423327dfec940fd497f970c6db69ef42e95bc`.
- Isolated worktree: `/shared/moon-workspace/AutoResearchFinance_v2-indicator-engine-v1`.
- Feature branch: `feat/p0-indicator-research-engine-v1`.
- No merge into baseline, no production MCP deploy, no live orders.
- Restore original baseline by checking out the original worktree/branch.
  Do not reset or force-push either branch.
- Policy: incremental scoped tests, `ruff check .`, `mypy .`,
  `pytest -q` and independent review before a future merge.

## Delivered vertical slice — paper provenance, tested kernels, hypotheses

The original `core.features` already has a broad technical indicator
catalog, a registry and many calculators. Do not add duplicate catalog items
or equate `REGISTERED` existing names with independently certified academic
results. The new `research.indicator_engine` research layer is separate from
the production FeatureRegistry.

1. A local SQLite `ResearchCatalog` provides immutable, normalized DOI
   provenance with citation-count snapshots only when provider and observation
   date are known. No manufactured citation counts or downloads.
2. Seed data contains **four** verified DOI references and **five proposed
   signal mappings**, not an assertion of paper replication or market alpha:
   - Brock, Lakonishok & LeBaron (1992), moving average and range breakout,
     `10.1111/j.1540-6261.1992.tb04681.x`.
   - Jegadeesh & Titman (1993), relative/cross-sectional momentum,
     `10.1111/j.1540-6261.1993.tb04702.x`.
   - Moskowitz, Ooi & Pedersen (2012), time-series momentum,
     `10.1016/j.jfineco.2011.11.003`.
   - Garman & Klass (1980), OHLC volatility estimator,
     `10.1086/296072`.
3. Registered mathematical calculators (in isolated research-only module):
   `sma_direction`, `previous_range_breakout`,
   `time_series_momentum`, and `garman_klass_variance`.
   Each output is known only after the current *completed* OHLC bar, and
   strategies must delay execution at least one bar.
4. Real verification recalculates independent mathematical reference values,
   runs prefix-extension no-future-leak tests, checks deterministic results,
   validates missing and invalid input handling and resource bounds.
   Verification evidence is tied to a SHA-256 canonical definition and
   recalculated before any `PROPOSED → VERIFIED` database transaction.
   A synthetic fixture cannot authenticate historical data provenance,
   market results, alpha, or PIT compliance.
5. `cross_sectional_momentum` deliberately remains unverified/unusable until
   a point-in-time, survivorship-safe, multi-asset universe is installed.
   Direct QQQ-only application would not replicate Jegadeesh & Titman.
6. `compose_hypotheses` accepts *only mathematically VERIFIED* signals and
   generates a bounded, semantically hashed 2- or 3-signal hypothesis with
   disjoint `entry`, `regime`, optional `risk` roles.
   Every output is tagged `RESEARCH_ONLY`, `executable=false`,
   `sealed_oos_approved=false`. It cannot be submitted to the existing
   Strategy IR evaluator or broker.
7. Manual-only research CLI; no network requirement, MCP schema change,
   auto-promotions or background processes.

### Usage in isolated development worktree

```bash
# Use existing Python virtual environment in the original checkout.
PY=/shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory/.venv/bin/python
DB=state/indicator-engine/research.sqlite
$PY -m research.indicator_engine.cli --database "$DB" seed
$PY -m research.indicator_engine.cli --database "$DB" status
$PY -m research.indicator_engine.cli --database "$DB" verify sma_direction
$PY -m research.indicator_engine.cli --database "$DB" verify previous_range_breakout
$PY -m research.indicator_engine.cli --database "$DB" compose previous_range_breakout sma_direction
```

Only sample mathematical correctness is verified by the `verify` command;
it is not an implementation approval for production trading.

## Deferred P0 work before any production integration

- Separate academic signal *math accuracy* from verified paper reproduction:
  use primary-paper methodology, independently computed fixture/reference
  results and historical replay with true as-of data and corporate actions.
- Connect Crossref/OpenAlex citation API with provenance, date,
  dedup, rate limits and no external arbitrary code execution. Validate every
  DOI metadata change manually before accepted update.
- Add a strategy-composition adapter to the existing strict `StrategyIR`
  only for existing whitelisted evaluator features; validate alignment,
  non-future lookahead, signal role/units, gate policies, resource budgets,
  exact serialized code and feature implementation hashes.
- Multi-asset data and benchmark separation; do not reintroduce the prior
  null QQQ-CAGR-delta rejection gate.
- Duplicate/correlation family controls and proper DSR/PBO accounting,
  authenticated benchmark, PIT vintage audits, cross-asset/OOS tests,
  performance comparison against `4a74233`.
- Independent code review, PR check, recovery exercises; merge only after
  technical and research evidence is demonstrated.

## Research quality disclaimers

Popularity / citations are evidence of academic impact, **not** proof of
tradability. Candidate labels in the database are **mathematical validation
only**, not a rating or objective investment recommendation. All four papers
were confirmed through DOI/publisher pages; no live citation count was
inserted because source-specific dates and provider counts need explicit
freshly fetched snapshots.

## Actual verification evidence (2026-10-13)

- New research unit tests: **10/10 PASS**. Reference calculations,
  prefix extension, invalid OHLC, forged evidence, SQLite re-open,
  deduplicated source seeding, and bounded research-only composition covered.
- `ruff check .`: **PASS**.
- `mypy .`: **PASS**, 204 source files.
- Initial full `pytest -q -p no:cacheprovider`: **1,166 PASS, 3 FAIL**.
  These three were isolated-worktree environment assumptions, not diffs to
  existing production modules:
  1. Baseline real QQQ Parquet was ignored by Git and absent under the
     new worktree `data/`.
  2. Local MCP stdio launcher expected `./.venv/bin/python`, which was
     absent in the clean worktree.
  3. Offline tunnel preflight also expected the local `./.venv` path.
- **All three affected tests re-run PASS (3/3)** after adding an ignored
  *local development-only* `.venv` symlink to the existing environment and
  copying the historical test Parquet into the new worktree's ignored
  `data/` directory. The full suite was **not** re-run end-to-end after
  that local fixture restoration. Do not claim a single full-suite green run.
- Real isolated-worktree SQLite run: 4 papers and 5 PROPOSED signals seeded;
  mathematical verification of four single-asset calculators completed,
  leaving cross-sectional momentum PROPOSED. Two `RESEARCH_ONLY`
  entry+regime(+risk) hypotheses emitted; no orders.
- All paper source metadata are in Git so future users can rebuild the
  research catalog; the example SQLite database and test market data are
  ignored by Git and were **not pushed**.

## Merge policy

The pushed feature branch is an **independently reviewable P0 foundation**.
It is not deployable to the live MCP, and **no merge is authorized** until
the runtime adapter, PIT/benchmark verification, independent review and
an appropriate full regression acceptance have passed. The operational
baseline remains at its original fixed SHA.

## P0-2 incremental expansion — 2026-10-13 (feature branch only)

Two additional academic sources were verified against public paper records
and added to the curated research source set:

- **Parkinson (1980)**, *The Extreme Value Method for Estimating the
  Variance of the Rate of Return*, DOI `10.1086/296071`.
  Research calculator `parkinson_variance` uses the rolling completed-bar
  estimator `mean((ln(H)-ln(L))²/(4 ln(2)), n)`, requiring positive, finite,
  internally consistent OHLC inputs. It is a variance estimator, **not**
  an investment timing strategy.
- **Moreira & Muir (2017)**, *Volatility-Managed Portfolios*,
  DOI `10.1111/jofi.12513`. Research calculator
  `volatility_managed_exposure` applies an **adapted, cash-only,
  nonleveraged** dynamic exposure rule after the current close:
  `min(ex_ante_exposure_cap, ex_ante_target_daily_variance /
  mean(past_n_log_returns²))`, assigned to **the next bar only**.
  When historical variance is effectively zero, the exposure stays at the
  pre-declared cap instead of dividing by zero. This differs from the
  paper's scaled cross-sectional factor portfolios and is **not**
  a replication or evidence of alpha. Both the variance target and cap
  must be chosen before evaluation; they are included in the candidate
  identity. The cap may not exceed 100% and no leverage is authorized.

These were introduced as PROPOSED with their formulas and input/role
contracts sealed. Independent arithmetic reference, prefix causality,
nonfinite/malformed OHLC, immutability/reproducibility and bounded
lookback tests must pass before a math-only VERIFIED status is granted.

**Recorded repeatable smoke test (isolated development-only state):**

- 6 DOI references, 7 indicator candidates.
- 6 single-asset mathematical calculations VERIFIED; 1 cross-sectional
  momentum signal remains PROPOSED until a historical point-in-time
  investable universe exists.
- Existing raw QQQ 2020–2025 data: 1,508 daily OHLC observations,
  `parkinson_variance` returned 1,489 finite non-warmup values;
  `volatility_managed_exposure` returned 1,488 finite non-warmup
  exposures, each between 0 and 1.
- Composer now generates **8 distinct, non-executable RESEARCH_ONLY**
  hypotheses from 2 entry, 1 regime and 3 risk-feature choices
  (including no-risk-overlay variants). No actual strategy evaluation,
  economic outperformance or OOS performance was measured.
- New P0-2 unit tests: six additional tests for DOI seed upgrade,
  direct hand-calculated Parkinson math, scale invariance, invalid
  OHLC/parameters/roles, one-bar execution, bounded exposure and
  verified-only eligibility.
- Source verification:
  `https://doi.org/10.1086/296071` and
  `https://doi.org/10.1111/jofi.12513`.
  Academic citation counts and their snapshot dates remain unfilled
  until captured from a named provider; no counts are inferred from
  research performance.

This step does not change protected evaluator code, order-execution
gateways, production MCP schema, or the operational baseline branch.
Next P0 task: audited citation metadata ingest plus feature-to-StrategyIR
*paper-evaluation-only* translation, PIT-compliant historical signal
alignment and explicit independent benchmark; retain **no merge** until
separate research acceptance.

### P0-2 regression acceptance

- `ruff check .`: PASS.
- `mypy .`: PASS, 204 source files.
- Complete captured regression execution:
  `pytest -q -p no:cacheprovider`: **1,175 passed, 0 failed,
  368.61 seconds**.
- One additional eight-hypothesis composer regression test was added
  while the full run was in progress; all **17 indicator-specific tests**
  were subsequently run independently and PASS. The two executions
  together cover the final code revision, although the single full
  process collected its tests before that last test was appended.
- No changes to `docs/mcp-phase3-5-1-state-inventory` baseline;
  **research feature branch ONLY**. No sealed OOS, broker orders, or
  production deployment were performed.


## P0-3: DOI citation capture and sealed research feature replay (2026-10-13 UTC)

**Crossref ingest:** `research.indicator_engine.citations` implements strictly
bounded read-only DOI lookup against `https://api.crossref.org/works/{doi}`.
Only previously curated DOI IDs are eligible. Redirects are disabled,
responses are size-capped at 256 KiB, and the source must provide matching
DOI, title overlap, publication year and a nonnegative integer
`is-referenced-by-count`. No paper abstracts, licensed PDF copies or remote
Python code are fetched or executed. HTTP errors/mismatches result in no
database insertion.

The independent `citation_snapshots` SQL table records
`(doi, provider, UTC date, count, verified-record hash)` and the normalized
title/year used for acceptance. Equal same-day replay is idempotent; changed
same-day values fail rather than replacing earlier evidence. Stored snapshots
are rechecked against their verification hashes when read. The original
`Paper` and indicator VERIFIED status are not changed by citation lookup.
These internal hashes detect accidental tampering; they are not signed
proofs of publisher authenticity. Crossref citation coverage is incomplete
and cannot establish investment return.

**Live adapter acceptance:** The development-only, manual command

```bash
.venv/bin/python -m research.indicator_engine.cli \
  --database state/indicator-engine/research.sqlite refresh-citations --limit 6
```

actually retrieved all **six curated papers**. The 2026-10-13 UTC snapshot
saved 6 and reported 0 failures; re-running it returned 0 inserted and
6 unchanged. Provider-observed counts at that UTC capture:

| Source | Crossref is-referenced-by-count |
|---|---:|
| Jegadeesh & Titman (1993) | 9,835 |
| Brock, Lakonishok & LeBaron (1992) | 1,623 |
| Parkinson (1980) | 1,483 |
| Moskowitz, Ooi & Pedersen (2012) | 1,279 |
| Garman & Klass (1980) | 1,214 |
| Moreira & Muir (2017) | 558 |

These are dated registry observations, not live financial signals and
not interchangeable with Google Scholar or OpenAlex citation totals.
Any later capture on the same UTC day with revised provider values
is intentionally rejected until the next date; manually reconcile
the evidence instead of overwriting.

**Development feature replay:** `research.indicator_engine.bridge` consumes
existing `MarketDataSet` instances from the canonical Parquet reader and
only structurally VERIFIED `ResearchHypothesis` instances. It calculates
typed feature vectors against completed, sorted, single-symbol,
`DataZone.DEVELOPMENT` daily bars. Every observation at bar `t`
records **earliest potential evaluation at `t+1`**; the final bar
has no next-bar execution timestamp. Stale/forged hypothesis hashes,
cross-asset input and SEALED_OOS/VALIDATION datasets are rejected.
This is **not a trading simulation** and has no portfolio P&L,
transaction costs or action interface.

The exact exploratory QQQ raw daily dataset from 2020-2025 was read
through `ParquetDataProvider.read`: 1,508 bars, latest-revision provenance,
8 prepared non-executable academic hypotheses, signal-vector length
1,508 each, and unique research hashes. Two underlying entry/regime
combinations showed 684 and 210 positive bar-level intersections respectively.
These are **indicator conjunctions, not executed trades, profits or
independent results**. The replay expressly returns:
`NON_PIT_DEVELOPMENT_ONLY`, `executable=false`,
`strategy_ir_compatible=false`,
`benchmark_independently_verified=false`,
`sealed_oos_approved=false`.

**Non-negotiable next integration conditions:** the current production
`StrategyIR.IndicatorType` does not guarantee identical output semantics
for the new academic calculators. Do NOT alias a boolean signal to an
unrelated moving-average output or pass these feature vectors through
`series_data_path`, which is currently used for benchmark input.
A reviewed compiler/feature adapter, feature-level frozen version hashes,
independent benchmark series with publication `available_at` times,
corporate-action lineage and PIT vendor vintages are required before
the research candidate may enter the existing evaluator. The
`MarketSourceProvenance.revision_policy=latest` QQQ fixture **cannot**
meet PIT or independent OOS acceptance.

**Verification:** deterministic mocked HTTP replay, invalid and forged
DOI/title/year/count/hash, redirect, oversized responses, on-disk hash
tamper, verified-only composition, causal prefix replay, safe next-bar
alignment, future-bar perturbation and OOS blocking are covered.
The full repository regression is run separately; preserve exact
observed pass/fail counts rather than claim success before it finishes.


### P0-3 final test acceptance

- Full repository `pytest -q -p no:cacheprovider`:
  **1,196 passed, 0 failed in 375.89 seconds**.
- `mypy .`: **206 source files passed**.
- `ruff check .`: **PASS**.
- All P0 indicator research tests targeted: **37 passed, 0 failed**.
- Existing connected Quant research service separately queried:
  `READY`, `orders_enabled=false`.
- All changes remain on
  `feat/p0-indicator-research-engine-v1`. Operational baseline
  `docs/mcp-phase3-5-1-state-inventory` is unchanged at
  `4a7423327dfec940fd497f970c6db69ef42e95bc`.
- No StrategyIR production evaluator execution, benchmark performance
  comparison, PIT certification, sealed OOS evaluation, branch merge
  or order placement occurred.


## P0-4 local StrategyIR academic evaluation adapter (feature branch only)

Implemented `research.indicator_engine.strategy_adapter` after writing
failure-first research compiler acceptance tests. The module emits actual
canonical `StrategyIR` structures from *whitelisted, math-VERIFIED*
academic hypotheses. It passes precomputed academic feature vectors
under exact feature aliases to the existing local `BacktestEngine`.
It does **not** touch the protected `core/backtest`, `core/data`
or evaluator source code. No MCP/tool-plane change or order API exists.

**Current compatibility limits are deliberate and fail-closed:**

- Admits precisely one binary entry calculator
  (`time_series_momentum` or `previous_range_breakout`)
  and the validated `sma_direction` regime filter.
- Rejects all six academic risk-overlay combinations because the
  continuous volatility measure or dynamic exposure curve has no
  reviewed StrategyIR risk translation yet. In particular, it must not
  silently turn `volatility_managed_exposure` into static position sizing
  or mistake a variance estimate for a boolean trade signal.
- Uses a mandatory but **unreferenced** native 2-period SMA placeholder
  due to the existing StrategyIR minimum-indicator schema. The active
  conditions refer exclusively to reviewed academic feature vectors.
- Explicitly declared exploratory exit rule: close-confirmed exit when
  the academic entry signal drops to zero; not a reproduction of
  the original papers' complete trading rules.
- Cash-only baseline 100% position sizing without stop/profit targets;
  trading fee model: commission 1 bps, spread 2 bps,
  slippage 5 bps, matching local research defaults.
- Uses the existing `BacktestEngine` next-bar open execution
  (signal known at completed close on bar `t`, order-filled in
  the local simulation at bar `t+1` open).
- Recomputes dataset hash, StrategyIR hash, academic replay hash,
  replay timestamp mapping and feature arrays at the adapter boundary.
  Rejects tampering, sealed/validation inputs and unverified hypotheses.
- The compiled StrategyIR is confined to the local
  `evaluate_compiled_development` function. It is not exported through
  a broker interface, mutation engine, promotion path, batch worker
  or production StrategyIR registry. Reports mark
  `NON_PIT_DEVELOPMENT_RESULT`, `candidate_promotable=false`,
  `broker_executable=false`, `qqq_cagr_delta=None`,
  `pbo=None`, `dsr=None`, `out_of_sample_approved=false`.

**Measured development-only QQQ smoke test** with the previously loaded
2020-01-02–2025-12-31 raw 1,508-bar latest-revision dataset,
10,000 USD initial hypothetical equity:

| Research hypothesis | Buy/sell execution events | Total charged costs | Final marked equity |
|---|---:|---:|---:|
| Time-series momentum + SMA-direction regime | 11 | $93.27 | $17,150.13 |
| Prior trading-range breakout + SMA-direction regime | 232 | $1,588.99 | $8,340.52 |

These figures are *not* independently reproduced research alpha. They
are model-dependent in-sample/development observations, with no confirmed
PIT vendor vintages, transaction-market realism beyond the chosen fee
model, tested QQQ buy-and-hold excess return, certified independent
benchmark, or sealed OOS. The first result has 11 **execution events**,
not 11 completed round-trip transactions.

Required steps before further integration: independently reviewed
risk overlay semantics, no-lookahead multi-asset data, immutable
time-of-release metadata for external features, independent benchmark
verification, fold-train-only optimization, multiple-testing adjustment,
and a complete acceptance comparison against the preserved
`4a74233` baseline. None of these is claimed completed here.


### P0-4 verified final regression and Git boundary

- The complete repository regression run after the adapter and replay-integrity
  tests: **1,200 passed, 0 failed, 372.70 seconds**.
- Mypy: **207 source files PASS**; Ruff check: **PASS**.
- No upstream core/backtest, sealed OOS or order-gateway files changed.
- Feature revision commit `7e068f17e31e549b9d8e56d79ef57608714aef86`
  was pushed to `feat/p0-indicator-research-engine-v1`.
- Operating baseline remains `4a7423327dfec940fd497f970c6db69ef42e95bc`.
- All 6 academic risk-overlay combinations remain *uncompiled* because
  their execution/risk roles are not proven equivalent to existing native
  StrategyIR conditions; Champion promotion and production deploy remain
  disabled. No actual independent alpha or OOS performance claim.
