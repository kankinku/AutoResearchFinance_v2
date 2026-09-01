from __future__ import annotations

from dataclasses import dataclass

from evaluation.metrics import Metrics
from evaluation.robustness import RobustnessReport


@dataclass(frozen=True)
class FunnelConfig:
    min_fast_trades: int = 10
    min_fast_return: float = 0.0
    min_full_trades: int = 10
    min_full_return: float = 0.0
    min_robust_score: float = 0.5
    require_validation: bool = True
    champion_score: float | None = None


@dataclass(frozen=True)
class FunnelInput:
    candidate_hash: str
    family: str
    fast_metrics: Metrics
    full_metrics: Metrics
    robustness: RobustnessReport
    validation_passed: bool


@dataclass(frozen=True)
class GateDecision:
    name: str
    passed: bool
    threshold: float | int | bool | None
    actual: float | int | bool | None
    reason: str | None = None


@dataclass(frozen=True)
class FunnelResult:
    candidate_hash: str
    family: str
    status: str
    score: float
    gates: tuple[GateDecision, ...]


def select_candidate(candidate: FunnelInput, config: FunnelConfig) -> FunnelResult:
    fast_passed = candidate.fast_metrics.trade_count >= config.min_fast_trades
    fast_return_passed = candidate.fast_metrics.total_return >= config.min_fast_return
    full_passed = candidate.full_metrics.trade_count >= config.min_full_trades
    full_return_passed = candidate.full_metrics.total_return >= config.min_full_return
    robust_passed = (
        candidate.robustness.status == "OK"
        and candidate.robustness.robust_score >= config.min_robust_score
    )
    validation_passed = candidate.validation_passed if config.require_validation else True
    score = candidate.robustness.robust_score
    promotion_passed = config.champion_score is None or score > config.champion_score
    gates = (
        GateDecision(
            "fast",
            fast_passed and fast_return_passed,
            config.min_fast_trades,
            candidate.fast_metrics.trade_count,
            None if fast_passed and fast_return_passed else _first_reason(
                not fast_passed, "trade_count", not fast_return_passed, "total_return"
            ),
        ),
        GateDecision(
            "full",
            full_passed and full_return_passed,
            config.min_full_trades,
            candidate.full_metrics.trade_count,
            None if full_passed and full_return_passed else _first_reason(
                not full_passed, "trade_count", not full_return_passed, "total_return"
            ),
        ),
        GateDecision(
            "robustness",
            robust_passed,
            config.min_robust_score,
            score,
            None if robust_passed else candidate.robustness.status.lower(),
        ),
        GateDecision(
            "validation",
            validation_passed,
            True if config.require_validation else None,
            candidate.validation_passed,
            None if validation_passed else "validation",
        ),
        GateDecision(
            "promotion",
            promotion_passed,
            config.champion_score,
            score,
            None if promotion_passed else "not_better_than_champion",
        ),
    )
    failures = [gate for gate in gates if not gate.passed]
    if not failures:
        status = "SURVIVOR"
    elif len(failures) == 1 and failures[0].name in {"fast", "full", "robustness"}:
        status = "NEAR_MISS"
    else:
        status = "REJECT"
    return FunnelResult(candidate.candidate_hash, candidate.family, status, score, gates)


def _first_reason(*pairs: bool | str) -> str:
    for index in range(0, len(pairs), 2):
        if pairs[index]:
            return str(pairs[index + 1])
    return "gate"
