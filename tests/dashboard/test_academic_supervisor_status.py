"""T4 read-only supervisor observability, no real model worker or mutation API."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

from dashboard.academic_run import create_academic_app
from dashboard.academic_worker_status import supervised_status
from research.llm.supervised_checkpoint_runner import ResearchRunSupervisor
from tests.integrations.test_academic_mcp_sessions import _setup

SID = "f" * 32


def _app(tmp_path: Path):
    _, started = _setup(tmp_path)
    checkpoint = tmp_path / "state" / "academic-gpt-checkpoints"
    control = checkpoint.parent / "academic-supervisor-control"
    return started, checkpoint, control, TestClient(create_academic_app(checkpoint))


def test_unconnected_model_clearly_shows_external_input_required(tmp_path: Path) -> None:
    started, _, control, app = _app(tmp_path)
    response = app.get("/api/academic/overview")
    assert response.status_code == 200
    data = response.json()
    assert data["checkpoint"]["code"] == "AWAITING_PLAN"
    assert data["supervisor"]["code"] == "PROVIDER_REQUIRED"
    assert data["supervisor"]["verified_worker_running"] is False
    assert data["supervisor"]["can_proceed_without_model"] is False
    assert data["supervisor"]["orders_enabled"] is False
    assert data["completed"] == 0
    assert not control.exists(), "observing monitor must never create supervisor state"
    html = app.get("/academic").text
    assert "GPT 연구 실행 상태" in html
    assert app.post("/api/academic/start").status_code in (404, 405)
    assert app.post("/api/academic/stop").status_code in (404, 405)
    assert "checkpoint_token" not in response.text


def test_safe_pause_stop_requests_visible_without_exposing_identity(tmp_path: Path) -> None:
    started, checkpoint, control, app = _app(tmp_path)
    sid = started["session_id"]
    owner = ResearchRunSupervisor(control)
    owner.request(sid, "PAUSE")
    obj = app.get("/api/academic/overview").json()["supervisor"]
    assert obj["code"] == "PAUSE_REQUESTED"
    assert obj["verified_worker_running"] is False
    assert obj["orders_enabled"] is False
    owner.request(sid, "STOP")
    obj = app.get("/api/academic/sessions/" + sid).json()["supervisor"]
    assert obj["code"] == "STOP_REQUESTED"
    owner.request(sid, "RUN")
    assert app.get("/api/academic/overview").json()["supervisor"]["code"] == "PROVIDER_REQUIRED"
    assert (checkpoint / "cycles.sqlite").is_file()


def test_stale_and_recent_heartbeat_never_verified_as_running(tmp_path: Path) -> None:
    started, _, control, app = _app(tmp_path)
    owner = ResearchRunSupervisor(control)
    sid = started["session_id"]
    owner._save(
        owner._path(sid, "status.json"),
        {
            "session_id": sid,
            "supervisor_state": "RUNNING",
            "owner_pid": 17,
            "owner_nonce": "secret_owner_nonce_do_not_show",
            "heartbeat_at_utc": "2020-01-01T00:00:00+00:00",
            "heartbeat_interval_seconds": 1,
            "orders_enabled": False,
            "independent_oos_approved": False,
        },
    )
    resp = app.get("/api/academic/overview")
    assert resp.status_code == 200
    obj = resp.json()["supervisor"]
    assert obj["code"] == "STALE_HEARTBEAT"
    assert obj["heartbeat_health"] == "STALE_OR_UNVERIFIED"
    assert "secret_owner_nonce" not in resp.text
    assert "owner_pid" not in resp.text
    assert obj["verified_worker_running"] is False

    from datetime import datetime, timezone

    changed = owner._load(owner._path(sid, "status.json"))
    changed["heartbeat_at_utc"] = datetime.now(timezone.utc).isoformat()
    owner._save(owner._path(sid, "status.json"), changed)
    resp2 = app.get("/api/academic/overview")
    assert resp2.status_code == 200
    assert resp2.json()["supervisor"]["code"] == "HEARTBEAT_UNVERIFIED"
    assert resp2.json()["supervisor"]["verified_worker_running"] is False


def test_damaged_control_fails_closed_and_keeps_evidence_visible(tmp_path: Path) -> None:
    started, _, control, app = _app(tmp_path)
    owner = ResearchRunSupervisor(control)
    sid = started["session_id"]
    bad = owner._path(sid, "status.json")
    bad.write_text('{"untrusted":"token-secret-do-not-expose"}')
    os.chmod(bad, 0o644)
    resp = app.get("/api/academic/overview")
    assert resp.status_code == 200
    assert resp.json()["supervisor"]["code"] == "CONTROL_STATE_UNAVAILABLE"
    assert resp.json()["supervisor"]["verified_worker_running"] is False
    assert "token-secret" not in resp.text
    assert resp.json()["completed"] == 0


def test_symlink_and_terminal_research_status_never_fake_active(tmp_path: Path) -> None:
    checkpoint = tmp_path / "academic-gpt-checkpoints"
    c = checkpoint.parent / "academic-supervisor-control"
    c.mkdir(mode=0o700)
    target = tmp_path / "secret"
    target.write_text(json.dumps({"session_id": SID}))
    (c / (SID + ".status.json")).symlink_to(target)
    obj = supervised_status(checkpoint, SID, "AWAITING_PLAN")
    assert obj["code"] == "CONTROL_STATE_UNAVAILABLE"
    assert supervised_status(checkpoint, SID, "COMPLETED")["verified_worker_running"] is False
