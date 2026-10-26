"""Real local Quant MCP response contract, not a simulated SDK-only snapshot."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from application.sdk_quant_generation_control import (
    UnsafeCheckpoint,
    analyze_checkpoint,
    verify_diagnosis_acceptance,
)
from tests.integrations.test_academic_mcp_sessions import _setup
from tests.research.test_autonomous_academic_cycle import ScriptedResearcher


def _accepted(tmp_path: Path):
    server, started = _setup(tmp_path)
    model = ScriptedResearcher()
    sid = started["session_id"]
    staged = server._dispatch(
        "submit_algorithm_plan",
        {
            "session_id": sid,
            "checkpoint_token": started["checkpoint_token"],
            "plan": model.propose(started["model_context"]),
        },
    )
    result = server._dispatch(
        "submit_algorithm_diagnosis",
        {
            "session_id": sid,
            "checkpoint_token": staged["checkpoint_token"],
            "diagnosis": model.propose(staged["model_context"]),
        },
    )
    return server, started, staged, result


def test_sdk_accepts_authentic_quant_plan_context_without_context_hash(tmp_path: Path):
    server, started = _setup(tmp_path)
    assert "context_hash" not in started["model_context"]
    parsed = analyze_checkpoint(started, expected_session=started["session_id"])
    assert parsed["completed"] == 0
    assert parsed["source_context_hash"] is None
    assert parsed["context_hash"]
    assert parsed["context_fingerprint_is_local"] is True


def test_sdk_handles_real_diagnosis_and_separate_s7_receipt(tmp_path: Path):
    server, started, staged, reply = _accepted(tmp_path)
    sid = started["session_id"]
    parsed = analyze_checkpoint(staged, expected_session=sid)
    assert parsed["source_context_hash"] == staged["model_context"]["context_hash"]
    committed = server._dispatch("get_algorithm_research", {"session_id": sid})
    assert committed["final_report"] is None  # genuine nonterminal Quant response
    checked = verify_diagnosis_acceptance(reply, committed, prior_completed=0)
    assert checked["generation"] == 1
    assert checked["s7_record_hash"] == reply["latest_controlled_experiments"]["record_hash"]
    assert checked["independent_provider_attested"] is False


def test_sdk_detects_s7_receipt_mutation_and_wrong_target(tmp_path: Path):
    server, started, _, reply = _accepted(tmp_path)
    committed = server._dispatch("get_algorithm_research", {"session_id": started["session_id"]})
    forged = deepcopy(reply)
    forged["latest_controlled_experiments"]["record_hash"] = "0" * 64
    with pytest.raises(UnsafeCheckpoint, match="S7"):
        verify_diagnosis_acceptance(forged, committed, prior_completed=0)
    forged = deepcopy(reply)
    forged["latest_controlled_experiments"]["original_generation_evidence_hash"] = "f" * 64
    with pytest.raises(UnsafeCheckpoint, match="S7"):
        verify_diagnosis_acceptance(forged, committed, prior_completed=0)
    with pytest.raises(UnsafeCheckpoint, match="one new generation"):
        verify_diagnosis_acceptance(reply, committed, prior_completed=1)


def test_sdk_detects_history_chain_rewrite(tmp_path: Path):
    server, started, _, reply = _accepted(tmp_path)
    sid = started["session_id"]
    current = server._dispatch("get_algorithm_research", {"session_id": sid})
    assert analyze_checkpoint(current, expected_session=sid)["completed"] == 1
    altered = deepcopy(current)
    altered["history"][0]["previous_evidence_hash"] = "e" * 64
    with pytest.raises(UnsafeCheckpoint, match="chain"):
        analyze_checkpoint(altered, expected_session=sid)
