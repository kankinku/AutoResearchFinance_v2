from __future__ import annotations

from finance_autoresearch.search.optuna_adapter import OptunaAdapter
from finance_autoresearch.search.trial_manager import TrialManager
from tests.strategy.test_strategy_dsl_compiler import make_genome


def test_trial_manager_caps_total_candidates_by_effective_limit() -> None:
    manager = TrialManager(
        optuna_adapter=OptunaAdapter(max_variants=8),
        frontier_candidate_limit=3,
        prescreen_max_candidates=2,
    )

    candidates = manager.build_candidates(
        run_id="run-001",
        iteration=1,
        artifact=make_genome(),
    )

    assert manager.candidate_limit == 2
    assert len(candidates) == 2
    assert candidates[0].search_origin == "base"
