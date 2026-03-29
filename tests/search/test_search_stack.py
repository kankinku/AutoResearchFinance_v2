from __future__ import annotations

from tests.strategy.test_strategy_dsl_compiler import make_genome


def test_optuna_adapter_generates_bounded_deterministic_variants() -> None:
    from finance_autoresearch.search.optuna_adapter import OptunaAdapter

    adapter = OptunaAdapter(max_variants=4)

    first = adapter.suggest_variants(make_genome())
    second = adapter.suggest_variants(make_genome())

    assert len(first) == 4
    assert len(second) == 4
    assert first == second
    assert all(item["kind"] == "strategy_genome_v1" for item in first)
    assert any(
        variant["indicator_specs"][0]["params"]["window"] != 20 for variant in first
    )


def test_candidate_frontier_promotes_top_two_passing_candidates() -> None:
    from finance_autoresearch.search.candidate_frontier import select_candidate_frontier

    frontier = select_candidate_frontier(
        prescreen_results=[
            {
                "candidate_id": "a",
                "passed": True,
                "reason": "passed",
                "score": 0.10,
            },
            {
                "candidate_id": "b",
                "passed": True,
                "reason": "passed",
                "score": 0.70,
            },
            {
                "candidate_id": "c",
                "passed": False,
                "reason": "zero_exposure",
                "score": -1.0,
            },
            {
                "candidate_id": "d",
                "passed": True,
                "reason": "passed",
                "score": 0.50,
            },
        ],
        candidate_limit=3,
        promotion_limit=2,
    )

    assert [item["candidate_id"] for item in frontier] == ["b", "d", "a", "c"]
    assert [item["candidate_id"] for item in frontier if item["promoted"]] == ["b", "d"]
