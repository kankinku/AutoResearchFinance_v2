from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from finance_autoresearch.localization import DEFAULT_LOCALIZER, OutputLocalizer

from .complexity import inspect_strategy_complexity


MAX_VALIDATION_SHARPE_GAP = 1.0
MAX_STARTUP_EXPOSURE_GAP = 0.55
MAX_STARTUP_TRADE_COUNT_RATIO = 0.2
MAX_INDICATOR_COUNT = 4
MAX_NEW_CLAUSE_COUNT = 2
MAX_REGIME_BRANCH_COUNT = 2
MAX_EXIT_FAMILY_COUNT = 2


@dataclass(slots=True, frozen=True)
class FalsificationReport:
    passed: bool
    summary: str
    checks: dict[str, dict[str, Any]]

    def to_payload(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "summary": self.summary,
            "checks": {key: dict(value) for key, value in self.checks.items()},
        }


def falsify_candidate(
    *,
    backtest_results: dict[str, Any],
    evaluation: dict[str, Any],
    strategy_path: Path | str,
    compile_result: dict[str, Any] | None = None,
    localizer: OutputLocalizer | None = None,
) -> FalsificationReport:
    resolved_localizer = localizer or DEFAULT_LOCALIZER
    validation_check = _validation_stability_check(backtest_results, localizer=resolved_localizer)
    startup_check = _startup_stability_check(backtest_results, localizer=resolved_localizer)
    complexity_check = _complexity_budget_check(
        strategy_path=Path(strategy_path),
        compile_result=compile_result,
        localizer=resolved_localizer,
    )
    checks = {
        "validation_stability": validation_check,
        "startup_stability": startup_check,
        "complexity_budget": complexity_check,
    }
    passed = all(bool(check["passed"]) for check in checks.values()) and bool(
        evaluation.get("guardrails_passed", False)
    )
    failed_checks = [name for name, check in checks.items() if not bool(check["passed"])]
    if failed_checks:
        summary = ", ".join(failed_checks)
    elif not bool(evaluation.get("guardrails_passed", False)):
        summary = resolved_localizer.log("falsifier.guardrails_failed")
    else:
        summary = resolved_localizer.log("falsifier.all_checks_passed")
    return FalsificationReport(passed=passed, summary=summary, checks=checks)


def _validation_stability_check(
    backtest_results: dict[str, Any],
    *,
    localizer: OutputLocalizer,
) -> dict[str, Any]:
    gaps: list[float] = []
    worst_key = ""
    worst_gap = 0.0
    failed_pairs: list[str] = []
    for key, combination in dict(backtest_results.get("combinations", {})).items():
        validation = combination["splits"]["validation"]
        out_of_sample = combination["splits"]["out_of_sample"]
        gap = abs(float(validation["sharpe"]) - float(out_of_sample["sharpe"]))
        gaps.append(gap)
        symbol, timeframe = key
        pair_label = f"{symbol} {timeframe}"
        if gap > worst_gap:
            worst_gap = gap
            worst_key = pair_label
        if gap > MAX_VALIDATION_SHARPE_GAP:
            failed_pairs.append(pair_label)
    mean_gap = sum(gaps) / len(gaps) if gaps else 0.0
    passed = not failed_pairs
    message = (
        localizer.log("falsifier.validation_gap_passed", mean_gap=mean_gap)
        if passed
        else localizer.log(
            "falsifier.validation_gap_failed",
            cap=MAX_VALIDATION_SHARPE_GAP,
            worst_key=worst_key,
            mean_gap=mean_gap,
        )
    )
    return {
        "passed": passed,
        "message": message,
        "mean_gap": mean_gap,
        "worst_gap": worst_gap,
        "failed_pairs": failed_pairs,
    }


def _startup_stability_check(
    backtest_results: dict[str, Any],
    *,
    localizer: OutputLocalizer,
) -> dict[str, Any]:
    unstable_pairs: list[str] = []
    for key, combination in dict(backtest_results.get("combinations", {})).items():
        validation = combination["splits"]["validation"]
        out_of_sample = combination["splits"]["out_of_sample"]
        validation_trade_count = max(float(validation["trade_count"]), 1.0)
        trade_count_ratio = float(out_of_sample["trade_count"]) / validation_trade_count
        exposure_gap = abs(float(validation["exposure"]) - float(out_of_sample["exposure"]))
        if trade_count_ratio < MAX_STARTUP_TRADE_COUNT_RATIO or exposure_gap > MAX_STARTUP_EXPOSURE_GAP:
            symbol, timeframe = key
            unstable_pairs.append(f"{symbol} {timeframe}")
    passed = not unstable_pairs
    message = (
        localizer.log("falsifier.startup_stable")
        if passed
        else localizer.log(
            "falsifier.startup_failed",
            pairs=", ".join(sorted(unstable_pairs)),
        )
    )
    return {"passed": passed, "message": message, "unstable_pairs": unstable_pairs}


def _complexity_budget_check(
    *,
    strategy_path: Path,
    compile_result: dict[str, Any] | None,
    localizer: OutputLocalizer,
) -> dict[str, Any]:
    complexity = inspect_strategy_complexity(strategy_path)
    indicator_count = int(
        compile_result.get("indicator_count", complexity.indicator_count)
        if compile_result is not None
        else complexity.indicator_count
    )
    new_clause_count = int(
        compile_result.get("new_clause_count", complexity.new_clause_count)
        if compile_result is not None
        else complexity.new_clause_count
    )
    regime_branch_count = int(
        compile_result.get("regime_branch_count", complexity.regime_branch_count)
        if compile_result is not None
        else complexity.regime_branch_count
    )
    exit_family_count = int(
        compile_result.get("exit_family_count", complexity.exit_family_count)
        if compile_result is not None
        else complexity.exit_family_count
    )
    passed = (
        indicator_count <= MAX_INDICATOR_COUNT
        and new_clause_count <= MAX_NEW_CLAUSE_COUNT
        and regime_branch_count <= MAX_REGIME_BRANCH_COUNT
        and exit_family_count <= MAX_EXIT_FAMILY_COUNT
    )
    message = localizer.log(
        "falsifier.complexity_ok" if passed else "falsifier.complexity_failed"
    )
    return {
        "passed": passed,
        "message": message,
        "indicator_count": indicator_count,
        "new_clause_count": new_clause_count,
        "regime_branch_count": regime_branch_count,
        "exit_family_count": exit_family_count,
    }
