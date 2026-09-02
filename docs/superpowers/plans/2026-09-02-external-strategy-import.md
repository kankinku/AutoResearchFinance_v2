# External GitHub Strategy Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Safely clone external strategy repositories, statically convert supported strategies into Strategy IR, retain non-convertible strategies for review, detect semantic duplicates, and expose the complete catalog to the dashboard.

**Architecture:** Add a focused `strategy_import` package. A source manager pins a temporary clone to a commit; format analyzers return a common import record; a registry writes immutable provenance/profile/IR artifacts and computes semantic fingerprints. The CLI invokes this pipeline, while the dashboard reads a credential-free catalog projection. No external code is executed.

**Tech Stack:** Python 3.10+, AST, pathlib, subprocess git, Pydantic v2, pytest, FastAPI.

---

### Task 1: Define import records and safe repository inputs

**Files:**
- Create: `strategy_import/__init__.py`
- Create: `strategy_import/models.py`
- Create: `strategy_import/sources.py`
- Test: `tests/strategy_import/test_sources.py`

- [ ] **Step 1: Write failing tests** for accepted local files, rejected `.env`/credentials, GitHub URL parsing, and sanitized clone metadata.
- [ ] **Step 2: Run `python -m pytest tests/strategy_import/test_sources.py -q` and confirm the new imports do not exist.**
- [ ] **Step 3: Implement immutable `RepositorySource`, `SourceFile`, `ImportRecord`, and `CloneManager`; use `git clone --no-checkout`, checkout an explicit commit/ref, reject unsafe schemes and credential-bearing URLs, and expose only commit plus relative paths.
- [ ] **Step 4: Re-run the source tests and confirm PASS.**
- [ ] **Step 5: Commit `feat: add safe external strategy source records`.**

### Task 2: Add static analyzers for Strategy IR and KIS formats

**Files:**
- Create: `strategy_import/analyzers.py`
- Modify: `strategy_ir/normalizer.py`
- Test: `tests/strategy_import/test_analyzers.py`
- Test: `tests/strategy_ir/test_normalizer.py`

- [ ] **Step 1: Write failing tests** using representative KIS `builder_state`, KIS `StrategyDefinition` builder source, a standard `STRATEGY` literal, a dynamic Python source, and two equivalent SMA crossover files.
- [ ] **Step 2: Run `python -m pytest tests/strategy_import/test_analyzers.py tests/strategy_ir/test_normalizer.py -q` and confirm KIS sources are currently unsupported and the new analyzer API is absent.**
- [ ] **Step 3: Implement AST-only extraction. Literal mappings are validated directly; KIS registrations and builder state are mapped to indicators/conditions/risk; supported `StrategyDefinition` constructor literals are mapped; calls, imports, and custom Lean bodies are never executed.
- [ ] **Step 4: Replace the permissive cross-over regex fallback with an explicit compatibility analyzer result so a textual coincidence cannot produce a fake IR.**
- [ ] **Step 5: Re-run the focused tests and confirm KIS samples produce valid IR or `REVIEW_REQUIRED` with a retained profile.**
- [ ] **Step 6: Commit `feat: statically normalize KIS strategy formats`.**

### Task 3: Persist imports and compute semantic duplicates

**Files:**
- Create: `strategy_import/registry.py`
- Create: `strategy_import/fingerprint.py`
- Create: `strategies/catalog.json`
- Modify: `.gitignore`
- Test: `tests/strategy_import/test_registry.py`
- Test: `tests/strategy_import/test_fingerprint.py`

- [ ] **Step 1: Write failing tests** for atomic imported/normalized artifact writes, review-required retention, exact duplicate detection across different files, partial duplicate detection when only risk differs, and idempotent re-import.
- [ ] **Step 2: Run the focused tests and confirm they fail because registry and fingerprint functions are absent.**
- [ ] **Step 3: Implement canonical semantic payload hashing from strategy IR fields, excluding provenance and source hash; classify `NEW`, `EXACT_DUPLICATE`, and `PARTIAL_DUPLICATE`.
- [ ] **Step 4: Implement atomic JSON artifact writes under `strategies/imported` and `strategies/normalized`, plus a catalog index containing sanitized provenance, status, duplicate links, extracted profile, and IR hash.
- [ ] **Step 5: Add clone caches, temporary files, raw source dumps, and runtime import artifacts to `.gitignore` while keeping normalized IR/catalog reviewable.
- [ ] **Step 6: Re-run focused tests and commit `feat: persist strategy imports and semantic duplicates`.**

### Task 4: Connect CLI import and KIS ten-strategy batch processing

**Files:**
- Modify: `cli.py`
- Modify: `README.md`
- Create: `docs/operations/external-strategy-import.md`
- Test: `tests/cli/test_strategy_import_cli.py`

- [ ] **Step 1: Write failing CLI tests** for local import, GitHub source import through an injected clone manager, dry-run analysis, and batch summary containing all ten KIS preset records.
- [ ] **Step 2: Run `python -m pytest tests/cli/test_strategy_import_cli.py -q` and confirm the new command is absent.**
- [ ] **Step 3: Add `import-strategies --source` and `import-strategies --repo` commands with explicit `--commit/--ref`, `--dry-run`, and `--batch` options; route every source through the same registry.
- [ ] **Step 4: Add a KIS preset discovery rule for `strategy_builder/strategy_core/preset` and `backtester/kis_backtest/strategies/preset`, without importing the files.
- [ ] **Step 5: Ensure `run-generation` consumes only a persisted normalized IR path inside the project root and gives actionable status for `REVIEW_REQUIRED`.
- [ ] **Step 6: Document the commands and paper-only behavior, then run focused CLI tests and commit `feat: expose external strategy import CLI`.**

### Task 5: Add dashboard strategy catalog and evaluation status

**Files:**
- Modify: `dashboard/contracts.py`
- Modify: `dashboard/service.py`
- Modify: `dashboard/app.py`
- Modify: `dashboard/static/index.html`
- Modify: `dashboard/static/app.js`
- Test: `tests/dashboard/test_strategy_catalog.py`
- Test: `tests/dashboard/test_static_assets.py`

- [ ] **Step 1: Write failing API tests** for an empty catalog, normalized KIS strategy, exact duplicate, and review-required strategy with no credential values.
- [ ] **Step 2: Run the dashboard tests and confirm `/api/strategies/catalog` is absent.**
- [ ] **Step 3: Add credential-free response models and `DashboardService.strategy_catalog()` reading only the persisted catalog.
- [ ] **Step 4: Add `GET /api/strategies/catalog` and render Korean status labels, provenance, duplicate classification, evaluation state, return, and Nasdaq excess return in the existing dashboard.
- [ ] **Step 5: Re-run dashboard tests and commit `feat: expose strategy catalog in dashboard`.**

### Task 6: Run ten-strategy integration verification and regression checks

**Files:**
- Create: `tests/integration/test_kis_strategy_import.py`
- Create: `docs/operations/external-strategy-import-verification.md`

- [ ] **Step 1: Add integration fixtures copied from the audited KIS source shapes, not executable external code, and assert all ten builder presets enter one common pipeline.
- [ ] **Step 2: Run `python -m pytest tests/strategy_import tests/cli/test_strategy_import_cli.py tests/dashboard/test_strategy_catalog.py tests/integration/test_kis_strategy_import.py -q` and record the result.
- [ ] **Step 3: Run `python -m pytest -q`, `ruff check .`, and `python -m mypy .`; separate pre-existing unrelated failures from import failures.
- [ ] **Step 4: Run a real read-only clone of the official KIS repository at a pinned commit, import the ten presets, inspect the generated catalog, and confirm no source code or secret values were stored.
- [ ] **Step 5: Confirm `state/mode.json` remains paper-only and no order-capable client was called.
- [ ] **Step 6: Commit `test: verify external strategy import pipeline` and report exact PASS/FAIL/blocked evidence.**

## Validation checklist

- External source code is never imported or executed.
- All supported strategies produce valid Strategy IR with provenance.
- Unsupported semantics remain as reviewable records rather than disappearing.
- Duplicate detection ignores source path/hash and compares normalized meaning.
- KIS ten-strategy batch uses the same importer and registry as other GitHub sources.
- Dashboard shows strategies independently from Champion/Frontier state.
- No live or paper order endpoint is called.
- Secrets, account identifiers, raw source dumps, and clone caches remain ignored.

