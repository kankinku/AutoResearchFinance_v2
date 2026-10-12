"""GPT-guided research checkpoints and failure-boundary tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.gpt_guided_research_service import GPTGuidedResearchService
from integrations.chatgpt_mcp_sdk import chatgpt_tools
from integrations.codex_mcp_core import create_mcp_server
from memory.evidence_store import EvidenceStore
from tests.orchestration.test_evaluation_runner import _write_inputs


def proposal() -> dict:
    return {
        "source_path": "strategy.yaml",
        "intent": {
            "mode": "structure",
            "parent_ids": ["runner-test"],
            "operations": [],
            "rationale": "External GPT decides next hypothesis",
        },
    }


def start(server: object) -> dict:
    return server._dispatch(
        "start_guided_research",
        {
            "data_path": "bars.parquet",
            "generations": 2,
            "method": "grid",
            "count": 1,
            "seed": 20,
            "min_trades": 30,
            "min_annual_trades": 30,
            "min_qqq_cagr_delta": 0.1,
        },
    )


def test_guided_two_generations_with_explicit_gpt_checkpoints(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    server = create_mcp_server(state_dir=tmp_path / "state", project_root=tmp_path)
    first = start(server)
    assert first["status"] == "AWAITING_GPT" and first["generation"] == 1
    assert EvidenceStore(tmp_path / "state").events() == []

    def args(point: dict) -> dict:
        return {
            "session_id": first["session_id"],
            "checkpoint_token": point["checkpoint_token"],
            "generation": point["generation"],
            **proposal(),
        }

    after = server._dispatch("submit_guided_generation", args(first))
    assert after["status"] == "AWAITING_GPT" and after["generation"] == 2
    assert after["checkpoint_token"] != first["checkpoint_token"]
    assert after["previous_failed_gates"]
    with pytest.raises(ValueError, match="checkpoint|stale"):
        server._dispatch("submit_guided_generation", args(first))
    reopened = create_mcp_server(state_dir=tmp_path / "state", project_root=tmp_path)
    point = reopened._dispatch("get_guided_research", {"session_id": first["session_id"]})
    final = reopened._dispatch("submit_guided_generation", args(point))
    assert final["status"] == "COMPLETED" and final["completed_generations"] == 2
    assert final["checkpoint_token"] is None and final["orders_enabled"] is False
    assert final["history"][1]["previous_run_id"] == final["history"][0]["run_id"]
    runs = [e for e in EvidenceStore(tmp_path / "state").events() if e["kind"] == "run"]
    assert len(runs) == 2
    assert (
        runs[1]["payload"]["settings"]["previous_research_run_id"] == final["history"][0]["run_id"]
    )


def test_failed_preflight_does_not_consume_checkpoint(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    server = create_mcp_server(state_dir=tmp_path / "state", project_root=tmp_path)
    point = start(server)
    args = {
        "session_id": point["session_id"],
        "checkpoint_token": point["checkpoint_token"],
        "generation": 1,
        **proposal(),
    }
    with pytest.raises(ValueError):
        server._dispatch(
            "submit_guided_generation",
            {**args, "intent": {**args["intent"], "parent_ids": ["invalid-parent"]}},
        )
    current = server._dispatch("get_guided_research", {"session_id": point["session_id"]})
    assert current["checkpoint_token"] == point["checkpoint_token"]
    assert EvidenceStore(tmp_path / "state").events() == []


def test_dataset_changed_and_stale_checkpoint_rejected(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    service = GPTGuidedResearchService(project_root=tmp_path, state_dir=tmp_path / "state")
    point = service.start(
        {"data_path": "bars.parquet", "generations": 2, "method": "grid", "count": 1, "seed": 3}
    )
    args = {
        "session_id": point["session_id"],
        "checkpoint_token": point["checkpoint_token"],
        "generation": 1,
        **proposal(),
    }
    with pytest.raises(ValueError, match="checkpoint"):
        service.submit({**args, "checkpoint_token": "f" * 32})
    with (tmp_path / "bars.parquet").open("ab") as handle:
        handle.write(b"extra")
    with pytest.raises(ValueError, match="dataset|changed"):
        service.submit(args)
    assert service.get(point["session_id"])["completed_generations"] == 0
    assert EvidenceStore(tmp_path / "state").events() == []


def test_guided_tools_are_explicit() -> None:
    tools = {item["name"]: item for item in chatgpt_tools()}
    assert {
        "start_guided_research",
        "get_guided_research",
        "submit_guided_generation",
    } <= tools.keys()
    assert {"checkpoint_token", "intent", "source_path"} <= set(
        tools["submit_guided_generation"]["inputSchema"]["required"]
    )


def test_policy_gates_are_not_relaxed_when_starting_guided_session(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    service = GPTGuidedResearchService(project_root=tmp_path, state_dir=tmp_path / "state")
    for field, value in (("min_trades", 0), ("min_annual_trades", 0), ("min_qqq_cagr_delta", 0.0)):
        with pytest.raises(ValueError, match="must be|relaxed"):
            service.start({"data_path": "bars.parquet", "generations": 2, field: value})
    with pytest.raises(ValueError, match="generations"):
        service.start({"data_path": "bars.parquet", "generations": True})


def test_evaluation_failure_fails_closed_without_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from application.evaluation_service import EvaluationService

    _write_inputs(tmp_path)
    service = GPTGuidedResearchService(project_root=tmp_path, state_dir=tmp_path / "state")
    point = service.start({"data_path": "bars.parquet", "generations": 2})

    def interrupted(*args: object, **kwargs: object) -> None:
        raise RuntimeError("test-injected evaluator outage")

    monkeypatch.setattr(EvaluationService, "run", interrupted)
    kwargs = {
        "session_id": point["session_id"],
        "checkpoint_token": point["checkpoint_token"],
        "generation": 1,
        **proposal(),
    }
    with pytest.raises(RuntimeError, match="outage"):
        service.submit(kwargs)
    assert service.get(point["session_id"])["status"] == "INTERRUPTED"
    with pytest.raises(ValueError, match="checkpoint"):
        service.submit(kwargs)
