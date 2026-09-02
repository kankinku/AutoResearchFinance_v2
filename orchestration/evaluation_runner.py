from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
from typing import Any

from core.data.contracts import MarketDataSet, SeriesDataSet
from core.data.parquet import ParquetDataProvider
from core.features.alignment import align_as_of
from core.features.registry import research_feature_specs
from dashboard.ledger import append_funnel_results
from evaluation.benchmark import BenchmarkData
from evaluation.selector import FunnelConfig
from mutation.engine import MutationOperation
from mutation.parameter import ParameterDomain, ParameterValue
from orchestration.pipeline import GenerationPipeline
from strategy_ir.normalizer import normalize_source
from strategy_ir.schema import StrategyIR

ALLOWED_STRATEGY_SUFFIXES = frozenset({".yaml", ".yml", ".json", ".py", ".pine", ".pinescript"})


def resolve_project_input(project_root: Path, value: object, suffixes: frozenset[str]) -> Path:
    if isinstance(value, Path):
        raw_value = value
    elif isinstance(value, str) and value.strip():
        raw_value = Path(value)
    else:
        raise ValueError("path is required")
    candidate = (project_root / raw_value).resolve()
    if project_root.resolve() not in candidate.parents:
        raise PermissionError("path is outside project root")
    if candidate.name.lower() == ".env" or candidate.suffix.lower() not in suffixes:
        raise PermissionError("path is not an allowed research input")
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    return candidate


def run_local_evaluation(
    *,
    project_root: Path,
    state_dir: Path,
    source_path: object,
    data_path: object,
    method: str = "grid",
    count: int = 1,
    seed: int = 0,
    min_trades: int = 10,
    parameter_domains: Sequence[ParameterDomain] = (),
    operations: Sequence[MutationOperation] = (),
    strategy_override: StrategyIR | None = None,
    generation: int | None = None,
    series_data_path: object | None = None,
    min_qqq_cagr_delta: float | None = None,
    min_annual_trades: int | None = 30,
) -> dict[str, object]:
    source = resolve_project_input(project_root, source_path, ALLOWED_STRATEGY_SUFFIXES)
    data = resolve_project_input(project_root, data_path, frozenset({".parquet"}))
    if method not in {"grid", "random", "bayesian"}:
        raise ValueError("evaluation method is invalid")
    if count < 1 or seed < 0 or min_trades < 0:
        raise ValueError("evaluation numeric options are invalid")
    if generation is not None and generation < 1:
        raise ValueError("generation must be positive")
    if min_annual_trades is not None and min_annual_trades < 0:
        raise ValueError("minimum annual trades cannot be negative")
    if min_qqq_cagr_delta is not None and not isfinite(min_qqq_cagr_delta):
        raise ValueError("QQQ CAGR target must be finite")
    domains = tuple(parameter_domains)
    if any(not isinstance(domain, ParameterDomain) for domain in domains):
        raise TypeError("parameter_domains must contain ParameterDomain values")
    typed_operations = tuple(operations)
    if any(not isinstance(operation, MutationOperation) for operation in typed_operations):
        raise TypeError("operations must contain MutationOperation values")
    imported = normalize_source(source) if strategy_override is None else None
    strategy = strategy_override or (imported.strategy if imported is not None else None)
    if strategy is None:
        raise ValueError("strategy source is unsupported")
    dataset = ParquetDataProvider.read(data)
    series = _read_series_input(project_root, series_data_path)
    feature_specs = {spec.name: spec for spec in research_feature_specs()}
    feature_inputs = _market_feature_inputs(dataset)
    benchmark = _benchmark_data(dataset, series) if series is not None else None
    pipeline_result = GenerationPipeline().run(
        parent=strategy,
        dataset=dataset,
        operations=typed_operations,
        domains=domains,
        method=method,
        count=count,
        seed=seed,
        funnel=FunnelConfig(
            min_fast_trades=min_trades,
            min_full_trades=min_trades,
            min_qqq_cagr_delta=min_qqq_cagr_delta,
            min_annual_trades=min_annual_trades,
        ),
        benchmark_data=benchmark,
        feature_specs=feature_specs,
        feature_inputs=feature_inputs,
        external_series=series,
    )
    record_generation = strategy.generation + 1 if generation is None else generation
    append_funnel_results(
        state_dir / "test-records.jsonl",
        generation=record_generation,
        results=pipeline_result.funnel,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    return {
        "status": "COMPLETED",
        "candidate_count": len(pipeline_result.candidates),
        "search_mode": "baseline" if not domains and not typed_operations else method,
        "counts": {
            status: sum(item.status == status for item in pipeline_result.funnel)
            for status in sorted({item.status for item in pipeline_result.funnel})
        },
        **_best_strategy_payload(pipeline_result),
    }


def _best_strategy_payload(pipeline_result: object) -> dict[str, object]:
    candidates = getattr(pipeline_result, "candidates", ())
    results = getattr(pipeline_result, "funnel", ())
    eligible = [
        (candidate, result)
        for candidate, result in zip(candidates, results, strict=True)
        if result.status != "REJECT"
    ]
    if not eligible:
        return {}
    candidate, _result = max(eligible, key=lambda item: (item[1].score, item[0].candidate_hash))
    return {"best_strategy": candidate.strategy.model_dump(mode="json", by_alias=True)}


def parse_parameter_domains(raw: object) -> tuple[ParameterDomain, ...]:
    """Parse CLI/MCP JSON values into validated local search domains."""

    if raw is None:
        return ()
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        raise ValueError("parameter_domains must be an array")
    domains: list[ParameterDomain] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise ValueError("each parameter domain must be an object")
        name = item.get("name")
        values = item.get("values")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("parameter domain name is required")
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
            raise ValueError(f"parameter domain values must be an array: {name}")
        typed_values: list[ParameterValue] = []
        for value in values:
            if isinstance(value, (bool, int, float, str)):
                typed_values.append(value)
            else:
                raise ValueError(f"parameter domain value is not scalar: {name}")
        domains.append(ParameterDomain(name.strip(), tuple(typed_values)))
    return tuple(domains)


def _read_series_input(project_root: Path, value: object | None) -> SeriesDataSet | None:
    if value is None:
        return None
    path = resolve_project_input(project_root, value, frozenset({".parquet"}))
    return ParquetDataProvider.read_series(path)


def _market_feature_inputs(dataset: MarketDataSet) -> dict[str, tuple[float, ...]]:
    return {
        field: tuple(float(getattr(bar, field)) for bar in dataset.bars)
        for field in ("open", "high", "low", "close", "volume")
    }


def _benchmark_data(
    dataset: MarketDataSet, series: SeriesDataSet | None
) -> BenchmarkData | None:
    if series is None:
        return None
    target_timestamps = tuple(sorted({bar.timestamp for bar in dataset.bars}))
    available_ids = {item.series_id.upper() for item in series.observations}
    if not (available_ids & {"QQQ", "NASDAQ"}):
        return None
    values: dict[str, tuple[float, ...]] = {}
    for series_id in ("QQQ", "NASDAQ"):
        observations = tuple(
            item for item in series.observations if item.series_id.upper() == series_id
        )
        if not observations:
            raise ValueError(f"series data must include {series_id} benchmark")
        aligned = align_as_of(target_timestamps, observations)
        if any(value is None for value in aligned):
            raise ValueError(f"benchmark series is missing an as-of value: {series_id}")
        values[series_id] = tuple(float(value) for value in aligned if value is not None)
    return BenchmarkData(values["QQQ"], values["NASDAQ"])


def build_research_context(state_dir: Path, *, source_path: Path | None = None) -> dict[str, Any]:
    from core.features.registry import research_feature_specs
    from dashboard.state import DashboardStateReader
    from research.llm.codex_exec import sanitize_context

    snapshot = DashboardStateReader(state_dir).read()
    supported_timeframes = ["1m", "5m", "15m", "1h", "1d", "1w", "1mo"]
    context = sanitize_context(
        {
            "generation": snapshot.strategy.generation or 0,
            "champion": snapshot.strategy.model_dump(mode="json"),
            "frontier": [],
            "observations": [item.model_dump(mode="json") for item in snapshot.tests[:20]],
            "feature_catalog": [
                {
                    "name": spec.name,
                    "canonical_id": spec.canonical_id,
                    "aliases": list(spec.aliases),
                    "family": spec.family,
                    "inputs": list(spec.inputs),
                    "calculator": spec.calculator,
                    "lookback": spec.lookback,
                    "timeframe": spec.timeframe,
                    "supported_timeframes": supported_timeframes,
                    "lag_bars": spec.lag_bars,
                    "parameters": dict(spec.parameters),
                    "implementation_hash": spec.implementation_hash,
                    "source_repositories": list(spec.source_repositories),
                    "source_licenses": list(spec.source_licenses),
                    "data_contract": spec.data_contract,
                    "status": spec.status,
                    "duplicate_group": spec.duplicate_group,
                }
                for spec in research_feature_specs()
            ],
        }
    )
    if not isinstance(context, dict):
        raise ValueError("research context must be an object")
    if source_path is not None:
        imported = normalize_source(source_path)
        if imported.strategy is None:
            raise ValueError("strategy source is unsupported")
        context["source_strategy"] = imported.strategy.model_dump(mode="json", by_alias=True)
        context["parent_ids_hint"] = [imported.strategy.strategy_id]
    return context
