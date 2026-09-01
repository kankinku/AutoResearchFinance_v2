from __future__ import annotations

from experiments.candidate_generator import generate_candidates
from experiments.deduplicator import deduplicate_candidates
from experiments.planner import ExperimentPlan, plan_experiment
from mutation.engine import MutationOperation
from mutation.parameter import ParameterDomain
from strategy_ir.validator import validate_strategy
from tests.strategy_ir.test_schema import example_document


def test_planner_records_structure_before_parameter_search() -> None:
    plan = plan_experiment(
        parent_ids=("S001923",),
        structure_operations=(MutationOperation("CHANGE_AND_OR", "entry.logic", "OR"),),
        parameter_domains=(ParameterDomain("risk.stop_loss_pct", (2.0, 3.0, 4.0)),),
        method="grid",
        count=3,
        seed=10,
    )

    assert isinstance(plan, ExperimentPlan)
    assert plan.search_stage == "parameter"
    assert plan.method == "grid"
    assert plan.seed == 10
    assert plan.parent_ids == ("S001923",)


def test_candidate_generation_is_deterministic_and_keeps_lineage() -> None:
    parent = validate_strategy(example_document())
    operations = (MutationOperation("CHANGE_AND_OR", "entry.logic", "OR"),)
    domains = (ParameterDomain("risk.stop_loss_pct", (2.0, 3.0)),)

    first = generate_candidates(parent, operations, domains, method="grid", count=2, seed=3)
    second = generate_candidates(parent, operations, domains, method="grid", count=2, seed=3)

    assert first == second
    assert len(first) == 2
    assert {candidate.strategy.entry.logic for candidate in first} == {"OR"}
    assert all(candidate.parent_id == parent.strategy_id for candidate in first)
    assert len({candidate.candidate_hash for candidate in first}) == 2


def test_deduplicator_removes_hash_duplicates_preserving_first() -> None:
    parent = validate_strategy(example_document())
    candidates = generate_candidates(
        parent,
        (MutationOperation("CHANGE_AND_OR", "entry.logic", "OR"),),
        (ParameterDomain("risk.stop_loss_pct", (2.0,)),),
        method="grid",
        count=1,
        seed=3,
    )

    result = deduplicate_candidates([candidates[0], candidates[0]])

    assert result.unique == (candidates[0],)
    assert result.duplicate_hashes == (candidates[0].candidate_hash,)
