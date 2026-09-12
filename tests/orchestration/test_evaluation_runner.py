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


def test_rejected_evidence_accumulates_and_reaches_next_context(tmp_path: Path) -> None:
    from memory.evidence_knowledge import sync_knowledge
    from memory.research_evidence import research_evidence

    _write_inputs(tmp_path)
    state = tmp_path / "state"
    state.mkdir()
    prior = {"schema_version": 1, "known_good": [{"candidate_hash": "old"}],
             "known_bad": [], "unexplored": [], "custom_field": {"keep": True}}
    (state / "knowledge.json").write_text(json.dumps(prior), encoding="utf-8")
    for _ in range(2):
        run_local_evaluation(project_root=tmp_path, state_dir=state,
                             source_path="strategy.yaml", data_path="bars.parquet")
    knowledge = json.loads((state / "knowledge.json").read_text(encoding="utf-8"))
    assert knowledge["known_good"] == prior["known_good"]
    assert knowledge["custom_field"] == {"keep": True}
    assert len(knowledge["known_bad"]) == 2
    sync_knowledge(state)
    assert json.loads((state / "knowledge.json").read_text(encoding="utf-8")) == knowledge
    context = build_research_context(state)
    assert len(context["failure_knowledge"]) == 1
    assert context["failure_knowledge"][0]["occurrences"] == 2
    assert all(r["causal_status"] == "UNKNOWN" for r in context["failure_knowledge"])
    evidence = research_evidence(state)
    assert len(evidence["runs"]) == 2
    assert all(r["reject_count"] == 1 for r in evidence["runs"])
    assert evidence["legacy"]["record_count"] == 0
    assert evidence["runs"][0]["manifest"]["cost_model"]["version"] == "cost-v1"


def test_changed_inputs_in_same_run_are_rejected(tmp_path: Path) -> None:
    import pytest

    from memory.evidence_store import EvidenceIntegrityError, EvidenceStore

    _write_inputs(tmp_path)
    state = tmp_path / "state"
    store = EvidenceStore(state)
    store.append("run", "run:fixed", {
        "research_run_id": "fixed", "requested_generations": 2, "seed": 0,
    })
    kwargs = dict(project_root=tmp_path, state_dir=state, source_path="strategy.yaml",
                  data_path="bars.parquet", research_run_id="fixed")
    run_local_evaluation(**kwargs, attempt_id="first", generation=1)
    with pytest.raises(EvidenceIntegrityError, match="conflict"):
        run_local_evaluation(**kwargs, attempt_id="second", generation=2, min_trades=999)


def test_sealed_metadata_denied_before_loading_rows(tmp_path: Path, monkeypatch) -> None:
    import pandas as pd
    import pytest

    from memory.evidence_store import EvidenceIntegrityError

    _, data, _ = _write_inputs(tmp_path)
    original = ParquetDataProvider.read(data)
    ParquetDataProvider.write(data, MarketDataSet(original.version, DataZone.SEALED_OOS,
                                                original.bars))
    def forbidden(*args, **kwargs):
        raise AssertionError("sealed rows were read")
    monkeypatch.setattr(pd, "read_parquet", forbidden)
    with pytest.raises(EvidenceIntegrityError, match="sealed"):
        run_local_evaluation(project_root=tmp_path, state_dir=tmp_path / "state",
                             source_path="strategy.yaml", data_path="bars.parquet")


def test_actual_loop_feeds_first_rejection_to_second_proposal(tmp_path: Path) -> None:
    from research.llm.director import ResearchDirector
    from research.llm.provider import CodexIntentProvider
    from runtime.research_loop import ResearchLoopConfig, run_autoresearch

    _write_inputs(tmp_path)
    contexts = []
    def propose(context):
        contexts.append(context)
        return {"mode": "parameter", "parent_ids": ["runner-test"],
                "operations": [], "rationale": "baseline control"}
    outcome = run_autoresearch(
        ResearchLoopConfig(project_root=tmp_path, state_dir=tmp_path / "state",
                           source_path="strategy.yaml", data_path="bars.parquet",
                           generations=2, intent_repair_attempts=0),
        ResearchDirector(CodexIntentProvider(propose)),
    )
    assert contexts[0]["failure_knowledge"] == []
    assert contexts[1]["failure_knowledge"]
    assert contexts[1]["failure_knowledge"][0]["failed_gates"]
    assert outcome["status"] == "COMPLETED"


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


def test_local_evaluation_persists_explicit_generation_number(tmp_path: Path) -> None:
    _strategy, _data, _series = _write_inputs(tmp_path)

    run_local_evaluation(
        project_root=tmp_path,
        state_dir=tmp_path / "state",
        source_path="strategy.yaml",
        data_path="bars.parquet",
        count=1,
        min_trades=0,
        generation=4,
    )

    records = [
        json.loads(line)
        for line in (tmp_path / "state" / "test-records.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert records
    assert {record["generation"] for record in records} == {4}


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
