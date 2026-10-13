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
