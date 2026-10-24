"""T4: bounded, reproducible random *candidate* controls, not LLM generations."""

from pathlib import Path

import pytest

from core.integrity.hashes import content_hash
from research.indicator_engine.algorithm_plan import AlgorithmPlan, compile_algorithm_plan
from research.indicator_engine.catalog import ResearchCatalogError
from research.llm.p4_random_candidate_control import (
    _semantic_plan,
    evaluate_random_candidate_cohort,
    generate_random_candidate_plans,
)
from tests.research.test_academic_algorithm_plan import _catalog, _market


def test_random_candidates_are_precommitted_no_replacement_and_deterministic(tmp_path: Path):
    catalog = _catalog(tmp_path)
    first = generate_random_candidate_plans(catalog, count=10, seed=20261024)
    second = generate_random_candidate_plans(catalog, count=10, seed=20261024)
    assert first == second
    assert len(first) == 10
    assert all(isinstance(p, AlgorithmPlan) for p in first)
    signatures = [content_hash(_semantic_plan(p)) for p in first]
    assert len(set(signatures)) == 10
    for p in first:
        assert p.position_size_pct == 100
        assert 1 <= len(p.cases) <= 2
        for c in p.cases:
            assert catalog.get_indicator(c.when.indicator_id).status == "VERIFIED"
            for v in c.votes:
                assert catalog.get_indicator(v.indicator_id).role == "entry"


@pytest.mark.parametrize(
    "count,seed",
    [
        (0, 20261024),
        (11, 20261024),
        (10, -1),
        (10, 2**80),
        (True, 10),
    ],
)
def test_invalid_budget_is_rejected(count, seed, tmp_path: Path):
    with pytest.raises(ValueError):
        generate_random_candidate_plans(_catalog(tmp_path), count=count, seed=seed)


def test_random_cohort_replays_one_candidate_and_s7_per_slot(tmp_path: Path):
    catalog = _catalog(tmp_path)
    market = _market()
    plans = generate_random_candidate_plans(catalog, count=3, seed=20261024)
    out = evaluate_random_candidate_cohort(catalog, market, plans, seed=20261024)
    assert out["schema"] == "p4-t4-random-candidate-slot-control-v1"
    assert out["candidate_slots_requested"] == 3
    assert out["candidate_s2_completed"] == 3
    assert out["s7_attempt_slots"] == 3
    assert out["real_llm_generations"] == 0
    assert out["independent_oos_approved"] is False
    assert out["broker_executable"] is False
    assert len(out["candidates"]) == 3
    assert len({c["semantic_plan_hash"] for c in out["candidates"]}) == 3
    assert out == evaluate_random_candidate_cohort(catalog, market, plans, seed=20261024)
    for item in out["candidates"]:
        compiled = compile_algorithm_plan(
            catalog, AlgorithmPlan.model_validate(item["plan"]), market
        )
        assert item["strategy_hash"] == compiled.compiled.strategy_hash
        assert item["s2_total_return"] > -1
        assert item["s7_attempt_status"] in (
            "MEASURED",
            "NOT_EXECUTABLE_NO_OBSERVED_TRADE",
        )


def test_random_cohort_refuses_new_or_sealed_data_and_duplicate_plans(tmp_path: Path):
    catalog, market = _catalog(tmp_path), _market()
    from dataclasses import replace

    from core.data.contracts import DataZone

    plans = generate_random_candidate_plans(catalog, count=2, seed=20261024)
    with pytest.raises(ResearchCatalogError):
        evaluate_random_candidate_cohort(
            catalog, replace(market, zone=DataZone.SEALED_OOS), plans, seed=20261024
        )
    with pytest.raises(ValueError, match="duplicate"):
        evaluate_random_candidate_cohort(catalog, market, (plans[0], plans[0]), seed=20261024)
