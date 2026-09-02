from __future__ import annotations

from enum import Enum
from typing import Any

from core.integrity.hashes import content_hash
from strategy_ir.schema import StrategyIR


class DuplicateKind(str, Enum):
    NEW = "NEW"
    EXACT_DUPLICATE = "EXACT_DUPLICATE"
    PARTIAL_DUPLICATE = "PARTIAL_DUPLICATE"


def semantic_payload(strategy: StrategyIR, *, include_risk: bool = True) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "family": strategy.family,
        "indicators": {
            key: value.model_dump(mode="json") for key, value in sorted(strategy.indicators.items())
        },
        "features": {
            key: value.model_dump(mode="json") for key, value in sorted(strategy.features.items())
        },
        "entry": strategy.entry.model_dump(mode="json"),
        "exit": strategy.exit.model_dump(mode="json"),
        "regime_filters": [item.model_dump(mode="json") for item in strategy.regime_filters],
    }
    if include_risk:
        payload["risk"] = strategy.risk.model_dump(mode="json")
    return payload


def strategy_fingerprint(strategy: StrategyIR) -> str:
    return content_hash(semantic_payload(strategy))


def classify_duplicate(candidate: StrategyIR, existing: list[StrategyIR]) -> Any:
    candidate_exact = strategy_fingerprint(candidate)
    candidate_signal = content_hash(semantic_payload(candidate, include_risk=False))
    for item in existing:
        if strategy_fingerprint(item) == candidate_exact:
            return _result(DuplicateKind.EXACT_DUPLICATE, item.strategy_id)
    for item in existing:
        if content_hash(semantic_payload(item, include_risk=False)) == candidate_signal:
            return _result(DuplicateKind.PARTIAL_DUPLICATE, item.strategy_id)
    return _result(DuplicateKind.NEW)


def _result(kind: DuplicateKind, duplicate_of: str | None = None) -> Any:
    from strategy_import.models import DuplicateResult

    return DuplicateResult(kind=kind.value, duplicate_of=duplicate_of)
