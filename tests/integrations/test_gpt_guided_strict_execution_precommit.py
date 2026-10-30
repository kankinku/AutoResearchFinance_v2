"""Strict guided generations must not count no-op IR / zero-fill results."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.gpt_guided_research_service import GPTGuidedResearchService
from integrations.chatgpt_mcp_sdk import chatgpt_tools
from memory.evidence_store import EvidenceStore
from tests.orchestration.test_evaluation_runner import _write_inputs


def _setup(tmp_path: Path):
    _write_inputs(tmp_path)
    service = GPTGuidedResearchService(project_root=tmp_path, state_dir=tmp_path / "state")
    session = service.start(
        {
            "data_path": "bars.parquet",
            "generations": 1,
            "method": "random",
            "count": 1,
            "require_execution_change": True,
        }
    )
    return service, session


def _submit(session: dict, operations: list[dict], *, source="strategy.yaml"):
    return {
        "session_id": session["session_id"],
        "checkpoint_token": session["checkpoint_token"],
        "generation": 1,
        "source_path": source,
        "intent": {
            "mode": "mixed",
            "parent_ids": ["runner-test"],
            "operations": operations,
            "rationale": "strict costed unchanged-fill review",
        },
    }


@pytest.mark.parametrize(
    ("op", "code"),
    [
        (
            {
                "op": "ADD_REGIME_FILTER",
                "path": "regime_filters",
                "condition": {"enabled": True, "op": "greater_than", "left": "close", "value": 0},
            },
            "STRICT_EXECUTION_UNCHANGED",
        ),
        (
            {
                "op": "ADD_REGIME_FILTER",
                "path": "regime_filters",
                "condition": {
                    "enabled": True,
                    "op": "greater_than",
                    "left": "close",
                    "value": 100000,
                },
            },
            "STRICT_EXECUTION_NO_TRADES",
        ),
    ],
)
def test_ineffective_indicator_filter_never_spends_generation_or_logs_evidence(
    tmp_path: Path,
    op: dict,
    code: str,
):
    service, point = _setup(tmp_path)
    assert point["require_execution_change"] is True
    with pytest.raises(ValueError, match=code):
        service.submit(_submit(point, [op]))
    after = service.get(point["session_id"])
    assert after["completed_generations"] == 0
    assert after["checkpoint_token"] == point["checkpoint_token"]
    assert after["status"] == "AWAITING_GPT"
    assert EvidenceStore(tmp_path / "state").events() == []


def test_changed_execution_is_counted_after_strict_rejection(
    tmp_path: Path,
):
    service, point = _setup(tmp_path)
    with pytest.raises(ValueError, match="STRICT_EXECUTION_UNCHANGED"):
        service.submit(
            _submit(
                point,
                [
                    {
                        "op": "ADD_REGIME_FILTER",
                        "path": "regime_filters",
                        "condition": {"op": "greater_than", "left": "close", "value": 0},
                    }
                ],
            )
        )
    current = service.get(point["session_id"])
    changed = {
        "op": "REPLACE_RULE",
        "path": "entry.conditions.0",
        "condition": {"op": "greater_than", "left": "close", "value": 102},
    }
    final = service.submit(_submit(current, [changed]))
    assert final["status"] == "COMPLETED"
    assert final["completed_generations"] == 1
    assert final["checkpoint_token"] is None
    assert (
        len([x for x in EvidenceStore(tmp_path / "state").events() if x["kind"] == "attempt"]) == 1
    )


def test_strict_option_pinned_only_at_session_start(tmp_path: Path):
    service, point = _setup(tmp_path)
    with pytest.raises(ValueError, match="unknown guided session arguments|boolean"):
        service.start(
            {"data_path": "bars.parquet", "generations": 1, "require_execution_change": "true"}
        )
    with pytest.raises(ValueError, match="cannot override"):
        service.submit({**_submit(point, []), "require_execution_change": False})
    schema = {item["name"]: item for item in chatgpt_tools()}
    props = schema["start_guided_research"]["inputSchema"]["properties"]
    assert props["require_execution_change"]["type"] == "boolean"
    assert (
        "require_execution_change"
        not in schema["submit_guided_generation"]["inputSchema"]["properties"]
    )


def test_legacy_sessions_keep_default_behavior(tmp_path: Path):
    _write_inputs(tmp_path)
    service = GPTGuidedResearchService(project_root=tmp_path, state_dir=tmp_path / "state")
    point = service.start({"data_path": "bars.parquet", "generations": 1})
    assert point["require_execution_change"] is False
    final = service.submit(_submit(point, []))
    assert final["completed_generations"] == 1
