"""Regression for precommit vs counted full effective inherited signals."""

from dataclasses import replace

from research.llm.inherited_execution_identity import inherited_effective_signal_hash
from tests.research.test_v3_inherited_audit_warmup import _warmup_fixture


def test_effective_identity_changes_when_executable_rule_changes():
    compiled, market = _warmup_fixture()
    baseline = inherited_effective_signal_hash(compiled, market)
    ir = compiled.strategy.model_copy(update={
        "entry": compiled.strategy.entry.model_copy(update={"logic": "AND"}),
    })
    changed = replace(compiled, strategy=ir)
    assert baseline != inherited_effective_signal_hash(changed, market)


def test_effective_identity_ignores_nonexecuted_metadata():
    compiled, market = _warmup_fixture()
    altered = compiled.strategy.model_copy(update={"strategy_id": "new-trace-id"})
    assert inherited_effective_signal_hash(compiled, market) == (
        inherited_effective_signal_hash(replace(compiled, strategy=altered), market)
    )


def test_effective_identity_not_just_entry_and_regime():
    compiled, market = _warmup_fixture()
    modified = compiled.strategy.model_copy(update={
        "exit": compiled.strategy.exit.model_copy(update={
            "conditions": [
                compiled.strategy.exit.conditions[0].model_copy(
                    update={"op": "greater_than", "value": 0.5}
                )
            ]
        })
    })
    assert inherited_effective_signal_hash(compiled, market) != (
        inherited_effective_signal_hash(replace(compiled, strategy=modified), market)
    )


def test_stage_rejects_full_history_signal_duplicate_before_diagnosis(tmp_path, monkeypatch):
    import pytest

    from application.academic_checkpoint_service import AcademicMCPCheckpointService
    from core.features.registry import research_feature_specs
    from research.llm.director import ResearchIntent
    from research.llm.intent_bridge import apply_intent

    parent, market = _warmup_fixture()
    intent = ResearchIntent.model_validate({
        "mode": "structure",
        "parent_ids": [parent.strategy.strategy_id],
        "operations": [{"op": "CHANGE_AND_OR", "path": "entry.logic", "logic": "AND"}],
        "rationale": "Test an executable AND entry while preserving exit.",
    })
    child = apply_intent(parent.strategy, intent, research_feature_specs())
    successor = replace(parent, strategy=child)
    duplicate_signal = inherited_effective_signal_hash(successor, market)
    state = {
        "session_id": "1" * 32,
        "completed_generations": 88,
        "history": [{
            "generation": 88,
            "strategy_hash": "0" * 64,
            "effective_signal_hash": duplicate_signal,
        }],
    }
    checkpoint = AcademicMCPCheckpointService(
        project_root=tmp_path, state_dir=tmp_path / "research",
    )
    monkeypatch.setattr(
        checkpoint, "_selected_ir",
        lambda *_: (parent, {"algorithm_plan": {}}, {"selection_hash": "3" * 64}),
    )
    with pytest.raises(ValueError, match="DUPLICATE_EFFECTIVE_INHERITED_SIGNALS.*88"):
        checkpoint._stage_inherited_plan(
            None, None, None, market, state,
            {"plan": intent.model_dump(mode="json")}, require_execution_change=True,
        )
