from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from evaluation.benchmark import BenchmarkComparison
from evaluation.metrics import Metrics
from evaluation.risk import RiskEvaluation
from evaluation.robustness import RobustnessReport
from mutation.parameter import ParameterValue


@dataclass(frozen=True)
class FunnelConfig:
    min_fast_trades: int = 10
    min_fast_return: float = 0.0
    min_full_trades: int = 10
    min_full_return: float = 0.0
    min_robust_score: float = 0.5
    require_validation: bool = True
    require_risk_compliance: bool = True
    min_qqq_cagr_delta: float | None = None
    min_annual_trades: int | None = None
    champion_score: float | None = None


@dataclass(frozen=True)
class FunnelInput:
    candidate_hash: str
    family: str
    fast_metrics: Metrics
    full_metrics: Metrics
    robustness: RobustnessReport
    validation_passed: bool
    fast_benchmark: BenchmarkComparison | None = None
    full_benchmark: BenchmarkComparison | None = None
    risk_evaluation: RiskEvaluation | None = None
    feature_ids: tuple[str, ...] = ()
    parameters: Mapping[str, ParameterValue] | None = None
    dataset_hash: str | None = None
    benchmark_dataset_hash: str | None = None
    validation_folds: tuple[Mapping[str, object], ...] = ()
    yearly_metrics: tuple[Mapping[str, object], ...] = ()


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
    fast_benchmark: BenchmarkComparison | None = None
    full_benchmark: BenchmarkComparison | None = None
    risk_evaluation: RiskEvaluation | None = None
    feature_ids: tuple[str, ...] = ()
    full_total_return: float | None = None
    full_max_drawdown: float | None = None
    parameters: Mapping[str, ParameterValue] | None = None
    dataset_hash: str | None = None
    benchmark_dataset_hash: str | None = None
    full_cagr: float | None = None
    full_sharpe: float | None = None
    full_sortino: float | None = None
    full_profit_factor: float | None = None
    full_trade_count: int | None = None
    full_turnover: float | None = None
    full_exposure: float | None = None
    validation_folds: tuple[Mapping[str, object], ...] = ()
    yearly_metrics: tuple[Mapping[str, object], ...] = ()


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
    risk_passed = (
        not config.require_risk_compliance
        or candidate.risk_evaluation is None
        or candidate.risk_evaluation.compliant
    )
    qqq_cagr_delta = (
        candidate.full_benchmark.qqq_cagr_delta
        if candidate.full_benchmark is not None
        else None
    )
    qqq_target_passed = (
        config.min_qqq_cagr_delta is None
        or (
            qqq_cagr_delta is not None
            and qqq_cagr_delta >= config.min_qqq_cagr_delta
        )
    )
    annual_counts = tuple(
        int(trade_count)
        for item in candidate.yearly_metrics
        if bool(item.get("complete", True))
        and isinstance((trade_count := item.get("trade_count")), (int, float, str))
    )
    annual_trade_passed = (
        config.min_annual_trades is None
        or (
            bool(annual_counts)
            and all(count > config.min_annual_trades for count in annual_counts)
        )
    )
    annual_trade_actual = min(annual_counts) if annual_counts else None
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
            "risk",
            risk_passed,
            True if config.require_risk_compliance else None,
            (
                candidate.risk_evaluation.compliant
                if candidate.risk_evaluation is not None
                else None
            ),
            None if risk_passed else "risk_policy_breach",
        ),
        GateDecision(
            "qqq_cagr_delta",
            qqq_target_passed,
            config.min_qqq_cagr_delta,
            qqq_cagr_delta,
            None if qqq_target_passed else "qqq_target_not_met",
        ),
        GateDecision(
            "annual_trade_count",
            annual_trade_passed,
            config.min_annual_trades,
            annual_trade_actual,
            None if annual_trade_passed else "annual_trade_count_not_met",
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
    return FunnelResult(
        candidate.candidate_hash,
        candidate.family,
        status,
        score,
        gates,
        candidate.fast_benchmark,
        candidate.full_benchmark,
        candidate.risk_evaluation,
        candidate.feature_ids,
        candidate.full_metrics.total_return,
        candidate.full_metrics.max_drawdown,
        candidate.parameters,
        candidate.dataset_hash,
        candidate.benchmark_dataset_hash,
        candidate.full_metrics.cagr,
        candidate.full_metrics.sharpe,
        candidate.full_metrics.sortino,
        candidate.full_metrics.profit_factor,
        candidate.full_metrics.trade_count,
        candidate.full_metrics.turnover,
        candidate.full_metrics.exposure,
        candidate.validation_folds,
        candidate.yearly_metrics,
    )


def _first_reason(*pairs: bool | str) -> str:
    for index in range(0, len(pairs), 2):
        if pairs[index]:
            return str(pairs[index + 1])
    return "gate"
