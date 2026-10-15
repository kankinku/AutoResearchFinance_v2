# Quant Autoresearch Harness Repository Contract

This repository implements the approved Quant Autoresearch Harness architecture.

## Source of truth

## Product scope lock — MANDATORY before all Quant Autoresearch work

**Top-level user-approved product contract**:
- Original, unchanged 20-question interview: `docs/decisions/2026-10-14-autoresearch-interview-20q.md`
- Current user-confirmed interpretation and frozen remaining-work order:
  `docs/decisions/2026-10-16-autoresearch-20q-scope-lock-v1.md`
- Live implementation/status ledger: `docs/operations/autoresearch-master-progress.md`

Read **all three** before writing a roadmap, code, or a scope-changing proposal.
User's original goal is **autonomous algorithm research**, not hand-tuning an individual
QQQ trading strategy. A true generation includes candidate creation, canonical
backtest/trace, real LLM diagnosis, a justified next plan, and immutable evidence.
Do not claim model autonomy from mocks or prove profitability from non-PIT data.
The original three acceptance phases (engine → LLM evolution → independently
validated realizable net profit) and all Q01–Q20 stay in scope.

**Frozen current delivery order:** V05 bounded cost/statistics → T4 real
10/100-generation ChatGPT MCP loop → V01–V04 external PIT/OOS dependencies
(as they become available) → V06 non-order paper trading → V07 separate GO/NO-GO.
Code for necessary original-interview dependencies may be added only when
connected to these gates. This is not a license to indefinitely expand validation
tools while T4 remains unverified.

Before each task state/verify: stage ID, Q IDs, user value, boundaries, concrete
acceptance test, next frozen task, and non-goals. Record that mapping and honest
status in the ledger. **Any change to an original objective, planned stage order,
model/MCP default, permission/OOS boundary, success condition or material new
scope requires explicit user approval documented by a new ADR BEFORE work.**
Proposal, generated recommendation, or a passing unit test is not approval.
Do not edit the original 20-question file. Run the scope-governance tests as
part of T0/T1 whenever changing the roadmap, policies, or target workflows.

- Strategy IR is the canonical strategy representation.
- Generated Python/Lean is an execution artifact, never the strategy source.
- `docs/architecture/quant-autoresearch-architecture-v1.0.md` is the approved architecture source and is preserved byte-for-byte.

## Protected paths

The Research Director and generated strategy artifacts must not write to or mutate:

- `core/data`
- `core/backtest`
- `core/evaluator`
- `core/validation`
- `core/costs`
- `core/integrity`

Sealed OOS data and KIS order-capable modules have separate process permissions.

## Generated and sensitive data

Runtime output, caches, credentials, raw source dumps, and local state are ignored by `.gitignore`.
Do not store API keys, tokens, account identifiers, session logs, or raw market-data dumps in Git.

## Required checks

```powershell
python -m pytest -q
ruff check .
python -m mypy .
```

Every implementation task must add tests before production code and finish with an atomic commit.

## Mandatory progress ledger (every completed task)

- The authoritative development status and remaining-work checklist is `docs/operations/autoresearch-master-progress.md`. Read it before starting the next task.
- Before reporting any task as completed, update its stage/status, remaining dependencies, next development order, and required test order in that document; append a dated completed-work entry with the actual code changes and test results.
- Explicitly distinguish **passed**, **failed**, **interrupted**, and **not run** checks. Run scoped tests and static checks during development; defer full-system/economic/OOS validation until integration or final evaluation, without relaxing security, correctness, or non-trading restrictions.
- Commit and push source changes, then record the resulting branch/SHA and push/deployment status in the ledger; commit and push the ledger update. A documentation-only task must still update and push the ledger.
- Do not declare the work complete if the ledger was not persisted; report any update/push failure and the actual state to the user. Never assert unattended/background documentation updates: update the file as part of each explicitly performed Moon task.
