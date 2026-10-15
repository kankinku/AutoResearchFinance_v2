# Quant Autoresearch Harness Repository Contract

This repository implements the approved Quant Autoresearch Harness architecture.

## Source of truth

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
