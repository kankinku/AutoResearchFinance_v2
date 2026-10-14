"""Research S2: LLM diagnostic proposals must bind to real evidence."""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from research.indicator_engine.decision_audit import (
    audit_compiled_academic_decisions,
)
from research.llm.diagnostic_research import (
    DiagnosisContractError,
    approve_diagnostic_plan,
    build_diagnostic_context,
    diagnose_with_provider,
)
from tests.research.test_academic_decision_audit import _fixture


def _inputs(tmp_path: Path):
    market, compiled = _fixture(tmp_path)
    audit = audit_compiled_academic_decisions(compiled, market)
    context = build_diagnostic_context(audit, compiled.strategy)
    reference = audit.round_trips[0].trade_id
    payload = {
        "context_hash": context["context_hash"],
        "audit_hash": audit.trace_hash,
        "strategy_hash": compiled.strategy_hash,
        "dataset_hash": market.dataset_hash,
        "summary": "Test whether excluding one regime filter improves blocked entry behavior.",
        "hypotheses": [{
            "hypothesis_id": "h-regime-1",
            "observed_ids": [reference, audit.round_trips[0].entry_fill.decision_id],
            "mechanism": "A hard binary regime filter might exclude recoveries.",
            "alternative": "The filter could reduce trading costs in choppy periods.",
            "expected_metric": "total_return",
            "predicted_direction": "INCREASE",
            "test_design": "ABLATION",
            "control": "PARENT_UNCHANGED",
            "next_intent": {
                "mode": "structure",
                "parent_ids": [compiled.strategy.strategy_id],
                "operations": [{"op": "REMOVE_REGIME_FILTER", "path": "regime_filters.0"}],
                "rationale": "Compare a single filter ablation against the unchanged parent.",
            },
        }],
    }
    return audit, compiled.strategy, context, payload


def test_approved_diagnosis_is_evidence_bound_not_verified_causality(tmp_path: Path):
    audit, parent, context, payload = _inputs(tmp_path)
    result = approve_diagnostic_plan(audit, parent, context, payload)
    assert result.audit_hash == audit.trace_hash
    assert result.context_hash == context["context_hash"]
    assert result.status == "VALIDATED_PROPOSAL_REQUIRES_EXPERIMENT"
    assert result.causal_claim == "UNTESTED_HYPOTHESIS"
    assert result.independent_oos_approved is False
    assert len(result.experiments) == 1
    experiment = result.experiments[0]
    assert experiment.parent_id == parent.strategy_id
    assert experiment.test_design == "ABLATION"
    assert "hard binary regime" in experiment.mechanism
    assert "trading costs" in experiment.alternative
    assert experiment.control == "PARENT_UNCHANGED"
    assert result.analysis_summary == payload["summary"]
    assert experiment.proposed_intent.operations[0].op == "REMOVE_REGIME_FILTER"
    assert not experiment.child.regime_filters
    assert experiment.child.parents[-1] == parent.strategy_id
    assert experiment.child.generation == parent.generation + 1
    assert experiment.child.strategy_id != ""
    assert experiment.child_hash != audit.evaluation.strategy_hash
    assert result == approve_diagnostic_plan(audit, parent, context, payload)


def test_provider_receives_verified_context_and_one_typed_response(tmp_path: Path):
    audit, parent, context, payload = _inputs(tmp_path)

    class FakeLLM:
        calls = 0

        def propose(self, request):
            self.calls += 1
            assert request == context
            assert request["causal_status"] == "NOT_ESTABLISHED"
            assert request["observations"]["loss_cases"] is not None
            assert "sealed_oos" not in request
            assert request["execution_policy"] == "PROPOSE_ONLY_NO_ORDER_OR_APPROVAL"
            return deepcopy(payload)

    model = FakeLLM()
    assert diagnose_with_provider(audit, parent, model).experiments
    assert model.calls == 1


@pytest.mark.parametrize("change", [
    lambda p: p.update(context_hash="fake"),
    lambda p: p.update(audit_hash="fake"),
    lambda p: p.update(strategy_hash="fake"),
    lambda p: p.update(dataset_hash="fake"),
    lambda p: p["hypotheses"][0].update(observed_ids=["fabricated-trade"]),
    lambda p: p["hypotheses"][0].update(control="HINDSIGHT_BEST"),
    lambda p: p["hypotheses"][0].update(next_intent={**p["hypotheses"][0]["next_intent"],
        "operations": []}),
    lambda p: p["hypotheses"][0].update(next_intent={**p["hypotheses"][0]["next_intent"],
        "parent_ids": ["unrelated-parent"]}),
    lambda p: p["hypotheses"][0].update(next_intent={**p["hypotheses"][0]["next_intent"],
        "python_patch": "exec('bad')"}),
    lambda p: p["hypotheses"][0].update(next_intent={**p["hypotheses"][0]["next_intent"],
        "primitive_request": {"name": "unverified"}}),
    lambda p: p.update(pretend_verified=True),
    lambda p: p["hypotheses"][0].update(causal_status="PROVEN"),
])
def test_reject_forged_unscoped_or_privileged_output(tmp_path: Path, change):
    audit, parent, context, payload = _inputs(tmp_path)
    change(payload)
    with pytest.raises((DiagnosisContractError, ValueError)):
        approve_diagnostic_plan(audit, parent, context, payload)


def test_reject_tampered_evidence_even_with_matching_packet(tmp_path: Path):
    audit, parent, _, _ = _inputs(tmp_path)
    modified = replace(audit, llm_packet={**audit.llm_packet, "measured_final_equity": 99e9})
    with pytest.raises(DiagnosisContractError, match="audit"):
        build_diagnostic_context(modified, parent)
    original = audit.decisions[30]
    changed = replace(original, regime_signal=0.999)
    changed_audit = replace(audit, decisions=(
        *audit.decisions[:30], changed, *audit.decisions[31:],
    ))
    with pytest.raises(DiagnosisContractError, match="audit"):
        build_diagnostic_context(changed_audit, parent)
    other_parent = parent.model_copy(update={"strategy_id": "other_parent"})
    with pytest.raises(DiagnosisContractError, match="strategy"):
        build_diagnostic_context(audit, other_parent)


def test_invalid_structural_modification_is_not_accepted(tmp_path: Path):
    audit, parent, context, payload = _inputs(tmp_path)
    payload["hypotheses"][0]["next_intent"]["operations"] = [
        {"op": "REMOVE_RULE", "path": "entry.conditions.0"},
    ]
    with pytest.raises(DiagnosisContractError, match="intent"):
        approve_diagnostic_plan(audit, parent, context, payload)


def test_reject_duplicate_hypotheses_and_duplicate_observations(tmp_path: Path):
    audit, parent, context, payload = _inputs(tmp_path)
    payload["hypotheses"] *= 2
    with pytest.raises(DiagnosisContractError):
        approve_diagnostic_plan(audit, parent, context, payload)
    payload["hypotheses"] = payload["hypotheses"][:1]
    payload["hypotheses"][0]["observed_ids"] *= 2
    with pytest.raises(DiagnosisContractError):
        approve_diagnostic_plan(audit, parent, context, payload)


def test_reject_semantically_unchanged_retain_or_same_value(tmp_path: Path):
    audit, parent, context, payload = _inputs(tmp_path)
    payload["hypotheses"][0]["next_intent"]["operations"] = [{"op": "RETAIN"}]
    with pytest.raises(DiagnosisContractError, match="duplicate or unchanged"):
        approve_diagnostic_plan(audit, parent, context, payload)
    payload["hypotheses"][0]["next_intent"]["operations"] = [
        {"op": "CHANGE_POSITION_SIZE", "path": "risk.position_size_pct", "value": 100.0}
    ]
    with pytest.raises(DiagnosisContractError, match="duplicate or unchanged"):
        approve_diagnostic_plan(audit, parent, context, payload)


def test_reject_reference_not_presented_to_model(tmp_path: Path):
    audit, parent, context, payload = _inputs(tmp_path)
    # This legitimate audit ID was intentionally omitted from bounded LLM input.
    assert len(audit.decisions) > 100
    payload["hypotheses"][0]["observed_ids"] = [audit.decisions[-12].decision_id]
    with pytest.raises(DiagnosisContractError, match="unknown"):
        approve_diagnostic_plan(audit, parent, context, payload)
