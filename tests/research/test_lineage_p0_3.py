"""P0-3: replay exact S7 children and preserve experimental lineage without orders."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from core.integrity.hashes import content_hash
from research.llm.lineage_replay import LineageReplayError, verified_child_successor
from tests.integrations.test_academic_mcp_sessions import _setup
from tests.research.test_autonomous_academic_cycle import ScriptedResearcher

ROOT = Path("/shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory")
SID = "2ba41aaeacd547319cfbf7e6f266ad11"


def _actual_source(generation: int = 29):
    if not (ROOT / "state/moon-http/research/academic-gpt-checkpoints/gateway.sqlite").exists():
        pytest.skip("historical Moon evidence not installed in this runtime")
    service = AcademicMCPCheckpointService(
        project_root=ROOT,
        state_dir=ROOT / "state/moon-http/research",
    )
    with service._connect() as db:
        row, catalog, market, state = service._state(db, SID)
        original = state["history"][generation - 1]
        stored = service._stored_experiment(db, SID, generation)
    assert stored is not None
    proposal = original["experiments"][0]
    continuation = {
        "mode": "structure",
        "parent_ids": proposal["proposed_intent"]["parent_ids"],
        "operations": [
            {
                "op": "ADD_RULE",
                "path": "entry.conditions",
                "condition": {
                    "left": "time_series_momentum",
                    "op": "greater_than",
                    "value": 0.5,
                    "enabled": True,
                },
            }
        ],
        "rationale": "Replay a measured S7 child, then vary one verified entry rule.",
    }
    return catalog, market, original, stored, proposal, continuation


def test_real_child_to_grandchild_exact_reproduction():
    catalog, market, original, stored, proposal, continuation = _actual_source()
    result = verified_child_successor(
        catalog,
        market,
        original,
        stored,
        hypothesis_id=proposal["hypothesis_id"],
        expected_child_strategy_hash=proposal["proposal_child_hash"],
        continuation_intent=continuation,
    )
    assert result["child_total_return"] == pytest.approx(0.4444, abs=0.0002)
    assert result["successor_total_return"] == pytest.approx(0.4895, abs=0.0002)
    assert result["reproduced_child_strategy_hash"] == proposal["proposal_child_hash"]
    assert result["successor_strategy_hash"] != proposal["proposal_child_hash"]
    assert result["child_fills"] >= 60
    assert result["generation_counter_incremented"] is False
    assert result["independent_oos_approved"] is False
    assert result["broker_executable"] is False


def test_changed_child_hash_or_parent_economics_fails_before_continuation():
    catalog, market, original, stored, proposal, continuation = _actual_source()
    with pytest.raises(LineageReplayError, match="child identity"):
        verified_child_successor(
            catalog,
            market,
            original,
            stored,
            hypothesis_id=proposal["hypothesis_id"],
            expected_child_strategy_hash="f" * 64,
            continuation_intent=continuation,
        )
    forged = deepcopy(stored)
    forged["report"]["experiments"][0]["child_final_equity"] += 50000
    with pytest.raises(LineageReplayError, match="integrity"):
        verified_child_successor(
            catalog,
            market,
            original,
            forged,
            hypothesis_id=proposal["hypothesis_id"],
            expected_child_strategy_hash=proposal["proposal_child_hash"],
            continuation_intent=continuation,
        )


def test_gateway_preserves_checkpoint_and_adds_idempotent_lineage(tmp_path, monkeypatch):
    server, started = _setup(tmp_path)
    writer = ScriptedResearcher()
    staged = server._dispatch(
        "submit_algorithm_plan",
        {
            "session_id": started["session_id"],
            "checkpoint_token": started["checkpoint_token"],
            "plan": writer.propose(started["model_context"]),
        },
    )
    final = server._dispatch(
        "submit_algorithm_diagnosis",
        {
            "session_id": started["session_id"],
            "checkpoint_token": staged["checkpoint_token"],
            "diagnosis": writer.propose(staged["model_context"]),
        },
    )
    assert final["completed_generations"] == 1
    item = final["history"][0]["experiments"][0]
    request = {
        "session_id": started["session_id"],
        "generation": 1,
        "checkpoint_token": final["checkpoint_token"],
        "hypothesis_id": item["hypothesis_id"],
        "child_strategy_hash": item["proposal_child_hash"],
        "continuation_intent": item["proposed_intent"],
    }
    body = {
        "source_generation": 1,
        "source_evidence_hash": final["history"][0]["evidence_hash"],
        "hypothesis_id": item["hypothesis_id"],
        "reproduced_child_strategy_hash": item["proposal_child_hash"],
        "successor_strategy_hash": "f" * 64,
        "successor_final_equity": 13000.0,
        "successor_total_return": 0.3,
        "successor_max_drawdown": 0.12,
        "improvement_vs_child_pp": 10.0,
        "continuation_intent": item["proposed_intent"],
        "generation_counter_incremented": False,
        "independent_oos_approved": False,
        "execution_delta": {"event_samples": ({"kind": "ADDED"},)},
    }
    fake = {**body, "report_hash": content_hash(body)}
    import json
    normalized = json.loads(json.dumps(fake))
    import application.academic_checkpoint_service as gateway

    monkeypatch.setattr(gateway, "verified_child_successor", lambda *a, **k: fake)
    persisted = server._dispatch("evaluate_algorithm_experiments", request)
    assert persisted == normalized
    monkeypatch.setattr(
        gateway,
        "verified_child_successor",
        lambda *a, **k: pytest.fail("idempotent replay re-executed"),
    )
    assert server._dispatch("evaluate_algorithm_experiments", request) == persisted
    state = server._dispatch(
        "get_algorithm_research",
        {
            "session_id": started["session_id"],
        },
    )
    assert state["completed_generations"] == 1
    assert state["checkpoint_token"] == final["checkpoint_token"]
    assert len(state["model_context"]["verified_successor_lineages"]) == 1
    assert (
        state["model_context"]["verified_successor_lineages"][0]["successor_strategy_hash"]
        == "f" * 64
    )
    with pytest.raises(ValueError, match="checkpoint"):
        server._dispatch(
            "evaluate_algorithm_experiments",
            {
                **request,
                "checkpoint_token": "0" * 32,
            },
        )


def test_existing_s7_tool_contract_is_backward_compatible():
    from integrations.chatgpt_mcp_sdk import chatgpt_tools

    tools = {x["name"]: x for x in chatgpt_tools()}
    assert len(tools) == 32
    schema = tools["evaluate_algorithm_experiments"]["inputSchema"]
    assert schema["required"] == ["session_id", "generation"]
    assert set(
        ("hypothesis_id", "child_strategy_hash", "checkpoint_token", "continuation_intent")
    ) <= set(schema["properties"])
    assert schema["additionalProperties"] is False
