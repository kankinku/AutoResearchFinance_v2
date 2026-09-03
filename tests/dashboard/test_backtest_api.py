from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from dashboard.app import create_app
from dashboard.service import DashboardService


def test_backtest_endpoint_exposes_run_ledger_summary_and_connected_actions(tmp_path: Path) -> None:
    (tmp_path / "test-records.jsonl").write_text(
        "\n".join(
            json.dumps(item)
            for item in (
                {
                    "run_id": "run-good",
                    "strategy_hash": "strategy-good",
                    "generation": 3,
                    "timestamp": "2026-09-01T10:00:00+00:00",
                    "score": 0.82,
                    "total_return": 0.24,
                    "nasdaq_excess_return": 0.08,
                    "max_drawdown": 0.11,
                    "risk_compliant": True,
                    "status": "SURVIVOR",
                },
                {
                    "run_id": "run-bad",
                    "strategy_hash": "strategy-bad",
                    "generation": 2,
                    "timestamp": "2026-08-31T10:00:00+00:00",
                    "score": 0.31,
                    "total_return": -0.04,
                    "nasdaq_excess_return": -0.12,
                    "max_drawdown": 0.22,
                    "risk_compliant": False,
                    "status": "REJECT",
                },
            )
        ),
        encoding="utf-8",
    )
    client = TestClient(create_app(DashboardService(tmp_path)))

    response = client.get("/api/backtest")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["total_runs"] == 2
    assert payload["summary"]["succeeded_runs"] == 1
    assert payload["summary"]["rejected_runs"] == 1
    assert payload["summary"]["risk_compliant_runs"] == 1
    assert payload["summary"]["latest_run_at"] == "2026-09-01T10:00:00+00:00"
    assert payload["summary"]["best_run_id"] == "run-good"
    assert payload["summary"]["best_total_return"] == 0.24
    assert payload["summary"]["generation_count"] == 2
    assert payload["summary"]["risk_compliance_rate"] == 0.5
    assert [item["run_id"] for item in payload["runs"]] == ["run-good", "run-bad"]
    actions = {item["id"]: item for item in payload["capabilities"]}
    assert actions["validate_strategy"]["status"] == "CONNECTED"
    assert actions["run_generation"]["status"] == "CONNECTED"
    assert actions["equity_curve"]["status"] == "NOT_AVAILABLE"
    assert payload["mode"]["live_enabled"] is False


def test_backtest_run_detail_returns_only_matching_record(tmp_path: Path) -> None:
    record = {
        "run_id": "run-detail",
        "strategy_hash": "strategy-detail",
        "generation": 1,
        "timestamp": "2026-09-01T10:00:00+00:00",
        "status": "SURVIVOR",
    }
    (tmp_path / "test-records.jsonl").write_text(json.dumps(record), encoding="utf-8")
    client = TestClient(create_app(DashboardService(tmp_path)))

    response = client.get("/api/backtest/runs/run-detail")
    missing = client.get("/api/backtest/runs/missing")

    assert response.status_code == 200
    assert response.json()["run_id"] == record["run_id"]
    assert response.json()["strategy_hash"] == record["strategy_hash"]
    assert response.json()["status"] == record["status"]
    assert response.json()["total_return"] is None
    assert missing.status_code == 404


def test_backtest_page_is_served_as_a_separate_route(tmp_path: Path) -> None:
    client = TestClient(create_app(DashboardService(tmp_path)))

    response = client.get("/backtest")

    assert response.status_code == 200
    assert "백테스트 관리" in response.text
    assert "연구 운영" in response.text
