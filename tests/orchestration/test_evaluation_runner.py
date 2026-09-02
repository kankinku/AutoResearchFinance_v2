from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.data.contracts import Bar, DataZone, MarketDataSet, SeriesDataSet, SeriesObservation
from core.data.parquet import ParquetDataProvider
from mutation.engine import MutationOperation
from mutation.parameter import ParameterDomain
from orchestration.evaluation_runner import build_research_context, run_local_evaluation
from strategy_ir.schema import FeatureRef


def _write_inputs(root: Path) -> tuple[Path, Path, Path]:
    strategy = root / "strategy.yaml"
    strategy.write_text(
        "schema_version: 1\n"
        "id: runner-test\n"
        "family: trend\n"
        "generation: 0\n"
        "indicators:\n"
        "  fast: {type: SMA, period: 2}\n"
        "entry: {logic: AND, conditions: [{op: greater_than, left: close, value: 0}]}\n"
        "exit: {logic: AND, conditions: [{op: less_than, left: close, value: 0}]}\n"
        "risk: {stop_loss_pct: 0, take_profit_pct: 0}\n",
        encoding="utf-8",
    )
    timestamps = tuple(
        datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=index)
        for index in range(6)
    )
    bars = tuple(
        Bar(timestamp, "QQQ", 100 + index, 101 + index, 99 + index, 100 + index, 1000)
        for index, timestamp in enumerate(timestamps)
    )
    data = root / "bars.parquet"
    ParquetDataProvider.write(data, MarketDataSet("bars-v1", DataZone.DEVELOPMENT, bars))
    observations = tuple(
        SeriesObservation(series_id, timestamp, start + index)
        for series_id, start in (("NASDAQ", 200.0), ("QQQ", 100.0))
        for index, timestamp in enumerate(timestamps)
    )
    series = root / "series.parquet"
    ParquetDataProvider.write_series(
        series, SeriesDataSet("series-v1", DataZone.DEVELOPMENT, observations)
    )
    return strategy, data, series


def test_local_evaluation_runs_parameter_domain_and_benchmark(tmp_path: Path) -> None:
    strategy, data, series = _write_inputs(tmp_path)

    result = run_local_evaluation(
        project_root=tmp_path,
        state_dir=tmp_path / "state",
        source_path="strategy.yaml",
        data_path="bars.parquet",
        series_data_path="series.parquet",
        parameter_domains=(
            ParameterDomain("indicators.fast.period", (2, 3)),
        ),
        count=2,
        min_trades=0,
        min_qqq_cagr_delta=0.10,
    )

    assert strategy.is_file() and data.is_file() and series.is_file()
    assert result["candidate_count"] == 2
    records = [
        json.loads(line)
        for line in (tmp_path / "state" / "test-records.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert len(records) == 2
    assert all(record["nasdaq_excess_return"] is not None for record in records)
    assert all(record["qqq_cagr_delta"] is not None for record in records)
    assert all(record["status"] == "REJECT" for record in records)


def test_local_evaluation_without_domains_is_explicit_baseline(tmp_path: Path) -> None:
    _strategy, _data, _series = _write_inputs(tmp_path)

    result = run_local_evaluation(
        project_root=tmp_path,
        state_dir=tmp_path / "state",
        source_path="strategy.yaml",
        data_path="bars.parquet",
        count=4,
        min_trades=0,
    )

    assert result["candidate_count"] == 1
    assert result["search_mode"] == "baseline"


def test_local_evaluation_applies_intent_operations_and_records_feature_lineage(
    tmp_path: Path,
) -> None:
    strategy, data, series = _write_inputs(tmp_path)
    operations = (
        MutationOperation(
            "ADD_FEATURE",
            "features.us10y_rsi",
            FeatureRef(
                feature_id="rsi",
                inputs=("US10Y.close",),
                timeframe="1w",
                lookback=2,
                lag_bars=1,
            ),
        ),
    )
    # Add the selected external series to the same versioned series input.
    series_data = ParquetDataProvider.read_series(series)
    timestamps = tuple(
        item.timestamp
        for item in series_data.observations
        if item.series_id == "QQQ"
    )
    observations = tuple(series_data.observations) + tuple(
        SeriesObservation("US10Y", timestamp, 1.0 + index)
        for index, timestamp in enumerate(timestamps)
    )
    ParquetDataProvider.write_series(
        series,
        SeriesDataSet(
            "series-v2",
            DataZone.DEVELOPMENT,
            tuple(
                sorted(
                    observations,
                    key=lambda item: (item.series_id, item.timestamp),
                )
            ),
        ),
    )

    result = run_local_evaluation(
        project_root=tmp_path,
        state_dir=tmp_path / "state",
        source_path=str(strategy.name),
        data_path=str(data.name),
        series_data_path=str(series.name),
        operations=operations,
        count=1,
        min_trades=0,
        min_annual_trades=None,
    )

    assert result["candidate_count"] == 1
    record = json.loads(
        (tmp_path / "state" / "test-records.jsonl").read_text(encoding="utf-8")
    )
    assert record["feature_ids"] == ["rsi"]
    assert record["feature_lineage"][0]["timeframe"] == "1w"


def test_research_context_exposes_registered_feature_selection_contract(tmp_path: Path) -> None:
    strategy, _data, _series = _write_inputs(tmp_path)

    context = build_research_context(tmp_path / "state", source_path=strategy)

    feature = next(
        item for item in context["feature_catalog"] if item["name"] == "us_20y_change"
    )
    assert feature["canonical_id"]
    assert feature["status"] == "REGISTERED"
    assert feature["inputs"] == ["US20Y.close"]
    assert feature["supported_timeframes"] == ["1m", "5m", "15m", "1h", "1d", "1w", "1mo"]
