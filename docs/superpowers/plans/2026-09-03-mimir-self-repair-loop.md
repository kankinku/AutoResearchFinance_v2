# Mimir Self-Repair Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `Mimir /research N` process every requested generation by invoking an independent read-only Codex repair agent for invalid intents and using a recorded parent-baseline fallback when repair is exhausted.

**Architecture:** The research loop will preflight every intent through the existing registry and Strategy IR mutation validator before evaluation. `CodexExecProvider.repair()` will launch a separate `codex exec` process with a repair-only instruction; the loop will retry at most three times per generation, then evaluate the unchanged parent strategy and mark that generation `FALLBACK` instead of aborting. Configuration errors before the loop remain fail-fast, while per-generation provider, intent, and evaluator errors are recorded and do not stop later generations.

**Tech Stack:** Python 3.10+, pytest, Pydantic Strategy IR, existing `CodexExecProvider`, existing local `GenerationPipeline`, JSON state records.

---

### Task 1: Define repair and continuation contracts in tests

**Files:**
- Modify: `tests/research/test_codex_exec.py`
- Modify: `tests/runtime/test_autoresearch_loop.py`

- [x] **Step 1: Add a fake Codex repair provider contract test**

Create a provider double with `propose()` returning an invalid intent and `repair()` returning a valid registered-feature intent. Assert that the loop invokes `repair()` with the validation error and then calls the evaluator with typed operations.

- [x] **Step 2: Add a fallback continuation test**

Use a provider whose proposal and every repair response are invalid. Run two generations with a fake evaluator and assert both generations are evaluated with `operations=()`, the result has `completed_generations == 2`, and records contain `FALLBACK` plus the repair-attempt count.

- [x] **Step 3: Add the independent Codex repair command test**

Use the existing fake subprocess runner to call `CodexExecProvider.repair()`. Assert the command is a new `codex exec` invocation with `--ephemeral`, `--sandbox read-only`, the schema, and a repair instruction that contains the validation error but no KIS credential fields.

- [x] **Step 4: Run the focused tests and confirm RED**

Run:

```powershell
python -m pytest -q tests/research/test_codex_exec.py tests/runtime/test_autoresearch_loop.py
```

Expected: failures because `CodexExecProvider.repair()` and the loop continuation contract do not yet exist.

### Task 2: Add independent Codex intent repair

**Files:**
- Modify: `research/llm/codex_exec.py`
- Modify: `research/llm/director.py`
- Test: `tests/research/test_codex_exec.py`

- [x] **Step 1: Add the repair protocol to the Director boundary**

Add `ResearchDirector.repair(context, invalid_intent, error)` that requires the provider to expose a callable `repair()` method, validates the returned mapping as `ResearchIntent`, and raises a clear `IntentRepairUnavailable` error when the provider has no repair capability.

- [x] **Step 2: Implement a separate Codex repair invocation**

Implement `CodexExecProvider.repair()` by creating a fresh subprocess request with a repair-specific instruction. The request must demand only registered feature selections, typed mutation names, Strategy IR-root dotted paths, no `feature_proposal`, no code/evaluator changes, no file edits, and no order calls. Reuse the existing temporary output, schema validation, child-environment redaction, timeout, service-tier override, and diagnostic handling.

- [x] **Step 3: Run the focused provider tests**

Run:

```powershell
python -m pytest -q tests/research/test_codex_exec.py
```

Expected: all provider and repair-command tests PASS.

### Task 3: Make each research generation self-healing and non-aborting

**Files:**
- Modify: `runtime/research_loop.py`
- Modify: `runtime/mimir.py`
- Test: `tests/runtime/test_autoresearch_loop.py`
- Test: `tests/runtime/test_mimir.py`

- [x] **Step 1: Add bounded repair configuration**

Add `intent_repair_attempts: int = 3` to `ResearchLoopConfig`, reject negative values, expose `--intent-repairs` in `Mimir /research`, and persist the value in `state/system/research_loop.json`.

- [x] **Step 2: Add local intent preflight**

Before calling the evaluator, convert the intent with `intent_to_operations()` and validate the complete operation set against the current parent using `apply_intent()`. Treat feature-proposal, invalid path, unsupported operation, malformed feature, and parent mismatch errors as repairable intent errors.

- [x] **Step 3: Implement the bounded independent repair cycle**

For each generation, call the primary Director once. On a repairable error, call `director.repair()` up to the configured limit, record each attempt and reason, and use the first intent that passes local preflight. Record `REPAIRED` when a repaired intent is accepted.

- [x] **Step 4: Implement deterministic fallback and continuation**

When no intent passes repair, record any feature proposal for later verification, use the unchanged parent with `operations=()`, call the evaluator once, and label the generation `FALLBACK`. If the fallback evaluator also errors, record `DEGRADED` and continue to the next generation without inventing a strategy result.

- [x] **Step 5: Persist accurate terminal status**

Increment `completed_generations` after every processed generation. Return `COMPLETED` when all generations were processed without degraded evaluation, `COMPLETED_WITH_FALLBACKS` when fallback generations occurred, and `COMPLETED_WITH_ERRORS` when degraded generations occurred. Always return `orders_enabled: false`; never convert a per-generation failure into a global `BLOCKED` return.

- [x] **Step 6: Run loop and CLI tests**

Run:

```powershell
python -m pytest -q tests/runtime/test_autoresearch_loop.py tests/runtime/test_mimir.py
```

Expected: invalid primary intents are repaired or fall back, and a two-generation test reaches `completed_generations == 2`.

### Task 4: Document operations and repair behavior

**Files:**
- Modify: `README.md`
- Modify: `.env.example`

- [x] **Step 1: Document the repair limit**

Document `Mimir /research 100 --intent-repairs 3` and explain that the value limits independent Codex repair calls per generation.

- [x] **Step 2: Document fallback status and safety**

Explain that `REPAIRED`, `FALLBACK`, and `DEGRADED` are recorded per generation, that fallback evaluates the unchanged parent, and that research remains paper-only with no order calls.

- [x] **Step 3: Document the registered-feature gate**

Explain that a proposed unregistered feature is not silently registered; the repair agent first removes or replaces it with a registered feature, otherwise the generation continues with the parent baseline and the proposal is recorded for verification.

### Task 5: Full verification and atomic commit

**Files:**
- Modify only the files listed above and the new plan file.

- [x] **Step 1: Run the full test and quality suite**

Run:

```powershell
python -m pytest -q
ruff check .
python -m mypy .
git diff --check
```

Expected: all tests pass, Ruff and mypy report no errors, and diff check is clean.

- [x] **Step 2: Run one real paper-only Mimir generation**

Run:

```powershell
Mimir /research 1 --count 1 --min-trades 0 --min-annual-trades 0 --intent-repairs 3
```

Expected: the command reaches `COMPLETED`, `COMPLETED_WITH_FALLBACKS`, or `COMPLETED_WITH_ERRORS` after one processed generation, never an early global `BLOCKED`; `orders_enabled` remains `false`.

- [x] **Step 3: Commit only the implementation files**

```powershell
git add docs/superpowers/plans/2026-09-03-mimir-self-repair-loop.md research/llm/codex_exec.py research/llm/director.py runtime/research_loop.py runtime/mimir.py tests/research/test_codex_exec.py tests/runtime/test_autoresearch_loop.py tests/runtime/test_mimir.py README.md .env.example
git commit -m "feat: continue Mimir research with self-repair"
```
