from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
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
from research.llm.contracts import CANONICAL_CONDITION_OPERATORS
from research.llm.director import (
    IntentRepairUnavailable,
    ResearchDirector,
    ResearchIntent,
)
from research.llm.intent_bridge import (
    IntentEligibilityError,
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
                generation=generation + 1,
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
    progress = _ResearchProgress(config, records)
    progress.emit("run_started", phase="STARTING")
    feature_specs = research_feature_specs()
    try:
        for generation in range(config.generations):
            generation_number = generation + 1
            progress.emit(
                "generation_started", phase="GENERATION", generation=generation_number
            )
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
            attempted_repair_payloads: set[str] = set()

            try:
                progress.emit("proposal_started", phase="PROPOSING", generation=generation_number)
                intent = director.propose(context)
                record_intent(config.state_dir / "llm" / "intents.jsonl", intent)
                proposal_to_record = intent.feature_proposal
                operations = _preflight_intent(current, intent, feature_specs)
                progress.emit(
                    "preflight_completed",
                    phase="VALIDATING",
                    generation=generation_number,
                    detail={"operation_count": len(operations)},
                )
                progress.emit(
                    "proposal_completed",
                    phase="PROPOSING",
                    generation=generation_number,
                    detail={"mode": intent.mode, "operation_count": len(operations)},
                )
            except Exception as exc:
                intent_error = _error_text(exc)
                diagnostic = _diagnostic_from_exception(
                    exc,
                    phase="PROPOSING",
                    generation=generation_number,
                    strategy=current,
                    intent=intent,
                )
                progress.emit(
                    "proposal_failed",
                    phase="PROPOSING",
                    generation=generation_number,
                    error=intent_error,
                    detail={"diagnostic": diagnostic},
                )
                invalid_payload = _intent_payload(intent)
                _record_repair_knowledge(
                    config,
                    generation_number,
                    invalid_payload,
                    intent_error,
                    status="PROPOSAL_FAILED",
                    diagnostic=diagnostic,
                )
                if intent is not None and intent.feature_proposal is not None:
                    proposal_to_record = intent.feature_proposal
                repaired_intent: ResearchIntent | None = None
                for attempt in range(config.intent_repair_attempts):
                    repair_input_signature = _payload_signature(invalid_payload)
                    if repair_input_signature in attempted_repair_payloads:
                        duplicate_error = (
                            "INTENT_REPAIR_DUPLICATE: identical invalid repair payload "
                            "was already rejected"
                        )
                        repair_errors.append(duplicate_error)
                        repair_history.append(
                            {"attempt": attempt + 1, "status": "SKIPPED_DUPLICATE"}
                        )
                        _record_repair_knowledge(
                            config,
                            generation_number,
                            invalid_payload,
                            duplicate_error,
                            status="SKIPPED_DUPLICATE",
                        )
                        progress.emit(
                            "repair_skipped_duplicate",
                            phase="REPAIRING",
                            generation=generation_number,
                            repair_attempt=repair_attempts,
                            error=duplicate_error,
                        )
                        break
                    attempted_repair_payloads.add(repair_input_signature)
                    repair_attempts += 1
                    progress.emit(
                        "repair_started",
                        phase="REPAIRING",
                        generation=generation_number,
                        repair_attempt=repair_attempts,
                        detail={
                            "allowed_attempts": config.intent_repair_attempts,
                            "reason": intent_error,
                        },
                    )
                    try:
                        repaired_intent = director.repair(
                            context,
                            invalid_payload,
                            _format_repair_error(intent_error, diagnostic),
                        )
                        attempted_repair_payloads.add(
                            _payload_signature(_intent_payload(repaired_intent))
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
                        progress.emit(
                            "preflight_completed",
                            phase="VALIDATING",
                            generation=generation_number,
                            repair_attempt=repair_attempts,
                            detail={"operation_count": len(operations)},
                        )
                        intent = repaired_intent
                        record_intent(
                            config.state_dir / "llm" / "intents.jsonl", repaired_intent
                        )
                        intent_status = "REPAIRED"
                        progress.emit(
                            "repair_completed",
                            phase="REPAIRING",
                            generation=generation_number,
                            repair_attempt=repair_attempts,
                            detail={"operation_count": len(operations)},
                        )
                        break
                    except IntentRepairUnavailable as exc:
                        intent_error = _error_text(exc)
                        repair_errors.append(intent_error)
                        progress.emit(
                            "repair_unavailable",
                            phase="REPAIRING",
                            generation=generation_number,
                            repair_attempt=repair_attempts,
                            error=intent_error,
                        )
                        repair_history.append(
                            {"attempt": attempt + 1, "status": "UNAVAILABLE"}
                        )
                        _record_repair_knowledge(
                            config,
                            generation_number,
                            invalid_payload,
                            intent_error,
                            status="UNAVAILABLE",
                        )
                        break
                    except Exception as exc:
                        intent_error = _error_text(exc)
                        diagnostic = _diagnostic_from_exception(
                            exc,
                            phase="REPAIRING",
                            generation=generation_number,
                            strategy=current,
                            intent=repaired_intent,
                        )
                        repair_errors.append(intent_error)
                        progress.emit(
                            "repair_failed",
                            phase="REPAIRING",
                            generation=generation_number,
                            repair_attempt=repair_attempts,
                            error=intent_error,
                            detail={"diagnostic": diagnostic},
                        )
                        repair_history.append(
                            {
                                "attempt": attempt + 1,
                                "status": "FAILED",
                                "error": intent_error,
                            }
                        )
                        _record_repair_knowledge(
                            config,
                            generation_number,
                            invalid_payload,
                            intent_error,
                            status="FAILED",
                            diagnostic=diagnostic,
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
                progress.emit(
                    "evaluation_started", phase="BACKTESTING", generation=generation_number
                )
                evaluation = _run_intent_evaluation(
                    runner,
                    config,
                    generation,
                    operations=operations,
                    strategy=current,
                )
                progress.emit(
                    "evaluation_completed",
                    phase="BACKTESTING",
                    generation=generation_number,
                    detail={"status": evaluation.get("status", "UNKNOWN")},
                )
            except Exception as exc:
                evaluation_error = _error_text(exc)
                progress.emit(
                    "evaluation_failed",
                    phase="BACKTESTING",
                    generation=generation_number,
                    error=evaluation_error,
                )
                while evaluation is None and repair_attempts < config.intent_repair_attempts:
                    repair_input = _intent_payload(intent)
                    repair_input_signature = _payload_signature(repair_input)
                    repair_diagnostic = _diagnostic_from_error(
                        evaluation_error or "evaluation failed",
                        phase="BACKTESTING",
                        generation=generation_number,
                    )
                    if repair_input_signature in attempted_repair_payloads:
                        duplicate_error = (
                            "INTENT_REPAIR_DUPLICATE: identical invalid repair payload "
                            "was already rejected"
                        )
                        repair_errors.append(duplicate_error)
                        repair_history.append(
                            {"attempt": repair_attempts, "status": "SKIPPED_DUPLICATE"}
                        )
                        _record_repair_knowledge(
                            config,
                            generation_number,
                            repair_input,
                            duplicate_error,
                            status="SKIPPED_DUPLICATE",
                        )
                        progress.emit(
                            "repair_skipped_duplicate",
                            phase="REPAIRING",
                            generation=generation_number,
                            repair_attempt=repair_attempts,
                            error=duplicate_error,
                        )
                        break
                    attempted_repair_payloads.add(repair_input_signature)
                    repair_attempts += 1
                    progress.emit(
                        "repair_started",
                        phase="REPAIRING",
                        generation=generation_number,
                        repair_attempt=repair_attempts,
                        detail={
                            "allowed_attempts": config.intent_repair_attempts,
                            "reason": evaluation_error,
                        },
                    )
                    try:
                        repaired_intent = director.repair(
                            context,
                            _intent_payload(intent),
                            _format_repair_error(
                                evaluation_error or "evaluation failed", repair_diagnostic
                            ),
                        )
                        attempted_repair_payloads.add(
                            _payload_signature(_intent_payload(repaired_intent))
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
                        progress.emit(
                            "repair_completed",
                            phase="REPAIRING",
                            generation=generation_number,
                            repair_attempt=repair_attempts,
                            detail={"operation_count": len(operations)},
                        )
                        progress.emit(
                            "evaluation_completed",
                            phase="BACKTESTING",
                            generation=generation_number,
                            detail={"status": evaluation.get("status", "UNKNOWN")},
                        )
                    except IntentRepairUnavailable as repair_exc:
                        repair_error = _error_text(repair_exc)
                        repair_errors.append(repair_error)
                        progress.emit(
                            "repair_unavailable",
                            phase="REPAIRING",
                            generation=generation_number,
                            repair_attempt=repair_attempts,
                            error=repair_error,
                        )
                        repair_history.append(
                            {"attempt": repair_attempts, "status": "UNAVAILABLE"}
                        )
                        _record_repair_knowledge(
                            config,
                            generation_number,
                            repair_input,
                            repair_error,
                            status="UNAVAILABLE",
                        )
                        evaluation_error = f"candidate={evaluation_error}; repair={repair_error}"
                        break
                    except Exception as repair_exc:
                        repair_error = _error_text(repair_exc)
                        repair_diagnostic = _diagnostic_from_exception(
                            repair_exc,
                            phase="REPAIRING",
                            generation=generation_number,
                            strategy=current,
                            intent=repaired_intent,
                        )
                        repair_errors.append(repair_error)
                        progress.emit(
                            "repair_failed",
                            phase="REPAIRING",
                            generation=generation_number,
                            repair_attempt=repair_attempts,
                            error=repair_error,
                            detail={"diagnostic": repair_diagnostic},
                        )
                        repair_history.append(
                            {
                                "attempt": repair_attempts,
                                "status": "FAILED",
                                "error": repair_error,
                            }
                        )
                        _record_repair_knowledge(
                            config,
                            generation_number,
                            repair_input,
                            repair_error,
                            status="FAILED",
                            diagnostic=repair_diagnostic,
                        )
                        evaluation_error = f"candidate={evaluation_error}; repair={repair_error}"

                if evaluation is None:
                    intent_status = "FALLBACK"
                    operations = ()
                    try:
                        progress.emit(
                            "fallback_evaluation_started",
                            phase="BACKTESTING",
                            generation=generation_number,
                        )
                        evaluation = _run_intent_evaluation(
                            runner,
                            config,
                            generation,
                            operations=operations,
                            strategy=current,
                        )
                        progress.emit(
                            "evaluation_completed",
                            phase="BACKTESTING",
                            generation=generation_number,
                            detail={"status": evaluation.get("status", "UNKNOWN")},
                        )
                    except Exception as fallback_exc:
                        evaluation_error = (
                            f"{evaluation_error}; fallback={_error_text(fallback_exc)}"
                        )
                        progress.emit(
                            "fallback_evaluation_failed",
                            phase="BACKTESTING",
                            generation=generation_number,
                            error=_error_text(fallback_exc),
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
            progress.emit(
                "generation_completed",
                phase="FINALIZING",
                generation=generation_number,
                completed_generations=len(records),
                detail={
                    "status": record.get("status", "UNKNOWN"),
                    "intent_status": intent_status,
                    "repair_attempts": repair_attempts,
                },
            )
            if generation + 1 < config.generations and config.interval_seconds:
                time.sleep(config.interval_seconds)
    except Exception as exc:
        progress.emit(
            "run_failed",
            phase="FAILED",
            status="FAILED",
            completed_generations=len(records),
            error=_error_text(exc),
        )
        raise
    final_status = _autoresearch_final_status(records)
    progress.emit(
        "run_completed",
        phase="COMPLETED",
        status=final_status,
        completed_generations=len(records),
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
        generation=generation + 1,
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


def _payload_signature(payload: object) -> str:
    canonical = json.dumps(
        sanitize_context(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _record_repair_knowledge(
    config: ResearchLoopConfig,
    generation: int,
    payload: object,
    error: str,
    *,
    status: str,
    diagnostic: Mapping[str, object] | None = None,
) -> None:
    target = config.state_dir / "system" / "repair-knowledge.jsonl"
    record = {
        "timestamp": _utc_now(),
        "generation": generation,
        "status": status,
        "error": error[:1000],
        "error_code": _error_code(error),
        "payload_signature": _payload_signature(payload),
        "diagnostic": dict(
            diagnostic
            or _diagnostic_from_error(error, phase="REPAIRING", generation=generation)
        ),
    }
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        return


def _error_code(error: str) -> str:
    for token in error.replace(";", " ").replace(":", " ").split():
        if token.startswith("INTENT_"):
            return token
    return "INTENT_UNKNOWN"


def _diagnostic_from_exception(
    error: Exception,
    *,
    phase: str,
    generation: int,
    strategy: StrategyIR | None = None,
    intent: ResearchIntent | None = None,
) -> dict[str, object]:
    if isinstance(error, IntentEligibilityError):
        diagnostic = dict(error.diagnostic)
    else:
        diagnostic = _diagnostic_from_error(
            _error_text(error), phase=phase, generation=generation
        )
    diagnostic.setdefault("phase", phase)
    diagnostic["generation"] = generation
    diagnostic.setdefault("message", _error_text(error))
    if strategy is not None:
        diagnostic["available_references"] = sorted(
            {
                *strategy.indicators,
                *strategy.features,
                "open",
                "high",
                "low",
                "close",
                "volume",
            }
        )
        diagnostic["available_targets"] = sorted(
            [
                *(f"indicators.{name}" for name in strategy.indicators),
                *(f"features.{name}" for name in strategy.features),
                "entry.conditions.<index>",
                "exit.conditions.<index>",
                "regime_filters",
            ]
        )
    if intent is not None:
        diagnostic["operation_count"] = len(intent.operations) + len(intent.feature_selections)
    match = re.search(r"unknown reference ['\"]([^'\"]+)['\"]", str(error))
    if match:
        diagnostic["reference_received"] = match.group(1)
    return diagnostic


def _diagnostic_from_error(error: str, *, phase: str, generation: int) -> dict[str, object]:
    code = _error_code(error)
    diagnostic: dict[str, object] = {
        "code": code,
        "phase": phase,
        "generation": generation,
        "message": error[:1000],
        "retryable": code in {"INTENT_PATH_TARGET", "INTENT_VALUE_TYPE"},
    }
    if "features.<alias>" in error:
        diagnostic.update(
            {
                "path_expected": "features.<alias>",
                "repair_action": "set_canonical_target_path",
            }
        )
    elif "indicators.<alias>" in error:
        diagnostic.update(
            {
                "path_expected": "indicators.<alias>",
                "repair_action": "set_canonical_target_path",
            }
        )
    elif "regime_filters list" in error:
        diagnostic.update(
            {
                "path_expected": "regime_filters",
                "repair_action": "target_regime_filter_list",
            }
        )
    elif "unknown reference" in error:
        diagnostic["repair_action"] = "use_declared_indicator_or_feature_alias"
    elif "unsupported operator" in error:
        diagnostic.update(
            {
                "allowed_operators": list(CANONICAL_CONDITION_OPERATORS),
                "repair_action": "use_verified_condition_operator",
            }
        )
    return diagnostic


def _format_repair_error(error: str, diagnostic: Mapping[str, object]) -> str:
    fields = [
        f"code={diagnostic.get('code', 'INTENT_UNKNOWN')}",
        f"phase={diagnostic.get('phase', 'PREFLIGHT')}",
    ]
    for key in ("path_received", "path_expected", "repair_action"):
        if key in diagnostic:
            fields.append(f"{key}={diagnostic[key]}")
    fields.append(f"message={error[:600]}")
    return " ".join(fields)


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
    current_generation: int | None = None,
    current_phase: str | None = None,
    phase_started_at: str | None = None,
    phase_elapsed_seconds: float | None = None,
    last_event: str | None = None,
    last_event_at: str | None = None,
    repair_attempt: int | None = None,
    repair_attempts_allowed: int | None = None,
    timing_summary: Mapping[str, object] | None = None,
) -> None:
    payload: dict[str, object] = {
        "status": status,
        "orders_enabled": False,
        "completed_generations": completed_generations,
        "requested_generations": config.generations,
        "generations": records,
    }
    payload.update(
        {
            "current_generation": current_generation,
            "current_phase": current_phase,
            "phase_started_at": phase_started_at,
            "phase_elapsed_seconds": phase_elapsed_seconds,
            "last_event": last_event,
            "last_event_at": last_event_at,
            "repair_attempt": repair_attempt,
            "repair_attempts_allowed": repair_attempts_allowed,
        }
    )
    if timing_summary is not None:
        payload["timing_summary"] = dict(timing_summary)
    if error is not None:
        payload["error"] = error
    target = config.state_dir / "system" / "autoresearch.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    try:
        os.replace(temporary, target)
    except OSError:
        try:
            temporary.unlink()
        except OSError:
            pass
        return


class _ResearchProgress:
    """Persist phase heartbeats without allowing diagnostics to stop research."""

    def __init__(self, config: ResearchLoopConfig, records: list[dict[str, object]]) -> None:
        self.config = config
        self.records = records
        self.phase = "STARTING"
        self.phase_started_at = _utc_now()
        self.phase_started_mono = time.monotonic()
        self.current_generation: int | None = None
        self.events: list[dict[str, object]] = []

    def emit(
        self,
        event: str,
        *,
        phase: str,
        generation: int | None = None,
        status: str = "RUNNING",
        completed_generations: int | None = None,
        repair_attempt: int | None = None,
        error: str | None = None,
        detail: Mapping[str, object] | None = None,
    ) -> None:
        if phase != self.phase:
            self.phase = phase
            self.phase_started_at = _utc_now()
            self.phase_started_mono = time.monotonic()
        if generation is not None:
            self.current_generation = generation
        now = _utc_now()
        elapsed = round(max(0.0, time.monotonic() - self.phase_started_mono), 3)
        payload: dict[str, object] = {
            "timestamp": now,
            "event": event,
            "phase": self.phase,
            "generation": self.current_generation,
            "duration_seconds": elapsed,
        }
        if repair_attempt is not None:
            payload["repair_attempt"] = repair_attempt
        if error is not None:
            payload["error"] = error
        if detail:
            sanitized_detail = sanitize_context(detail)
            if isinstance(sanitized_detail, dict) and "diagnostic" in sanitized_detail:
                payload["diagnostic"] = sanitized_detail.pop("diagnostic")
            if sanitized_detail:
                payload["detail"] = sanitized_detail
        self.events.append(payload)
        _append_research_event(self.config, payload)
        _write_autoresearch_status(
            self.config,
            status,
            completed_generations=(
                len(self.records) if completed_generations is None else completed_generations
            ),
            records=self.records,
            error=error if status == "FAILED" else None,
            current_generation=self.current_generation,
            current_phase=self.phase,
            phase_started_at=self.phase_started_at,
            phase_elapsed_seconds=elapsed,
            last_event=event,
            last_event_at=now,
            repair_attempt=repair_attempt,
            repair_attempts_allowed=self.config.intent_repair_attempts,
            timing_summary=_timing_summary(self.events),
        )


def _append_research_event(config: ResearchLoopConfig, payload: Mapping[str, object]) -> None:
    target = config.state_dir / "system" / "research-events.jsonl"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        return


def _timing_summary(events: list[dict[str, object]]) -> dict[str, object]:
    stage_events = {
        "proposal": ("proposal_started", ("proposal_failed", "preflight_completed")),
        "repair": (
            "repair_started",
            ("preflight_completed", "repair_failed", "repair_unavailable"),
        ),
        "backtest": ("evaluation_started", ("evaluation_completed",)),
        "generation": ("generation_started", ("generation_completed",)),
    }
    return {
        stage: _timing_stats(_paired_event_durations(events, start, terminals))
        for stage, (start, terminals) in stage_events.items()
    }


def _paired_event_durations(
    events: list[dict[str, object]], start_event: str, terminal_events: tuple[str, ...]
) -> list[float]:
    durations: list[float] = []
    for index, event in enumerate(events):
        if event.get("event") != start_event:
            continue
        generation = event.get("generation")
        started_at = _event_datetime(event)
        if started_at is None:
            continue
        for terminal in events[index + 1 :]:
            if terminal.get("generation") != generation:
                continue
            if terminal.get("event") not in terminal_events:
                continue
            ended_at = _event_datetime(terminal)
            if ended_at is not None:
                durations.append(round(max(0.0, (ended_at - started_at).total_seconds()), 3))
            break
    return durations


def _event_datetime(event: Mapping[str, object]) -> dt.datetime | None:
    timestamp = event.get("timestamp")
    if not isinstance(timestamp, str):
        return None
    try:
        return dt.datetime.fromisoformat(timestamp)
    except ValueError:
        return None


def _timing_stats(values: list[float]) -> dict[str, object]:
    if not values:
        return {
            "count": 0,
            "total_seconds": 0.0,
            "p50_seconds": 0.0,
            "p95_seconds": 0.0,
            "max_seconds": 0.0,
        }
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "total_seconds": round(sum(ordered), 3),
        "p50_seconds": _percentile(ordered, 0.50),
        "p95_seconds": _percentile(ordered, 0.95),
        "max_seconds": ordered[-1],
    }


def _percentile(values: list[float], fraction: float) -> float:
    position = (len(values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weighted = values[lower] + (values[upper] - values[lower]) * (position - lower)
    return round(weighted, 3)


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


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
