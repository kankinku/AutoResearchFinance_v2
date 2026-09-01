# Quant Autoresearch Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete `LLM-assisted Autonomous Quant Research Harness` described in `docs/architecture/quant-autoresearch-architecture-v1.0.md`, including Strategy IR, mutation and search, parallel isolated backtests, immutable evaluation, robustness statistics, frontier/champion/rescue memory, generation orchestration, and the isolated KIS deployment boundary.

**Architecture:** Strategy IR is the only canonical strategy representation. Local deterministic components validate, mutate, compile, schedule, execute, cache, evaluate, and persist experiments; the LLM only emits research intent, interprets compact summaries, and proposes new primitives. `core/data`, `core/backtest`, `core/evaluator`, `core/validation`, `core/costs`, and `core/integrity` are protected from agent writes, while KIS order execution is a separate trust boundary requiring human approval.

**Tech Stack:** Python 3.12, Pydantic v2/JSON Schema, PyYAML, SQLite, DuckDB/Parquet, pandas/numpy/scipy, scikit-learn, Docker Engine, pytest/Hypothesis, mypy or BasedPyright, Ruff, and a pluggable LLM client. The first local scheduler uses asyncio plus process workers; Bayesian parameter search is implemented locally with a deterministic sklearn-compatible surrogate and does not require Ray/Celery.

---

## A. Understanding of the Request

The pasted architecture is the complete target specification, not a request to produce a reduced V1. The implementation must cover all 25 sections:

1. system roles and trust boundaries;
2. reuse/adaptation of the existing KIS backtester concepts;
3. Strategy IR as Single Source of Truth;
4. mutation operations;
5. imported/normalized/primitive/generated/champion strategy library;
6. resource-aware parallel workers;
7. read-only shared data and isolated run outputs;
8. content-addressed experiment cache;
9. separate structure and parameter search;
10. generation-level LLM calls;
11. local result analysis and compact context;
12. immutable evaluator access restrictions and hashes;
13. development/validation/sealed-OOS data zones;
14. fast/full/robustness/validation funnel;
15. transaction-cost, stress, walk-forward, CPCV/CSCV, DSR, PBO, and complexity checks;
16. CRASH through CHAMPION state machine;
17. family-preserving Frontier and exploit/explore/crossover/rescue policy;
18. raw/knowledge/LLM memory layers;
19. SQLite/Parquet/JSON storage;
20. meaningful Git snapshots, commits, and tags;
21. research/deployment/KIS separation;
22. repository layout;
23. canonical generation loop;
24. conditional LLM invocation and plateau detection;
25. five non-negotiable design principles.

The current repository is an empty initial `master` checkout except for `.omx`; therefore discovery must verify whether a KIS/backtester exists elsewhere, and the plan must provide a self-contained adapter and local engine when it does not. No requirement is removed because that discovery is unresolved.

## B. Gaps and Ambiguities

- The source document does not specify a KIS repository path, market-data vendor, asset universe, calendar, or Docker image digest. These are configuration inputs, not blockers: the implementation creates explicit adapters and fails closed when a required provider/configuration is absent.
- The source document names both CPCV and CSCV. The evaluator will implement both algorithms behind one `ValidationMethod` interface and record which one is active in the evaluator version.
- The source document says Bayesian search is optional. The user's instruction requires no omission, so Bayesian search is included as a first-class local search strategy alongside grid and random search.
- The LLM provider and credentials are unspecified. The harness will define a provider-neutral interface, a deterministic offline director fixture, and a configured live provider adapter; missing credentials disable only live LLM generation and never bypass local research or evaluation rules.
- The existing `.omx` directory is untracked. It is preserved and excluded from the implementation's generated artifacts unless repository policy explicitly says otherwise.

## C. Clarifying Questions

No clarification is required before writing the plan. The items above are resolved as explicit configuration and fail-closed behavior so implementation can proceed without silently choosing a market, broker, or live-trading policy.

## D. Structured Specification

### Goal

Continuously discover, test, statistically challenge, and remember investment strategies with a reproducible local runtime, an LLM that chooses research direction rather than code, and no path from the research agent to live orders.

### Context

The architecture extends the current KIS/backtester concepts (`parameters`, `indicators`, `entry`, `exit`, `risk`, parameter optimization, Docker isolation, and run IDs) into a complete autonomous research platform. Generated Python is an artifact; Strategy IR, hashes, evaluator versions, data versions, and promotion records are the durable research truth.

### Scope

- Complete repository scaffold and developer tooling.
- Strategy IR schema, parser, validator, compiler, primitive registry, and provenance.
- Source import and normalization for YAML/Python/PineScript/Backtrader/structured research notes with raw-source provenance boundaries.
- Parameter grid, random, and Bayesian search; structural mutation; crossover; strategy combination; deduplication and cache.
- Shared read-only data mounts, Docker Lean workers, resource-aware scheduling, retries, cancellation, resume, and result queues.
- Immutable core backtest/evaluator/cost/integrity contracts with tamper-evident hashes.
- Funnel evaluation and all robustness/statistical layers named in the architecture.
- Full state machine, family-preserving Frontier, Champion, Rescue Pool, and configurable exploration policy.
- Raw experiment, statistical knowledge, and compact LLM memory persisted to SQLite/Parquet/JSON.
- Generation-level LLM director, local context builder, plateau/new-family/new-primitive triggers, and offline deterministic mode.
- Git snapshot/tag automation for Frontier/Champion only.
- Research-to-paper-to-live promotion gates and KIS adapter with order permission denied by default.
- CLI, observability, operational recovery, documentation, fixtures, integration tests, property tests, benchmark tests, and security tests.

### Out of Scope

- Choosing a profitable market strategy on behalf of the user.
- Guaranteeing future returns or treating backtest results as investment advice.
- Unattended live order submission. The live adapter may validate and simulate an approved deployment contract, but a human approval token is mandatory before any order-capable process can be enabled.
- Storing secrets, credentials, session logs, or raw external source prose in the repository.

### Constraints

- Strategy mutation must operate on validated IR, never by free-form LLM edits to Python.
- The evaluator, data contract, cost model, integrity checks, and sealed OOS data are immutable to the Research Director.
- Experiments must be reproducible from canonical IR, parameters, symbols, date ranges, dataset version, evaluator version, cost model version, and seed.
- Shared historical data is mounted read-only; run output directories are unique and isolated.
- LLM receives compact local summaries, not full result tables or raw market data.
- Research and trading processes have separate permissions, packages, and configuration.
- Every stage has a machine-verifiable pass/fail gate; no silent fallback converts a failure into a result.

### Assumptions

- Python is the implementation language and Docker is available for isolated Lean execution.
- Local storage is sufficient for SQLite metadata and generation-level Parquet result partitions.
- Market data can be supplied through a versioned `DataProvider` adapter; a fixture provider is used for tests.
- KIS integration can be added through an API adapter without importing order credentials into research workers.
- All random generators accept an explicit seed and record it in the experiment manifest.

### Inputs and Outputs

Inputs are research policy/program files, strategy sources, primitive definitions, versioned market data, search requests, optional LLM research intent, and explicit human promotion approvals. Outputs are validated IR, candidate manifests, isolated worker artifacts, immutable evaluation records, generation Parquet partitions, SQLite experiment history, Frontier/Champion/Rescue/Knowledge JSON, audit logs, Git snapshots/tags, paper-trading reports, and deployment approval records.

### User/System Flow

```text
Human policy/program
  -> Director intent (optional/triggered)
  -> local planner
  -> structure/parameter candidate generation
  -> hash/cache/deduplicate/validate
  -> fast worker funnel
  -> full backtest
  -> robustness + validation + sealed-OOS promotion gate
  -> local metrics and state update
  -> raw/knowledge/LLM memory
  -> compact generation summary
  -> next generation or plateau/new-family/new-primitive trigger
  -> explicit human approval -> paper -> live validation -> KIS boundary
```

### Acceptance Criteria

- A clean checkout can create a generation from fixtures using offline LLM mode and reproducibly produce the same candidate hashes, metrics, states, and memory checksums.
- Every architecture section has an implementation task, test, and evidence artifact mapped in the traceability table below.
- A strategy has no executable path unless it passes IR schema, semantic validation, data integrity, and evaluator contract checks.
- A Research Director cannot modify protected evaluator/data/cost/integrity modules or read sealed OOS data through its context builder.
- Duplicate experiments return `CACHE_HIT` with the original result and do not start a worker.
- Worker failure, timeout, cancellation, and retry exhaustion produce explicit `CRASH`/`REJECT` records and never appear as valid performance.
- The funnel evaluates only candidates admitted by each gate, records exclusion reasons, and preserves `NEAR_MISS` mutations in Rescue Pool.
- Champion selection is multi-objective and family-aware; Frontier does not collapse to one greedy champion.
- KIS order submission is impossible from the research process and requires a separate signed human approval artifact.
- Unit, property, integration, security, determinism, data-leakage, and end-to-end tests pass; lint/type checks pass; benchmark output records throughput and resource limits.

### Edge Cases

- Empty or contradictory IR; unknown indicator/operator; cyclic indicator dependency; invalid period/range; impossible entry/exit logic.
- Duplicate operations, duplicate candidates, equivalent YAML key order, floating-point normalization, and cache-version mismatch.
- Missing data, gaps, timezone/calendar mismatch, split/dividend adjustment mismatch, look-ahead access, and sealed-OOS access attempts.
- Docker unavailable, worker killed, corrupt result, stale queue lease, out-of-memory pressure, partial generation, retry exhaustion, and process restart.
- Zero trades, too few trades, infinite/NaN metrics, negative/zero denominator metrics, excessive turnover, and cost model failure.
- Parameter sensitivity with one valid point, failed folds in walk-forward/CPCV/CSCV, PBO with insufficient combinations, DSR with insufficient trials, and non-comparable objective vectors.
- Empty Frontier/Champion/Rescue/Knowledge stores, plateau at generation one, all candidates rejected, and no LLM credentials.
- Unauthorized KIS configuration, expired human approval, stale champion hash, deployment artifact mismatch, and paper/live drift.

### Risks

- Overfitting and multiple testing: separate data zones, funnel gates, DSR/PBO, CPCV/CSCV, complexity penalty, and trial-count recording.
- Data leakage: immutable sealed OOS provider, access tests, date-boundary assertions, and process-level permissions.
- Evaluator gaming: protected modules, evaluator hash, signed version manifest, and security tests.
- False reproducibility: canonical serialization, explicit seeds, dependency/image digests, and deterministic fixture replay.
- Resource exhaustion: adaptive concurrency, memory/CPU limits, queue backpressure, timeout, and resumable leases.
- Corrupted state: SQLite transactions, checksums, atomic JSON replacement, Parquet manifest, and recovery command.
- Unsafe trading: separate package/process, no credentials in research, approval token, paper gate, and order-capability integration test.

### Open Questions

The deployment configuration must supply the real data provider, symbol universe, calendar, date ranges, Docker image digest, KIS environment, and LLM endpoint before the corresponding deployment gate is marked PASS. The implementation defines validation schemas and sample fixture values for each so these choices cannot remain implicit.

## E. Detailed Implementation Plan

### Recommended Approach

Implement bottom-up in TDD-gated slices. Begin with contracts, canonical serialization, and protected boundaries; then build IR and mutation; then candidate planning/cache; then isolated execution; then immutable evaluation and funnel selection; then memory and generation orchestration; finally KIS/deployment and operational packaging. Each task ends with focused tests, a full relevant test command, and one atomic Git commit. No stage is considered complete without its evidence artifact and traceability update.

### File Map

The implementation creates the following responsibility-bounded files and directories:

```text
AGENTS.md
README.md
pyproject.toml
research/program.md
research/policy.yaml
research/objectives.yaml
research/llm/director.py
research/llm/context_builder.py
research/llm/provider.py
strategies/{primitives,templates,imported,normalized,generated,champions}/
strategy_ir/schema.py
strategy_ir/parser.py
strategy_ir/validator.py
strategy_ir/compiler.py
strategy_ir/normalizer.py
mutation/{engine,operations,parameter,structural,crossover,primitive_registry}.py
experiments/{planner,candidate_generator,deduplicator,cache,manifest}.py
runtime/{scheduler,queue,worker_pool,lean_worker,resource_manager,recovery}.py
runtime/docker/{Dockerfile,lean-worker-entrypoint.sh}
core/data/{contracts,provider,partitions,access}.py
core/backtest/{engine,adapter,result_contract}.py
core/evaluator/{contract,immutable_guard,version}.py
core/validation/{gates,walk_forward,cpcv,cscv}.py
core/costs/{model,slippage}.py
core/integrity/{hashes,signatures,audit}.py
evaluation/{metrics,robustness,sensitivity,regimes,pareto,scoring,selector}.py
memory/{experiment_store,knowledge,compressor,rescue_pool,state_files}.py
state/{experiments.sqlite,champion.json,frontier.json,knowledge.json,rescue_pool.json}
orchestration/{generation,plateau,policies}.py
integrations/kis/{research_adapter,paper_adapter,live_gate,permissions}.py
deployment/{paper,live}/
cli.py
tests/{contracts,strategy_ir,mutation,experiments,runtime,core,evaluation,memory,orchestration,integrations,security,fixtures}/
docs/{architecture,operations,runbooks,traceability}.md
```

### Task 1: Repository Contract, Tooling, and Traceability

**Files:**
- Create: `AGENTS.md`, `README.md`, `pyproject.toml`, `.gitignore`, `docs/traceability.md`
- Create: `tests/fixtures/`, `tests/test_repository_contract.py`

- [ ] **Step 1: Define the repository contract.** Document Python version, commands, protected paths, generated paths, secret policy, and the rule that `.omx` is preserved but never treated as application state.
- [ ] **Step 2: Add the executable quality configuration.** Configure pytest, Ruff, type checking, coverage, Hypothesis, and package discovery in `pyproject.toml`; configure `.gitignore` to exclude credentials, caches, Docker output, local state locks, and raw source dumps.
- [ ] **Step 3: Write the repository contract test.** Assert required directories, protected-module list, `state/` file names, and absence of tracked secret patterns.
- [ ] **Step 4: Run the baseline gate.** Run `python -m pytest tests/test_repository_contract.py -q`, `ruff check .`, and the configured type checker; expected result is PASS with the scaffold only.
- [ ] **Step 5: Commit.** Commit `chore: establish quant autoresearch repository contract`.

### Task 2: Policy, Canonical Serialization, and Integrity Boundary

**Files:**
- Create: `research/program.md`, `research/policy.yaml`, `research/objectives.yaml`
- Create: `core/integrity/hashes.py`, `core/integrity/signatures.py`, `core/integrity/audit.py`, `core/evaluator/version.py`, `core/evaluator/immutable_guard.py`
- Test: `tests/contracts/test_policy_and_integrity.py`, `tests/security/test_protected_boundary.py`

- [ ] **Step 1: Define policy schemas and fixture values.** Include data zones, allowed mutation operations, exploit/explore/crossover/rescue ratios, fast/full/robustness thresholds, retry/timeouts, resource limits, LLM trigger rules, and KIS approval requirements. Ratios are validated to sum to 1 and remain editable by policy, not code.
- [ ] **Step 2: Implement canonical serialization and hashes.** Serialize JSON/YAML-derived values with sorted keys, normalized decimals, UTC timestamps excluded from content hashes, and explicit version fields. Implement `strategy_hash`, `experiment_hash`, `data_hash`, `engine_hash`, `evaluator_hash`, and `cost_model_hash`.
- [ ] **Step 3: Implement audit records and protected-path checks.** Every mutation, compile, run, evaluation, promotion, and deployment event records actor, input hashes, output hashes, policy version, and reason. `immutable_guard` rejects writes and import-time monkey patches against protected core paths.
- [ ] **Step 4: Test tamper evidence and policy validation.** Mutating one input byte changes the expected hash; key order does not; evaluator/data/cost changes invalidate cache; invalid ratios, sealed-OOS reads, and protected writes fail closed.
- [ ] **Step 5: Run and commit.** Run the two focused test files plus `pytest tests/contracts tests/security -q`; commit `feat: add policy and immutable integrity contracts`.

### Task 3: Strategy IR Schema, Parser, Validator, Compiler, and Primitive Registry

**Files:**
- Create: `strategy_ir/schema.py`, `strategy_ir/parser.py`, `strategy_ir/validator.py`, `strategy_ir/compiler.py`, `strategy_ir/normalizer.py`
- Create: `mutation/primitive_registry.py`, fixture IR under `strategies/primitives/` and `strategies/templates/`
- Test: `tests/strategy_ir/test_schema.py`, `test_parser.py`, `test_validator.py`, `test_compiler.py`, `tests/contracts/test_ir_json_schema.py`

- [ ] **Step 1: Define typed IR models.** Implement strategy identity/family/generation/parents, indicator nodes, boolean conditions, entry/exit, risk, research metadata, provenance, and optional regime filters. Reject unknown fields unless an explicit schema version supports them.
- [ ] **Step 2: Implement canonical parse/normalize.** Accept YAML and JSON, normalize aliases and numeric formats, preserve source provenance/hash, and produce one deterministic `StrategyIR` object.
- [ ] **Step 3: Implement semantic validation.** Check references, periods, operator types, AND/OR arity, indicator dependency acyclicity, risk bounds, position sizing bounds, and no forward-looking indicator inputs.
- [ ] **Step 4: Implement compiler output.** Compile valid IR into a sandboxed Lean/Python artifact with a manifest containing the IR hash and compiler version; compilation never changes the canonical IR.
- [ ] **Step 5: Register all named primitives.** Register SMA/EMA cross, RSI, MACD, ATR, ADX, Bollinger, volume breakout, 52-week high, volatility/regime filters, stop/take-profit/trailing stop, and position sizing with typed parameter domains.
- [ ] **Step 6: Test valid, invalid, cyclic, and deterministic cases.** Include the exact architecture example and cases for unknown ops, null trailing stop, equivalent key order, and compile artifact hash stability.
- [ ] **Step 7: Run and commit.** Run `pytest tests/strategy_ir tests/contracts/test_ir_json_schema.py -q`; commit `feat: establish Strategy IR and compiler`.

### Task 4: Strategy Import, Normalization, and Library Provenance

**Files:**
- Create: `strategies/imported/README.md`, `strategy_ir/normalizer.py`, `strategies/library_manifest.json`
- Create: `strategies/importers/{yaml_importer,python_importer,pine_importer,backtrader_importer,note_importer}.py`
- Test: `tests/strategy_ir/test_importers.py`, `tests/contracts/test_provenance.py`

- [ ] **Step 1: Implement source adapters.** Parse supported source formats into an intermediate record containing source type, source hash, license/provenance metadata, extracted signals, and confidence; unsupported constructs are explicit `UNSUPPORTED`, never silently dropped.
- [ ] **Step 2: Normalize into IR or a review queue.** Fully mappable strategies become `normalized`; incomplete strategies retain their provenance and a machine-readable rejection reason. Raw source remains outside generated research artifacts unless the user explicitly supplies it as a project source.
- [ ] **Step 3: Build the library manifest.** Record IDs, family, source hash, IR hash, status, and normalized file path for imported/normalized/generated/champion entries.
- [ ] **Step 4: Test all five adapter paths and provenance boundaries.** Verify no distinctive source text is copied into generated IR, unsupported syntax is surfaced, and source hash changes invalidate normalization.
- [ ] **Step 5: Run and commit.** Commit `feat: add strategy library import and normalization`.

### Task 5: Mutation, Structure Search, Parameter Search, Crossover, and Candidate Validation

**Files:**
- Create: `mutation/operations.py`, `mutation/engine.py`, `mutation/parameter.py`, `mutation/structural.py`, `mutation/crossover.py`
- Create: `experiments/planner.py`, `experiments/candidate_generator.py`, `experiments/manifest.py`
- Test: `tests/mutation/test_operations.py`, `test_parameter_search.py`, `test_structural_search.py`, `test_crossover.py`, `tests/experiments/test_candidate_generation.py`

- [ ] **Step 1: Implement every named mutation operation.** Support `SET_PARAMETER`, `ADD_RULE`, `REMOVE_RULE`, `REPLACE_RULE`, `ENABLE_RULE`, `DISABLE_RULE`, `CHANGE_AND_OR`, `ADD_INDICATOR`, `REMOVE_INDICATOR`, `SWAP_INDICATOR`, `CHANGE_ENTRY`, `CHANGE_EXIT`, `CHANGE_STOP`, `CHANGE_TAKE_PROFIT`, `CHANGE_TRAILING_STOP`, `CHANGE_POSITION_SIZE`, `ADD_REGIME_FILTER`, `REMOVE_REGIME_FILTER`, `CROSSOVER`, and `COMBINE_STRATEGY` against typed IR paths.
- [ ] **Step 2: Implement search engines.** Implement grid and random search with seeded sampling, plus Bayesian search using an explicit initial design, surrogate, acquisition function, domain constraints, and deterministic seed. Emit the full requested domain in the experiment manifest.
- [ ] **Step 3: Implement structure-first planning.** Structure search emits indicator/rule/family changes; promising structures are admitted to parameter search through a policy threshold. A policy can interleave searches only by explicit configuration, and the chosen order is recorded.
- [ ] **Step 4: Implement crossover and rescue mutation reuse.** Combine parent entry/exit/risk components only when the resulting IR validates; Rescue Pool mutations are selectable inputs without copying invalid parent state.
- [ ] **Step 5: Validate/deduplicate candidates.** Every candidate receives canonical IR, parent/mutation lineage, seed, search stage, and candidate hash; invalid and duplicate candidates carry status/reason.
- [ ] **Step 6: Test exhaustive operation coverage.** Use property tests for operation composition, no mutation of parent objects, deterministic seeded output, Bayesian domain bounds, and rejection of invalid combinations.
- [ ] **Step 7: Run and commit.** Commit `feat: add local mutation and candidate search engines`.

### Task 6: Data Zones, Backtest Core, Cost Model, and Shared Read-Only Contracts

**Files:**
- Create: `core/data/contracts.py`, `core/data/provider.py`, `core/data/partitions.py`, `core/data/access.py`
- Create: `core/backtest/engine.py`, `core/backtest/adapter.py`, `core/backtest/result_contract.py`
- Create: `core/costs/model.py`, `core/costs/slippage.py`, `tests/fixtures/data/{development,validation,sealed_oos}.parquet`
- Test: `tests/core/test_data_zones.py`, `test_backtest_contract.py`, `test_cost_model.py`, `tests/security/test_oos_isolation.py`

- [ ] **Step 1: Define versioned data contracts.** Require symbol, UTC timestamp, OHLCV, corporate-action adjustment state, calendar, dataset version, and content hash; reject duplicates, gaps outside policy, timezone ambiguity, and future timestamps.
- [ ] **Step 2: Implement three data zones.** Development allows exploration, Validation requires promotion authorization, and Sealed OOS is exposed only through a promotion-gate process with a separate capability token. Research Director context cannot enumerate or read OOS rows.
- [ ] **Step 3: Implement the backtest adapter.** Provide a fixture engine and a Lean adapter with read-only algorithm/data mounts and unique run output. Result contract includes trades, equity curve hash, metrics input hash, logs summary, and exit status.
- [ ] **Step 4: Implement cost/slippage models.** Apply commission, spread, slippage stress, turnover, and position-size constraints consistently in standard and robustness runs; include model version in every experiment hash.
- [ ] **Step 5: Test leakage, cost accounting, and result integrity.** Verify a strategy cannot access future bars or OOS data, costs reduce gross performance correctly, and corrupt/missing results fail validation.
- [ ] **Step 6: Run and commit.** Commit `feat: add versioned data zones and immutable backtest contracts`.

### Task 7: Docker Lean Workers, Queue, Resource Manager, Scheduler, and Recovery

**Files:**
- Create: `runtime/queue.py`, `runtime/resource_manager.py`, `runtime/lean_worker.py`, `runtime/worker_pool.py`, `runtime/scheduler.py`, `runtime/recovery.py`
- Create: `runtime/docker/Dockerfile`, `runtime/docker/lean-worker-entrypoint.sh`
- Test: `tests/runtime/test_queue.py`, `test_resource_manager.py`, `test_scheduler.py`, `test_recovery.py`, `tests/integration/test_parallel_workers.py`

- [ ] **Step 1: Define job lifecycle and leases.** Use `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `TIMED_OUT`, `CANCELLED`, and `RETRY_EXHAUSTED` with idempotent job IDs, lease expiry, attempt count, and artifact hash.
- [ ] **Step 2: Build the resource manager.** Sample CPU/RAM/Docker usage, calculate safe concurrency from policy and observed average cost, apply backpressure, and reserve/release resources atomically.
- [ ] **Step 3: Build process workers and Docker isolation.** Mount shared market data read-only, mount each candidate artifact read-only, write only to `runs/E#######/`, set CPU/memory/time limits, and return structured status rather than parsing free-form logs.
- [ ] **Step 4: Build the async scheduler.** Schedule fast/full/robustness jobs, preserve candidate ordering only where required, support cancellation and restart, and keep worker count adaptive rather than fixed.
- [ ] **Step 5: Implement recovery.** Reconcile stale leases on startup, verify artifacts before marking success, retry only policy-approved failures, and mark retry exhaustion as `CRASH`/`REJECT` with evidence.
- [ ] **Step 6: Test real parallelism and isolation.** Run at least four fixture jobs concurrently, assert separate outputs, shared read-only data, bounded concurrency, timeout handling, worker crash recovery, and deterministic rerun.
- [ ] **Step 7: Run and commit.** Commit `feat: add resource-aware isolated worker runtime`.

### Task 8: Experiment Manifest, Hash Cache, and Persistent Raw Results

**Files:**
- Create: `experiments/cache.py`, `experiments/deduplicator.py`, `memory/experiment_store.py`, `state/experiments.sqlite`
- Create: `state/results/.gitkeep`, `docs/operations/storage.md`
- Test: `tests/experiments/test_cache.py`, `tests/memory/test_experiment_store.py`

- [ ] **Step 1: Implement the canonical experiment manifest.** Include strategy/parameter/search/data/evaluator/cost/compiler/image versions, symbols, date ranges, seed, policy version, and parent lineage.
- [ ] **Step 2: Implement SHA-256 cache lookup.** A full manifest match returns `CACHE_HIT`; any relevant version, data, evaluator, or cost change returns `CACHE_MISS` and schedules a new run.
- [ ] **Step 3: Implement transactional SQLite storage.** Store candidate, job, run, metric, state transition, audit, and promotion records with foreign keys and unique experiment hash constraints.
- [ ] **Step 4: Write generation-level Parquet partitions.** Store wide result records in `results/generation_NNN.parquet` with a manifest and checksum; atomic writes prevent partial partitions from being considered complete.
- [ ] **Step 5: Test cache idempotency and recovery.** Duplicate submissions do not create jobs; interrupted transactions recover; corrupted Parquet is rejected and rebuildable from SQLite/run artifacts.
- [ ] **Step 6: Run and commit.** Commit `feat: add experiment cache and durable result store`.

### Task 9: Metrics, Funnel Evaluation, Robustness, and Statistical Tests

**Files:**
- Create: `evaluation/metrics.py`, `evaluation/robustness.py`, `evaluation/sensitivity.py`, `evaluation/regimes.py`, `evaluation/pareto.py`, `evaluation/scoring.py`, `evaluation/selector.py`
- Create: `core/validation/gates.py`, `walk_forward.py`, `cpcv.py`, `cscv.py`
- Test: `tests/evaluation/{test_metrics,test_robustness,test_sensitivity,test_regimes,test_pareto,test_scoring,test_selector}.py`, `tests/core/validation/test_*`

- [ ] **Step 1: Implement metric calculations.** Calculate CAGR, return, Sharpe, Sortino, MDD, Calmar, win rate, profit factor, trade count, turnover, exposure, and cost-adjusted values with explicit NaN/zero-trade behavior.
- [ ] **Step 2: Implement the funnel.** Apply fast screen, full backtest, robustness, validation, and promotion gates in order; record every candidate's gate, threshold, actual value, and rejection reason.
- [ ] **Step 3: Implement stress and sensitivity.** Run transaction-cost/slippage stress, parameter perturbation, trade/order perturbation where supported, parameter importance, and stability intervals.
- [ ] **Step 4: Implement regime and temporal validation.** Add regime breakdown, walk-forward, CPCV, and CSCV with fold manifests, no overlap leakage, and insufficient-evidence statuses rather than fabricated scores.
- [ ] **Step 5: Implement DSR, PBO, and complexity penalty.** Record number of trials, selection bias inputs, probability of backtest overfitting, model/condition count, and final robust score; do not rank by Sharpe alone.
- [ ] **Step 6: Implement multi-objective Pareto selection.** Select by robust score, drawdown, stability, trade sufficiency, complexity, and family diversity; classify CRASH, REJECT, NEAR_MISS, SURVIVOR, FRONTIER, CHAMPION_CANDIDATE, and CHAMPION.
- [ ] **Step 7: Test known fixtures and insufficiency cases.** Verify expected metric values, cost monotonicity, fold boundaries, DSR/PBO input counts, complex-strategy penalties, and correct status for no-trade/too-few-trade/NaN results.
- [ ] **Step 8: Run and commit.** Commit `feat: add funnel and robustness evaluator`.

### Task 10: Frontier, Champion, Rescue Pool, and Policy-Based Selection

**Files:**
- Create: `memory/rescue_pool.py`, `memory/state_files.py`, `orchestration/policies.py`
- Create: `state/champion.json`, `state/frontier.json`, `state/rescue_pool.json`
- Test: `tests/memory/test_frontier.py`, `test_rescue_pool.py`, `tests/orchestration/test_policy_selection.py`

- [ ] **Step 1: Implement family-aware Frontier.** Keep independent representatives for Momentum, Mean Reversion, Breakout, Trend, and Hybrid or configured families; prevent one family from deleting all alternatives.
- [ ] **Step 2: Implement Champion promotion/demotion.** Require all configured gates, compare against current Champion, preserve lineage, and write atomic snapshot plus audit record. A Champion is a research artifact, not a live-trading approval.
- [ ] **Step 3: Implement Rescue Pool.** Store useful near-miss mutations, failure reason, parent hash, and reusability evidence; deduplicate rescue entries and expire only by explicit policy.
- [ ] **Step 4: Implement exploit/explore/crossover/rescue allocation.** Sample according to policy ratios, record the selected source and random seed, and support policy changes without code edits.
- [ ] **Step 5: Test empty stores, family diversity, near misses, and atomic recovery.** Assert no invalid candidate becomes Champion and stale snapshots are rejected by hash mismatch.
- [ ] **Step 6: Run and commit.** Commit `feat: add family frontier and rescue state management`.

### Task 11: Knowledge Memory, LLM Memory, and Local Analyzer Context

**Files:**
- Create: `memory/knowledge.py`, `memory/compressor.py`, `research/llm/context_builder.py`, `evaluation/local_analyzer.py`
- Create: `state/knowledge.json`, `docs/operations/memory.md`
- Test: `tests/memory/test_knowledge.py`, `test_compressor.py`, `tests/research/test_context_builder.py`

- [ ] **Step 1: Implement local analyzer summaries.** Produce compact YAML/JSON containing tested/valid counts, Champion, Frontier, stable parameter ranges, sensitivity, correlations, regime breakdown, cost sensitivity, unexplored areas, and evidence sufficiency.
- [ ] **Step 2: Implement three memory layers.** Raw Memory references every experiment in SQLite/Parquet; Knowledge Memory stores only repeated statistically supported known-good/known-bad/interactions/unexplored facts; LLM Memory stores a bounded compressed generation state with source hashes.
- [ ] **Step 3: Implement evidence thresholds and contradiction handling.** A finding needs configured repetitions/effect size/confidence; contradictory findings remain separate with status and confidence instead of being overwritten.
- [ ] **Step 4: Enforce context minimization.** Context builder sends summaries and IDs/hashes only, excludes raw market data, sealed OOS, credentials, full logs, and untrusted source prose, and validates output size/schema.
- [ ] **Step 5: Test compactness and provenance.** Assert no raw rows/secrets appear, all facts link to experiment hashes, insufficient evidence is labeled, and deterministic compression is stable.
- [ ] **Step 6: Run and commit.** Commit `feat: add statistical knowledge and compact LLM memory`.

### Task 12: Research Director, Trigger Rules, and Full Generation Orchestrator

**Files:**
- Create: `research/llm/provider.py`, `research/llm/director.py`, `orchestration/generation.py`, `orchestration/plateau.py`
- Test: `tests/research/test_director.py`, `tests/orchestration/test_generation.py`, `test_plateau.py`, `tests/integration/test_end_to_end_generation.py`

- [ ] **Step 1: Define provider-neutral director contracts.** Input is compact context; output is schema-validated Research Intent containing search mode, parent IDs, operations/templates, primitive request, and rationale. The director cannot output Python patches or evaluator changes.
- [ ] **Step 2: Implement offline and live providers.** Offline fixture mode is deterministic and always testable; live provider credentials come only from external secret configuration and are never persisted in context or state.
- [ ] **Step 3: Implement trigger rules.** Call the LLM at generation start when policy requires, on plateau, when a new family is needed, or when a new primitive is justified. Continue local exploration without LLM when improvement is ongoing.
- [ ] **Step 4: Implement the exact 20-step loop.** Load Champion/Frontier, load Knowledge, obtain intent if triggered, plan, generate, cache-check, mutate, validate, fast-backtest, hard-gate, full-backtest, robustness, analyze, score, update states, save DB, extract knowledge, compress context, detect plateau, and schedule the next generation.
- [ ] **Step 5: Implement generation idempotency and resume.** A generation manifest tracks completed stages and hashes; restart resumes incomplete jobs and never double-promotes a result.
- [ ] **Step 6: Test one complete fixture generation.** Assert 256-candidate planning, 1–2 director calls as policy permits, local-only result computation, cache reuse, all state/memory outputs, plateau behavior, and exact stage audit sequence.
- [ ] **Step 7: Run and commit.** Commit `feat: add generation orchestration and research director`.

### Task 13: Primitive Creation Workflow and Generated Artifact Controls

**Files:**
- Modify: `research/llm/director.py`, `mutation/primitive_registry.py`, `strategy_ir/compiler.py`
- Create: `strategies/generated/README.md`, `docs/operations/primitive-lifecycle.md`
- Test: `tests/security/test_primitive_boundary.py`, `tests/research/test_new_primitive_flow.py`

- [ ] **Step 1: Define new-primitive proposal.** A director may request a primitive specification with typed inputs/outputs, formula, lookback behavior, computational limits, test vectors, and justification; it may not write into protected core modules.
- [ ] **Step 2: Validate and register the primitive.** Require schema validation, no forward data access, reference-vector tests, complexity/resource limits, provenance, reviewer status, and a registry version bump before use.
- [ ] **Step 3: Compile generated strategy artifacts separately.** Store generated Python/Lean only under run artifacts or `strategies/generated`; include source IR/evaluator/compiler hashes and reject unregistered code.
- [ ] **Step 4: Test malicious/invalid proposals.** Reject arbitrary imports, filesystem/network access, order APIs, evaluator paths, undeclared indicators, and missing test vectors.
- [ ] **Step 5: Run and commit.** Commit `feat: add controlled primitive proposal lifecycle`.

### Task 14: Git Snapshots, Champion Tags, and Reproducible Release Artifacts

**Files:**
- Create: `scripts/snapshot_frontier.py`, `scripts/tag_champion.py`, `docs/operations/git-lineage.md`
- Test: `tests/integration/test_git_lineage.py`

- [ ] **Step 1: Implement snapshot rules.** General candidates remain in DB; Frontier writes a content-addressed snapshot; Champion Candidate creates an auditable commit; Champion creates `champion-vNNN` tag with strategy/evaluator/data hashes.
- [ ] **Step 2: Implement safe Git automation.** Refuse dirty protected changes, secret-containing artifacts, missing tests, or tag collisions; never rewrite history and never commit all raw experiment output.
- [ ] **Step 3: Test lineage.** A tag resolves to the Champion IR, policy, compiler, evaluator, cost model, and dependency/image manifest used for the result.
- [ ] **Step 4: Run and commit.** Commit `feat: add champion lineage snapshots and tags`.

### Task 15: KIS Research Adapter, Paper Trading, Live Gate, and Permission Separation

**Files:**
- Create: `integrations/kis/research_adapter.py`, `integrations/kis/paper_adapter.py`, `integrations/kis/live_gate.py`, `integrations/kis/permissions.py`
- Create: `deployment/paper/README.md`, `deployment/live/README.md`, `docs/operations/deployment-gates.md`
- Test: `tests/integrations/test_kis_research_isolation.py`, `test_paper_gate.py`, `test_live_gate.py`, `tests/security/test_order_permission.py`

- [ ] **Step 1: Define the research adapter.** It may retrieve approved historical/reference data through a read-only interface but exposes no order methods, credentials, or live account state to research workers.
- [ ] **Step 2: Define paper deployment.** Require a Champion hash, evaluator/data/cost hashes, deployment config, monitoring window, and signed approval; simulate orders and record drift without live side effects.
- [ ] **Step 3: Define live gate.** Require separate process, separate secret store, current paper validation, explicit human approval, expiry, risk limits, and exact Champion hash match. Default is `DENY`.
- [ ] **Step 4: Add process/package checks.** Research dependencies cannot import live order modules; live adapter refuses research-generated unsigned artifacts; test doubles prove no network/order call is possible in research mode.
- [ ] **Step 5: Run and commit.** Commit `feat: enforce research to KIS deployment trust boundary`.

### Task 16: CLI, Operations, Observability, and Failure Runbooks

**Files:**
- Create: `cli.py`, `docs/operations/run-generation.md`, `docs/operations/recovery.md`, `docs/runbooks/{worker-failure,data-integrity,cache-rebuild,live-gate}.md`
- Create: `tests/cli/test_cli.py`, `tests/integration/test_resume_and_recovery.py`

- [ ] **Step 1: Implement explicit CLI commands.** Provide `init`, `import-strategy`, `validate-strategy`, `plan-generation`, `run-generation`, `status`, `resume`, `rebuild-cache`, `promote-paper`, `request-live-approval`, and `audit` with structured exit codes.
- [ ] **Step 2: Add observability.** Emit generation/job IDs, queue depth, cache hit rate, candidate/gate counts, worker utilization, runtime, failure reasons, hashes, and state transitions without secrets or raw data.
- [ ] **Step 3: Implement operational recovery.** Support stale lease reconciliation, partial generation resume, SQLite/Parquet verification, cache rebuild from manifests, and explicit manual intervention for sealed-OOS or live-gate failures.
- [ ] **Step 4: Test command contracts and restart behavior.** Run a generation, terminate the scheduler, restart, resume, and assert no duplicated work or state regression.
- [ ] **Step 5: Run and commit.** Commit `feat: add operational CLI and recovery workflows`.

### Task 17: Full Verification, Benchmark, Security Audit, and Documentation Release

**Files:**
- Modify: `README.md`, `docs/traceability.md`; preserve `docs/architecture/quant-autoresearch-architecture-v1.0.md` byte-for-byte as the approved source
- Create: `tests/test_full_system.py`, `benchmarks/benchmark_generation.py`, `docs/verification/2026-09-01-baseline.md`

- [ ] **Step 1: Complete the traceability matrix.** Map source sections 0–25 to implementation files, focused tests, integration tests, and evidence output paths. Every row must have a concrete artifact and a PASS/FAIL result.
- [ ] **Step 2: Run the full quality gate.** Run `python -m pytest -q --cov`, Ruff, type checking, schema validation, secret scanning, protected-path audit, and import-boundary checks; record exact commands and outputs in the verification report.
- [ ] **Step 3: Run determinism and leakage tests.** Execute the same fixture generation twice, compare candidate/result/state hashes, attempt sealed-OOS/context access, mutate evaluator/cost/data versions, and confirm expected cache invalidation.
- [ ] **Step 4: Run resource and throughput benchmark.** Measure sequential versus adaptive parallel execution, cache hit rate, peak CPU/RAM, queue wait, failure recovery, and LLM calls per generation; record hardware, Docker image, dataset, policy, and commit hashes.
- [ ] **Step 5: Run end-to-end security review.** Verify no credentials/raw sources/sealed OOS enter artifacts, no Research Director path reaches evaluator mutation or KIS order APIs, and invalid signatures/approval expiry fail closed.
- [ ] **Step 6: Publish the operational handoff.** README explains architecture and quick start; operations docs explain configuration, generation, recovery, promotion, and audit; the verification report states PASS/FAIL/blocked per gate without converting missing external configuration into a false PASS.
- [ ] **Step 7: Commit the verified release.** Commit `docs: publish implementation traceability and verification evidence`; create the first release tag only after all required local gates pass.

### Dependencies and Stage Gates

```text
1 repository contract
  -> 2 integrity/policy
  -> 3 Strategy IR
  -> 4 import/library
  -> 5 mutation/search
  -> 6 data/backtest/cost
  -> 7 workers/runtime
  -> 8 cache/store
  -> 9 evaluation
  -> 10 state selection
  -> 11 memory/context
  -> 12 generation loop
  -> 13 primitive lifecycle
  -> 14 Git lineage
  -> 15 KIS/deployment
  -> 16 CLI/operations
  -> 17 complete verification
```

No task may skip a predecessor's failing gate. A failure produces a named evidence record and corrective task; it does not become a silent placeholder or a permanently disabled feature. External choices such as a real KIS account, live data vendor, or LLM credential are represented as validated configuration gates and are not falsely marked PASS until supplied.

### Validation/Testing Plan

- Unit tests for every pure contract, operation, metric, hash, state transition, and serialization rule.
- Property tests for IR mutation invariants, canonical hash stability, candidate deduplication, bounded search domains, and state-machine legality.
- Integration tests for Docker workers, shared read-only data, queue recovery, SQLite/Parquet persistence, cache reuse, and full generation replay.
- Statistical tests with synthetic fixtures whose expected metrics, folds, costs, DSR/PBO inputs, and regime outcomes are known.
- Security tests for protected imports/writes, sealed-OOS access, secret/raw-data redaction, arbitrary primitive code, evaluator tampering, KIS order permissions, and approval expiry.
- Determinism tests compare hashes and state across repeated fixture runs; benchmark tests record actual current performance rather than reusing historical claims.
- Final evidence must include test/type/lint/security output, traceability matrix, generation manifest, artifact checksums, and explicit PASS/FAIL/blocked classification.

### Next Deliverables

1. Repository contract and integrity/policy scaffold.
2. Strategy IR and primitive registry with fixture compiler.
3. Mutation/search/candidate manifest and cache.
4. Data/backtest/cost contracts and isolated workers.
5. Evaluator, funnel, robustness, and state selection.
6. Memory, Director, and complete generation loop.
7. Git lineage, KIS trust boundary, CLI, and release verification.

## F. Risks and Validation Checklist

- [ ] The saved architecture source is preserved at `docs/architecture/quant-autoresearch-architecture-v1.0.md`.
- [ ] No source section 0–25 is absent from the traceability matrix.
- [ ] Strategy IR, not generated Python, is the canonical source.
- [ ] All named mutation operations and grid/random/Bayesian search are implemented and tested.
- [ ] Candidate hashes include all data/evaluator/cost/compiler/image inputs named by the architecture.
- [ ] Shared data is read-only and every run has an isolated output directory.
- [ ] Resource-aware parallel execution, retry, timeout, cancellation, and resume are tested.
- [ ] Evaluator/data/cost/integrity paths are protected from the Research Director.
- [ ] Development, Validation, and sealed OOS zones are separate and leakage-tested.
- [ ] Fast screen, full backtest, robustness, validation, CPCV/CSCV, DSR, PBO, and complexity penalty are present.
- [ ] CRASH, REJECT, NEAR_MISS, SURVIVOR, FRONTIER, CHAMPION_CANDIDATE, and CHAMPION are persisted with legal transitions.
- [ ] Frontier preserves multiple families and Rescue Pool preserves useful near misses.
- [ ] Raw, Knowledge, and LLM memory have separate schemas and provenance.
- [ ] SQLite, Parquet, and JSON state are transactionally/checksum protected.
- [ ] Git stores meaningful Frontier/Champion lineage only; Champion tags are reproducible.
- [ ] KIS research, paper, and live processes are separate; live order permission defaults to deny.
- [ ] LLM calls occur per generation/trigger, while local computation remains local.
- [ ] Full verification reports exact current evidence; no historical metric is presented as current.

## Source-to-Plan Traceability

| Architecture source | Implementing tasks | Verification evidence |
|---|---:|---|
| Sections 0–1: roles and existing KIS concepts | 1, 2, 6, 15 | contract tests, trust-boundary tests |
| Section 2: optimizer/Lean reuse | 5, 6, 7 | adapter and parallel-worker tests |
| Section 3: Strategy IR | 3 | schema/validator/compiler tests |
| Section 4: Mutation Engine | 5, 13 | exhaustive operation and primitive tests |
| Section 5: Strategy Library | 4 | importer/provenance tests |
| Sections 6–7: parallelism/data sharing | 6, 7 | Docker isolation and concurrency evidence |
| Section 8: Candidate Cache | 2, 8 | cache idempotency/invalidation tests |
| Section 9: search layers | 5 | structure/parameter/Bayesian tests |
| Sections 10–11: generation and local analysis | 11, 12 | context and end-to-end generation evidence |
| Section 12: immutable evaluator | 2, 6, 9, 13 | protected boundary/security audit |
| Section 13: data zones | 6 | sealed-OOS leakage tests |
| Section 14: funnel | 9 | gate admission/rejection report |
| Section 15: robustness | 9 | stress, fold, DSR, PBO evidence |
| Sections 16–18: state/frontier/memory | 10, 11 | state transition and memory tests |
| Section 19: storage | 8 | SQLite/Parquet/JSON recovery evidence |
| Section 20: Git | 14 | lineage/tag integration evidence |
| Section 21: research/trading separation | 15 | import/order permission audit |
| Section 22: repository | 1 and all implementation tasks | repository contract and tree audit |
| Section 23: canonical loop | 12 | exact stage audit sequence |
| Section 24: LLM rules | 11–13 | trigger/offline/no-code-patch tests |
| Section 25: five principles | 2, 3, 6, 12, 15 | final security and traceability report |
