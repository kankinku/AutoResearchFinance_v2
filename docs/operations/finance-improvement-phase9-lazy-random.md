# T-009 partial — memory-bounded uniform random parameter search

The previous `random_search` materialized the entire Cartesian product using `grid_search`, only to sample a small finite candidate budget. A 28-dimensional binary domain would allocate hundreds of millions of dictionaries and likely exhaust RAM even when only 5 strategies were wanted.

The replacement performs seeded uniform sampling without replacement from a mixed-radix integer index space. Per-domain repeated scalar values are deduplicated using the legacy type-sensitive `(type_name, repr)` identity; different `1`, `True`, `1.0` values remain distinct. Duplicate parameter names now fail closed rather than silently overwriting dictionary keys. Sampling uses Python's lazy `range` while the product fits the platform maximum, and arbitrary-precision `randrange` with a picked-index set above that limit. Memory usage is proportional to the input domain value counts plus the requested sample budget, not the number of combinations.

Tests explicitly forbid any call to `grid_search` from random search with 2**28 possible points; cover a 2**70 point space, mixed boolean/numeric identities, repeated domain values, invalid duplicate domain names and exactly matching the legacy seeded order for distinct small grids. `grid_search` and `bayesian_search` remain unchanged; Bayesian acquisition still materializes its grid and requires separate scaling work.

No improvements to statistical OOS performance are implied; this change only removes an exponential memory bottleneck from the random mutation proposal stage.
