"""F3 must measure changes against the same costed, replayed parent, never infer alpha."""

from dataclasses import replace

import pytest

from research.indicator_engine.inherited_decision_audit import audit_inherited_decisions
from research.indicator_engine.inherited_experiments import compare_inherited_experiments
from research.llm.diagnostic_research import approve_diagnostic_plan, build_diagnostic_context
from research.llm.feature_contribution_f3 import (
    ContributionEvidenceError,
    build_costed_s7_contribution,
    build_verified_s7_contribution_review,
)
from tests.research.test_p0_3b_inherited_audit import _diagnosis_from_audit, _real


def _source():
    market, compiled = _real()
    audit = audit_inherited_decisions(compiled, market)
    diagnosis = _diagnosis_from_audit(audit, compiled.strategy)
    report = compare_inherited_experiments(compiled, market, diagnosis)
    validated = approve_diagnostic_plan(
        audit, compiled.strategy, build_diagnostic_context(audit, compiled.strategy), diagnosis
    )
    proposed = validated.experiments[0]
    child = replace(compiled, strategy=proposed.child, strategy_hash=proposed.child_hash)
    candidate = audit_inherited_decisions(child, market)
    return market, audit, candidate, report


def test_actual_s7_measured_contribution_has_costs_missed_winners_and_benchmark():
    market, parent, child, report = _source()
    f3 = build_costed_s7_contribution(
        parent, child, market, report, report.experiments[0].hypothesis_id
    )
    assert f3 == build_costed_s7_contribution(
        parent, child, market, report, report.experiments[0].hypothesis_id
    )
    assert f3["schema"] == "f3-costed-parent-child-contribution-v1"
    assert f3["parent_audit_hash"] == parent.trace_hash
    assert f3["child_audit_hash"] == child.trace_hash
    assert f3["measured_s7_report_hash"] == report.evidence_hash
    assert f3["parent_strategy_hash"] != f3["child_strategy_hash"]
    assert f3["dataset_hash"] == market.dataset_hash
    assert f3["parent_closed_trades"] == len(parent.round_trips)
    assert f3["child_closed_trades"] == len(child.round_trips)
    assert f3["parent_only_closed_winning_entries"] >= 0
    assert f3["parent_only_closed_losing_entries"] >= 0
    assert f3["parent_only_closed_winning_entries"] + f3[
        "parent_only_closed_losing_entries"
    ] <= len(parent.round_trips)
    assert f3["parent_total_paid_costs"] == pytest.approx(parent.evaluation.total_paid_costs)
    assert f3["child_total_paid_costs"] == pytest.approx(child.evaluation.total_paid_costs)
    assert f3["parent_final_equity"] == pytest.approx(report.experiments[0].parent_final_equity)
    assert f3["child_final_equity"] == pytest.approx(report.experiments[0].child_final_equity)
    assert f3["delta_final_equity"] == pytest.approx(
        child.evaluation.final_equity - parent.evaluation.final_equity
    )
    assert f3["parent_max_drawdown"] >= 0 and f3["child_max_drawdown"] >= 0
    assert 0 <= f3["parent_market_exposure"] <= 1
    assert 0 <= f3["child_market_exposure"] <= 1
    assert f3["execution_delta"]["matched_event_count"] >= 0
    assert f3["qqq_costed_buy_and_hold_return"] is not None
    assert f3["relative_qqq_return_delta"] == pytest.approx(f3["return_delta"])
    assert f3["counterfactual_scope"] == "WHOLE_PORTFOLIO_RERUN_DESCRIPTIVE_ONLY"
    assert f3["observed_parent_only_entries_not_proven_avoided_losses"] is True
    assert f3["observed_parent_only_winners_not_proven_missed_child_profit"] is True
    assert f3["auto_promotable"] is False
    assert f3["independent_oos_approved"] is False
    assert f3["evidence_hash"]


def test_rejects_changed_s7_outcome_and_uncertified_parent():
    market, parent, child, report = _source()
    with pytest.raises(ContributionEvidenceError):
        build_costed_s7_contribution(
            parent,
            child,
            market,
            replace(
                report, experiments=(replace(report.experiments[0], child_final_equity=9999.0),)
            ),
            report.experiments[0].hypothesis_id,
        )
    with pytest.raises(ContributionEvidenceError):
        build_costed_s7_contribution(
            replace(parent, trace_hash="f" * 64),
            child,
            market,
            report,
            report.experiments[0].hypothesis_id,
        )
    with pytest.raises(ContributionEvidenceError):
        build_costed_s7_contribution(
            parent,
            child,
            replace(market, bars=market.bars[:-1]),
            report,
            report.experiments[0].hypothesis_id,
        )
    with pytest.raises(ContributionEvidenceError):
        build_costed_s7_contribution(parent, child, market, report, "unknown_hypothesis")


def test_no_false_success_from_lower_costs_or_fewer_trades():
    market, parent, child, report = _source()
    outcome = report.experiments[0]
    f3 = build_costed_s7_contribution(parent, child, market, report, outcome.hypothesis_id)
    assert f3["adoption_review"] in {
        "PARENT_REMAINS_BETTER_ON_RETURN_OR_RISK",
        "INCONCLUSIVE_DEVELOPMENT_ONLY",
        "CANDIDATE_REQUIRES_INDEPENDENT_VALIDATION",
    }
    assert f3["adoption_review"] != "PROMOTED"
    assert len(f3["parent_only_entry_examples"]) <= 8
    assert len(f3["child_only_entry_examples"]) <= 8
    assert f3["not_same_entry_means_not_a_simulated_alternative_exit"] is True


def test_actual_typed_strategy_review_and_optional_f2_link_reject_wrong_source():
    from core.integrity.hashes import content_hash
    from research.indicator_engine.inherited_decision_audit import audit_inherited_decisions

    market, compiled = _real()
    source = audit_inherited_decisions(compiled, market)
    diagnosis = _diagnosis_from_audit(source, compiled.strategy)
    report = compare_inherited_experiments(compiled, market, diagnosis)
    hypotheses = approve_diagnostic_plan(
        source,
        compiled.strategy,
        build_diagnostic_context(source, compiled.strategy),
        diagnosis,
    ).experiments
    child = replace(compiled, strategy=hypotheses[0].child, strategy_hash=hypotheses[0].child_hash)
    unlinked = build_verified_s7_contribution_review(
        compiled,
        child,
        market,
        report,
        hypotheses[0].hypothesis_id,
    )
    assert unlinked["intervention_scope"] == "EXIT_ONLY"
    assert unlinked["intervention_components"] == ["exit"]
    assert unlinked["matched_weakness"] is None
    assert unlinked["auto_promotable"] is False
    unknown = {
        "source_audit_hash": source.trace_hash,
        "strategy_hash": source.evaluation.strategy_hash,
        "dataset_hash": market.dataset_hash,
        "causal_status": "NOT_ESTABLISHED",
        "weaknesses": [
            {
                "weakness_id": "f2_observed_example",
                "observation_code": "EXIT_BELOW_OBSERVED_CLOSE_PEAK",
                "needed_information": "Is exit timing improved without excess trading?",
            }
        ],
    }
    unknown["guidance_hash"] = content_hash(unknown)
    tied = build_verified_s7_contribution_review(
        compiled,
        child,
        market,
        report,
        hypotheses[0].hypothesis_id,
        weakness_guidance=unknown,
        weakness_id="f2_observed_example",
    )
    assert tied["matched_weakness"]["source_guidance_hash"] == unknown["guidance_hash"]
    assert tied["matched_weakness"]["mechanism_validation"] == "STILL_NOT_ESTABLISHED"
    with pytest.raises(ContributionEvidenceError):
        build_verified_s7_contribution_review(
            compiled,
            child,
            market,
            report,
            hypotheses[0].hypothesis_id,
            weakness_guidance={**unknown, "dataset_hash": "f" * 64},
            weakness_id="f2_observed_example",
        )
