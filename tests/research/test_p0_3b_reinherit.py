"""P0-3B G134 S7 descendants compete for G135 with exact immutable proof."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from research.llm.autonomous_cycle import AcademicCycleService
from research.llm.lineage_selection import choose_development_parent
from tests.research.historical_g33_fixture import copy_historical_g33_checkpoint
from tests.research.test_lineage_p0_3 import ROOT, SID

_SOURCE = ROOT / "state/moon-http/research/academic-gpt-checkpoints"


def _isolated_service(path: Path) -> AcademicMCPCheckpointService:
    """Replay historical G34/G35 only from pinned, isolated G33 snapshot."""
    dst = copy_historical_g33_checkpoint(path)
    service = AcademicMCPCheckpointService(project_root=ROOT, state_dir=path)
    service.cycle = AcademicCycleService(dst / "cycles.sqlite")
    return service


def _intent(parent_id: str, threshold: float) -> dict:
    return {
        "mode": "structure",
        "parent_ids": [parent_id],
        "operations": [
            {
                "op": "REPLACE_RULE",
                "path": "exit.conditions.0",
                "condition": {"op": "less_equal", "left": "plan_vote_score", "value": threshold},
            }
        ],
        "rationale": "Study a prespecified parent mutation within development-only research.",
    }


def _advance(service: AcademicMCPCheckpointService, threshold: float, hypothesis: float):
    from dataclasses import replace

    from core.features.registry import research_feature_specs
    from core.integrity.hashes import content_hash
    from research.indicator_engine.inherited_decision_audit import audit_inherited_decisions
    from research.llm.diagnostic_research import build_diagnostic_context
    from research.llm.director import ResearchIntent
    from research.llm.intent_bridge import apply_intent

    before = service.get({"session_id": SID})
    with service._connect() as db:
        _, catalog, market, state = service._state(db, SID)
    parent, _, _ = service._selected_ir(catalog, market, state)
    plan = _intent(parent.strategy.strategy_id, threshold)
    staged = service.submit_plan(
        {
            "session_id": SID,
            "checkpoint_token": before["checkpoint_token"],
            "plan": plan,
        }
    )
    child = apply_intent(
        parent.strategy, ResearchIntent.model_validate(plan), research_feature_specs()
    )
    compiled = replace(
        parent,
        strategy=child,
        strategy_hash=content_hash(child.model_dump(mode="json", by_alias=True)),
    )
    audit = audit_inherited_decisions(compiled, market)
    context = build_diagnostic_context(audit, child)
    assert context["context_hash"] == staged["model_context"]["context_hash"]
    sample = context["observations"]["execution_samples"][0]
    diagnosis = {
        "context_hash": context["context_hash"],
        "audit_hash": context["audit_hash"],
        "strategy_hash": context["strategy_hash"],
        "dataset_hash": context["dataset_hash"],
        "summary": "Measure the inherited child before choosing whether to retain it.",
        "hypotheses": [
            {
                "hypothesis_id": f"verified_{int(hypothesis * 100):02d}",
                "observed_ids": [sample["trade_id"]],
                "mechanism": "Changing the exit boundary may change trade outcomes.",
                "alternative": "The same change may worsen drawdown or not change fills.",
                "expected_metric": "total_return",
                "predicted_direction": "INCREASE",
                "test_design": "PARAMETER",
                "control": "PARENT_UNCHANGED",
                "next_intent": _intent(child.strategy_id, hypothesis),
            }
        ],
    }
    return service.submit_diagnosis(
        {
            "session_id": SID,
            "checkpoint_token": staged["checkpoint_token"],
            "diagnosis": diagnosis,
            "require_signal_change": True,
        }
    )


def test_competing_verified_counted_child_wins_only_when_better():
    from tests.research.test_lineage_parent_selection_p0_3b import _candidate

    champion = _candidate()
    challenger = _candidate(
        source_generation=34,
        source_evidence_hash="e" * 64,
        lineage_report_hash="f" * 64,
        successor_strategy_hash="1" * 64,
        strategy_equity_hash="2" * 64,
        child_total_return=0.49,
        successor_total_return=0.55,
        successor_max_drawdown=0.15,
        successor_closed_trades=48,
        successor_market_exposure=0.43,
        source_kind="COUNTED_S7_CHILD",
        hypothesis_id="verified_39",
        source_report_hash="3" * 64,
    )
    selected = choose_development_parent([champion, challenger])
    assert selected and selected["source_generation"] == 34
    assert selected["source_kind"] == "COUNTED_S7_CHILD"
    worse = {**challenger, "successor_total_return": 0.47}
    selected = choose_development_parent([champion, worse])
    assert selected and selected["source_generation"] == champion["source_generation"]


def test_shadow_g134_to_g135_retains_or_promotes_and_rejects_tampering(tmp_path):
    service = _isolated_service(tmp_path)
    first = _advance(service, 0.44, 0.39)
    assert first["completed_generations"] == 34
    candidate = first["latest_controlled_experiments"]["report"]["experiments"][0]
    assert candidate["status"] == "NO_OBSERVED_EFFECT"
    second = service.get({"session_id": SID})
    selection = second["model_context"]["selected_development_parent"]
    assert selection is not None
    assert selection["source_generation"] == 29  # challenger has no observed improvement
    assert second["model_context"]["inheritance_decision"]["rejected_counted_s7"] >= 1
    chosen_hash = selection["selection_hash"]
    assert (
        service.get({"session_id": SID})["model_context"]["selected_development_parent"][
            "selection_hash"
        ]
        == chosen_hash
    )
    stage = _advance(service, 0.28, 0.25)
    assert stage["completed_generations"] == 35
    assert stage["history"][-1]["inherited_parent"]["parent_selection_hash"] == chosen_hash
    assert service.get({"session_id": SID})["completed_generations"] == 35
    assert (
        service.get({"session_id": SID})["model_context"]["selected_development_parent"] is not None
    )
    assert stage["history"][-1]["broker_executable"] is False
    # Source rows are checked before they influence the next candidate pool.
    with service._connect() as db:
        report = db.execute(
            "SELECT report_json FROM experiment_reports WHERE session_id=? AND generation=34",
            (SID,),
        ).fetchone()
        value = json.loads(report[0])
        value["report"]["experiments"][0]["child_final_equity"] += 1000
        db.execute(
            "UPDATE experiment_reports SET report_json=? WHERE session_id=? AND generation=34",
            (json.dumps(value), SID),
        )
    with pytest.raises(ValueError, match="integrity|evidence|mismatch"):
        service.get({"session_id": SID})


def test_shadow_verified_s7_child_enters_parent_pool_and_can_be_replayed(tmp_path):
    service = _isolated_service(tmp_path)
    first = _advance(service, 0.28, 0.35)
    report = first["latest_controlled_experiments"]["report"]["experiments"][0]
    assert report["child_fill_count"] >= 60
    assert report["status"] == "DIRECTION_MATCHED_DEVELOPMENT_ONLY"
    after = service.get({"session_id": SID})
    review = after["model_context"]["inheritance_decision"]
    assert review["counted_s7_tested"] >= 1
    assert review["eligible_counted_s7"] >= 1
    compared = review["comparisons"][0]
    assert compared["replay_verified"] is True
    assert compared["policy_eligible"] is True
    assert compared["closed_trades"] >= 30
    assert 0 < compared["market_exposure"] < 1
    assert compared["qqq_buy_and_hold_return"] > compared["total_return"]
    assert compared["vs_champion_return_pp"] <= 0.01
    assert compared["decision"] in (
        "RETAINED_HIGHER_RANKED_PARENT",
        "PROMOTED_BEST_VERIFIED_CANDIDATE",
    )
    selected = after["model_context"]["selected_development_parent"]
    assert selected is not None
    if selected["source_generation"] == 34:
        assert selected["source_kind"] == "COUNTED_S7_CHILD"
        with service._connect() as db:
            _, catalog, data, state = service._state(db, SID)
        parent, original, _ = service._selected_ir(catalog, data, state)
        assert parent.strategy_hash == selected["successor_strategy_hash"]
        assert original["generation"] == 34
        second = _advance(service, 0.25, 0.24)
        assert second["completed_generations"] == 35
        assert second["history"][-1]["inherited_parent"]["source_generation"] == 34
    else:
        assert review["champion_retained"] is True
        assert review["baseline_parent_strategy_hash"] == selected["successor_strategy_hash"]


def test_shadow_counted_s7_parent_materializes_and_counts_135(tmp_path, monkeypatch):
    import application.academic_checkpoint_service as gateway

    service = _isolated_service(tmp_path)
    genuine_choose = gateway.choose_development_parent

    def force_research_candidate(candidates):
        """Route a genuinely replayed child to test IR wiring, not scoring policy."""
        selected = [x for x in candidates if x.get("source_kind") == "COUNTED_S7_CHILD"]
        return genuine_choose(selected or candidates)

    monkeypatch.setattr(gateway, "choose_development_parent", force_research_candidate)
    first = _advance(service, 0.28, 0.35)
    assert first["completed_generations"] == 34
    next_context = service.get({"session_id": SID})
    chosen = next_context["model_context"]["selected_development_parent"]
    assert chosen and chosen["source_kind"] == "COUNTED_S7_CHILD"
    assert chosen["source_generation"] == 34
    with service._connect() as db:
        _, catalog, data, state = service._state(db, SID)
    compiled, source, selected = service._selected_ir(catalog, data, state)
    assert source["generation"] == 34
    assert selected["successor_strategy_hash"] == compiled.strategy_hash

    second = _advance(service, 0.25, 0.24)
    assert second["completed_generations"] == 35
    generation = second["history"][-1]
    assert generation["inherited_parent"]["source_generation"] == 34
    assert generation["inherited_parent"]["parent_strategy_hash"] == compiled.strategy_hash
    assert generation["inherited_parent"]["source_evidence_hash"] == source["evidence_hash"]
    assert generation["observed_trades"] > 0
    assert (
        second["latest_controlled_experiments"]["original_generation_evidence_hash"]
        == generation["evidence_hash"]
    )
    assert second["checkpoint_phase"] == "AWAITING_PLAN"
