from __future__ import annotations

from dataclasses import dataclass

from mutation.engine import MutationOperation
from mutation.parameter import ParameterDomain


@dataclass(frozen=True)
class ExperimentPlan:
    parent_ids: tuple[str, ...]
    structure_operations: tuple[MutationOperation, ...]
    parameter_domains: tuple[ParameterDomain, ...]
    method: str
    count: int
    seed: int
    search_stage: str = "parameter"


def plan_experiment(
    *,
    parent_ids: tuple[str, ...],
    structure_operations: tuple[MutationOperation, ...],
    parameter_domains: tuple[ParameterDomain, ...],
    method: str,
    count: int,
    seed: int,
) -> ExperimentPlan:
    if not parent_ids:
        raise ValueError("at least one parent strategy is required")
    if method not in {"grid", "random", "bayesian"}:
        raise ValueError(f"unsupported search method: {method}")
    if count <= 0:
        raise ValueError("count must be positive")
    return ExperimentPlan(
        parent_ids=parent_ids,
        structure_operations=structure_operations,
        parameter_domains=parameter_domains,
        method=method,
        count=count,
        seed=seed,
    )
