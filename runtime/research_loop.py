from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.features.lifecycle import record_feature_proposal
from core.features.registry import research_feature_specs
from mutation.parameter import ParameterDomain
from orchestration.evaluation_runner import (
    ALLOWED_STRATEGY_SUFFIXES,
    build_research_context,
    resolve_project_input,
    run_local_evaluation,
)
from research.llm.codex_exec import record_intent, sanitize_context
from research.llm.director import ResearchDirector
from research.llm.intent_bridge import IntentEligibilityError, intent_to_operations
from strategy_ir.normalizer import normalize_source
from strategy_ir.schema import StrategyIR


@dataclass(frozen=True)
class ResearchLoopConfig:
    project_root: Path
    state_dir: Path
    source_path: str
    data_path: str
    method: str = "random"
    count: int = 8
    seed: int = 0
    min_trades: int = 10
    min_annual_trades: int | None = 30
    min_qqq_cagr_delta: float | None = None
    series_data_path: str | None = None
    parameter_domains: tuple[ParameterDomain, ...] = ()
    generations: int = 1
    interval_seconds: float = 0.0


EvaluationRunner = Callable[..., dict[str, object]]


def run_repeated_evaluation(
    config: ResearchLoopConfig,
    *,
    evaluator: EvaluationRunner | None = None,
) -> dict[str, Any]:
    _validate_config(config)
    runner = evaluator or run_local_evaluation
    records: list[dict[str, object]] = []
    _write_status(config, "RUNNING", completed_generations=0, records=records)
    try:
        for generation in range(config.generations):
            result = runner(
                project_root=config.project_root,
                state_dir=config.state_dir,
                source_path=config.source_path,
                data_path=config.data_path,
                method=config.method,
                count=config.count,
                seed=config.seed + generation,
                min_trades=config.min_trades,
                series_data_path=config.series_data_path,
                min_qqq_cagr_delta=config.min_qqq_cagr_delta,
                min_annual_trades=config.min_annual_trades,
                parameter_domains=config.parameter_domains,
            )
            records.append(
                {"generation": generation + 1, "seed": config.seed + generation, **result}
            )
            _write_status(
                config,
                "RUNNING" if generation + 1 < config.generations else "COMPLETED",
                completed_generations=generation + 1,
                records=records,
            )
            if generation + 1 < config.generations and config.interval_seconds:
                time.sleep(config.interval_seconds)
    except Exception as exc:
        _write_status(
            config,
            "FAILED",
            completed_generations=len(records),
            records=records,
            error=type(exc).__name__,
        )
        raise
    return {
        "status": "COMPLETED",
        "completed_generations": len(records),
        "generations": records,
        "orders_enabled": False,
    }


def run_autoresearch(
    config: ResearchLoopConfig,
    director: ResearchDirector,
    *,
    evaluator: EvaluationRunner | None = None,
) -> dict[str, Any]:
    """Run bounded Codex-directed generations through the local IR pipeline."""

    _validate_config(config)
    source = resolve_project_input(
        config.project_root, config.source_path, ALLOWED_STRATEGY_SUFFIXES
    )
    imported = normalize_source(source)
    if imported.strategy is None:
        raise ValueError("strategy source is unsupported")
    current = imported.strategy
    runner = evaluator or run_local_evaluation
    records: list[dict[str, object]] = []
    _write_autoresearch_status(config, "RUNNING", completed_generations=0, records=records)
    try:
        for generation in range(config.generations):
            parent_id = current.strategy_id
            context = build_research_context(config.state_dir, source_path=source)
            context.update(
                {
                    "generation": current.generation,
                    "source_strategy": current.model_dump(mode="json", by_alias=True),
                    "parent_ids_hint": [current.strategy_id],
                    "frontier": [{"id": current.strategy_id, "family": current.family}],
                }
            )
            intent = director.propose(context)
            record_intent(config.state_dir / "llm" / "intents.jsonl", intent)
            try:
                operations = intent_to_operations(intent, research_feature_specs())
            except IntentEligibilityError as exc:
                if intent.feature_proposal is not None:
                    record_feature_proposal(
                        config.state_dir / "system" / "feature-proposals.jsonl",
                        intent.feature_proposal,
                        generation=current.generation + 1,
                    )
                record = {
                    "generation": generation + 1,
                    "parent_id": parent_id,
                    "status": "BLOCKED",
                    "reason": type(exc).__name__,
                    "intent": sanitize_context(intent.model_dump(mode="json")),
                }
                records.append(record)
                _write_autoresearch_status(
                    config,
                    "BLOCKED",
                    completed_generations=generation,
                    records=records,
                )
                return {
                    "status": "BLOCKED",
                    "completed_generations": generation,
                    "generations": records,
                    "orders_enabled": False,
                }
            evaluation = runner(
                project_root=config.project_root,
                state_dir=config.state_dir,
                source_path=config.source_path,
                data_path=config.data_path,
                method=config.method,
                count=config.count,
                seed=config.seed + generation,
                min_trades=config.min_trades,
                series_data_path=config.series_data_path,
                min_qqq_cagr_delta=config.min_qqq_cagr_delta,
                min_annual_trades=config.min_annual_trades,
                parameter_domains=config.parameter_domains,
                operations=operations,
                strategy_override=current,
            )
            next_strategy = _strategy_from_evaluation(evaluation)
            if next_strategy is not None:
                current = next_strategy
            record = {
                "generation": generation + 1,
                "parent_id": parent_id,
                "status": str(evaluation.get("status", "UNKNOWN")),
                "intent": sanitize_context(intent.model_dump(mode="json")),
                "operations": [
                    {"op": operation.op, "path": operation.path}
                    for operation in operations
                ],
                "evaluation": sanitize_context(evaluation),
            }
            records.append(record)
            _write_autoresearch_status(
                config,
                "RUNNING" if generation + 1 < config.generations else "COMPLETED",
                completed_generations=generation + 1,
                records=records,
            )
            if generation + 1 < config.generations and config.interval_seconds:
                time.sleep(config.interval_seconds)
    except Exception as exc:
        _write_autoresearch_status(
            config,
            "FAILED",
            completed_generations=len(records),
            records=records,
            error=type(exc).__name__,
        )
        raise
    return {
        "status": "COMPLETED",
        "completed_generations": len(records),
        "generations": records,
        "orders_enabled": False,
    }


def _strategy_from_evaluation(evaluation: Mapping[str, object]) -> StrategyIR | None:
    payload = evaluation.get("best_strategy")
    if not isinstance(payload, Mapping):
        return None
    try:
        return StrategyIR.model_validate(payload)
    except (TypeError, ValueError):
        return None


def _write_autoresearch_status(
    config: ResearchLoopConfig,
    status: str,
    *,
    completed_generations: int,
    records: list[dict[str, object]],
    error: str | None = None,
) -> None:
    payload: dict[str, object] = {
        "status": status,
        "orders_enabled": False,
        "completed_generations": completed_generations,
        "requested_generations": config.generations,
        "generations": records,
    }
    if error is not None:
        payload["error"] = error
    target = config.state_dir / "system" / "autoresearch.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, target)


def _validate_config(config: ResearchLoopConfig) -> None:
    if config.generations < 1:
        raise ValueError("generations must be positive and explicitly bounded")
    if config.interval_seconds < 0:
        raise ValueError("interval_seconds cannot be negative")
    if config.count < 1 or config.seed < 0 or config.min_trades < 0:
        raise ValueError("loop numeric options are invalid")
    if config.min_annual_trades is not None and config.min_annual_trades < 0:
        raise ValueError("min_annual_trades cannot be negative")


def _write_status(
    config: ResearchLoopConfig,
    status: str,
    *,
    completed_generations: int,
    records: list[dict[str, object]],
    error: str | None = None,
) -> None:
    payload: dict[str, object] = {
        "status": status,
        "orders_enabled": False,
        "completed_generations": completed_generations,
        "requested_generations": config.generations,
        "min_annual_trades": config.min_annual_trades,
        "records": records,
        "config": {
            key: str(value) if isinstance(value, Path) else value
            for key, value in asdict(config).items()
            if key not in {"project_root", "state_dir"}
        },
    }
    if error is not None:
        payload["error"] = error
    target = config.state_dir / "system" / "research_loop.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, target)
