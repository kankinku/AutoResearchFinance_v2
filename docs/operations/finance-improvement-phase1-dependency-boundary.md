# T-002 partial — isolate financial validation core from analytics models

`core.validation.gates.hard_gate` previously imported `evaluation.metrics.Metrics`, which violates the intended core-to-analysis dependency direction. It now accepts a small structural `MetricsView` protocol consisting only of `trade_count` and `total_return`. This avoids a runtime dependency on the analytics module while preserving the gate's runtime behavior and its existing consumers; all existing public function arguments remain unchanged.

Tests: `tests/core/validation/test_dependency_boundary.py` parses the core module and asserts no dependency on `evaluation` modules, and verifies an independent structural metric provider. The pre-change test failed. Existing hard-gate contracts pass.

T-002 as a whole remains partial: the Strategy IR/compiler dependency on core integrity hashes, strategy importing, mutation definitions, and other inverted edges still require a separately audited dependency DAG refactor.

## Compiler hash inversion (second patch)

Compiler hashing formerly imported `core.integrity.hashes` from inside `strategy_ir`. Canonical JSON serialization and SHA-256 hashing now reside in neutral `foundation.hashes`; `strategy_ir.compiler` imports it directly, and `core.integrity.hashes` transparently re-exports both function objects to preserve API and historical data hashes. `experiment_hash` remains a core integrity function and its canonicalization delegates unchanged to the same function. `tests/strategy_ir/test_hash_boundary.py` asserts compiler import direction and validates byte-for-byte hash parity against the financial-core public contract. This intentionally avoids schema changes or any financial execution semantics changes.

Other inbound edges to Strategy IR from `strategy_import` and `mutation` remain; T-002 is not fully resolved.

## Packaging follow-up

The neutral `foundation` package is included explicitly in setuptools package discovery and Mypy package lists in `pyproject.toml`; a static packaging test locks this dependency. Without that addition, local source tests could pass while an installed distribution lacked the shared hashing module. The worker Dockerfile presently copies the whole project, but this packaging test also prevents packaged deployments from omitting `foundation`.
