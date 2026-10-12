"""Market-data audit separates reproducibility, adjustment checks, and PIT proof."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from application.market_data_audit import MarketDataAuditService
from application.market_data_service import MarketDataError
from core.data.contracts import Bar, DataZone, MarketDataSet, MarketSourceProvenance
from core.data.parquet import ParquetDataProvider


def _write_dataset(
    root: Path,
    *,
    vendor: str = "tiingo",
    policy: str = "raw",
    shift: float = 0,
    price_factor: float = 1.0,
    volume_factor: float = 1.0,
    latest: bool = True,
    one_bad_factor: bool = False,
) -> str:
    initial = date(2024, 1, 2)
    relative = f"data/market/{vendor}/QQQ_{initial.isoformat()}_2024-01-04_{policy}.parquet"
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for index in range(3):
        raw = 100 + index + shift
        adjusted = price_factor * raw
        high_factor = 1.5 if index == 1 and one_bad_factor else 1.0
        records.append(
            Bar(
                datetime(2024, 1, 2, tzinfo=timezone.utc) + timedelta(days=index),
                "QQQ",
                adjusted,
                (raw + 2) * price_factor * high_factor,
                (raw - 2) * price_factor,
                (raw + 1) * price_factor,
                1000 * volume_factor,
            )
        )
    dataset = MarketDataSet(
        "dataset-test-v1",
        DataZone.DEVELOPMENT,
        tuple(records),
        provenance=MarketSourceProvenance(
            source_id=vendor,
            retrieved_at=datetime(2024, 2, 1, tzinfo=timezone.utc),
            revision_policy="latest" if latest else "as_of",
            universe_policy="single_symbol",
            corporate_action_policy=policy,
            corporate_action_reference=(
                "https://www.tiingo.com/documentation/end-of-day" if policy != "raw" else None
            ),
            includes_delisted=False,
        ),
    )
    ParquetDataProvider.write(path, dataset)
    return relative


def _audit(root: Path) -> MarketDataAuditService:
    return MarketDataAuditService(root, state_dir=root / "state/private-research")


def test_latest_raw_snapshot_is_reproducible_but_never_pit_certified(tmp_path: Path) -> None:
    raw = _write_dataset(tmp_path)
    service = _audit(tmp_path)
    report = service.audit(raw)
    assert report["status"] == "RESEARCH_ONLY_NOT_PIT_VERIFIED"
    assert report["point_in_time_independently_verified"] is False
    assert report["independent_vendor_comparison"] is None
    assert report["file_sha256"]
    assert "revisions_not_as_of" in report["blocking_reasons"]
    assert "corporate_action_adjustment_unverified" in report["blocking_reasons"]
    assert report["pin_status"] == "NOT_PINNED"
    assert not (tmp_path / "state").exists()
    anchored = service.pin(raw)
    assert anchored["pin_status"] == "MATCHED"
    assert _audit(tmp_path).audit(raw)["pin_status"] == "MATCHED"


def test_pin_detects_mutated_existing_parquet_without_overwriting_original(tmp_path: Path) -> None:
    raw = _write_dataset(tmp_path)
    service = _audit(tmp_path)
    service.pin(raw)
    file = tmp_path / raw
    old = file.read_bytes()
    file.write_bytes(old + b"extra")
    result = service.audit(raw)
    assert result["pin_status"] == "FILE_CHANGED"
    assert result["point_in_time_independently_verified"] is False
    with pytest.raises(MarketDataError, match="changed"):
        service.pin(raw)
    file.write_bytes(old)
    assert service.audit(raw)["pin_status"] == "MATCHED"


def test_dual_vendor_match_is_useful_but_does_not_prove_pit(tmp_path: Path) -> None:
    raw = _write_dataset(tmp_path)
    second = _write_dataset(tmp_path, vendor="kis")
    audit = _audit(tmp_path).audit(raw, comparison_path=second)
    comparison = audit["independent_vendor_comparison"]
    assert comparison["status"] == "MATCH"
    assert comparison["independent_vendors"] is True
    assert comparison["compared_bars"] == 3
    assert audit["point_in_time_independently_verified"] is False


def test_divergence_and_self_comparison_are_not_independent_evidence(tmp_path: Path) -> None:
    raw = _write_dataset(tmp_path)
    changed = _write_dataset(tmp_path, vendor="kis", shift=10)
    report = _audit(tmp_path).audit(raw, comparison_path=changed)
    assert report["independent_vendor_comparison"]["status"] == "PRICE_MISMATCH"
    assert report["independent_vendor_comparison"]["mismatched_bars"] > 0
    same = _audit(tmp_path).audit(raw, comparison_path=raw)
    assert same["independent_vendor_comparison"]["status"] == "NOT_INDEPENDENT"
    assert same["point_in_time_independently_verified"] is False


def test_raw_adjusted_factor_consistency_and_corruption_detection(tmp_path: Path) -> None:
    raw = _write_dataset(tmp_path)
    adjusted = _write_dataset(
        tmp_path, policy="total_return_adjusted", price_factor=0.9, volume_factor=1.1
    )
    good = _audit(tmp_path).audit(raw, adjusted_path=adjusted)
    assert good["corporate_action_consistency"]["status"] == "PRICE_FACTORS_CONSISTENT"
    assert good["corporate_action_consistency"]["compared_bars"] == 3
    assert good["point_in_time_independently_verified"] is False

    adjusted = _write_dataset(
        tmp_path,
        policy="total_return_adjusted",
        price_factor=0.9,
        one_bad_factor=True,
    )
    bad = _audit(tmp_path).audit(raw, adjusted_path=adjusted)
    assert bad["corporate_action_consistency"]["status"] == "ADJUSTMENT_MISMATCH"
    assert bad["corporate_action_consistency"]["mismatched_bars"] > 0


def test_managed_dev_only_path_and_no_untrusted_certificate(tmp_path: Path) -> None:
    raw = _write_dataset(tmp_path, latest=False)
    audit = _audit(tmp_path)
    report = audit.audit(raw)
    assert report["point_in_time_independently_verified"] is False
    assert "independent_historical_as_of_snapshots_missing" in report["blocking_reasons"]
    with pytest.raises(MarketDataError):
        audit.audit("../../../../etc/passwd")
    with pytest.raises(MarketDataError):
        audit.pin("../../../../etc/passwd")
