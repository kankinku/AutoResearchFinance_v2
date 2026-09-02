from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.features.contracts import FeatureSpec
from core.features.lifecycle import record_feature_proposal
from core.features.registry import research_feature_specs
from mutation.engine import MutationOperation
from mutation.parameter import ParameterDomain
from orchestration.evaluation_runner import (
    ALLOWED_STRATEGY_SUFFIXES,
    build_research_context,
    resolve_project_input,
    run_local_evaluation,
)
from research.llm.codex_exec import record_intent, sanitize_context
from research.llm.director import (
    IntentRepairUnavailable,
    ResearchDirector,
    ResearchIntent,
)
from research.llm.intent_bridge import (
    apply_intent,
    intent_to_operations,
)
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
    intent_repair_attempts: int = 3
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
    feature_specs = research_feature_specs()
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
            intent: ResearchIntent | None = None
            repair_history: list[dict[str, object]] = []
            repair_errors: list[str] = []
            repair_attempts = 0
            intent_status = "PROPOSED"
            intent_error: str | None = None
            proposal_to_record = None
            operations: tuple[MutationOperation, ...] = ()

            try:
                intent = director.propose(context)
                record_intent(config.state_dir / "llm" / "intents.jsonl", intent)
                proposal_to_record = intent.feature_proposal
                operations = _preflight_intent(current, intent, feature_specs)
            except Exception as exc:
                intent_error = _error_text(exc)
                invalid_payload = _intent_payload(intent)
                if intent is not None and intent.feature_proposal is not None:
                    proposal_to_record = intent.feature_proposal
                repaired_intent: ResearchIntent | None = None
                for attempt in range(config.intent_repair_attempts):
                    repair_attempts += 1
                    try:
                        repaired_intent = director.repair(
                            context,
                            invalid_payload,
                            intent_error,
                        )
                        repair_history.append(
                            {
                                "attempt": attempt + 1,
                                "status": "RECEIVED",
                                "intent": _intent_payload(repaired_intent),
                            }
                        )
                        if (
                            proposal_to_record is None
                            and repaired_intent.feature_proposal is not None
                        ):
                            proposal_to_record = repaired_intent.feature_proposal
                        operations = _preflight_intent(
                            current, repaired_intent, feature_specs
                        )
                        intent = repaired_intent
                        record_intent(
                            config.state_dir / "llm" / "intents.jsonl", repaired_intent
                        )
                        intent_status = "REPAIRED"
                        break
                    except IntentRepairUnavailable as exc:
                        intent_error = _error_text(exc)
                        repair_errors.append(intent_error)
                        repair_history.append(
                            {"attempt": attempt + 1, "status": "UNAVAILABLE"}
                        )
                        break
                    except Exception as exc:
                        intent_error = _error_text(exc)
                        repair_errors.append(intent_error)
                        repair_history.append(
                            {
                                "attempt": attempt + 1,
                                "status": "FAILED",
                                "error": intent_error,
                            }
                        )
                        invalid_payload = _intent_payload(repaired_intent) or invalid_payload
                else:
                    repaired_intent = None

                if intent_status != "REPAIRED":
                    intent_status = "FALLBACK"
                    operations = ()

            evaluation: dict[str, object] | None = None
            evaluation_error: str | None = None
            try:
                evaluation = _run_intent_evaluation(
                    runner,
                    config,
                    generation,
                    operations=operations,
                    strategy=current,
                )
            except Exception as exc:
                evaluation_error = _error_text(exc)
                while evaluation is None and repair_attempts < config.intent_repair_attempts:
                    repair_attempts += 1
                    try:
                        repaired_intent = director.repair(
                            context,
                            _intent_payload(intent),
                            evaluation_error,
                        )
                        repair_history.append(
                            {
                                "attempt": repair_attempts,
                                "status": "RECEIVED",
                                "intent": _intent_payload(repaired_intent),
                            }
                        )
                        if (
                            proposal_to_record is None
                            and repaired_intent.feature_proposal is not None
                        ):
                            proposal_to_record = repaired_intent.feature_proposal
                        operations = _preflight_intent(
                            current, repaired_intent, feature_specs
                        )
                        intent = repaired_intent
                        record_intent(
                            config.state_dir / "llm" / "intents.jsonl", repaired_intent
                        )
                        intent_status = "REPAIRED"
                        evaluation = _run_intent_evaluation(
                            runner,
                            config,
                            generation,
                            operations=operations,
                            strategy=current,
                        )
                    except IntentRepairUnavailable as repair_exc:
                        repair_error = _error_text(repair_exc)
                        repair_errors.append(repair_error)
                        repair_history.append(
                            {"attempt": repair_attempts, "status": "UNAVAILABLE"}
                        )
                        evaluation_error = f"candidate={evaluation_error}; repair={repair_error}"
                        break
                    except Exception as repair_exc:
                        repair_error = _error_text(repair_exc)
                        repair_errors.append(repair_error)
                        repair_history.append(
                            {
                                "attempt": repair_attempts,
                                "status": "FAILED",
                                "error": repair_error,
                            }
                        )
                        evaluation_error = f"candidate={evaluation_error}; repair={repair_error}"

                if evaluation is None:
                    intent_status = "FALLBACK"
                    operations = ()
                    try:
                        evaluation = _run_intent_evaluation(
                            runner,
                            config,
                            generation,
                            operations=operations,
                            strategy=current,
                        )
                    except Exception as fallback_exc:
                        evaluation_error = (
                            f"{evaluation_error}; fallback={_error_text(fallback_exc)}"
                        )

            if proposal_to_record is not None:
                record_feature_proposal(
                    config.state_dir / "system" / "feature-proposals.jsonl",
                    proposal_to_record,
                    generation=current.generation + 1,
                )

            if evaluation is not None:
                next_strategy = _strategy_from_evaluation(evaluation)
                if next_strategy is not None:
                    current = next_strategy
                status = intent_status if intent_status != "PROPOSED" else str(
                    evaluation.get("status", "UNKNOWN")
                )
                record: dict[str, object] = {
                    "generation": generation + 1,
                    "parent_id": parent_id,
                    "status": status,
                    "intent_status": intent_status,
                    "intent": _intent_payload(intent),
                    "operations": [
                        {"op": operation.op, "path": operation.path}
                        for operation in operations
                    ],
                    "evaluation": sanitize_context(evaluation),
                }
            else:
                record = {
                    "generation": generation + 1,
                    "parent_id": parent_id,
                    "status": "DEGRADED",
                    "intent_status": intent_status,
                    "intent": _intent_payload(intent),
                    "operations": [],
                }
            if intent_error is not None:
                record["intent_error"] = intent_error
            if repair_attempts:
                record["repair_attempts"] = repair_attempts
                record["repair_errors"] = repair_errors
                record["repair_history"] = repair_history
            if evaluation_error is not None:
                record["evaluation_error"] = evaluation_error
            records.append(record)
            _write_autoresearch_status(
                config,
                "RUNNING",
                completed_generations=len(records),
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
    final_status = _autoresearch_final_status(records)
    _write_autoresearch_status(
        config,
        final_status,
        completed_generations=len(records),
        records=records,
    )
    return {
        "status": final_status,
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


def _preflight_intent(
    current: StrategyIR,
    intent: ResearchIntent,
    feature_specs: tuple[FeatureSpec, ...],
) -> tuple[MutationOperation, ...]:
    operations = intent_to_operations(intent, feature_specs)
    apply_intent(current, intent, feature_specs)
    return operations


def _run_intent_evaluation(
    runner: EvaluationRunner,
    config: ResearchLoopConfig,
    generation: int,
    *,
    operations: tuple[MutationOperation, ...],
    strategy: StrategyIR,
) -> dict[str, object]:
    return runner(
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
        strategy_override=strategy,
    )


def _intent_payload(intent: ResearchIntent | None) -> dict[str, object] | None:
    if intent is None:
        return None
    payload = intent.model_dump(mode="json", exclude_none=True)
    sanitized = sanitize_context(payload)
    return sanitized if isinstance(sanitized, dict) else None


def _error_text(error: Exception) -> str:
    message = f"{type(error).__name__}: {error}".strip()
    return message[:1000] + ("..." if len(message) > 1000 else "")


def _autoresearch_final_status(records: list[dict[str, object]]) -> str:
    statuses = {str(record.get("status")) for record in records}
    if "DEGRADED" in statuses:
        return "COMPLETED_WITH_ERRORS"
    if "FALLBACK" in statuses:
        return "COMPLETED_WITH_FALLBACKS"
    return "COMPLETED"


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
    if config.intent_repair_attempts < 0:
        raise ValueError("intent_repair_attempts cannot be negative")
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
