from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.data.parquet import ParquetDataProvider
from dashboard.ledger import append_funnel_results
from evaluation.selector import FunnelConfig
from orchestration.pipeline import GenerationPipeline
from strategy_ir.normalizer import normalize_source

ALLOWED_STRATEGY_SUFFIXES = frozenset({".yaml", ".yml", ".json", ".py", ".pine", ".pinescript"})


def resolve_project_input(project_root: Path, value: object, suffixes: frozenset[str]) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("path is required")
    candidate = (project_root / value).resolve()
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
) -> dict[str, object]:
    source = resolve_project_input(project_root, source_path, ALLOWED_STRATEGY_SUFFIXES)
    data = resolve_project_input(project_root, data_path, frozenset({".parquet"}))
    if method not in {"grid", "random", "bayesian"}:
        raise ValueError("evaluation method is invalid")
    if count < 1 or seed < 0 or min_trades < 0:
        raise ValueError("evaluation numeric options are invalid")
    imported = normalize_source(source)
    if imported.strategy is None:
        raise ValueError("strategy source is unsupported")
    pipeline_result = GenerationPipeline().run(
        parent=imported.strategy,
        dataset=ParquetDataProvider.read(data),
        operations=(),
        domains=(),
        method=method,
        count=count,
        seed=seed,
        funnel=FunnelConfig(min_fast_trades=min_trades, min_full_trades=min_trades),
    )
    append_funnel_results(
        state_dir / "test-records.jsonl",
        generation=imported.strategy.generation + 1,
        results=pipeline_result.funnel,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    return {
        "status": "COMPLETED",
        "candidate_count": len(pipeline_result.candidates),
        "counts": {
            status: sum(item.status == status for item in pipeline_result.funnel)
            for status in sorted({item.status for item in pipeline_result.funnel})
        },
    }


def build_research_context(state_dir: Path, *, source_path: Path | None = None) -> dict[str, Any]:
    from core.features.registry import default_feature_registry
    from dashboard.state import DashboardStateReader
    from research.llm.codex_exec import sanitize_context

    snapshot = DashboardStateReader(state_dir).read()
    context = sanitize_context(
        {
            "generation": snapshot.strategy.generation or 0,
            "champion": snapshot.strategy.model_dump(mode="json"),
            "frontier": [],
            "observations": [item.model_dump(mode="json") for item in snapshot.tests[:20]],
            "feature_catalog": [
                {
                    "name": spec.name,
                    "family": spec.family,
                    "inputs": list(spec.inputs),
                    "calculator": spec.calculator,
                    "lookback": spec.lookback,
                    "timeframe": spec.timeframe,
                }
                for spec in default_feature_registry().all()
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
