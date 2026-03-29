from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean
from typing import Any

from .falsifier import MAX_VALIDATION_SHARPE_GAP


@dataclass(slots=True, frozen=True)
class PrescreenReport:
    candidate_id: str
    passed: bool
    reason: str
    score: float
    metrics: dict[str, float]

    def to_payload(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "passed": self.passed,
            "reason": self.reason,
            "score": self.score,
            "metrics": dict(self.metrics),
        }


def prescreen_candidate(
    *,
    candidate_id: str,
    backtest_results: dict[str, Any],
) -> PrescreenReport:
    combinations = dict(backtest_results.get("combinations", {}))
    if not combinations:
        return PrescreenReport(
            candidate_id=candidate_id,
            passed=False,
            reason="dead_strategy",
            score=-10.0,
            metrics={},
        )

    exposures: list[float] = []
    trade_counts: list[float] = []
    turnovers: list[float] = []
    stability_gaps: list[float] = []
    oos_sharpes: list[float] = []
    combination_reasons: list[tuple[str, str]] = []
    for combination in combinations.values():
        symbol = str(combination.get("symbol", ""))
        timeframe = str(combination.get("timeframe", ""))
        combination_label = f"{symbol} {timeframe}".strip()
        validation = combination["splits"]["validation"]
        out_of_sample = combination["splits"]["out_of_sample"]
        exposure = float(out_of_sample["exposure"])
        trade_count = float(out_of_sample["trade_count"])
        turnover = float(out_of_sample["turnover"])
        validation_sharpe = float(validation["sharpe"])
        oos_sharpe = float(out_of_sample["sharpe"])
        if not all(
            math.isfinite(value)
            for value in (exposure, trade_count, turnover, validation_sharpe, oos_sharpe)
        ):
            return PrescreenReport(
                candidate_id=candidate_id,
                passed=False,
                reason="obvious_instability",
                score=-10.0,
                metrics={},
            )
        if exposure <= 0.0:
            combination_reasons.append(("zero_exposure", combination_label))
        elif trade_count < 2.0:
            combination_reasons.append(("extreme_undertrading", combination_label))
        elif trade_count > 150.0 or turnover > 30.0:
            combination_reasons.append(("extreme_overtrading", combination_label))
        elif abs(validation_sharpe - oos_sharpe) > MAX_VALIDATION_SHARPE_GAP:
            combination_reasons.append(("obvious_instability", combination_label))
        exposures.append(exposure)
        trade_counts.append(trade_count)
        turnovers.append(turnover)
        stability_gaps.append(abs(validation_sharpe - oos_sharpe))
        oos_sharpes.append(oos_sharpe)

    aggregate = {
        "mean_exposure": float(mean(exposures)),
        "mean_trade_count": float(mean(trade_counts)),
        "mean_turnover": float(mean(turnovers)),
        "mean_stability_gap": float(mean(stability_gaps)),
        "mean_oos_sharpe": float(mean(oos_sharpes)),
    }
    if combination_reasons:
        reason, combination_label = combination_reasons[0]
        metrics = {
            **aggregate,
            "failed_combination": combination_label,
        }
        failure_scores = {
            "zero_exposure": -9.0,
            "extreme_undertrading": -8.0,
            "extreme_overtrading": -7.0,
            "obvious_instability": -6.0,
        }
        return PrescreenReport(
            candidate_id,
            False,
            reason,
            failure_scores[reason],
            metrics,
        )

    score = (
        aggregate["mean_oos_sharpe"]
        + min(aggregate["mean_exposure"], 1.0)
        - (aggregate["mean_turnover"] / 100.0)
    )
    return PrescreenReport(candidate_id, True, "passed", float(score), aggregate)
