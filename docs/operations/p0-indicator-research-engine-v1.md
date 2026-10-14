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


## P0-5 isolated dynamic risk overlay research (2026-10-14 KST)

A **separate** `research.indicator_engine.risk_replay` module now models
causal, cash-only *dynamic exposure* on the existing research feature
replays. The protected `core/backtest`, StrategyIR runtime schema,
order tools, current MCP endpoint, sealed OOS and Champion frontier
have **not** been modified. These evaluations do not enter the ordinary
StrategyIR admission or production promotion path.

**Source semantics:**

- `garman_klass_variance` and `parkinson_variance` yield a measured
  **daily variance**, not a buy/sell signal or direct position fraction.
  Ex-ante exposure is `min(max_exposure, target_daily_variance / variance)`,
  zero risk history capped at the predetermined ceiling.
- `volatility_managed_exposure` **already** yields a 0..1 exposure
  using an internal `target_daily_variance` and
  `max_exposure`. Research policy may impose a smaller maximum
  but must **agree on the embedded variance target**; conflicting
  targets cause a hard failure rather than silently ignoring one.
- Entry and regime decisions must be from independently verified
  binary academic calculators. A positive regime condition permits
  a new entry. For an existing position, a negative regime condition
  alone does not force liquidation; a negative entry signal or
  missing/invalid risk estimate does. This preserves the reviewed
  entry/exit meaning of the earlier developer-only compiler.
- Features at close `t-1` may change holdings only at `t` open.
  Holdings are marked at `t` close. Transaction costs use 1 bp
  commission, 2 bps spread, 5 bps slippage per transaction.
  All purchases are funded from existing cash including expenses;
  short sales and margin are excluded.
- `rebalance_band` is an **absolute portfolio weight discrepancy**,
  3 percentage points in the recorded smoke test, not 3% of the
  previous weight. Closing an invalid/negative-signal position
  always takes priority over the deadband.
- Separate fields record the *desired fraction at each open* and the
  *actual marked fraction at each close*. The latter can drift
  above the requested target intraday without leverage; it is
  guaranteed within 0..1 as long as cash and shares stay nonnegative.
- The policy is immutable and bounded. Input fingerprints, signal
  replay and policy are hashed; final equity curve and trade details
  carry stable research-only evidence identifiers. No broker methods
  are called or permitted.

### Measured historical research smoke test

QQQ Tiingo raw daily 2020-01-02 to 2025-12-31 (1,508 bars),
**latest-revision data, NOT independently PIT certified**.
Initial notional 10,000 USD; variance target `0.0001` per day;
cash-only maximum invested `0.7` of equity; opening rebalance
deadband `0.03`. All prices and returns are illustrative
**development-only backtests**.

| Entry + SMA regime + risk overlay | Buy/sell events | Total model costs USD | Final marked equity USD |
|---|---:|---:|---:|
| TSMOM + Garman–Klass | 68 | 83.27 | 14,147.53 |
| TSMOM + Parkinson | 70 | 82.56 | 14,231.12 |
| TSMOM + vol-managed exposure | 127 | 116.12 | 14,613.49 |
| Range breakout + Garman–Klass | 241 | 1,108.34 | 9,103.59 |
| Range breakout + Parkinson | 236 | 1,102.18 | 9,146.34 |
| Range breakout + vol-managed exposure | 238 | 1,014.58 | 9,335.48 |

**Not a formal StrategyIR strategy run, not live fill quality and not
a sealed-OOS evaluation.** No realistic realized capital gains taxation,
funding, bid/ask depth, action availability vintages, corporate action
as-of certification or independent benchmark were established.
No statistical superiority or excess alpha is claimed. `events`
means individual buy/sell execution records, not completed
round-trip transactions.

The new tests validate the three risk indicator families, price
causality under future-bar perturbations, warm-up without trades,
reject-on-invalid parameters or OOS, no leverage, next-open fills,
deterministic replay, and refusal of an inconsistent pre-filtered
variance target. No new live order or promotion entrypoint exists.


### P0-5 verification and release boundary

- Broad repository regression process (collected before the last targeted
  policy mismatch test was appended): **1,207 passed / 0 failed**,
  **378.85 seconds**.
- Final-check `tests/research` run on the final feature-branch tree:
  **95 passed / 0 failed** including all 8 academic risk-overlay tests.
- Post-change `ruff check .`: **PASS**;
  `mypy .`: **208 files PASS**.
- Confirmed `docs/mcp-phase3-5-1-state-inventory` remote HEAD remains the
  unchanged rollback commit `4a7423327dfec940fd497f970c6db69ef42e95bc`.
- Production promotion, independent out-of-sample approval, broker orders,
  benchmark-alpha measurement, core risk-engine code modifications and
  protected-branch merge: **NOT PERFORMED**.
- Known limitation: risk overlays currently have a **research-only local
  simulator**, not canonical `StrategyIR` runtime risk translation.
  The mathematical estimator semantics, position rebalancing and return
  accounting must undergo additional independent review before any such
  compiler admission.

## P0-6 research risk contract and same-source market audit (2026-10-14 KST)

**Scope:** P0-1 risk accounting bridge and preliminary P0-2 integrity screening,
restricted to development-only, cash-funded single-asset observations.
No protected runtime module, broker adapter, promotion API, or sealed OOS is changed.

- `research.indicator_engine.risk_adapter` binds the reviewed binary
  entry/regime StrategyIR to a separately hashed, **non-native** dynamic risk
  sidecar. The ordinary StrategyIR schema is static-position-only, so this
  does **not** grant full native StrategyIR execution of a variable-weight
  strategy. It revalidates strategy, risk definition, model policy, replay,
  hashes and dataset before each research evaluation. Invalid/mutated plans
  are rejected. An independent ledger reconstructs open fills, fee model,
  funding, position fractions and marked equity. Its fee computation uses
  the shared reviewed `CostModel`; it is **not** an independently priced live
  execution benchmark or proof of exchange fill quality.
- `research.indicator_engine.market_audit` computes only an opening-price,
  first-day-funded, no-dividend **same-source raw-price reference**. It never
  identifies that reference as an authenticated benchmark or returns a
  promotion/point-in-time certificate, even when source metadata says `as_of`.
  A future independently verified and historically available data source is
  required to remove the certification blockers.
- Targeted acceptance (`tests/research/test_academic_risk_adapter.py`,
  `test_academic_market_audit.py` and earlier compiler/risk-replay tests):
  22 PASS, followed by Ruff and targeted mypy PASS. Tests reject forged
  cost/curve/target, mutated plans, conflicting volatility targets and
  sealed-zone inputs. Exact risk-ledger recomputation succeeds for all three
  academic risk estimators on the synthetic acceptance dataset.

**Observed Tiingo QQQ same-source smoke check:** 1,508 completed daily bars,
2020-01-02 through 2025-12-31; dataset fingerprint starts `328f1cbd8ac5`.
Market provenance is latest revision, raw OHLC (no independently verified
corporate actions or historical vintages). Starting with USD 10,000, the
price-only first-open buy-and-hold reference ends at **USD 28,629.61**.
All previously recorded two-signal canonical StrategyIR development runs
end at USD 17,150.13 and USD 8,340.52; six risk-overlay development runs
end between USD 9,103.59 and USD 14,613.49. The standalone risk-ledger
recalculation found **zero numerical disagreement in the marked equity**
for each of those six same-dataset runs. These are explicitly non-PIT,
non-independent, price-only, in-sample comparisons; the reference does not
include dividends and is **not** a return series matched for risk or a
claim about achievable excess alpha.

**Still blocked:** independently authenticated PIT market vintages and
corporate-action available-at lineage; a separate benchmark provider;
fold-trained walk-forward and sealed OOS; DSR/PBO/multiple-testing and
multi-market scenario sensitivity; independent native runtime risk semantics
review. Until all required gates pass, no branch merge, Champion promotion,
production release or live trading is authorized.

### Initial risk-policy sensitivity diagnostic (still in-sample)

For the QQQ time-series momentum + SMA regime + Parkinson estimator,
executed a predeclared 3×3 grid of daily variance targets
`0.00005 / 0.0001 / 0.0002` and absolute rebalance deadbands
`0.01 / 0.03 / 0.10`, with maximum exposure fixed at `0.70`.
Across the nine research runs, final marked equity ranged from
**USD 13,795.32 to USD 14,491.61**, execution events from **17 to 300**,
and charged model costs from **USD 66.67 to USD 137.31**.
None outperformed the same-source price-only USD 28,629.61 reference.
The observed sensitivity is descriptive only: **do not pick the best
in-sample policy as a validated strategy**. Volatility regimes, historical
execution friction, fold-trained parameters and true OOS remain untested.

### P0-6 final repository acceptance (2026-10-14 KST)

- Full `pytest -q -p no:cacheprovider` on the pushed feature tree:
  **1,218 passed / 0 failed in 442.79 seconds** (second full run).
- Earlier full run: **1,217 passed / 1 failed** in 452.35 seconds;
  the unrelated preexisting `tests/runtime/test_process_lifecycle.py::
  test_managed_process_identity_and_tree_termination` transiently failed its
  newly spawned child identity assertion; independent isolated rerun **PASS**.
  The final clean full run is the accepted evidence. No protected runtime
  source or test was modified in order to hide this transient observation.
- Repository-wide Ruff **PASS** and strict mypy **PASS, 210 files**;
  four targeted academic compiler/risk tests **22 PASS**.
- Commit containing the research adapter, market audit, tests and P0-6
  report: `5c62e6230fa6d6a4bb70c3a75c7e91b848be180a`.
- Scope guard remains active: no operating-baseline update, native dynamic
  StrategyIR activation, broker orders, independent PIT/OOS clearance or
  Champion promotion.

## P0-7 cross-vendor benchmark intake and fail-closed PIT audit (2026-10-14 KST)

**Added:** `research.indicator_engine.benchmark_reconciliation` plus an offline
`audit-benchmark` research CLI command. A source marked `as_of` by its own
vendor is **not** independently proven historical point-in-time evidence.
The audit strictly refuses a same-vendor comparison, identical historical
OHLCV payload, mismatched corporate-action conventions, incomplete NY
exchange-session coverage, duplicate sessions, cross-symbol substitution,
sealed OOS and missing source metadata. It never joins absent bars by
forward-fill and never upgrades to an approved independent benchmark.

Accepted different-provider input computes only *development* first-open
cash-funded, same-session price-only references and close-price disagreement,
all tied to an immutable hash of the two dataset snapshots and costs.
`point_in_time_verified`, `independent_benchmark_verified`,
`candidate_promotable` and `sealed_oos_approved` remain hard `false`
even for seemingly aligned vendor declarations. Additional independent
source authentication, bar-level publication/availability times, actual
corporate-action vintages and verified total-return treatment remain required.

**Manual offline command (no research database or network needed):**

```bash
.venv/bin/python -m research.indicator_engine.cli audit-benchmark \
  data/market/tiingo/QQQ_2020-01-02_2025-12-31_raw.parquet \
  path/to/a-separately-acquired-vendor-QQQ.parquet
```

Real local QQQ negative test with the same 1,508-bar Tiingo file passed twice:
`RECONCILIATION_BLOCKED`, exit code 2, `same_vendor_identity` and
`identical_ohlcv_payload`. No benchmark equity is emitted in blocked state.
A *separate authenticated QQQ source has not been installed*. Public endpoint
attempts on 2026-10-14 returned an anti-automation verification page for
Stooq and HTTP 429 for Yahoo Chart, so no CSV was misrepresented as sourced
market data. The unrelated previous same-source QQQ comparator is unchanged.

Priorities after this stage: provision independently licensed and verifiable
same-security historical data with versioned acquisition evidence; obtain
bar-level available-at and corporate-action revisions; reconcile market
prices on a real second source; only then evaluate fold-trained OOS/PBO/DSR.
No operational StrategyIR schema update, protected core modification,
production deploy, or order routing.

### P0-7 final acceptance

- Complete final-tree regression: `pytest -q -p no:cacheprovider`,
  **1,227 passed, 0 failed, 412.96 seconds**.
- Focused benchmark and earlier audit tests: **12 passed**.
- Repository-wide Ruff **PASS**, strict mypy **PASS on 211 source files**.
- Native broker, production MCP, protected evaluator, independent PIT/OOS
  datasets and operating baseline remain unchanged.

## P0-8 external Nasdaq QQQ capture and reproducible two-source replay (2026-10-14 KST)

**Actual external acquisition:** A bounded manual request to Nasdaq's public
`/api/quote/QQQ/historical?assetclass=etf&fromdate=2020-01-02&todate=2025-12-31&limit=4000`
returned **1,508 rows** (same sessions as the existing Tiingo file). The Nasdaq
response was retrieved at `2026-10-14T04:26:10.007887+00:00` and preserved as an
ignored raw JSON capture, a versioned development-only Parquet snapshot and an
append-only capture manifest. Original JSON SHA256:
`6ede5c3b5b9926b9d820268aa607b41c3c0cfe60141a0ace13302a42f7193f40`.
Parsed dataset SHA256:
`2a423bebcdcc5f5ad29178de353fd7a12eb7a415227a2e3fb1eb98823003f5be`.
Source IDs are `tiingo` and `nasdaq-public`, not a synthetic re-labelled file.
Captured bytes, Parquet and manifest reside under ignored `data/market/nasdaq/`
and `state/indicator-engine/source-captures/`; **not GitHub market-data files**.

**Engineering:** `nasdaq_source` enforces strict schema and complete records;
`nasdaq_capture` replays that parser against the exact preserved response bytes.
The offline `capture_integrity` verifier rehashes raw data, reconstructs the
historical rows and compares against immutable manifest references and Parquet.
Integrity replay on the real capture: `LOCAL_CAPTURE_BYTES_VERIFIED`, all
**1,508 rows**. The reconciliation also corrects the historical daily-bar
session convention: `00:00 UTC` is the exchange session **date label**, not an
actual midnight exchange timestamp. This prevents an accidental prior-day
New York timezone shift; separately supplied New York close-time bars are
normalized to the equivalent exchange-local date.

**Actual cross-source development observations (Tiingo vs Nasdaq):**

| Field | Sessions with numeric difference | Maximum absolute difference |
|---|---:|---:|
| Open | 103 | USD 0.35 |
| High | 15 | USD 0.005 |
| Low | 18 | USD 0.005 |
| Close | 0 | USD 0.00 |
| Volume | 1,385 | 5,107,354 shares |

Both datasets contain exactly 1,508 matching trading dates; 0 missing sessions.
The two data-series' first-open raw-price-only buy-and-hold references both
end at **USD 28,629.61**, starting with USD 10,000 under the previously
specified development cost assumptions. The data discrepancy metrics were
added to the audit's hashed report. This does **not** reconcile historical
volume, dividend returns or independently validate execution prices.

**Research safeguards:** Nasdaq currently exposes a *latest-revision* historical
series without the vendor release-time vintages or independently certified
corporate-action history required for PIT. `point_in_time_verified=false`,
`independent_benchmark_verified=false`, `candidate_promotable=false` and
`sealed_oos_approved=false` still hold. Separate fetching does not prove
vendor supply-chain independence, accurate past availability or total returns.
No OOS sealing, Champion promotion, protected engine change, production deploy,
branch merge or live order is permitted from these research-only captures.


**Offline verification command** (no HTTP or research DB):

```bash
.venv/bin/python -m research.indicator_engine.cli verify-nasdaq-capture \
  --output data/market/nasdaq/<capture>.parquet \
  --raw state/indicator-engine/source-captures/<capture>.raw.json \
  --manifest state/indicator-engine/source-captures/<capture>.manifest.json
```

The capture verifier rejects modified raw bytes, mutated Parquet, false PIT
approval flags and substituted source paths; **local integrity validation is
not independent historical PIT certification**.

### P0-8 final validation and preservation boundary

- Full repository `pytest -q -p no:cacheprovider`: **1,262 passed, 0 failed,
  386.57 seconds** on the final implementation tree.
- Targeted Nasdaq source, capture, integrity, and cross-vendor tests: **43 PASS**.
- Repository-wide Ruff **PASS**, strict mypy **PASS on 214 source files**.
- The research branch is the only intended Git destination. Baseline `4a74233`
  is never reset, force-pushed or merged. Raw Nasdaq and derived market snapshots
  are ignored, local-only, and must not enter GitHub. Future OOS/PIT release gates
  remain blocked pending historical vintages and certified corporate actions.

### P0-8 final acceptance

- Full regression `pytest -q -p no:cacheprovider`: **1,262 passed, 0 failed,
  383.88 seconds**; focused Nasdaq/audit tests: **44 PASS**.
- Repository-wide Ruff: **PASS**; strict mypy: **PASS, 214 source files**.
- Real archived Nasdaq QQQ capture integrity: **1,508 rows PASS**;
  cross-source date comparison 1,508/1,508 and raw close-price difference 0.
- Development-only; historical PIT, independent vendor-lineage certification,
  total-return adjustment, sealed OOS, Champion and broker routes not approved.

## P0-9 dividend/payment audit and rolling forward research (2026-10-14 KST)

**Cash actions:** Nasdaq's publicly reachable `api/quote/QQQ/dividends?assetclass=etf`
returned a 9,736-byte, current-revision dividend table. Its captured response
is preserved as ignored local-only JSON + an append-only hash manifest under
`state/indicator-engine/source-captures/`; the two-file manifest replay detects
bytes/metadata tampering. Requested ex-dates 2020-01-02–2025-12-31 yielded
**25 USD cash distribution events**, of which **24 have no declaration date**
in the Nasdaq response. The original raw response SHA-256 begins
`c7bca224b189d499` and the local evidence identity starts `15d736d6d98b93c9`.

The research-only cash distribution comparator buys QQQ at the first observed
open, credits cash only for shares held **strictly before the ex-date**, and
counts it only once the **payment date** has occurred within the sample.
It does not retroactively treat an unpaid distribution as cash, silently
reinvest income, assume a corporate split has not occurred, or include taxes.
With initial USD 10,000, that produces the following development-only
retrospective illustrative marked values on the Tiingo daily raw file:

| Baseline interpretation | Ending marked value |
|---|---:|
| Raw-price buy and hold (costed purchase, no distributions) | USD 28,629.61 |
| Raw-price buy and hold plus 25 paid cash distributions, no reinvestment | USD 29,270.22 |
| Incremental distribution cash | USD 640.60 |

**No trade-time PIT certificate**: original dividend declaration dates are
mostly absent; historical publication availability is not proven, and the
Nasdaq historical snapshot is latest-revision. The Nasdaq split route
`api/quote/QQQ/splits` returned HTTP 404; this does **not** prove there were
no splits. Split/corporate-action coverage, adjusted total return, actual
available-at vintage and complete exchange evidence remain unverified.
`DividendEvidence.is_available_for_decision` uses the observed 2026 snapshot
time, never a backfilled ex-date; retrospective payout reconstruction does
not authorize use of the downloaded table in past trading decisions.

**Chronological forward diagnostic:** Training-only canonical StrategyIR
selection was added in `research.indicator_engine.walkforward` using the
existing (protected, unchanged) costed BacktestEngine with
`signal_start_at=test_start`. Each expanding training prefix selects the
higher-scoring one of two previously VERIFIED entry signals:
`time_series_momentum` or `previous_range_breakout`, with a fixed
`sma_direction` regime filter. The runner prevents any pretest positions,
regenerates causal feature vectors using only each fold's prefix, resets
capital at fold boundaries, enforces non-overlapping test periods, and
stitches returns by multiplying independent fold multipliers.

Real QQQ 2020–2025 input, fixed 756 training bars and 252 test bars (last
partial window 248 bars), initial cash USD 10,000 and the prior cost model:

| Forward development fold | Selected entry | Strategy net ending value | Raw-price-only fold reference |
|---|---|---:|---:|
| 2023-01-03–2024-01-03 | Time-series momentum | USD 12,294.15 | USD 14,815.25 |
| 2024-01-04–2025-01-03 | Time-series momentum | USD 12,892.57 | USD 13,070.46 |
| 2025-01-06–2025-12-31 | Time-series momentum | USD 10,438.50 | USD 11,713.65 |
| **Chained three research folds** | — | **USD 16,545.36** | **USD 22,682.57** |

This explicitly **fails the price-only comparator**. The fold benchmark buys
at the first test open; the selected strategy first becomes eligible for
entry at the first test close with next-open execution. Comparative numbers
are consequently illustrative diagnostics, not identical fill timing.
This uses already-inspected latest-revision 2020–25 data rather than held-back
historically authenticated PIT; it is **not** independently sealed OOS.
PBO/DSR and fully separate independently audited test vintages are pending.
No Champion promotion, broker permission, live orders, protected core edit,
production merge or deploy is authorized by this experiment.

**Cross-vendor forward replay:** The same fixed three chronological research
folds were independently evaluated using the separately archived Nasdaq QQQ
Parquet snapshot. The two latest-revision sources produced the *same*
selected entry signals (time-series momentum in all three folds), the same
trade counts (5/1/3), and the same final compounded USD 16,545.36 strategy
and USD 22,682.57 price-only comparison at displayed cents precision.
This is a useful source-sensitivity sanity check, **not** proof of feed
independence, correctness of corporate actions or historical PIT compliance.

**P0-9 final acceptance (2026-10-14 KST):** the full repository
`pytest -q -p no:cacheprovider` reports **1,272 passed / 0 failed**
(384.13 seconds). New cash-action and walk-forward focused tests report
**10 passed**; Ruff passes and strict mypy passes on **216 source files**.
Both price vendors give the same rounded three-fold forward diagnostics.
The cash event raw payload and source manifest remain locally archived and
Git-ignored, not part of the source branch. No sealed OOS evaluation has
been authorized or executed. The remaining hard blockers are audited PIT
historical bars with available-at metadata, independently verified corporate
split/revision evidence, separate never-inspected OOS, PBO/DSR and independent
risk+strategy evaluation. No production merge or broker order.

## P0-10 causal underperformance attribution and passive benchmark hurdle (2026-10-14 KST)

**Question:** Why did the originally selected academic entry + SMA regime earn
less than QQQ raw-price passive holding in three rolling development folds?
An independent read-only research fill replay partitions each forward fold
into invested versus flat sessions and sums descriptive daily market moves.
It enforces market date and execution-price integrity, no sell beyond held
shares, and never accesses sealed OOS, broker routes or protected engine code.

| Forward fold | Invested bars | Flat/cash bars | Fees paid | Trades | Observed flat-day market log return |
|---|---:|---:|---:|---:|---:|
| 2023-01-03 onward | 168 / 252 | 84 | USD 40.00 | 5 | +0.202859 |
| 2024-01-04 onward | 249 / 252 | 3 | USD 8.00 | 1 | +0.021643 |
| 2025-01-06 onward | 235 / 248 | 13 | USD 20.43 | 3 | +0.072738 |

**Diagnosis:** A 252-day time-series momentum entry and long-only market
regime cannot readily participate during early trend transitions. In the
2023 fold, the first long position occurred only 2023-04-28; 2025's QQQ
position exited 2025-04-07 and did not re-enter until 2025-04-24. Missed
participation, delayed re-entry, and cash drag were important alongside the
measured transaction costs. *Flat-day market log return is diagnostic and
cannot be converted into achievable missed profit*, because overnight gaps
and the next-open execution boundary differ.

**Causal research improvement (opt-in):**
`run_development_walkforward(..., include_passive_challenger=True)` allows
an unconditional, cash-funded raw-price buy-and-hold candidate to compete
against the two VERIFIED academic entry hypotheses. The choice is determined
**only by historical training-prefix net results**, with stable tie-breaking
and no test-window access. A passive decision is executed at the first test
open; it is a comparator path, not a broker-executable StrategyIR. Existing
research behavior remains the default (`False`). A different falling-market
fixture confirms the guard does *not* always force passive exposure.

| Retrospective development test | 3-fold compounded final value (USD 10,000 start) |
|---|---:|
| Existing active-only signal selection | USD 16,545.36 |
| Training-only passive challenger, three folds each choose passive | USD 22,682.57 |
| Passive raw-price comparator in the same three folds | USD 22,682.57 |

**Interpretation:** This is an improvement in rejecting uncompetitive active
signals, **not new alpha or proof of risk-adjusted superiority**. The gated
result exactly equals simple passive investment and still excludes dividends.
The independently captured *Nasdaq* dataset gives the same displayed results
and selected fold choices as *Tiingo*. The 2020–25 data were already studied;
this experiment cannot claim to be a never-inspected holdout. Future research
must beat a matched passive opportunity-cost baseline *after* costs, verify
risk and loss protection, and pass sealed PIT OOS before any strategy promotion.
No run here initiates a live order or alters canonical backtesting, trading,
source data or risk-engine permissions.

**Risk nuance (research-only, no risk-adjusted promotion):** On the same
three test intervals, direct equity-series maximum drawdown and annualized
close-to-close realized volatility were:

| Development fold | Active max DD / vol | Passive max DD / vol |
|---|---|---|
| 2023 | −10.91% / 13.18% | −10.91% / 17.88% |
| 2024 | −13.56% / 17.87% | −13.56% / 17.96% |
| 2025 | −24.32% / 19.31% | −22.88% / 23.39% |

The guard chooses solely on *training* terminal dollars and does not certify
better risk-adjusted returns or crash resilience; therefore it is explicitly
**opt-in** and not a live risk engine replacement. These diagnostics use
mark-to-market holdings from the canonical execution model and exclude
unverified dividends. The 2025 active portfolio experienced a deeper marked
peak-to-trough decline despite somewhat lower realized volatility.

**P0-10 acceptance:** `pytest -q -p no:cacheprovider`: **1,279 passed,
0 failed**, 384.57 seconds; focused guarded-forward and diagnostic tests
**10 passed**; repository-wide Ruff **PASS**, mypy **PASS on 217 source
files**. Both vendor series produce identical displayed benchmark-hurdle
results. This update is on a feature branch only, does not merge production
code, and does not approve any novel alpha strategy or deploy a broker order.
