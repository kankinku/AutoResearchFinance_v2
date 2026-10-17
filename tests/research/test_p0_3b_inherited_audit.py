"""P0-3B: inherited IR is the real counted S2 audited parent, not a label."""

from dataclasses import replace

import pytest

from core.features.registry import research_feature_specs
from core.integrity.hashes import content_hash
from research.indicator_engine.algorithm_plan import AlgorithmPlan, compile_algorithm_plan
from research.indicator_engine.inherited_decision_audit import audit_inherited_decisions
from research.indicator_engine.strategy_adapter import evaluate_compiled_development
from research.llm.diagnostic_research import build_diagnostic_context
from research.llm.director import ResearchIntent
from research.llm.intent_bridge import apply_intent
from tests.research.test_lineage_p0_3 import _actual_source


def _real():
    catalog, data, original, report, proposal, continuation = _actual_source()
    base = compile_algorithm_plan(
        catalog, AlgorithmPlan.model_validate(original["algorithm_plan"]), data
    )
    child = apply_intent(
        base.compiled.strategy,
        ResearchIntent.model_validate(proposal["proposed_intent"]),
        research_feature_specs(),
    )
    successor = apply_intent(
        child, ResearchIntent.model_validate(continuation), research_feature_specs()
    )
    digest = content_hash(successor.model_dump(mode="json", by_alias=True))
    compiled = replace(base.compiled, strategy=successor, strategy_hash=digest)
    return data, compiled


def test_inherited_s2_replays_real_multiple_condition_ir_exactly():
    data, compiled = _real()
    expected = evaluate_compiled_development(compiled, data)
    audited = audit_inherited_decisions(compiled, data)
    assert audited.evaluation == expected
    assert audited.evaluation.strategy_hash == compiled.strategy_hash
    assert len(compiled.strategy.entry.conditions) == 2
    assert len(audited.fills) == 97
    assert len(audited.round_trips) == 48
    assert len(audited.decisions) == len(data.bars)
    assert audited.trace_hash == audited.llm_packet["audit_hash"]
    diagnostic = build_diagnostic_context(audited, compiled.strategy)
    assert diagnostic["strategy_hash"] == compiled.strategy_hash
    assert diagnostic["observations"]["closed_trades"] == 48
    assert not audited.broker_executable


def test_inherited_s2_rejects_elevated_risk_and_changed_hash():
    data, compiled = _real()
    with pytest.raises(ValueError, match="unsupported"):
        changed = compiled.strategy.model_copy(
            update={"risk": compiled.strategy.risk.model_copy(update={"stop_loss_pct": 1.0})}
        )
        audit_inherited_decisions(
            replace(
                compiled,
                strategy=changed,
                strategy_hash=content_hash(changed.model_dump(mode="json", by_alias=True)),
            ),
            data,
        )
    with pytest.raises(ValueError, match="hash"):
        audit_inherited_decisions(replace(compiled, strategy_hash="0" * 64), data)


def _diagnosis_from_audit(audited, strategy):
    ctx = build_diagnostic_context(audited, strategy)
    sample = ctx["observations"]["execution_samples"][0]
    return {
        "context_hash": ctx["context_hash"],
        "audit_hash": ctx["audit_hash"],
        "strategy_hash": ctx["strategy_hash"],
        "dataset_hash": ctx["dataset_hash"],
        "summary": "Test changing the exit threshold on the inherited entry gates.",
        "hypotheses": [
            {
                "hypothesis_id": "inherited_exit_rule_01",
                "observed_ids": [sample["trade_id"], sample["decision_id"]],
                "mechanism": "A changed exit threshold could reduce losses from reversals.",
                "alternative": "The changed threshold could also cut profitable positions early.",
                "expected_metric": "total_return",
                "predicted_direction": "INCREASE",
                "test_design": "PARAMETER",
                "control": "PARENT_UNCHANGED",
                "next_intent": {
                    "mode": "structure",
                    "parent_ids": [strategy.strategy_id],
                    "operations": [
                        {
                            "op": "REPLACE_RULE",
                            "path": "exit.conditions.0",
                            "condition": {
                                "op": "less_equal",
                                "left": "plan_vote_score",
                                "value": 0.44,
                            },
                        }
                    ],
                    "rationale": "Compare inherited baseline to a bounded exit threshold change.",
                },
            }
        ],
    }


def test_inherited_s7_measures_mutated_child_against_actual_parent():
    from research.indicator_engine.inherited_experiments import compare_inherited_experiments

    data, compiled = _real()
    audited = audit_inherited_decisions(compiled, data)
    diagnosis = _diagnosis_from_audit(audited, compiled.strategy)
    report = compare_inherited_experiments(compiled, data, diagnosis)
    assert report.audit_hash == audited.trace_hash
    assert len(report.experiments) == 1
    result = report.experiments[0]
    assert result.parent_final_equity == pytest.approx(audited.evaluation.final_equity)
    assert result.child_strategy_hash != compiled.strategy_hash
    assert result.child_fill_count >= 0
    assert result.causal_status == "NOT_ESTABLISHED"
    assert report.out_of_sample_approved is False
    assert report.broker_executable is False


def test_inherited_s7_rejects_tampered_diagnosis_without_counting():
    from research.indicator_engine.inherited_experiments import compare_inherited_experiments

    data, compiled = _real()
    audit = audit_inherited_decisions(compiled, data)
    diagnosis = _diagnosis_from_audit(audit, compiled.strategy)
    diagnosis["strategy_hash"] = "0" * 64
    with pytest.raises(ValueError, match="diagnostic|mismatch"):
        compare_inherited_experiments(compiled, data, diagnosis)


def test_cycle_counted_inherited_generation_preserves_hash_chain(tmp_path):

    from research.llm.autonomous_cycle import AcademicCycleService
    from tests.research.test_lineage_p0_3 import SID, _actual_source

    catalog, data, original, stored, proposal, continuation = _actual_source()
    _, base_compiled = _real()
    next_intent = ResearchIntent.model_validate(
        {
            "mode": "structure",
            "parent_ids": [base_compiled.strategy.strategy_id],
            "operations": [
                {
                    "op": "REPLACE_RULE",
                    "path": "exit.conditions.0",
                    "condition": {"op": "less_equal", "left": "plan_vote_score", "value": 0.44},
                }
            ],
            "rationale": "Study a changed exit on the selected verified parent.",
        }
    )
    descendant = apply_intent(base_compiled.strategy, next_intent, research_feature_specs())
    digest = content_hash(descendant.model_dump(mode="json", by_alias=True))
    compiled = replace(base_compiled, strategy=descendant, strategy_hash=digest)
    from tests.research.historical_g33_fixture import copy_historical_g33_checkpoint

    backup_db = copy_historical_g33_checkpoint(tmp_path) / "cycles.sqlite"
    cycle = AcademicCycleService(backup_db)
    assert cycle.get(SID, catalog, data)["completed_generations"] == 33
    audit = audit_inherited_decisions(compiled, data)

    class DiagnosisProvider:
        def propose(self, context):
            assert context["strategy_hash"] == digest
            diagnosis = _diagnosis_from_audit(audit, descendant)
            diagnosis["hypotheses"][0]["next_intent"]["operations"][0]["condition"]["value"] = 0.39
            return diagnosis

    lineage = {
        "schema": "p0-3b-counted-inheritance-input-v1",
        "source_generation": 29,
        "source_evidence_hash": original["evidence_hash"],
        "parent_strategy_hash": base_compiled.strategy_hash,
        "origin_lineage_hash": "9" * 64,
        "parent_selection_hash": "a" * 64,
    }
    completed = cycle.advance_inherited(
        SID,
        catalog,
        data,
        DiagnosisProvider(),
        parent_compiled=base_compiled,
        compiled=compiled,
        source_plan=original["algorithm_plan"],
        inheritance=lineage,
        inherited_intent=next_intent.model_dump(mode="json"),
    )
    assert completed["completed_generations"] == 34
    last = completed["history"][-1]
    assert last["strategy_hash"] == digest
    assert last["previous_evidence_hash"] == completed["history"][-2]["evidence_hash"]
    assert last["inherited_parent"]["parent_strategy_hash"] == base_compiled.strategy_hash
    assert last["audit_hash"] == audit.trace_hash
    assert last["inherited_strategy_ir"]["id"] == descendant.strategy_id
    assert last["measured_final_equity"] == pytest.approx(audit.evaluation.final_equity)
    assert last["broker_executable"] is False
    with pytest.raises(ValueError, match="duplicate|state|interrupted"):
        cycle.advance_inherited(
            SID,
            catalog,
            data,
            DiagnosisProvider(),
            parent_compiled=base_compiled,
            compiled=compiled,
            source_plan=original["algorithm_plan"],
            inheritance=lineage,
            inherited_intent=next_intent.model_dump(mode="json"),
        )


def test_exact_selected_parent_compilation_matches_p0_3a_lineage():
    import json

    from research.llm.lineage_selection import compile_replayed_successor
    from tests.research.test_lineage_p0_3 import ROOT, SID, _actual_source

    catalog, market, original, stored, proposal, continuation = _actual_source()
    saved = ROOT / "state/moon-http/research/academic-gpt-checkpoints/gateway.sqlite"
    with __import__("sqlite3").connect(f"file:{saved}?mode=ro", uri=True) as db:
        report = json.loads(
            db.execute(
                "SELECT result_json FROM successor_lineages WHERE session_id=?", (SID,)
            ).fetchone()[0]
        )
    compiled = compile_replayed_successor(catalog, market, original, stored, report)
    assert compiled.strategy_hash == report["successor_strategy_hash"]
    assert compiled.strategy.generation == 2
    assert len(compiled.strategy.entry.conditions) == 2
    audit = audit_inherited_decisions(compiled, market)
    assert audit.evaluation.final_equity == pytest.approx(report["successor_final_equity"])


def test_gateway_binds_counted_parent_to_staged_diagnosis(tmp_path):

    from application.academic_checkpoint_service import AcademicMCPCheckpointService
    from research.llm.autonomous_cycle import AcademicCycleService
    from tests.research.historical_g33_fixture import copy_historical_g33_checkpoint
    from tests.research.test_lineage_p0_3 import ROOT, SID

    dst = copy_historical_g33_checkpoint(tmp_path)
    svc = AcademicMCPCheckpointService(project_root=ROOT, state_dir=tmp_path)
    svc.cycle = AcademicCycleService(dst / "cycles.sqlite")
    state = svc.get({"session_id": SID})
    assert state["completed_generations"] == 33
    assert state["model_context"]["output_contract"] == "InheritedResearchIntent"
    _, parent = _real()
    intent = {
        "mode": "structure",
        "parent_ids": [parent.strategy.strategy_id],
        "operations": [
            {
                "op": "REPLACE_RULE",
                "path": "exit.conditions.0",
                "condition": {"op": "less_equal", "left": "plan_vote_score", "value": 0.44},
            }
        ],
        "rationale": "Study the verified child's exit behavior.",
    }
    staged = svc.submit_plan(
        {"session_id": SID, "checkpoint_token": state["checkpoint_token"], "plan": intent}
    )
    assert staged["checkpoint_phase"] == "AWAITING_DIAGNOSIS"
    assert staged["model_context"]["strategy_hash"] != parent.strategy_hash
    assert (
        svc.submit_plan(
            {"session_id": SID, "checkpoint_token": state["checkpoint_token"], "plan": intent}
        )
        == staged
    )
    context = staged["model_context"]
    first = context["observations"]["execution_samples"][0]
    diagnosis = {
        "context_hash": context["context_hash"],
        "audit_hash": context["audit_hash"],
        "strategy_hash": context["strategy_hash"],
        "dataset_hash": context["dataset_hash"],
        "summary": "Compare a controlled exit-rule change against the inherited generation.",
        "hypotheses": [
            {
                "hypothesis_id": "g134_exit",
                "observed_ids": [first["trade_id"]],
                "mechanism": "Modified exit rule may change losing trade durations.",
                "alternative": "Modified exit could also reduce winning durations.",
                "expected_metric": "total_return",
                "predicted_direction": "INCREASE",
                "test_design": "PARAMETER",
                "control": "PARENT_UNCHANGED",
                "next_intent": {
                    "mode": "structure",
                    "parent_ids": [parent.strategy.strategy_id],
                    "operations": [
                        {
                            "op": "REPLACE_RULE",
                            "path": "exit.conditions.0",
                            "condition": {
                                "op": "less_equal",
                                "left": "plan_vote_score",
                                "value": 0.39,
                            },
                        },
                    ],
                    "rationale": "Run a comparison of exit limits on inherited StrategyIR.",
                },
            }
        ],
    }
    done = svc.submit_diagnosis(
        {
            "session_id": SID,
            "checkpoint_token": staged["checkpoint_token"],
            "diagnosis": diagnosis,
            "require_signal_change": True,
        }
    )
    assert done["completed_generations"] == 34
    assert done["history"][-1]["inherited_parent"]["parent_strategy_hash"] == parent.strategy_hash
    assert done["history"][-1]["strategy_hash"] == context["strategy_hash"]
    assert done["latest_controlled_experiments"]["report"]["experiments"][0]["child_strategy_hash"]
    assert svc.get({"session_id": SID})["completed_generations"] == 34
    replay = svc.submit_diagnosis(
        {
            "session_id": SID,
            "checkpoint_token": staged["checkpoint_token"],
            "diagnosis": diagnosis,
            "require_signal_change": True,
        }
    )
    assert replay["history"][-1]["evidence_hash"] == done["history"][-1]["evidence_hash"]
