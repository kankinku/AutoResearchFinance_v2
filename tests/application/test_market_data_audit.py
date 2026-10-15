"""Market-data audit separates reproducibility, adjustment checks, and PIT proof."""

from __future__ import annotations

from dataclasses import replace
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



def test_audit_flags_weekend_and_same_day_repetition_without_calendar_certification(
    tmp_path: Path,
) -> None:
    source = _write_dataset(tmp_path)
    path = tmp_path / source
    original = ParquetDataProvider.read(path)
    rows = list(original.bars)
    # A second OHLC observation on a separately timestamped same exchange
    # date is not the same as a legitimate additional daily NYSE session.
    rows[1] = Bar(
        rows[0].timestamp + timedelta(hours=6),
        "QQQ", 101, 103, 99, 102, 1000,
    )
    # Third record reports a Saturday regular-session date.
    rows[2] = Bar(
        datetime(2024, 1, 6, tzinfo=timezone.utc),
        "QQQ", 102, 104, 100, 103, 1000,
    )
    # Match source filename to the expanded test interval.
    target = path.with_name("QQQ_2024-01-02_2024-01-06_raw.parquet")
    ParquetDataProvider.write(
        target, MarketDataSet(original.version, original.zone, tuple(rows),
                              provenance=original.provenance)
    )
    report = _audit(tmp_path).audit(target.relative_to(tmp_path).as_posix())
    observed = report["exchange_session_observations"]
    assert observed["weekend_bars"] == ["QQQ:2024-01-06"]
    assert observed["repeated_session_dates"] == ["QQQ:2024-01-02"]
    assert observed["calendar_independently_verified"] is False
    assert "weekend_exchange_session_bar" in report["blocking_reasons"]
    assert "repeated_exchange_session_date" in report["blocking_reasons"]
    assert "independent_exchange_session_calendar_missing" in report["blocking_reasons"]
    assert report["point_in_time_independently_verified"] is False



def test_official_nyse_calendar_catches_missing_regular_day_with_short_gap(
    tmp_path: Path,
) -> None:
    original_path = _write_dataset(tmp_path)
    original = ParquetDataProvider.read(tmp_path / original_path)
    # The filename still requests Jan 2-4. Omit just Wednesday Jan 3.
    shortened = MarketDataSet(
        original.version, original.zone,
        (original.bars[0], original.bars[2]),
        provenance=original.provenance,
    )
    ParquetDataProvider.write(tmp_path / original_path, shortened)
    report = _audit(tmp_path).audit(original_path)
    nyse = report["official_nyse_regular_sessions"]
    assert nyse["status"] == "MISMATCH_PINNED_NYSE_PUBLIC_SCHEDULE"
    assert nyse["missing_session_examples"] == ["2024-01-03"]
    assert nyse["missing_count"] == 1
    assert nyse["unexpected_count"] == 0
    assert "pinned_official_exchange_session_mismatch_or_unavailable" in report["blocking_reasons"]
    assert "independent_exchange_session_calendar_missing" in report["blocking_reasons"]
    assert report["point_in_time_independently_verified"] is False


def test_official_nyse_calendar_matches_synthetic_requested_full_period(
    tmp_path: Path,
) -> None:
    raw = _write_dataset(tmp_path)
    report = _audit(tmp_path).audit(raw)
    status = report["official_nyse_regular_sessions"]
    assert status["status"] == "MATCHED_PINNED_NYSE_PUBLIC_SCHEDULE"
    assert status["expected_sessions"] == status["observed_sessions"] == 3
    assert status["missing_count"] == 0
    assert status["comparison_scope"] == "requested_file_bounds"
    assert "independent_exchange_session_calendar_missing" not in report["blocking_reasons"]
    assert "independent_historical_as_of_snapshots_missing" in report["blocking_reasons"]
    assert report["point_in_time_independently_verified"] is False



def test_managed_revision_observation_detects_later_same_vendor_correction(
    tmp_path: Path,
) -> None:
    earlier_path = _write_dataset(tmp_path)
    earlier = ParquetDataProvider.read(tmp_path / earlier_path)
    bars = list(earlier.bars)
    bars[1] = replace(bars[1], close=bars[1].close + 0.25)
    bars.append(Bar(datetime(2024, 1, 5, tzinfo=timezone.utc),
                    "QQQ", 104, 106, 102, 105, 1000))
    later = replace(
        earlier,
        bars=tuple(bars),
        provenance=replace(earlier.provenance,
                           retrieved_at=datetime(2024, 3, 1, tzinfo=timezone.utc)),
    )
    revised_path = "data/market/tiingo/QQQ_2024-01-02_2024-01-05_raw.parquet"
    destination = tmp_path / revised_path
    ParquetDataProvider.write(destination, later)
    result = _audit(tmp_path).audit(
        earlier_path, revision_comparison_path=revised_path
    )
    revision = result["vendor_revision_observation"]
    assert revision["status"] == "HISTORICAL_ROWS_REVISED"
    assert revision["comparable_bars"] == 3
    assert revision["changed_bars"] == 1
    assert revision["changed_date_examples"] == ["2024-01-03"]
    assert "revision_comparison_changed_or_unavailable" in result["blocking_reasons"]
    assert revision["historical_point_in_time_price_verified"] is False
    assert result["point_in_time_independently_verified"] is False
    assert result["orders_enabled"] is False
