# Run generation

1. Initialize state with `python cli.py init --state-dir state`.
2. Validate every source with `validate-strategy`; unsupported imports are an explicit
   non-zero result and are not silently converted to candidates.
3. Load development or authorized validation Parquet data. Never pass sealed OOS data to
   `GenerationPipeline`; its access is reserved for a promotion-gate process.
4. Call `GenerationPipeline.run` with a parent IR, mutation operations, parameter domains,
   deterministic seed, and a `FunnelConfig`.
5. Persist the returned candidate hashes, gate decisions, state snapshot, and knowledge
   payload using `StateFileStore` and `AuditLog`. Store only hashes and abstract profiles
   in knowledge; raw market rows and source prose do not belong there.
6. Review `NEAR_MISS` entries through the Rescue Pool. A `SURVIVOR` is a research result,
   not permission to submit an order.

The reproducibility tuple is the Strategy IR, parameters, symbol/date range, dataset,
evaluator, cost model, compiler, Docker image digest, and seed. Changing any member
creates a new experiment hash.
