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
