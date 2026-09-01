from __future__ import annotations

from dataclasses import dataclass

from core.integrity.hashes import content_hash
from mutation.engine import MutationOperation, apply_operations
from mutation.parameter import (
    BayesianObservation,
    ParameterDomain,
    ParameterValue,
    bayesian_search,
    grid_search,
    random_search,
)
from strategy_ir.schema import StrategyIR


@dataclass(frozen=True)
class Candidate:
    strategy: StrategyIR
    parameters: dict[str, ParameterValue]
    operations: tuple[MutationOperation, ...]
    parent_id: str
    candidate_hash: str


def generate_candidates(
    parent: StrategyIR,
    operations: tuple[MutationOperation, ...],
    domains: tuple[ParameterDomain, ...],
    *,
    method: str,
    count: int,
    seed: int,
    observations: list[BayesianObservation] | None = None,
) -> tuple[Candidate, ...]:
    points = _search(domains, method, count, seed, observations or [])
    candidates: list[Candidate] = []
    for point in points:
        parameter_operations = tuple(
            MutationOperation("SET_PARAMETER", path, value) for path, value in point.items()
        )
        all_operations = operations + parameter_operations
        strategy = apply_operations(parent, list(all_operations))
        operation_payload = [
            {"op": op.op, "path": op.path, "value": op.value} for op in all_operations
        ]
        candidate_hash = content_hash(
            {
                "parent_id": parent.strategy_id,
                "strategy": strategy.model_dump(mode="json", by_alias=True),
                "parameters": point,
                "operations": operation_payload,
            }
        )
        candidates.append(
            Candidate(strategy, dict(point), all_operations, parent.strategy_id, candidate_hash)
        )
    return tuple(candidates)


def _search(
    domains: tuple[ParameterDomain, ...],
    method: str,
    count: int,
    seed: int,
    observations: list[BayesianObservation],
) -> list[dict[str, ParameterValue]]:
    if method == "grid":
        return grid_search(domains)[:count]
    if method == "random":
        return random_search(domains, count=count, seed=seed)
    if method == "bayesian":
        return bayesian_search(domains, observations, count=count, seed=seed)
    raise ValueError(f"unsupported search method: {method}")
