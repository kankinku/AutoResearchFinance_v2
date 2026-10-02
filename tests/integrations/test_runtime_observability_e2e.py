from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from integrations.codex_mcp_server import CodexMCPServer, create_mcp_server
from memory.evidence_store import EvidenceStore
from runtime.runtime_contracts import RuntimeSnapshot


def _call_status(server: CodexMCPServer) -> dict[str, object]:
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "get_system_status", "arguments": {}},
        }
    )
    assert isinstance(response, dict)
    result = response["result"]
    assert isinstance(result, dict)
    assert result["isError"] is False
    content = result["content"]
    assert isinstance(content, list)
    item = content[0]
    assert isinstance(item, dict)
    payload = json.loads(str(item["text"]))
    assert isinstance(payload, dict)
    return payload


def _managed_state(
    server: CodexMCPServer,
    *,
    managed_run_id: str = "managed-e2e",
    alive_pids: set[int],
) -> None:
    controller = server.services.system.controller
    controller._write_state(
        {
            "status": "STARTED",
            "managed_run_id": managed_run_id,
            "started_at": "2026-09-27T00:00:00+00:00",
            "project_root": "/private/project/root",
            "dashboard_port": 8080,
            "container_name": "private-container-name",
            "evaluation_execution": "docker_worker",
            "components": [
                {
                    "id": "dashboard",
                    "status": "STARTED",
                    "pid": 101,
                    "identity_markers": ["private-dashboard-marker"],
                },
                {
                    "id": "research_worker",
                    "status": "STARTED",
                    "pid": 102,
                    "identity_markers": [
                        "private-research-marker",
                        managed_run_id,
                    ],
                },
                {
                    "id": "evaluation_backend",
                    "status": "CONFIGURED",
                    "mode": "docker_worker",
                    "active_jobs": 0,
                    "queued_jobs": 0,
                },
            ],
        }
    )
    controller._process_probe = lambda pid, markers: pid in alive_pids


def _runtime(payload: dict[str, object]) -> RuntimeSnapshot:
    runtime = payload["runtime"]
    assert isinstance(runtime, dict)
    return RuntimeSnapshot.model_validate(runtime)


def test_mcp_get_system_status_is_pure_read_when_workspace_is_uninitialized(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    server = create_mcp_server(state_dir=state, project_root=tmp_path)

    payload = _call_status(server)

    assert payload["status"] == "STOPPED"
    runtime = _runtime(payload)
    assert runtime.system.status == "STOPPED"
    assert runtime.health.status == "HEALTHY"
    assert runtime.orders_enabled is False
    assert not state.exists()


def test_mcp_handshake_still_records_connection_state(tmp_path: Path) -> None:
    state = tmp_path / "state"
    server = create_mcp_server(state_dir=state, project_root=tmp_path)

    response = server.handle({"jsonrpc": "2.0", "id": 2, "method": "ping"})

    assert isinstance(response, dict)
    status = json.loads((state / "llm" / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "ONLINE"
    assert status["last_result"] == "MCP_CONNECTED"


@pytest.mark.parametrize(
    ("alive_pids", "worker_status", "expected_system", "expected_health"),
    [
        ({101, 102}, None, "RUNNING", "HEALTHY"),
        ({102}, None, "DEGRADED", "DEGRADED"),
        ({101}, "FAILED", "FAILED", "FAILING"),
    ],
)
def test_mcp_system_status_preserves_runtime_schema_across_managed_states(
    tmp_path: Path,
    alive_pids: set[int],
    worker_status: str | None,
    expected_system: str,
    expected_health: str,
) -> None:
    state = tmp_path / "state"
    server = create_mcp_server(state_dir=state, project_root=tmp_path)
    _managed_state(server, alive_pids=alive_pids)
    if worker_status is not None:
        (state / "system" / "research_worker.json").write_text(
            json.dumps(
                {
                    "managed_run_id": "managed-e2e",
                    "role": "research",
                    "status": worker_status,
                    "error": "RuntimeError: private worker failure",
                }
            ),
            encoding="utf-8",
        )

    payload = _call_status(server)
    runtime = _runtime(payload)

    assert payload["status"] == expected_system
    assert runtime.system.status == expected_system
    assert runtime.health.status == expected_health
    assert runtime.system.managed_run_id == "managed-e2e"
    assert runtime.orders_enabled is False


def test_mcp_status_recovers_interrupted_research_and_exposes_same_snapshot(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    server = create_mcp_server(state_dir=state, project_root=tmp_path)
    _managed_state(server, alive_pids={101})
    now = datetime.now(timezone.utc).isoformat()
    (state / "system" / "autoresearch.json").write_text(
        json.dumps(
            {
                "status": "RUNNING",
                "research_run_id": "research-e2e",
                "current_generation": 1,
                "current_phase": "BACKTESTING",
                "completed_generations": 0,
                "requested_generations": 1,
                "phase_started_at": now,
                "last_event": "evaluation_started",
                "last_event_at": now,
                "generations": [],
            }
        ),
        encoding="utf-8",
    )
    EvidenceStore(state).append(
        "run",
        "run:research-e2e",
        {
            "research_run_id": "research-e2e",
            "requested_generations": 1,
            "seed": 0,
        },
    )

    payload = _call_status(server)
    runtime = _runtime(payload)

    assert payload["status"] == "INTERRUPTED"
    assert runtime.system.status == "INTERRUPTED"
    assert runtime.research.status == "INTERRUPTED"
    assert runtime.evidence.status == "INTERRUPTED"
    assert runtime.evidence.closed is True
    assert runtime.health.status == "INTERRUPTED"
    assert runtime.health.primary_code == "RESEARCH_INTERRUPTED"
    recovery = payload["recovery"]
    assert isinstance(recovery, dict)
    assert recovery["interrupted_research_run_id"] == "research-e2e"


def test_mcp_runtime_health_preserves_source_precedence(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    system = state / "system"
    system.mkdir(parents=True)
    old = (datetime.now(timezone.utc) - timedelta(seconds=1900)).isoformat()
    (system / "autoresearch.json").write_text(
        json.dumps(
            {
                "status": "RUNNING",
                "research_run_id": "stale-e2e",
                "current_generation": 1,
                "current_phase": "BACKTESTING",
                "completed_generations": 0,
                "requested_generations": 1,
                "phase_started_at": old,
                "last_event": "evaluation_started",
                "last_event_at": old,
            }
        ),
        encoding="utf-8",
    )
    queue_path = system / "evaluation-jobs" / "queue.sqlite"
    queue_path.parent.mkdir(parents=True)
    queue_path.write_bytes(b"corrupted queue")
    server = create_mcp_server(state_dir=state, project_root=tmp_path)

    payload = _call_status(server)
    runtime = _runtime(payload)

    assert payload["status"] == "STOPPED"
    assert runtime.research.is_stale is True
    assert runtime.evaluation.queue_health == "UNAVAILABLE"
    assert runtime.health.status == "UNAVAILABLE"
    assert runtime.health.primary_source == "evaluation"
    assert runtime.health.primary_code == "EVALUATION_QUEUE_UNAVAILABLE"
    assert any(issue.code == "RESEARCH_STALE" for issue in runtime.health.issues)


def test_mcp_system_status_sanitizes_internal_identity_and_raw_errors(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    server = create_mcp_server(state_dir=state, project_root=tmp_path)
    _managed_state(server, alive_pids={101, 102})
    (state / "system" / "autoresearch.json").write_text(
        json.dumps(
            {
                "status": "RUNNING",
                "research_run_id": "secret-e2e",
                "current_generation": 1,
                "current_phase": "PROPOSING",
                "completed_generations": 0,
                "requested_generations": 1,
                "last_event": "proposal_started",
                "last_event_at": datetime.now(timezone.utc).isoformat(),
                "error": "ValueError: raw-secret-research-detail",
            }
        ),
        encoding="utf-8",
    )
    heartbeat = state / "worker-heartbeats"
    heartbeat.mkdir(exist_ok=True)
    (heartbeat / "eval-secret.json").write_text(
        json.dumps(
            {
                "worker_id": "eval-secret",
                "role": "evaluation",
                "status": "FAILED",
                "last_heartbeat": datetime.now(timezone.utc).isoformat(),
                "error": "ConnectionError: raw-secret-worker-detail",
            }
        ),
        encoding="utf-8",
    )

    payload = _call_status(server)
    serialized = json.dumps(payload)

    assert "project_root" not in payload
    assert "container_name" not in payload
    assert "identity_markers" not in serialized
    assert "private-dashboard-marker" not in serialized
    assert "private-research-marker" not in serialized
    assert "/private/project/root" not in serialized
    assert "private-container-name" not in serialized
    assert "raw-secret-research-detail" not in serialized
    assert "raw-secret-worker-detail" not in serialized
    runtime = _runtime(payload)
    assert runtime.research.error_class == "ValueError"
    assert any(
        issue.error_class == "ConnectionError"
        for issue in runtime.health.issues
        if issue.source == "worker:eval-secret"
    )
