from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from dashboard.app import create_app
from dashboard.service import DashboardService


def _record(
    run_id: str, generation: int, score: float, status: str = "REJECT"
) -> dict[str, object]:
    return {
        "run_id": run_id,
        "strategy_hash": f"strategy-{run_id}",
        "generation": generation,
        "timestamp": f"2026-09-0{generation}T10:00:00+00:00",
        "score": score,
        "total_return": score / 2,
        "strategy_cagr": score / 3,
        "qqq_cagr": 0.18,
        "qqq_cagr_delta": score / 3 - 0.18,
        "max_drawdown": 0.12,
        "sharpe": 1.1,
        "trade_count": 40,
        "risk_compliant": True,
        "status": status,
        "yearly_metrics": [
            {"year": 2025, "trade_count": 40, "total_return": 0.2, "complete": True}
        ],
        "feature_lineage": [
            {
                "alias": "rsi",
                "feature_id": "rsi.wilder",
                "inputs": ["close"],
                "timeframe": "1d",
                "lag_bars": 1,
                "lookback": 14,
                "parameters": {},
            }
        ],
    }


def test_backtest_snapshot_exposes_live_research_and_generation_performance(tmp_path: Path) -> None:
    records = [
        _record("g1-rejected", 1, 0.9),
        _record("g1-pass", 1, 0.4, "SURVIVOR"),
        _record("g2-pass", 2, 0.7, "SURVIVOR"),
    ]
    (tmp_path / "test-records.jsonl").write_text(
        "\n".join(json.dumps(item) for item in records), encoding="utf-8"
    )
    (tmp_path / "system").mkdir()
    (tmp_path / "system" / "autoresearch.json").write_text(
        json.dumps(
            {
                "status": "RUNNING",
                "requested_generations": 10,
                "completed_generations": 2,
                "current_generation": 3,
                "current_phase": "backtest",
                "phase_started_at": "2026-09-03T10:00:00+00:00",
                "generations": [
                    {
                        "generation": 1,
                        "intent": {"rationale": "활동성을 높인다", "feature_selections": []},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    def clock() -> datetime:
        return datetime(2026, 9, 3, 10, 2, tzinfo=timezone.utc)
    client = TestClient(create_app(DashboardService(tmp_path, clock=clock)))

    payload = client.get("/api/backtest").json()

    assert payload["research"]["completed_generations"] == 2
    assert payload["research"]["current_generation"] == 3
    assert payload["research"]["phase_elapsed_seconds"] == 120.0
    assert [item["generation"] for item in payload["generations"]] == [1, 2]
    assert payload["generations"][0]["best_run_id"] == "g1-pass"
    assert payload["generations"][0]["best_strategy_cagr"] == 0.13333333333333333
    assert payload["generations"][0]["proposal"]["rationale"] == "활동성을 높인다"
    assert payload["summary"]["generation_count"] == 2
    assert payload["summary"]["best_strategy_cagr"] == 0.2333333333333333


def test_generation_summary_keeps_diagnostics_in_detail_payload(tmp_path: Path) -> None:
    record = _record("detail", 4, 0.8, "SURVIVOR")
    record["gates"] = [{"name": "qqq_cagr_delta", "passed": True, "actual": 0.08, "threshold": 0.1}]
    record["validation_folds"] = [
        {"fold": 1, "strategy_cagr": 0.2, "qqq_cagr": 0.18, "passed": True}
    ]
    (tmp_path / "test-records.jsonl").write_text(json.dumps(record), encoding="utf-8")
    payload = TestClient(create_app(DashboardService(tmp_path))).get("/api/backtest").json()

    assert payload["generations"][0]["generation"] == 4
    assert payload["runs"][0]["run_id"] == "detail"
    assert payload["runs"][0]["gates"][0]["name"] == "qqq_cagr_delta"
    assert payload["runs"][0]["validation_folds"][0]["passed"] is True
