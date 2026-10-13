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
