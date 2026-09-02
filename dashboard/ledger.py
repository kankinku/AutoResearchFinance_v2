from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from evaluation.selector import FunnelResult


def append_funnel_results(
    path: Path,
    *,
    generation: int,
    results: Sequence[FunnelResult],
    timestamp: str,
) -> None:
    if generation < 0 or not timestamp or not results:
        raise ValueError("generation, timestamp, and results are required")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for result in results:
            record = {
                "run_id": f"{result.candidate_hash}-generation-{generation}",
                "strategy_hash": result.candidate_hash,
                "generation": generation,
                "timestamp": timestamp,
                "score": result.score,
                "total_return": result.full_total_return,
                "nasdaq_excess_return": (
                    result.full_benchmark.nasdaq_excess_return
                    if result.full_benchmark is not None
                    else None
                ),
                "qqq_excess_return": (
                    result.full_benchmark.qqq_excess_return
                    if result.full_benchmark is not None
                    else None
                ),
                "max_drawdown": result.full_max_drawdown,
                "risk_compliant": (
                    result.risk_evaluation.compliant
                    if result.risk_evaluation is not None
                    else None
                ),
                "qqq_cagr_delta": (
                    result.full_benchmark.qqq_cagr_delta
                    if result.full_benchmark is not None
                    else None
                ),
                "status": result.status,
            }
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
