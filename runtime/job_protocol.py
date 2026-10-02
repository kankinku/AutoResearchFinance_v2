from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from mutation.engine import MutationOperation
from mutation.parameter import ParameterDomain, ParameterValue
from strategy_ir.schema import StrategyIR


class ParameterDomainPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    values: tuple[ParameterValue, ...] = Field(min_length=1)


class MutationOperationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: str = Field(min_length=1)
    path: str | None = None
    value: Any = None
    other: dict[str, Any] | None = None


class EvaluationJobRequest(BaseModel):
    """Versioned, JSON-safe request consumed by local or container workers."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    source_path: str = Field(min_length=1)
    data_path: str = Field(min_length=1)
    method: Literal["grid", "random", "bayesian"] = "grid"
    count: int = Field(default=1, ge=1)
    seed: int = Field(default=0, ge=0)
    min_trades: int = Field(default=10, ge=0)
    parameter_domains: tuple[ParameterDomainPayload, ...] = ()
    operations: tuple[MutationOperationPayload, ...] = ()
    strategy_override: dict[str, Any] | None = None
    generation: int | None = Field(default=None, ge=1)
    series_data_path: str | None = None
    min_qqq_cagr_delta: float | None = None
    min_annual_trades: int | None = Field(default=30, ge=0)
    research_run_id: str | None = None
    attempt_id: str | None = None
    managed_run_id: str | None = None

    @classmethod
    def from_evaluation_kwargs(
        cls,
        project_root: Path,
        kwargs: Mapping[str, Any],
    ) -> EvaluationJobRequest:
        domains = tuple(
            ParameterDomainPayload(name=domain.name, values=domain.values)
            for domain in _typed_domains(kwargs.get("parameter_domains", ()))
        )
        operations = tuple(
            MutationOperationPayload(
                op=operation.op,
                path=operation.path,
                value=_jsonable(operation.value),
                other=(
                    operation.other.model_dump(mode="json", by_alias=True)
                    if operation.other is not None
                    else None
                ),
            )
            for operation in _typed_operations(kwargs.get("operations", ()))
        )
        strategy = kwargs.get("strategy_override")
        if strategy is not None and not isinstance(strategy, StrategyIR):
            raise TypeError("strategy_override must be a StrategyIR")
        return cls(
            source_path=_relative_input(project_root, kwargs.get("source_path")),
            data_path=_relative_input(project_root, kwargs.get("data_path")),
            method=_method(kwargs.get("method", "grid")),
            count=_required_int(kwargs.get("count", 1), "count"),
            seed=_required_int(kwargs.get("seed", 0), "seed"),
            min_trades=_required_int(kwargs.get("min_trades", 10), "min_trades"),
            parameter_domains=domains,
            operations=operations,
            strategy_override=(
                strategy.model_dump(mode="json", by_alias=True)
                if isinstance(strategy, StrategyIR)
                else None
            ),
            generation=_optional_int(kwargs.get("generation"), "generation"),
            series_data_path=_optional_relative_input(
                project_root, kwargs.get("series_data_path")
            ),
            min_qqq_cagr_delta=_optional_float(kwargs.get("min_qqq_cagr_delta")),
            min_annual_trades=_optional_int(
                kwargs.get("min_annual_trades", 30), "min_annual_trades"
            ),
            research_run_id=_optional_text(kwargs.get("research_run_id")),
            attempt_id=_optional_text(kwargs.get("attempt_id")),
            managed_run_id=_optional_text(kwargs.get("managed_run_id")),
        )

    def evaluation_kwargs(
        self,
        *,
        project_root: Path,
        state_dir: Path,
        execution_context: Mapping[str, object],
    ) -> dict[str, Any]:
        return {
            "project_root": project_root,
            "state_dir": state_dir,
            "source_path": self.source_path,
            "data_path": self.data_path,
            "method": self.method,
            "count": self.count,
            "seed": self.seed,
            "min_trades": self.min_trades,
            "parameter_domains": tuple(
                ParameterDomain(item.name, item.values)
                for item in self.parameter_domains
            ),
            "operations": tuple(
                MutationOperation(
                    item.op,
                    item.path,
                    item.value,
                    StrategyIR.model_validate(item.other) if item.other is not None else None,
                )
                for item in self.operations
            ),
            "strategy_override": (
                StrategyIR.model_validate(self.strategy_override)
                if self.strategy_override is not None
                else None
            ),
            "generation": self.generation,
            "series_data_path": self.series_data_path,
            "min_qqq_cagr_delta": self.min_qqq_cagr_delta,
            "min_annual_trades": self.min_annual_trades,
            "research_run_id": self.research_run_id,
            "attempt_id": self.attempt_id,
            "execution_context": dict(execution_context),
        }


class EvaluationJobResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    job_id: str = Field(min_length=1)
    queue_attempt: int = Field(ge=1)
    status: Literal["SUCCEEDED", "FAILED", "TIMED_OUT", "RETRY_EXHAUSTED"]
    result: dict[str, object] | None = None
    error_class: str | None = None


def _typed_domains(value: object) -> tuple[ParameterDomain, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise TypeError("parameter_domains must be a sequence")
    result = tuple(value)
    if any(not isinstance(item, ParameterDomain) for item in result):
        raise TypeError("parameter_domains must contain ParameterDomain values")
    return result


def _typed_operations(value: object) -> tuple[MutationOperation, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise TypeError("operations must be a sequence")
    result = tuple(value)
    if any(not isinstance(item, MutationOperation) for item in result):
        raise TypeError("operations must contain MutationOperation values")
    return result


def _relative_input(project_root: Path, value: object) -> str:
    if isinstance(value, Path):
        raw = value
    elif isinstance(value, str) and value:
        raw = Path(value)
    else:
        raise ValueError("evaluation input path is required")
    root = project_root.resolve()
    resolved = (root / raw).resolve()
    if resolved != root and root not in resolved.parents:
        raise PermissionError("evaluation input is outside project root")
    return resolved.relative_to(root).as_posix()


def _optional_relative_input(project_root: Path, value: object) -> str | None:
    return None if value is None else _relative_input(project_root, value)


def _jsonable(value: object) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"mutation value is not JSON-safe: {type(value).__name__}")




def _method(value: object) -> Literal["grid", "random", "bayesian"]:
    if value not in {"grid", "random", "bayesian"}:
        raise ValueError("evaluation method is invalid")
    if value == "grid":
        return "grid"
    if value == "random":
        return "random"
    return "bayesian"

def _required_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    return value


def _optional_int(value: object, name: str) -> int | None:
    return None if value is None else _required_int(value, name)


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError("floating-point option must be numeric")
    return float(value)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("identity must be a string")
    return value
