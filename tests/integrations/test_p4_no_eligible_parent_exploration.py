"""No eligible P4 parent should not kill fresh original-algorithm exploration."""

from types import SimpleNamespace

import pytest

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from research.llm.generalization_parent_v1 import GeneralizationParentError


def _service(tmp_path, *, quality=True):
    return AcademicMCPCheckpointService(
        project_root=tmp_path,
        state_dir=tmp_path / "isolated",
        parent_portfolio_v2=True,
        generalization_parent_v1=True,
        p4_quality_gate_v1=quality,
        p4_s7_quality_v1=quality,
    )


def _selected(service):
    return service._selected_development_parent(
        None,
        SimpleNamespace(bars=[SimpleNamespace(symbol="QQQ")]),
        {"session_id": "a" * 32, "completed_generations": 3, "history": []},
    )


def test_no_p4_eligible_parent_retains_quality_gate_and_explores(tmp_path, monkeypatch):
    svc = _service(tmp_path)

    def reject(*args):
        raise GeneralizationParentError("P4 no eligible non-cash audited research parent")

    monkeypatch.setattr(svc, "_choose_counted_generation_portfolio", reject)
    assert _selected(svc) is None
    assert svc.p4_quality_gate_v1 is True
    assert svc.p4_s7_quality_v1 is True


def test_unrelated_parent_integrity_error_is_not_suppressed(tmp_path, monkeypatch):
    svc = _service(tmp_path)

    def reject(*args):
        raise GeneralizationParentError("incomparable development years or market dataset")

    monkeypatch.setattr(svc, "_choose_counted_generation_portfolio", reject)
    with pytest.raises(GeneralizationParentError, match="incomparable development years"):
        _selected(svc)


def test_p4_fallback_does_not_activate_without_quality_enrollment(tmp_path, monkeypatch):
    svc = _service(tmp_path, quality=False)

    def reject(*args):
        raise GeneralizationParentError("P4 no eligible non-cash audited research parent")

    monkeypatch.setattr(svc, "_choose_counted_generation_portfolio", reject)
    with pytest.raises(GeneralizationParentError, match="no eligible non-cash"):
        _selected(svc)
