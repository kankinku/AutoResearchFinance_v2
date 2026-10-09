# T-002 partial — isolate financial validation core from analytics models

`core.validation.gates.hard_gate` previously imported `evaluation.metrics.Metrics`, which violates the intended core-to-analysis dependency direction. It now accepts a small structural `MetricsView` protocol consisting only of `trade_count` and `total_return`. This avoids a runtime dependency on the analytics module while preserving the gate's runtime behavior and its existing consumers; all existing public function arguments remain unchanged.

Tests: `tests/core/validation/test_dependency_boundary.py` parses the core module and asserts no dependency on `evaluation` modules, and verifies an independent structural metric provider. The pre-change test failed. Existing hard-gate contracts pass.

T-002 as a whole remains partial: the Strategy IR/compiler dependency on core integrity hashes, strategy importing, mutation definitions, and other inverted edges still require a separately audited dependency DAG refactor.
