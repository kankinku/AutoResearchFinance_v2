# T-009 — include all evaluator-affecting source/dependency changes in Evidence code identity

The frozen research manifest previously hashed only eight source packages, omitting `foundation` (canonical IR/data hashing), `memory` (candidate selection and evidence), `dashboard`, `integrations`, `application`, `strategy_import`, and source/dependency lock files. Consequently a new run using a changed common hash or dependency lock could appear comparable under the old `code_hash` despite running under different code.

`orchestration.evidence.project_code_hash(root)` now hashes deterministic relative paths and SHA-256 bytes for all Python/YAML/JSON files in the canonical source and integration packages plus root `pyproject.toml`, `uv.lock`, `cli.py` and `dashboard.py`. It deliberately excludes mutable user market data, runtime state, ignored outputs, credentials and tests; market/feature data must be separately committed through their own dataset hashes. Frozen research manifests now use this single shared digest. The update is an evidence **comparison-key version change**, not a retroactive rewrite of historical manifests; incompatible runs with a reused research-run ID must reject instead of overwriting immutable history.

Tests establish that editing `foundation` or `memory` module bytes, and editing or adding dependency locks, changes the hash. Existing runner manifest, pipeline, and type checks remain green.

Limits: This is not a signed supply-chain attestation and does not prove a specific Docker image or remote host environment; Windows Docker worker identity and audited runtime reproduction remain pending.
