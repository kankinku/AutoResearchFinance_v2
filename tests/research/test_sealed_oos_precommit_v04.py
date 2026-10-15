"""V04 OOS perimeter tests: only development candidate identities can be frozen."""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from core.data.contracts import DataZone
from core.data.parquet import ParquetDataProvider
from research.indicator_engine import cli
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.sealed_oos_precommit import (
    prepare_development_precommit,
    record_development_precommit,
    verify_development_precommit,
)
from tests.research.test_academic_algorithm_plan import _catalog, _market, _plan


def _setup(tmp_path: Path):
    return _catalog(tmp_path), _plan(), _market()


def test_one_shot_receipt_replays_without_oos_data(tmp_path: Path) -> None:
    catalog, plan, market = _setup(tmp_path)
    out = tmp_path / "precommit.json"
    expected = prepare_development_precommit(catalog, plan, market, study_id="research_q01")
    created = record_development_precommit(
        catalog, plan, market, study_id="research_q01", evidence_path=out,
    )
    assert created == expected
    assert created["status"] == "DEVELOPMENT_PRECOMMIT_ONLY_OOS_UNOPENED"
    assert created["selection_locked_for_research"] is True
    assert created["oos_access_performed"] is False
    assert created["oos_result_evaluated"] is False
    assert created["independent_custodian_signature_verified"] is False
    assert created["historical_pit_verified"] is False
    assert created["candidate_promotable"] is False
    assert created["broker_executable"] is False
    assert created["training_dataset_hash"] == market.dataset_hash
    assert created["plan_id"] == plan.plan_id
    assert created["strategy_ir_hash"]
    assert out.stat().st_size < 16_384
    result = verify_development_precommit(
        catalog, plan, market, study_id="research_q01", evidence_path=out,
    )
    assert result["status"] == "PRECOMMIT_REPLAY_MATCHED_OOS_STILL_SEALED"
    assert result["receipt_hash"] == created["receipt_hash"]
    assert result["oos_access_performed"] is False
    assert result["broker_executable"] is False
    assert result == verify_development_precommit(
        catalog, plan, market, study_id="research_q01", evidence_path=out,
    )


def test_second_selection_must_not_replace_prior_candidate(tmp_path: Path) -> None:
    catalog, plan, market = _setup(tmp_path)
    out = tmp_path / "precommit.json"
    original = record_development_precommit(
        catalog, plan, market, study_id="research_q01", evidence_path=out,
    )
    data = out.read_bytes()
    with pytest.raises(ResearchCatalogError, match="exists"):
        record_development_precommit(
            catalog, plan, _market(change_last=True),
            study_id="research_q01", evidence_path=out,
        )
    assert out.read_bytes() == data
    assert original["receipt_hash"]


def test_source_or_plan_changed_after_selection_refused(tmp_path: Path) -> None:
    catalog, plan, market = _setup(tmp_path)
    out = tmp_path / "precommit.json"
    record_development_precommit(
        catalog, plan, market, study_id="research_q01", evidence_path=out,
    )
    with pytest.raises(ResearchCatalogError, match="changed"):
        verify_development_precommit(
            catalog, plan, _market(change_last=True),
            study_id="research_q01", evidence_path=out,
        )
    with pytest.raises(ResearchCatalogError, match="changed"):
        verify_development_precommit(
            catalog, plan.model_copy(update={"plan_id":"different_plan"}),
            market, study_id="research_q01", evidence_path=out,
        )
    with pytest.raises(ResearchCatalogError, match="changed"):
        verify_development_precommit(
            catalog, plan, market, study_id="different_study",
            evidence_path=out,
        )


def test_forged_approval_and_receipt_hash_tampering_never_pass(tmp_path: Path) -> None:
    catalog, plan, market = _setup(tmp_path)
    out = tmp_path / "precommit.json"
    record_development_precommit(
        catalog, plan, market, study_id="research_q01", evidence_path=out,
    )
    raw = out.read_bytes()
    changed = json.loads(raw)
    changed["sealed_oos_approved"] = True
    out.write_text(json.dumps(changed))
    with pytest.raises(ResearchCatalogError, match="changed"):
        verify_development_precommit(
            catalog, plan, market, study_id="research_q01", evidence_path=out,
        )
    out.write_bytes(raw)
    changed = json.loads(raw)
    changed["training_dataset_hash"] = "f" * 64
    out.write_text(json.dumps(changed))
    with pytest.raises(ResearchCatalogError, match="changed"):
        verify_development_precommit(
            catalog, plan, market, study_id="research_q01", evidence_path=out,
        )


@pytest.mark.parametrize("zone", [DataZone.SEALED_OOS, DataZone.VALIDATION])
def test_sealed_and_validation_data_are_never_accepted(tmp_path: Path, zone: DataZone) -> None:
    catalog, plan, market = _setup(tmp_path)
    with pytest.raises(ResearchCatalogError, match="DEVELOPMENT"):
        prepare_development_precommit(
            catalog, plan, replace(market, zone=zone), study_id="research_q01",
        )
    assert not (tmp_path / "precommit.json").exists()


def test_symlink_receipt_and_parent_blocked(tmp_path: Path) -> None:
    catalog, plan, market = _setup(tmp_path)
    ordinary = tmp_path / "ordinary.json"
    ordinary.write_text("do not mutate")
    link = tmp_path / "shortcut.json"
    link.symlink_to(ordinary)
    with pytest.raises(ResearchCatalogError, match="path"):
        record_development_precommit(
            catalog, plan, market, study_id="research_q01", evidence_path=link,
        )
    assert ordinary.read_text() == "do not mutate"
    parent = tmp_path / "safe"
    parent.mkdir()
    shortcut = tmp_path / "shortcut"
    shortcut.symlink_to(parent, target_is_directory=True)
    with pytest.raises(ResearchCatalogError, match="symlink|path"):
        record_development_precommit(
            catalog, plan, market,
            study_id="research_q01", evidence_path=shortcut / "freeze.json",
        )


def test_cli_only_accepts_development_data_and_does_not_load_sealed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    catalog, plan, market = _setup(tmp_path)
    training = tmp_path / "training.parquet"
    ParquetDataProvider.write(training, market)
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(plan.model_dump_json(), encoding="utf-8")
    evidence = tmp_path / "precommit.json"
    base = [
        "indicator-research", "--database", str(catalog.database),
        "freeze-development-selection", "--market-parquet", str(training),
        "--plan-json-file", str(plan_file), "--study-id", "research_q01",
        "--receipt", str(evidence),
    ]
    monkeypatch.setattr(sys, "argv", base)
    assert cli.main() == 0
    answer = json.loads(capsys.readouterr().out)
    assert not answer["oos_access_performed"]
    assert evidence.exists()
    assert cli.main() == 2
    denied = json.loads(capsys.readouterr().out)
    assert denied["status"] == "DEVELOPMENT_FREEZE_REJECTED"
    base[3] = "verify-development-freeze"
    monkeypatch.setattr(sys, "argv", base)
    assert cli.main() == 0
    replay = json.loads(capsys.readouterr().out)
    assert replay["receipt_hash"] == answer["receipt_hash"]
    assert replay["sealed_oos_approved"] is False
    ParquetDataProvider.write(training, replace(market, zone=DataZone.SEALED_OOS))
    assert cli.main() == 2
    denied = json.loads(capsys.readouterr().out)
    assert denied["broker_executable"] is False


def test_invalid_study_ids_rejected_without_write(tmp_path: Path) -> None:
    catalog, plan, market = _setup(tmp_path)
    for study in ("../sealed_oos", "x", "NOT VALID", "data_path/../secrets"):
        with pytest.raises(ResearchCatalogError):
            record_development_precommit(
                catalog, plan, market, study_id=study,
                evidence_path=tmp_path / "precommit.json",
            )
    assert not (tmp_path / "precommit.json").exists()
