from __future__ import annotations

import json
from pathlib import Path

from dashboard.ledger import append_funnel_results
from dashboard.state import DashboardStateReader
from evaluation.benchmark import compare_benchmarks
from evaluation.selector import FunnelResult, GateDecision


def test_ledger_appends_sanitized_funnel_results_for_dashboard(tmp_path: Path) -> None:
    result = FunnelResult(
        "strategy-1",
        "macro",
        "SURVIVOR",
        0.8,
        (GateDecision("qqq_cagr_delta", True, 0.10, 0.12),),
        full_total_return=0.2,
        full_max_drawdown=0.05,
        full_cagr=0.12,
        full_sharpe=1.3,
        full_sortino=1.8,
        full_profit_factor=2.1,
        full_trade_count=14,
        full_turnover=3.2,
        full_exposure=0.4,
        parameters={"indicators.fast.period": 5},
        dataset_hash="data-hash",
        validation_folds=(
            {
                "fold": 0,
                "strategy_cagr": 0.1,
                "qqq_cagr_delta": 0.02,
                "trade_count": 4,
                "passed": True,
            },
        ),
        robustness_dsr=0.72,
        robustness_pbo=0.18,
        full_benchmark=compare_benchmarks(
            (100.0, 110.0, 121.0),
            (100.0, 105.0, 110.0),
            (100.0, 106.0, 112.0),
            periods_per_year=2,
        ),
    )

    append_funnel_results(
        tmp_path / "test-records.jsonl",
        generation=3,
        results=(result,),
        timestamp="2026-09-01T12:00:00+00:00",
    )

    payload = json.loads((tmp_path / "test-records.jsonl").read_text(encoding="utf-8"))
    snapshot = DashboardStateReader(tmp_path).read()
    assert payload["strategy_hash"] == "strategy-1"
    assert payload["total_return"] == 0.2
    assert payload["parameters"] == {"indicators.fast.period": 5}
    assert payload["dataset_hash"] == "data-hash"
    assert payload["strategy_cagr"] == 0.12
    assert payload["dsr"] == 0.72
    assert payload["pbo"] == 0.18
    assert payload["trade_count"] == 14
    assert payload["qqq_cagr"] is not None
    assert payload["gates"] == [
        {
            "actual": 0.12,
            "name": "qqq_cagr_delta",
            "passed": True,
            "reason": None,
            "threshold": 0.10,
        }
    ]
    assert payload["validation_folds"][0]["qqq_cagr_delta"] == 0.02
    assert snapshot.tests[0].run_id == "strategy-1-generation-3"
    assert snapshot.tests[0].dsr == 0.72
    assert snapshot.tests[0].pbo == 0.18
