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


def _rewrite_as_inherited(root: Path, sid: str) -> None:
    from core.integrity.hashes import content_hash
    from research.llm.autonomous_cycle import AcademicCycleService

    with sqlite3.connect(root / "cycles.sqlite") as db:
        row = db.execute(
            "SELECT evidence_json FROM generations WHERE session_id=? AND generation=1",
            (sid,),
        ).fetchone()
        assert row is not None
        payload = json.loads(row[0])
        payload["base_algorithm_plan"] = payload["algorithm_plan"]
        payload["algorithm_plan"] = None
        payload["inherited_strategy_ir"] = {
            "id": "research_plan_verified_ir", "schema_version": 1,
            "entry": {"logic": "AND", "conditions": []},
        }
        payload["strategy_hash"] = content_hash(payload["inherited_strategy_ir"])
        payload["inherited_parent"] = {
            "source_generation": 1,
            "parent_strategy_hash": "a" * 64,
        }
        digest = AcademicCycleService._row_evidence_hash(sid, 1, None, payload)
        db.execute(
            "UPDATE generations SET evidence_json=?,evidence_hash=? "
            "WHERE session_id=? AND generation=1",
            (json.dumps(payload, sort_keys=True), digest, sid),
        )
    with sqlite3.connect(root / "gateway.sqlite") as db:
        row = db.execute(
            "SELECT report_json FROM experiment_reports WHERE session_id=? AND generation=1",
            (sid,),
        ).fetchone()
        assert row
        report = json.loads(row[0])
        report["original_generation_evidence_hash"] = digest
        db.execute(
            "UPDATE experiment_reports SET report_json=?,report_hash=? "
            "WHERE session_id=? AND generation=1",
            (json.dumps(report, sort_keys=True), content_hash(report), sid),
        )
        db.execute(
            "UPDATE generation_timings SET evidence_hash=? "
            "WHERE session_id=? AND generation=1",
            (digest, sid),
        )


def test_inherited_ir_generation_does_not_crash_academic_api(tmp_path: Path) -> None:
    server, started, root = _fixture(tmp_path)
    scripted = ScriptedResearcher()
    plan = server._dispatch(
        "submit_algorithm_plan",
        {"session_id": started["session_id"], "checkpoint_token": started["checkpoint_token"],
         "plan": scripted.propose(started["model_context"])},
    )
    server._dispatch(
        "submit_algorithm_diagnosis",
        {"session_id": started["session_id"], "checkpoint_token": plan["checkpoint_token"],
         "diagnosis": scripted.propose(plan["model_context"])},
    )
    _rewrite_as_inherited(root, started["session_id"])
    response = TestClient(create_academic_app(root)).get("/api/academic/overview")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["completed"] == 1
    assert payload["checkpoint"]["code"] == "AWAITING_PLAN"
    assert payload["history"][0]["plan_id"].startswith("계승 IR")
    assert payload["history"][0]["strategy_kind"] == "INHERITED_STRATEGY_IR"
    assert payload["history"][0]["source_generation"] == 1
    assert payload["history"][0]["s7_status"] == "MEASURED"
    assert payload["orders_enabled"] is False


def test_inherited_ir_forged_strategy_hash_fails_closed(tmp_path: Path) -> None:
    server, started, root = _fixture(tmp_path)
    scripted = ScriptedResearcher()
    plan = server._dispatch(
        "submit_algorithm_plan",
        {"session_id": started["session_id"], "checkpoint_token": started["checkpoint_token"],
         "plan": scripted.propose(started["model_context"])},
    )
    server._dispatch(
        "submit_algorithm_diagnosis",
        {"session_id": started["session_id"], "checkpoint_token": plan["checkpoint_token"],
         "diagnosis": scripted.propose(plan["model_context"])},
    )
    _rewrite_as_inherited(root, started["session_id"])
    with sqlite3.connect(root / "cycles.sqlite") as db:
        row = db.execute(
            "SELECT evidence_json FROM generations WHERE session_id=? AND generation=1",
            (started["session_id"],),
        ).fetchone()
        payload = json.loads(row[0])
        payload["inherited_strategy_ir"]["id"] = "FORGED"
        from research.llm.autonomous_cycle import AcademicCycleService
        digest = AcademicCycleService._row_evidence_hash(
            started["session_id"], 1, None, payload
        )
        db.execute(
            "UPDATE generations SET evidence_json=?, evidence_hash=? "
            "WHERE session_id=? AND generation=1",
            (json.dumps(payload, sort_keys=True), digest, started["session_id"]),
        )
    response = TestClient(create_academic_app(root)).get("/api/academic/overview")
    assert response.status_code == 503
    assert response.json()["status"] == "RESEARCH_STATE_UNAVAILABLE"


def test_global_campaign_counters_come_from_verified_sqlite_not_stale_manifest(
    tmp_path: Path,
) -> None:
    origin_id = "a" * 32
    current_id = "b" * 32
    root = tmp_path / "academic-gpt-checkpoints"
    root.mkdir()
    with sqlite3.connect(root / "cycles.sqlite") as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE TABLE sessions (id TEXT PRIMARY KEY,requested INTEGER,"
            "completed INTEGER,status TEXT,dataset_hash TEXT)"
        )
        conn.execute(
            "CREATE TABLE generations (session_id TEXT,generation INTEGER)"
        )
        conn.execute(
            "INSERT INTO sessions VALUES(?,?,?,?,?)",
            (origin_id, 100, 100, "COMPLETED", "0" * 64),
        )
        conn.execute(
            "INSERT INTO sessions VALUES(?,?,?,?,?)",
            (current_id, 100, 35, "AWAITING_PROVIDER", "0" * 64),
        )
        conn.executemany(
            "INSERT INTO generations VALUES(?,?)",
            ((origin_id, i) for i in range(1, 101)),
        )
        info = {
            "schema": "quant-autoresearch-campaign-lineage-v1",
            "origin_session_id": origin_id,
            "origin_generations_completed": 100,
            "current_session_id": current_id,
            "current_global_range": [101, 200],
            "future_global_range": [201, 300],
            "current_local_completed": 33,  # stale historical manifest note
            "next_global_generation": 134,  # must not be used as current value
            "dataset_hash": "0" * 64,
            "orders_enabled": False,
            "independent_oos_approved": False,
        }
        (root / "campaign-101-300.json").write_text(json.dumps(info))
        row = conn.execute(
            "SELECT * FROM sessions WHERE id=?", (current_id,),
        ).fetchone()
        reader = AcademicMonitorReader(root)
        assert reader._campaign_progress(conn, current_id, row) == {
            "completed": 135, "requested": 300, "local_offset": 100,
        }
        assert reader._campaign_progress(conn, origin_id, row) is None
        conn.execute(
            "DELETE FROM generations WHERE session_id=? AND generation=100",
            (origin_id,),
        )
        with pytest.raises(Exception, match="CAMPAIGN"):
            reader._campaign_progress(conn, current_id, row)
