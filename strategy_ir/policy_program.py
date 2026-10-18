"""Bounded development-only policy switch over supplied, audited feature values.

Never evaluates Python source or fetches external series. Missing data fails closed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from math import isfinite

from core.data.contracts import MarketDataSet
from core.integrity.hashes import content_hash
from strategy_ir.policy_decision import PolicyDecision


@dataclass(frozen=True)
class Predicate:
    feature: str
    operator: str
    threshold: float

    def __post_init__(self) -> None:
        if (
            not self.feature
            or self.operator not in {"gt", "ge", "lt", "le"}
            or not isfinite(self.threshold)
        ):
            raise ValueError("invalid typed predicate")


@dataclass(frozen=True)
class PolicySwitch:
    predicates: tuple[Predicate, ...]
    match_weight: float
    otherwise_weight: float
    policy_id: str

    def __post_init__(self) -> None:
        if not 1 <= len(self.predicates) <= 8 or not self.policy_id.strip():
            raise ValueError("bounded predicates and policy id required")
        if not all(isfinite(w) and 0 <= w <= 1 for w in (self.match_weight, self.otherwise_weight)):
            raise ValueError("unsafe target weight")


def compile_policy_switch(
    dataset: MarketDataSet,
    program: PolicySwitch,
    features: Mapping[str, Sequence[float | None]],
    *,
    audited_features: frozenset[str],
) -> tuple[PolicyDecision, ...]:
    """Emit decisions after observed closes; executable strictly at the next open.

    Inputs are trusted only if their IDs were independently approved by the caller.
    This function does not grant a feature audit status.
    """
    if dataset.zone != "development":
        raise ValueError("only development datasets are accepted")
    bars = dataset.bars
    if len(bars) < 2 or len({bar.symbol for bar in bars}) != 1:
        raise ValueError("single symbol and two bars required")
    identifiers = {predicate.feature for predicate in program.predicates}
    if not identifiers.issubset(audited_features):
        raise ValueError("feature not audited")
    for identifier in identifiers:
        values = features.get(identifier)
        if values is None or len(values) != len(bars):
            raise ValueError("feature vector unavailable")
        if any(value is not None and not isfinite(value) for value in values):
            raise ValueError("nonfinite feature value")
    results = []
    for index, bar in enumerate(bars[:-1]):
        observed = {identifier: features[identifier][index] for identifier in sorted(identifiers)}
        if any(value is None for value in observed.values()):
            weight = 0.0
            branch = "missing_flat"
        else:
            outcomes = []
            for predicate in program.predicates:
                value = observed[predicate.feature]
                assert value is not None
                outcomes.append(
                    {
                        "gt": value > predicate.threshold,
                        "ge": value >= predicate.threshold,
                        "lt": value < predicate.threshold,
                        "le": value <= predicate.threshold,
                    }[predicate.operator]
                )
            matched = all(outcomes)
            weight = program.match_weight if matched else program.otherwise_weight
            branch = "match" if matched else "otherwise"
        results.append(
            PolicyDecision(
                decided_at=bar.timestamp,
                executable_at=bars[index + 1].timestamp,
                symbol=bar.symbol,
                target_weight=weight,
                policy_id=f"{program.policy_id}/{branch}",
                reason_hash=content_hash(
                    {
                        "program": asdict(program),
                        "observed": observed,
                        "index": index,
                        "branch": branch,
                    }
                ),
            )
        )
    return tuple(results)
