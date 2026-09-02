# QQQ Stability Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evaluate QQQ-only strategies on a long historical sample with actual walk-forward evidence and persist reproducible per-candidate test records.

**Architecture:** Research data and reports remain under ignored `runs/`; canonical `state/` and order-capable modules remain unchanged. The funnel record will include the candidate parameters, dataset hashes, full metrics, benchmark CAGR comparison, validation-fold evidence, cost-stress result, and every gate decision so a result can be reconstructed without promoting it.

**Tech Stack:** Python, pytest, Pydantic dashboard contracts, ParquetDataProvider, BacktestEngine, JSONL ledger.

---

### Task 1: Define detailed test-record contract

**Files:**
- Modify: `evaluation/selector.py`
- Modify: `dashboard/contracts.py`
- Test: `tests/evaluation/test_selector.py`
- Test: `tests/dashboard/test_ledger.py`

- [ ] **Step 1: Write failing assertions for parameters, full metrics, benchmark CAGR, and gate details.**

  Add a `parameters` mapping to the selector input/result and assert that the result preserves it. Add assertions that the dashboard record accepts `strategy_cagr`, `qqq_cagr`, `nasdaq_cagr`, `trade_count`, `sharpe`, `sortino`, `profit_factor`, `dataset_hash`, and serialized `gates`.

- [ ] **Step 2: Run the focused tests and verify they fail because the fields are absent.**

  Run: `python -m pytest -q tests/evaluation/test_selector.py tests/dashboard/test_ledger.py`

- [ ] **Step 3: Add backward-compatible optional fields.**

  Keep existing positional constructors valid by appending defaulted fields to `FunnelInput`, `FunnelResult`, and `TestRecord`. Preserve old JSONL records by making new dashboard fields nullable/defaulted.

- [ ] **Step 4: Run the focused tests and verify they pass.**

  Run: `python -m pytest -q tests/evaluation/test_selector.py tests/dashboard/test_ledger.py`

- [ ] **Step 5: Commit the contract change.**

  Run: `git add evaluation/selector.py dashboard/contracts.py tests/evaluation/test_selector.py tests/dashboard/test_ledger.py; git commit -m "feat: expand qqq research test record contract"`

### Task 2: Persist reproducible candidate evidence

**Files:**
- Modify: `dashboard/ledger.py`
- Modify: `orchestration/pipeline.py`
- Modify: `orchestration/evaluation_runner.py`
- Modify: `memory/knowledge.py`
- Test: `tests/dashboard/test_ledger.py`
- Test: `tests/orchestration/test_pipeline.py`

- [ ] **Step 1: Write failing assertions for JSONL evidence.**

  Assert that one ledger line contains the candidate parameters, dataset hash, full metric fields, benchmark CAGR fields, and one gate object per funnel gate with `name`, `passed`, `threshold`, `actual`, and `reason`.

- [ ] **Step 2: Run the focused tests and verify the evidence fields are missing.**

  Run: `python -m pytest -q tests/dashboard/test_ledger.py tests/orchestration/test_pipeline.py`

- [ ] **Step 3: Thread parameters and dataset identity through the pipeline.**

  Pass `candidate.parameters` into `FunnelInput`, copy it into `FunnelResult`, and pass `dataset.dataset_hash` to `append_funnel_results`. Serialize only scalar parameters and derived metrics; never serialize raw bars or credentials.

- [ ] **Step 4: Persist full metrics and gate decisions in the ledger and knowledge profile.**

  Record strategy CAGR, benchmark CAGRs, annualized QQQ delta, trade count, Sharpe, Sortino, profit factor, turnover, exposure, total return, maximum drawdown, risk result, and gate decisions. Keep cumulative `qqq_excess_return` as an additional field.

- [ ] **Step 5: Run the focused tests and verify they pass.**

  Run: `python -m pytest -q tests/dashboard/test_ledger.py tests/orchestration/test_pipeline.py`

- [ ] **Step 6: Commit the ledger change.**

  Run: `git add dashboard/ledger.py orchestration/pipeline.py orchestration/evaluation_runner.py memory/knowledge.py tests/dashboard/test_ledger.py tests/orchestration/test_pipeline.py; git commit -m "feat: persist reproducible qqq candidate evidence"`

### Task 3: Run long-sample QQQ research without order access

**Files:**
- Runtime only: `runs/qqq-research-20260902-long/`
- Do not modify: `state/`, `core/data/`, `core/backtest/`, `core/evaluator/`, `core/validation/`, `core/costs/`, `core/integrity/`

- [ ] **Step 1: Acquire QQQ and NASDAQ daily adjusted data from 2010-01-01 through the latest available completed session.**

  Store only ignored Parquet research inputs with dataset versions, timezone-aware timestamps, and QQQ/NASDAQ series aligned to common dates. Do not store API credentials or raw source dumps in Git.

- [ ] **Step 2: Execute the 10 normalized strategies and QQQ-specific strategy templates.**

  Use `min_trades=30`, `min_qqq_cagr_delta=0.10`, identical costs, and independent per-strategy state directories. Record completed, rejected, and blocked counts.

- [ ] **Step 3: Export a detailed research report from JSONL.**

  Include dataset hashes, period, candidate count, best candidate by QQQ CAGR delta, all gate failures, per-period return/drawdown, trade evidence, and the exact command used. Mark the result as research-only and do not update Champion/Frontier.

### Task 4: Verify and report honestly

**Files:**
- No production file changes.

- [ ] **Step 1: Run `python -m pytest -q`, `ruff check .`, and `python -m mypy .`.**

- [ ] **Step 2: Run the tracked-file secret scan and inspect `git status --short`.**

- [ ] **Step 3: Report whether the +10 percentage-point annualized QQQ target passed, whether long-sample stability is demonstrated, and every remaining blocker.**

