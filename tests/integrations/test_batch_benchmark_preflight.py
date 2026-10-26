"""Preflight must not queue paid evaluations with an unmeasurable required QQQ gate."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from application.research_batch_service import BatchRequestError, ResearchBatchService
from core.data.contracts import DataZone, SeriesDataSet, SeriesObservation
from core.data.parquet import ParquetDataProvider
from tests.integrations.test_gpt_research_batches import _request
from tests.orchestration.test_evaluation_runner import _write_inputs


def test_required_qqq_gate_rejects_missing_benchmark_before_queue(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    service = ResearchBatchService(project_root=tmp_path, state_dir=tmp_path / "state")
    request = {**_request(), "series_data_path": None}
    with pytest.raises(BatchRequestError) as error:
        service.preflight(request)
    assert error.value.code == "BENCHMARK_SERIES_REQUIRED"
    with pytest.raises(BatchRequestError) as start_error:
        service.start(request)
    assert start_error.value.code == "BENCHMARK_SERIES_REQUIRED"
    assert not service.database.exists()


def test_required_qqq_gate_rejects_missing_nasdaq_without_queuing(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    ParquetDataProvider.write_series(
        tmp_path / "series.parquet",
        SeriesDataSet(
            "one-benchmark-only", DataZone.DEVELOPMENT,
            tuple(SeriesObservation("QQQ", base + timedelta(days=i), 100.0 + i) for i in range(6)),
        ),
    )
    service = ResearchBatchService(project_root=tmp_path, state_dir=tmp_path / "state")
    with pytest.raises(BatchRequestError) as error:
        service.start(_request())
    assert error.value.code == "BENCHMARK_SERIES_INCOMPLETE"
    assert not service.database.exists()


def test_required_qqq_gate_rejects_asof_missing_at_first_bar(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    ParquetDataProvider.write_series(
        tmp_path / "series.parquet",
        SeriesDataSet(
            "late-benchmark", DataZone.DEVELOPMENT,
            tuple(
                SeriesObservation(symbol, base, value)
                for symbol, value in (("NASDAQ", 200.0), ("QQQ", 100.0))
            ),
        ),
    )
    service = ResearchBatchService(project_root=tmp_path, state_dir=tmp_path / "state")
    with pytest.raises(BatchRequestError) as error:
        service.preflight(_request())
    assert error.value.code == "BENCHMARK_SERIES_INCOMPLETE"
    assert not service.database.exists()


def test_optional_qqq_gate_allows_no_external_comparator(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    service = ResearchBatchService(project_root=tmp_path, state_dir=tmp_path / "state")
    request = {**_request(), "series_data_path": None, "min_qqq_cagr_delta": None}
    result = service.preflight(request)
    assert result["status"] in {"READY", "READY_WITH_WARNINGS"}
    assert result["orders_enabled"] is False
    assert not service.database.exists()


def test_valid_aligned_development_series_allows_required_benchmark_gate(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    service = ResearchBatchService(project_root=tmp_path, state_dir=tmp_path / "state")
    result = service.preflight(_request())
    assert result["status"] in {"READY", "READY_WITH_WARNINGS"}
    assert result["orders_enabled"] is False
    assert not service.database.exists()
