"""P3-B enrollment cannot retroactively mutate an old research campaign."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from tests.research.test_academic_inherited_historical_robustness import _market


def test_legacy_service_does_not_create_p3_enrollment(tmp_path: Path):
    service = AcademicMCPCheckpointService(
        project_root=tmp_path, state_dir=tmp_path / "state",
        parent_portfolio_v2=True,
    )
    with service._connect() as db:
        assert db.execute(
            "SELECT name FROM sqlite_master WHERE name='generalization_enrollments'"
        ).fetchone() is None


def test_p3_needs_scoped_portfolio(tmp_path: Path):
    with pytest.raises(ValueError, match="requires scoped"):
        AcademicMCPCheckpointService(
            project_root=tmp_path, state_dir=tmp_path/"state",
            generalization_parent_v1=True,
        )


@pytest.mark.parametrize("p4_quality", [False, True])
def test_explicit_new_session_policy_records_dataset_hash(tmp_path: Path, monkeypatch,
                                                          p4_quality: bool):
    service=AcademicMCPCheckpointService(
        project_root=tmp_path, state_dir=tmp_path/"state",
        parent_portfolio_v2=True, generalization_parent_v1=True,
        p4_quality_gate_v1=p4_quality,
    )
    market=_market()
    expected_id="c"*32
    monkeypatch.setattr(service, "_catalog", lambda *_: object())
    monkeypatch.setattr(service.cycle, "start",
                        lambda cat, data, generations: {"session_id": expected_id})
    monkeypatch.setattr(service, "get", lambda args: args)
    monkeypatch.setattr(
        "application.academic_checkpoint_service.resolve_project_input",
        lambda *args: tmp_path / "study.parquet"
    )
    monkeypatch.setattr(
        "application.academic_checkpoint_service.ParquetDataProvider.read",
        lambda *args: market
    )
    monkeypatch.setattr(
        "application.academic_checkpoint_service.get_s6_external_reference",
        lambda *args: SimpleNamespace(version="test-backend"),
    )
    monkeypatch.setattr(
        "research.indicator_engine.external_reference._backend_version",
        lambda: "test-backend",
    )
    service.start({"data_path":"study.parquet","generations":100})
    with service._connect() as db:
        row=db.execute(
            "SELECT dataset_hash, policy FROM generalization_enrollments WHERE session_id=?",
            (expected_id,),
        ).fetchone()
        assert row is not None
        assert row["dataset_hash"] == market.dataset_hash
        assert row["policy"] == (
            "AUDITED_EX_POST_PARENT_P4_QUALITY_V1"
            if p4_quality else "AUDITED_EX_POST_PARENT_V1"
        )
        assert db.execute(
            "SELECT COUNT(*) FROM generalization_enrollments"
        ).fetchone()[0] == 1


def test_p3_cannot_optimize_on_already_exposed_2026_data(tmp_path: Path):
    from dataclasses import replace
    from datetime import datetime, timezone

    from research.llm.autonomous_cycle import CycleStateError

    service = AcademicMCPCheckpointService(
        project_root=tmp_path, state_dir=tmp_path / "state",
        parent_portfolio_v2=True, generalization_parent_v1=True,
    )
    market = _market()
    last = replace(
        market.bars[-1],
        timestamp=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    future = replace(market, bars=(*market.bars, last))
    with pytest.raises(CycleStateError, match="exposed 2026"):
        service._scoped_generalization_selection(
            [], future, {"session_id": "b"*32, "completed_generations": 0}
        )


def test_p4_cannot_be_enabled_without_p3_opt_in(tmp_path: Path):
    with pytest.raises(ValueError, match="requires scoped generalization"):
        AcademicMCPCheckpointService(
            project_root=tmp_path, state_dir=tmp_path / "state",
            parent_portfolio_v2=True, p4_quality_gate_v1=True,
        )
