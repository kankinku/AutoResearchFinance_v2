"""Construct evidence from local typed results, without raw data or LLM text."""

from __future__ import annotations

import hashlib
import math
import platform
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path
from typing import Any

from core.costs.model import CostModel
from core.data.contracts import DataZone, MarketDataSet, SeriesDataSet
from evaluation.selector import FunnelConfig, FunnelResult
from memory.evidence_store import EvidenceIntegrityError, EvidenceStore, digest
from strategy_ir.schema import StrategyIR


def require_research_zone(path: Path) -> None:
    import pyarrow.parquet as parquet  # type: ignore[import-untyped]

    metadata = parquet.read_metadata(path).metadata or {}
    zone = metadata.get(b"data_zone")
    if zone != b"development":
        if zone == b"validation":
            raise EvidenceIntegrityError("validation data is promotion-only")
        if zone == b"sealed_oos":
            raise EvidenceIntegrityError("sealed OOS is promotion-gate-only")
        raise EvidenceIntegrityError("development research data zone metadata is required")


def require_validation_zone(path: Path) -> None:
    import pyarrow.parquet as parquet

    metadata = parquet.read_metadata(path).metadata or {}
    if metadata.get(b"data_zone") != b"validation":
        raise EvidenceIntegrityError("promotion validation requires validation data")


def freeze_manifest(
    state_dir: Path,
    run_id: str,
    *,
    source: StrategyIR,
    dataset: MarketDataSet,
    series: SeriesDataSet | None,
    funnel: FunnelConfig,
    cost_model: CostModel,
) -> str:
    if dataset.zone is not DataZone.DEVELOPMENT:
        raise EvidenceIntegrityError("research manifest requires development market data")
    if series is not None and series.zone is not DataZone.DEVELOPMENT:
        raise EvidenceIntegrityError("research manifest requires development series data")
    root = Path(__file__).resolve().parents[1]
    files = sorted(
        p
        for package in (
            "core",
            "evaluation",
            "strategy_ir",
            "mutation",
            "experiments",
            "orchestration",
            "research",
            "runtime",
        )
        for p in (root / package).rglob("*")
        if p.suffix in {".py", ".yaml"}
    )
    timestamps = [bar.timestamp for bar in dataset.bars]
    conditions = {
        "source_ir_hash": digest(source.model_dump(mode="json", by_alias=True)),
        "dataset_hash": dataset.dataset_hash,
        "data_zone": DataZone(dataset.zone).value,
        "dataset_version": dataset.version,
        "timeframe": dataset.timeframe,
        "calendar": dataset.calendar,
        "series_hash": series.dataset_hash if series else None,
        "series_zone": DataZone(series.zone).value if series else None,
        "series_version": series.version if series else None,
        "date_start": min(timestamps).isoformat() if timestamps else None,
        "date_end": max(timestamps).isoformat() if timestamps else None,
        "symbols": sorted({bar.symbol for bar in dataset.bars}),
        "evaluation_policy": asdict(funnel),
        "cost_model": asdict(cost_model),
        "runtime_versions": {
            "python": platform.python_version(),
            **{name: version(name) for name in ("numpy", "pandas", "pyarrow")},
        },
        "code_hash": digest(
            {
                p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in files
            }
        ),
        "execution_mode": "local_python",
        "docker_image_digest": None,
    }
    comparison_hash = digest(conditions)
    EvidenceStore(state_dir).append(
        "manifest",
        f"manifest:{run_id}",
        {
            "research_run_id": run_id,
            "comparison_key": comparison_hash,
            **conditions,
        },
    )
    return comparison_hash


def _number(value: float | int | None) -> float | int | None:
    return value if value is not None and math.isfinite(value) else None


def candidate_evidence(result: FunnelResult) -> dict[str, Any]:
    measured = bool(result.validation_folds)
    return {
        "candidate_hash": result.candidate_hash,
        "family": result.family,
        "status": result.status,
        "score": _number(result.score),
        "dsr": _number(result.robustness_dsr),
        "pbo": _number(result.robustness_pbo),
        "failed_gates": [gate.name for gate in result.gates if not gate.passed],
        "gates": [
            {
                "name": gate.name,
                "passed": gate.passed,
                "threshold": _number(gate.threshold),
                "actual": _number(gate.actual),
            }
            for gate in result.gates
        ],
        "full_cagr": _number(result.full_cagr),
        "full_sharpe": _number(result.full_sharpe),
        "max_drawdown": _number(result.full_max_drawdown),
        "trade_count": result.full_trade_count,
        "turnover": _number(result.full_turnover),
        "qqq_cagr_delta": _number(result.full_benchmark.qqq_cagr_delta)
        if result.full_benchmark
        else None,
        "nasdaq_cagr_delta": _number(result.full_benchmark.nasdaq_cagr_delta)
        if result.full_benchmark
        else None,
        "dataset_hash": result.dataset_hash,
        "benchmark_dataset_hash": result.benchmark_dataset_hash,
        "validation_evaluated": measured,
        "validation_passed": all(f.get("passed") is True for f in result.validation_folds)
        if measured
        else None,
        "validation_fold_count": len(result.validation_folds),
        "feature_ids": sorted(result.feature_ids),
        "parameters": dict(result.parameters or {}),
        "causal_status": "UNKNOWN",
    }
