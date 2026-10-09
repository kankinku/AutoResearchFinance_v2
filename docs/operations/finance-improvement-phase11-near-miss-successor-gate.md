# T-011 — development successor eligibility must exclude near misses

`_best_strategy_payload` previously advanced any funnel result except `REJECT` as the best strategy for the next development generation. That allowed `NEAR_MISS` candidates, which by definition did not pass the required evaluation gates, to become the next automatically selected strategy even when an eligible survivor was present with a lower score. This confused rescue-pool prospects with valid research survivors.

Candidate-to-successor selection now explicitly requires `SURVIVOR`, `FRONTIER`, `CHAMPION_CANDIDATE`, or `CHAMPION`. If every candidate is `NEAR_MISS`/`REJECT`, no `best_strategy` is returned; the active loop retains its existing parent. If a valid survivor is present, it wins over a higher-scoring near miss. This change does not grant champion status, sealed OOS approval, or live-order permissions. Development survivor selection is not an independently sealed promotion.

Tests assert both all-near-miss rejection and survivor-priority-over-higher-scoring-near-miss; existing local runner tests continue to pass.
