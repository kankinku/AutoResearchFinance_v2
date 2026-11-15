"""No past generations are seeded: selection-only fixed-candidate A/B."""

from core.integrity.hashes import content_hash
from scripts.t4_parent_diversity_equal_budget import compare_synthetic_parent_selection


def test_equal_budget_comparison_is_deterministic_and_not_profit_claim() -> None:
    report = compare_synthetic_parent_selection()
    assert report == compare_synthetic_parent_selection()
    assert report["report_hash"] == content_hash({
        key: value for key, value in report.items() if key != "report_hash"
    })
    assert report["selection_opportunities_each_arm"] == 25
    assert report["candidate_count_each_arm"] == 4
    assert report["candidate_scoring_slots_each_arm"] == 100
    assert report["actual_backtests_executed"] == 0
    assert report["llm_calls"] == 0
    assert report["hypothesis_direction_match_rate"] is None
    assert report["actual_new_replayed_signals"] is None
    assert report["superiority_demonstrated"] is False
    assert report["independent_oos_approved"] is False
    assert report["past_experiments_used_as_parent_or_memory"] is False


def test_diverse_opt_in_reduces_parent_concentration_not_realized_alpha() -> None:
    result = compare_synthetic_parent_selection()
    baseline = result["legacy"]
    selected = result["opt_in"]
    assert baseline["parent_counts"] == {"94": 25}
    assert len(selected["parent_counts"]) == 3
    assert max(selected["parent_counts"].values()) <= 9
    assert selected["max_parent_concentration"] < baseline["max_parent_concentration"]
    assert selected["distinct_executed_fill_hashes"] == 3
    assert selected["lowest_selected_development_drawdown"] < (
        baseline["lowest_selected_development_drawdown"]
    )
    assert result["default_parent_portfolio_v2_unchanged"] is True


def test_different_fixed_seeds_still_observe_same_pareto_lanes() -> None:
    baseline = compare_synthetic_parent_selection(seed=20261110)
    varied = compare_synthetic_parent_selection(seed=42)
    assert baseline["legacy"] == varied["legacy"]
    assert baseline["opt_in"] == varied["opt_in"]
    assert baseline["candidate_fixture_hash"] != varied["candidate_fixture_hash"]
