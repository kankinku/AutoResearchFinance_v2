# T-007 — fail-closed prior-optimizer provenance for train-only evidence

A previously evaluated Bayesian observation may contain returns from periods overlapping or after a walk-forward test fold. The existing fixed-cohort train-only selector did not carry the optimizer-observation history, so it could show `status=EVALUATED` and `selection_applied=true` even when candidate choices were already influenced by undisclosed later observations.

`GenerationPipeline.run` now supplies its search mode and whether prior Bayesian observations were used to the selection evidence builder. If a Bayesian search has previous observations without fold-specific as-of lineage, its `train_only_selection` status is `UNVERIFIED_UPSTREAM_OPTIMIZATION`, with **no selection folds**. It does not assert train-only success; the general candidate funnel remains for development diagnostics and no sealed/OOS promotion is implied.

Every `TrainOnlySelectionReport` explicitly includes `upstream_selection_verified=false`, even when a deterministic fixed candidate cohort was selected using only its training window. This means *the preexisting parent/hypothesis or data-driven upstream strategy-design process has not been independently demonstrated to be frozen before the test*. This is critical; train-only selection of an already cherry-picked cohort cannot establish an unbiased OOS backtest.

Further T-007 requirements: fold-specific optimization observation lineage with cutoff timestamps, training-only feature availability and a final fully sealed OOS set and authorized promotion gate. Tests: `tests/orchestration/test_train_only_selection.py` and existing runner payload/Evidence tests.
