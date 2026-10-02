from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from cli import main
from dashboard.app import create_app
from dashboard.service import DashboardService
from integrations.codex_mcp_server import create_mcp_server


@pytest.mark.parametrize("with_run", [False, True])
def test_research_evidence_empty_interfaces_agree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], with_run: bool
) -> None:
    if with_run:
        from memory.evidence_store import EvidenceStore

        store = EvidenceStore(tmp_path)
        store.append("run", "run-a", {
            "research_run_id": "run-a", "requested_generations": 1, "seed": 0,
        })
        store.append(
            "attempt",
            "attempt-a",
            {
                "research_run_id": "run-a",
                "attempt_id": "attempt-a",
                "generation": 1,
                "status": "COMPLETED",
                "candidates": [
                    {
                        "candidate_hash": "candidate-a",
                        "family": "trend",
                        "status": "REJECT",
                        "failed_gates": ["robustness"],
                    }
                ],
            },
        )
        store.append(
            "generation",
            "generation-a",
            {
                "research_run_id": "run-a",
                "attempt_id": "attempt-a",
                "generation": 1,
                "status": "FALLBACK",
            },
        )
    service = DashboardService(tmp_path)
    expected = service.research_evidence()
    assert expected["status"] == ("OK" if with_run else "EMPTY")
    if with_run:
        assert expected["runs"][0]["fallback_rate"] == 1
        assert expected["runs"][0]["reject_count"] == 1
        assert expected["runs"][0]["pass_rate"] == 0
    assert expected["orders_enabled"] is False
    assert expected["sealed_oos_survival"]["status"] == "NOT_MEASURED"
    assert expected["sealed_oos_survival"]["value"] is None
    output = tmp_path / "export.json"
    assert main(["research-evidence", "--state-dir", str(tmp_path), "--output", str(output)]) == 0
    assert json.loads(capsys.readouterr().out) == expected
    assert json.loads(output.read_text(encoding="utf-8")) == expected
    response = TestClient(create_app(service)).get("/api/research-evidence")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == expected
    server = create_mcp_server(state_dir=tmp_path, project_root=tmp_path)
    reply = server.handle(
        {"id": 1, "method": "tools/call", "params": {"name": "get_research_evidence"}}
    )
    assert reply is not None
    mcp_payload = json.loads(reply["result"]["content"][0]["text"])
    contract = mcp_payload.pop("_contract")
    assert mcp_payload == expected
    assert contract == {
        "schema_version": 1,
        "tool": "get_research_evidence",
        "plane": "EVIDENCE_STATUS",
        "orders_enabled": False,
    }


def test_research_evidence_filter_forwarded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = {"status": "OK", "runs": [{"research_run_id": "run-a"}]}
    with patch("memory.research_evidence.research_evidence", return_value=payload) as reader:
        assert main(["research-evidence", "--state-dir", str(tmp_path), "--run-id", "run-a"]) == 0
        assert json.loads(capsys.readouterr().out) == payload
        reader.assert_called_with(tmp_path, run_id="run-a")
        assert (
            TestClient(create_app(DashboardService(tmp_path)))
            .get("/api/research-evidence?run_id=run-a")
            .json()
            == payload
        )
        reader.assert_called_with(tmp_path, run_id="run-a")
        server = create_mcp_server(state_dir=tmp_path, project_root=tmp_path)
        assert server._dispatch("get_research_evidence", {"research_run_id": "run-a"}) == payload
        reader.assert_called_with(tmp_path.resolve(), run_id="run-a")


def test_research_evidence_corruption_is_sanitized(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with patch(
        "memory.research_evidence.research_evidence",
        side_effect=ValueError("SECRET private source"),
    ):
        service = DashboardService(tmp_path)
        expected = service.research_evidence()
        assert expected["status"] == "INTEGRITY_ERROR"
        assert "SECRET" not in json.dumps(expected)
        assert main(["research-evidence", "--state-dir", str(tmp_path)]) == 1
        assert json.loads(capsys.readouterr().out) == expected
        response = TestClient(create_app(service)).get("/api/research-evidence")
        assert response.status_code == 503
        assert response.json() == expected
        server = create_mcp_server(state_dir=tmp_path, project_root=tmp_path)
        assert server._dispatch("get_research_evidence", {}) == expected


def test_research_evidence_mcp_rejects_invalid_filter(tmp_path: Path) -> None:
    server = create_mcp_server(state_dir=tmp_path, project_root=tmp_path)
    reply = server.handle(
        {
            "id": 1,
            "method": "tools/call",
            "params": {"name": "get_research_evidence", "arguments": {"research_run_id": 123}},
        }
    )
    assert reply is not None
    assert reply["result"]["isError"] is True


def test_research_evidence_export_error_is_sanitized(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with patch(
        "dashboard.service.DashboardService.research_evidence", return_value={"status": "EMPTY"}
    ):
        assert (
            main(["research-evidence", "--state-dir", str(tmp_path), "--output", str(tmp_path)])
            == 1
        )
    assert json.loads(capsys.readouterr().out) == {"status": "ERROR", "reason": "EXPORT_FAILED"}
