# T-009 partial — memory-bounded uniform random parameter search

The previous `random_search` materialized the entire Cartesian product using `grid_search`, only to sample a small finite candidate budget. A 28-dimensional binary domain would allocate hundreds of millions of dictionaries and likely exhaust RAM even when only 5 strategies were wanted.

The replacement performs seeded uniform sampling without replacement from a mixed-radix integer index space. Per-domain repeated scalar values are deduplicated using the legacy type-sensitive `(type_name, repr)` identity; different `1`, `True`, `1.0` values remain distinct. Duplicate parameter names now fail closed rather than silently overwriting dictionary keys. Sampling uses Python's lazy `range` while the product fits the platform maximum, and arbitrary-precision `randrange` with a picked-index set above that limit. Memory usage is proportional to the input domain value counts plus the requested sample budget, not the number of combinations.

Tests explicitly forbid any call to `grid_search` from random search with 2**28 possible points; cover a 2**70 point space, mixed boolean/numeric identities, repeated domain values, invalid duplicate domain names and exactly matching the legacy seeded order for distinct small grids. `grid_search` and `bayesian_search` remain unchanged; Bayesian acquisition still materializes its grid and requires separate scaling work.

No improvements to statistical OOS performance are implied; this change only removes an exponential memory bottleneck from the random mutation proposal stage.

## Grid candidate generation follow-up

The bounded `generate_candidates(method="grid", count=N)` previously called **unbounded** `grid_search(domains)` and sliced only *after* materializing the entire grid. `grid_search` now takes an optional `limit` and expands only the first N combinations with `itertools.islice`, while no-limit callers retain the exact original ordering and complete result. The grid branch in `experiments.candidate_generator._search` passes the candidate budget at generation time rather than slicing later. Tests check a 2**28 combination space with a 3-point prefix, negative-limit rejection and actual candidate-generator budget propagation. This change is about bounded grid enumeration, not Bayesian search or performance returns.
