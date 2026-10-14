"""S4 research cycle tests: a complete generation includes LLM diagnosis."""
from pathlib import Path

import pytest

from core.data.contracts import DataZone, MarketDataSet
from research.llm.autonomous_cycle import AcademicCycleService, CycleStateError
from tests.research.test_academic_algorithm_plan import _catalog, _market, _plan


class ScriptedResearcher:
    """Deterministic stub; tests are NOT evidence of actual LLM execution."""

    def __init__(self, *, duplicate=False, bad_diagnosis=False):
        self.plans = []
        self.diagnoses = []
        self.duplicate = duplicate
        self.bad_diagnosis = bad_diagnosis
        self.fail_model = False

    def propose(self, context):
        if self.fail_model:
            raise RuntimeError("provider unavailable")
        if context.get("output_contract") == "AlgorithmPlan":
            self.plans.append(context)
            n = context["generation"]
            payload = _plan().model_dump(mode="json")
            payload["plan_id"] = f"generation_{n:02d}"
            if n > 1 and not self.duplicate:
                assert context["prior_research"]["generation"] == n - 1
                assert context["prior_research"]["causal_status"] == "UNTESTED_HYPOTHESIS"
                assert context["prior_research"]["diagnostic_proposal_hash"]
                if n == 2:
                    payload["cases"][0]["min_score"] = 0.75
                else:
                    payload["cases"][0]["min_score"] = 0.2
                    for case in payload["cases"]:
                        case["when"]["threshold"] = 0.0005
            return payload
        assert context["schema"] == "research-diagnostic-context-v1"
        self.diagnoses.append(context)
        observation = context["observations"]["execution_samples"][0]
        ids = ["invented_decision"] if self.bad_diagnosis else [
            observation["trade_id"], observation["decision_id"]
        ]
        return {
            "context_hash": context["context_hash"],
            "audit_hash": context["audit_hash"],
            "strategy_hash": context["strategy_hash"],
            "dataset_hash": context["dataset_hash"],
            "summary": "Compare a regime filter ablation with the unchanged reference.",
            "hypotheses": [{
                "hypothesis_id": "filter_ablation",
                "observed_ids": ids,
                "mechanism": "The regime filter may exclude some recovery windows.",
                "alternative": "Regime filters might protect against choppy trades.",
                "expected_metric": "total_return", "predicted_direction": "INCREASE",
                "test_design": "ABLATION", "control": "PARENT_UNCHANGED",
                "next_intent": {
                    "mode": "structure", "parent_ids": [context["algorithm_parent_id"]],
                    "operations": [{"op": "REMOVE_REGIME_FILTER", "path": "regime_filters.0"}],
                    "rationale": "Compare a single filter ablation with the unchanged parent.",
                },
            }],
        }


def _start(tmp_path, generations=3):
    catalog, market = _catalog(tmp_path), _market()
    service = AcademicCycleService(tmp_path / "state" / "academic-cycle.sqlite")
    start = service.start(catalog, market, generations=generations)
    return service, catalog, market, start["session_id"]


def test_multi_generation_evidence_and_feedback(tmp_path: Path):
    service, catalog, market, sid = _start(tmp_path, generations=2)
    provider = ScriptedResearcher()
    first = service.advance(sid, catalog, market, provider)
    assert first["completed_generations"] == 1
    assert first["status"] == "AWAITING_PROVIDER"
    assert first["history"][0]["observed_trades"] > 0
    assert first["history"][0]["hypothesis_ids"] == ["filter_ablation"]
    assert first["history"][0]["causal_status"] == "UNTESTED_HYPOTHESIS"
    last = service.advance(sid, catalog, market, provider)
    assert last["status"] == "COMPLETED"
    assert last["completed_generations"] == 2
    assert last["history"][1]["previous_evidence_hash"] == last["history"][0]["evidence_hash"]
    assert (
        last["history"][0]["algorithm_semantic_hash"]
        != last["history"][1]["algorithm_semantic_hash"]
    )
    assert len(provider.plans) == 2 and len(provider.diagnoses) == 2
    assert service.get(sid, catalog, market) == last
    assert not last["orders_enabled"] and not last["independent_oos_approved"]
    with pytest.raises(CycleStateError, match="complete"):
        service.advance(sid, catalog, market, provider)


def test_duplicate_semantics_cannot_be_laundered_with_new_plan_id(tmp_path: Path):
    service, catalog, market, sid = _start(tmp_path)
    provider = ScriptedResearcher(duplicate=True)
    service.advance(sid, catalog, market, provider)
    with pytest.raises(CycleStateError, match="duplicate"):
        service.advance(sid, catalog, market, provider)
    state = service.get(sid, catalog, market)
    assert state["completed_generations"] == 1
    assert state["status"] == "INTERRUPTED"


def test_bad_llm_and_resume_keep_completed_evidence(tmp_path: Path):
    service, catalog, market, sid = _start(tmp_path)
    provider = ScriptedResearcher(bad_diagnosis=True)
    with pytest.raises(ValueError):
        service.advance(sid, catalog, market, provider)
    assert service.get(sid, catalog, market)["status"] == "INTERRUPTED"
    assert service.get(sid, catalog, market)["completed_generations"] == 0
    with pytest.raises(CycleStateError, match="resume"):
        service.advance(sid, catalog, market, provider)
    provider.bad_diagnosis = False
    service.resume(sid, catalog, market)
    assert service.advance(sid, catalog, market, provider)["completed_generations"] == 1
    provider.fail_model = True
    with pytest.raises(RuntimeError, match="unavailable"):
        service.advance(sid, catalog, market, provider)
    assert service.get(sid, catalog, market)["completed_generations"] == 1


def test_sealed_and_modified_dataset_blocked_before_provider(tmp_path: Path):
    service, catalog, market, sid = _start(tmp_path)
    sealed = MarketDataSet(market.version, DataZone.SEALED_OOS, market.bars)
    other = AcademicCycleService(tmp_path / "other.sqlite")
    with pytest.raises(CycleStateError, match="development"):
        other.start(catalog, sealed, generations=2)
    provider = ScriptedResearcher()
    for mismatch in (sealed, _market(change_last=True)):
        with pytest.raises(CycleStateError, match="dataset"):
            service.advance(sid, catalog, mismatch, provider)
    assert not provider.plans and not provider.diagnoses


def test_sqlite_record_tampering_and_missing_provider(tmp_path: Path):
    service, catalog, market, sid = _start(tmp_path)
    with pytest.raises(CycleStateError, match="provider"):
        service.advance(sid, catalog, market, None)
    assert service.get(sid, catalog, market)["status"] == "AWAITING_PROVIDER"
    service.advance(sid, catalog, market, ScriptedResearcher())
    with service._connect() as db:
        db.execute("UPDATE generations SET evidence_hash=?", ("0" * 64,))
    with pytest.raises(CycleStateError, match="integrity"):
        service.get(sid, catalog, market)
    with pytest.raises(CycleStateError, match="integrity"):
        service.advance(sid, catalog, market, ScriptedResearcher())


def test_bounded_run_finishes_all_requested_generations_in_one_invocation(tmp_path: Path):
    service, catalog, market, sid = _start(tmp_path, generations=3)
    model = ScriptedResearcher()
    summary = service.run_bounded(sid, catalog, market, model, max_steps=3)
    assert summary["status"] == "COMPLETED"
    assert summary["completed_generations"] == 3
    assert len(model.plans) == 3 and len(model.diagnoses) == 3
    assert len({x["algorithm_semantic_hash"] for x in summary["history"]}) == 3
    assert len({x["effective_signal_hash"] for x in summary["history"]}) == 3
    assert len({x["evidence_hash"] for x in summary["history"]}) == 3
    assert service.get(sid, catalog, market) == summary


def test_after_start_catalog_cannot_silently_change(tmp_path: Path):
    service, catalog, market, sid = _start(tmp_path)
    # Build a separate catalog with an altered verification state, without writing
    # into the original catalog or modifying the session.
    from research.indicator_engine.catalog import ResearchCatalog
    from research.indicator_engine.seed import seed_approved_references
    other = ResearchCatalog(tmp_path / "alternate.sqlite")
    seed_approved_references(other)
    model = ScriptedResearcher()
    with pytest.raises(CycleStateError, match="catalog"):
        service.advance(sid, other, market, model)
    assert not model.plans


def test_changed_threshold_same_actual_signals_rejected(tmp_path: Path):
    service, catalog, market, sid = _start(tmp_path)

    class NoBehaviorChange(ScriptedResearcher):
        def propose(self, context):
            payload = super().propose(context)
            if context.get("output_contract") == "AlgorithmPlan" and context["generation"] == 2:
                payload["cases"][0]["min_score"] = 0.55
            return payload

    provider = NoBehaviorChange()
    service.advance(sid, catalog, market, provider)
    with pytest.raises(CycleStateError, match="effective signals"):
        service.advance(sid, catalog, market, provider)
    assert service.get(sid, catalog, market)["completed_generations"] == 1


def test_cancel_checkpoint_preserves_completed_evidence_and_blocks_further_llm(tmp_path: Path):
    service, catalog, market, sid = _start(tmp_path, generations=3)
    model = ScriptedResearcher()
    first = service.advance(sid, catalog, market, model)
    stopped = service.cancel(sid, catalog, market)
    assert stopped["status"] == "CANCELLED"
    assert stopped["completed_generations"] == 1
    assert stopped["history"] == first["history"]
    assert stopped["final_report"]["completion_reason"] == "CANCELLED_AT_CHECKPOINT"
    assert stopped["final_report"]["tested_hypotheses"] == 0
    assert not stopped["final_report"]["independent_profitability_verified"]
    with pytest.raises(CycleStateError, match="cancel|complete"):
        service.advance(sid, catalog, market, model)
    with pytest.raises(CycleStateError, match="interrupted"):
        service.resume(sid, catalog, market)
    with pytest.raises(CycleStateError, match="cancel"):
        service.cancel(sid, catalog, market)
    assert service.get(sid, catalog, market) == stopped


def test_report_complete_preserves_original_generation_metrics(tmp_path: Path):
    service, catalog, market, sid = _start(tmp_path, generations=2)
    result = service.run_bounded(sid, catalog, market, ScriptedResearcher(), max_steps=2)
    report = result["final_report"]
    assert report["completion_reason"] == "REQUESTED_GENERATIONS_COMPLETED"
    assert report["generations_completed"] == 2
    assert report["generations_requested"] == 2
    assert report["first_total_return"] == result["history"][0]["metrics"]["total_return"]
    assert report["last_total_return"] == result["history"][-1]["metrics"]["total_return"]
    assert report["best_development_return"] == max(
        h["metrics"]["total_return"] for h in result["history"]
    )
    assert report["tested_hypotheses"] == 0
    assert report["causal_status"] == "NOT_ESTABLISHED"
    assert not report["independent_profitability_verified"]


def test_reconcile_stale_claim_requires_explicit_action_without_losing_history(tmp_path: Path):
    service, catalog, market, sid = _start(tmp_path)
    initial = service.advance(sid, catalog, market, ScriptedResearcher())
    with service._connect() as db:
        db.execute(
            "UPDATE sessions SET status='EXECUTING',running_token=? WHERE id=?",
            ("failed-process-token", sid),
        )
    assert service.get(sid, catalog, market)["status"] == "EXECUTING"
    with pytest.raises(CycleStateError, match="resume"):
        service.advance(sid, catalog, market, ScriptedResearcher())
    fixed = service.interrupt_stale(sid, catalog, market)
    assert fixed["status"] == "INTERRUPTED"
    assert fixed["completed_generations"] == initial["completed_generations"]
    assert fixed["history"] == initial["history"]
    assert service.resume(sid, catalog, market)["status"] == "AWAITING_PROVIDER"
    assert service.advance(sid, catalog, market, ScriptedResearcher())[
        "completed_generations"
    ] == 2
