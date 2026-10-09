"""ChatGPT is an external MCP research director, not a local Codex subprocess."""

from __future__ import annotations

from pathlib import Path

import pytest

from integrations.codex_mcp_core import _tools, create_mcp_server
from memory.evidence_store import EvidenceStore
from tests.orchestration.test_evaluation_runner import _write_inputs


def _intent(parent_id: str = "runner-test") -> dict[str, object]:
    return {
        "mode": "structure",
        "parent_ids": [parent_id],
        "operations": [],
        "rationale": "Check reproducible baseline before changing parameters",
    }


def test_external_llm_tools_are_advertised_without_order_or_code_edit_access() -> None:
    advertised = {item["name"]: item for item in _tools()}
    assert "get_research_brief" in advertised
    assert "run_research_step" in advertised
    schema = advertised["run_research_step"]["inputSchema"]
    assert "intent" in schema["required"]
    assert "source_path" in schema["required"]
    assert "data_path" in schema["required"]
    assert "python_patch" not in schema["properties"]
    assert not any("order" in name or "credential" in name for name in advertised)


def test_external_llm_brief_is_read_only_and_has_bounded_provenance(tmp_path: Path) -> None:
    state = tmp_path / "state"
    server = create_mcp_server(state_dir=state, project_root=tmp_path)
    brief = server._dispatch("get_research_brief", {})
    assert isinstance(brief, dict)
    assert brief["llm_controller"] == "external_mcp_client"
    assert brief["orders_enabled"] is False
    assert brief["frontier"] == []
    assert "raw_market_rows" not in str(brief)
    assert not state.exists()


def test_chatgpt_proposed_intent_runs_without_invoking_internal_codex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from research.llm.codex_exec import CodexExecProvider

    _write_inputs(tmp_path)
    state = tmp_path / "state"
    server = create_mcp_server(state_dir=state, project_root=tmp_path)

    def forbidden_codex(*args: object, **kwargs: object) -> None:
        raise AssertionError("internal LLM provider must not be invoked")

    monkeypatch.setattr(CodexExecProvider, "from_env", forbidden_codex)
    result = server._dispatch(
        "run_research_step",
        {
            "source_path": "strategy.yaml",
            "data_path": "bars.parquet",
            "intent": _intent(),
            "method": "random",
            "count": 1,
            "seed": 9,
            "min_trades": 0,
            "min_annual_trades": 0,
            "min_qqq_cagr_delta": 0.0,
        },
    )
    assert isinstance(result, dict)
    assert result["status"] == "COMPLETED"
    assert result["orders_enabled"] is False
    assert result["llm_controller"] == "external_mcp_client"
    assert result["research_run_id"]
    events = EvidenceStore(state).events()
    assert [event["kind"] for event in events].count("run") == 1
    assert [event["kind"] for event in events].count("attempt") == 1
    assert [event["kind"] for event in events].count("end") == 1
    assert events[-1]["payload"]["status"] == "COMPLETED"
    assert (state / "llm" / "intents.jsonl").exists()


def test_chatgpt_intent_fails_closed_on_unknown_parent_or_unverified_feature(
    tmp_path: Path,
) -> None:
    _write_inputs(tmp_path)
    state = tmp_path / "state"
    server = create_mcp_server(state_dir=state, project_root=tmp_path)
    with pytest.raises(ValueError, match="parent"):
        server._dispatch(
            "run_research_step",
            {
                "source_path": "strategy.yaml",
                "data_path": "bars.parquet",
                "intent": _intent("unknown-parent"),
            },
        )
    with pytest.raises(ValueError, match="FEATURE|feature"):
        server._dispatch(
            "run_research_step",
            {
                "source_path": "strategy.yaml",
                "data_path": "bars.parquet",
                "intent": {
                    **_intent(),
                    "feature_selections": [{"alias": "unknown", "feature_id": "fake_feature"}],
                },
            },
        )
    assert EvidenceStore(state).events() == []
    assert not (state / "llm" / "intents.jsonl").exists()
