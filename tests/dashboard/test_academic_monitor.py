"""T4 local research monitor: real immutable academic MCP SQLite evidence."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dashboard.academic_monitor import AcademicMonitorReader
from dashboard.academic_run import create_academic_app, main
from dashboard.app import create_app
from dashboard.service import DashboardService
from tests.integrations.test_academic_mcp_sessions import _setup
from tests.research.test_autonomous_academic_cycle import ScriptedResearcher


def _fixture(tmp_path: Path) -> tuple[object, dict, Path]:
    server, started = _setup(tmp_path)
    root = tmp_path / "state" / "academic-gpt-checkpoints"
    assert (root / "cycles.sqlite").is_file()
    assert (root / "gateway.sqlite").is_file()
    return server, started, root


def test_empty_and_unavailable_states_are_honest(tmp_path: Path) -> None:
    client = TestClient(create_academic_app(tmp_path / "missing"))
    assert client.get("/").status_code == 200
    assert client.get("/academic").status_code == 200
    assert client.get("/static/academic.js").status_code == 200
    assert client.get("/static/academic.css").status_code == 200
    result = client.get("/api/academic/overview")
    assert result.status_code == 503
    assert result.json() == {"status": "RESEARCH_STATE_UNAVAILABLE"}
    assert "Cache-Control" in result.headers
    assert client.post("/api/academic/overview").status_code == 405


def test_pending_diagnosis_shows_current_uncommitted_plan_without_fake_metrics(
    tmp_path: Path,
) -> None:
    server, started, root = _fixture(tmp_path)
    scripted = ScriptedResearcher()
    original = server._dispatch(
        "submit_algorithm_plan",
        {
            "session_id": started["session_id"],
            "checkpoint_token": started["checkpoint_token"],
            "plan": scripted.propose(started["model_context"]),
        },
    )
    assert original["checkpoint_phase"] == "AWAITING_DIAGNOSIS"
    client = TestClient(create_academic_app(root))
    response = client.get("/api/academic/overview")
    assert response.status_code == 200
    data = response.json()
    assert data["selected_session_id"] == started["session_id"]
    assert data["checkpoint"]["code"] == "AWAITING_DIAGNOSIS"
    assert data["checkpoint"]["is_actively_running"] is False
    assert data["checkpoint"]["requires_external_action"] is True
    assert data["completed"] == 0 and data["requested"] == 2
    assert data["progress_pct"] == 0
    assert data["current_model"]["evaluation_status"] == "STAGED_NOT_COMMITTED"
    assert data["current_model"]["metrics"] is None
    assert data["latest_completed_model"] is None
    assert data["best_by_return"] is None
    assert data["profitability_verified"] is False
    assert data["orders_enabled"] is False
    assert "checkpoint_token" not in response.text
    assert "plan_json" not in response.text
    assert "model_context" not in response.text
    assert client.get("/api/academic/sessions/" + started["session_id"]).status_code == 200
    assert client.get("/api/academic/sessions/invalid' OR 1=1--").status_code == 404
    assert client.get("/", headers={"host": "evil.example"}).status_code == 400


def test_actual_evaluation_source_and_s7_integrity(tmp_path: Path) -> None:
    server, started, root = _fixture(tmp_path)
    scripted = ScriptedResearcher()
    p = server._dispatch(
        "submit_algorithm_plan",
        {
            "session_id": started["session_id"],
            "checkpoint_token": started["checkpoint_token"],
            "plan": scripted.propose(started["model_context"]),
        },
    )
    committed = server._dispatch(
        "submit_algorithm_diagnosis",
        {
            "session_id": started["session_id"],
            "checkpoint_token": p["checkpoint_token"],
            "diagnosis": scripted.propose(p["model_context"]),
        },
    )
    assert committed["completed_generations"] == 1
    base = AcademicMonitorReader(root).snapshot(started["session_id"])
    actual = committed["history"][0]
    assert base["history"][0]["metrics"]["total_return"] == actual["metrics"]["total_return"]
    assert base["history"][0]["metrics"]["max_drawdown"] == actual["metrics"]["max_drawdown"]
    assert base["history"][0]["metrics"]["sharpe"] == actual["metrics"]["sharpe"]
    assert base["best_by_return"]["generation"] == 1
    assert base["best_by_sharpe"]["generation"] == 1
    assert base["history"][0]["s7_status"] == "MEASURED"
    assert base["missing_s7_count"] == 0
    assert base["current_model"]["evaluation_status"] == "LAST_COMMITTED_GENERATION"
    assert base["current_model"]["metrics"] == actual["metrics"]
    assert base["profitability_verified"] is False
    assert base["point_in_time_verified"] is False
    assert base["independent_oos_approved"] is False
    assert base["auto_execution_verified"] is False
    assert len(base["sessions"]) >= 1

    # Tampering with a persisted S7 result must fail closed rather than
    # silently showing its related return as validated.
    with sqlite3.connect(root / "gateway.sqlite") as db:
        db.execute(
            "UPDATE experiment_reports SET report_json=? WHERE session_id=?",
            (json.dumps({"injected": "forged win"}), started["session_id"]),
        )
    response = TestClient(create_academic_app(root)).get("/api/academic/overview")
    assert response.status_code == 503
    assert response.json() == {"status": "RESEARCH_STATE_UNAVAILABLE"}
    assert "forged win" not in response.text


def test_terminal_status_overrides_stale_waiting_gateway_phase(tmp_path: Path) -> None:
    _, started, root = _fixture(tmp_path)
    with sqlite3.connect(root / "cycles.sqlite") as db:
        db.execute(
            "UPDATE sessions SET status='INTERRUPTED' WHERE id=?",
            (started["session_id"],),
        )
    status = AcademicMonitorReader(root).snapshot()["checkpoint"]
    assert status["code"] == "INTERRUPTED"
    assert status["label"] == "중단됨"
    assert status["is_actively_running"] is False


def test_local_runner_refuses_external_bind(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(["--checkpoint-dir", str(tmp_path), "--host", "0.0.0.0"])


def test_no_control_or_orders_routes_are_exposed(tmp_path: Path) -> None:
    client = TestClient(create_academic_app(tmp_path))
    for path in ("/api/refresh", "/api/orders", "/api/academic/start", "/api/academic/stop"):
        assert client.post(path).status_code in (404, 405)
    page = client.get("/").text
    assert "3초 자동 갱신" in page
    assert "ORDERS DISABLED" in page
    assert "실현" in page or "개발" in page


def test_existing_paper_dashboard_gets_readonly_academic_tab(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, started, root = _fixture(tmp_path)
    monkeypatch.setenv("QUANT_ACADEMIC_CHECKPOINT_DIR", str(root))
    client = TestClient(create_app(DashboardService(tmp_path)))
    assert client.get("/").status_code == 200
    assert 'href="/academic"' in client.get("/").text
    assert client.get("/academic").status_code == 200
    payload = client.get("/api/academic/overview")
    assert payload.status_code == 200
    assert payload.json()["selected_session_id"] == started["session_id"]
    assert payload.json()["orders_enabled"] is False
    assert client.post("/api/academic/overview").status_code == 405
