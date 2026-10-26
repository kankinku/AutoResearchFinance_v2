"""SDK state-machine steps against real Quant MCP tool calls, with FAKE model.

Tool/ledger/S7 are real local isolated code. Model is a fixture, therefore none
of these are genuine authenticated-provider generations.
"""

from __future__ import annotations

from pathlib import Path

from application.sdk_quant_generation_control import run_sdk_generation_loop
from tests.integrations.test_academic_mcp_sessions import _setup
from tests.research.test_autonomous_academic_cycle import ScriptedResearcher


class QuantReader:
    def __init__(self, server):
        self.server = server

    def get(self, args: dict) -> dict:
        return self.server._dispatch("get_algorithm_research", args)


class FakeModelUsingRealQuantTools:
    fixture_only = True

    def __init__(self, reader: QuantReader):
        self.reader = reader
        self.model = ScriptedResearcher()
        self.count = 0

    def dispatch(self, request: dict) -> dict:
        self.count += 1
        current = self.reader.get({"session_id": request["session_id"]})
        assert current["checkpoint_token"] == request["checkpoint_token"]
        assert current["checkpoint_phase"] == request["checkpoint_phase"]
        if current["checkpoint_phase"] == "AWAITING_PLAN":
            assert request["context_hash"] is None
            assert request["model_context_fingerprint_is_local"] is True
        else:
            assert request["context_hash"] == current["model_context"]["context_hash"]
            assert request["model_context_fingerprint_is_local"] is False
        proposal = self.model.propose(current["model_context"])
        kind = (
            "submit_algorithm_plan"
            if request["checkpoint_phase"] == "AWAITING_PLAN"
            else "submit_algorithm_diagnosis"
        )
        key = "plan" if kind.endswith("plan") else "diagnosis"
        return self.reader.server._dispatch(
            kind,
            {
                "session_id": request["session_id"],
                "checkpoint_token": request["checkpoint_token"],
                key: proposal,
            },
        )


def test_sdk_tool_loop_verifies_real_quant_mcp_s7_without_real_model(tmp_path: Path):
    server, started = _setup(tmp_path)
    reader = QuantReader(server)
    host = FakeModelUsingRealQuantTools(reader)
    sid = started["session_id"]
    state = run_sdk_generation_loop(
        reader,
        session_id=sid,
        target=1,
        host=host,
        fixture_mode=True,
        max_dispatches=2,
        lease_state_dir=tmp_path / "sdk-lease",
    )
    assert state["status"] == "TARGET_REACHED_TEST_ONLY"
    assert state["new_generations"] == 1
    assert state["model_dispatch_attempts"] == 2
    assert state["official_verified_generations"] == 0
    actual = reader.get({"session_id": sid})
    assert actual["completed_generations"] == 1
    assert actual["orders_enabled"] is False
    assert actual["independent_oos_approved"] is False
    experiment = server._dispatch(
        "evaluate_algorithm_experiments",
        {
            "session_id": sid,
            "generation": 1,
        },
    )
    assert experiment["original_generation_evidence_hash"] == actual["history"][0]["evidence_hash"]
    assert host.count == 2
    # SDK cannot invent an additional model turn for G2 after fixture ends.
    blocked = run_sdk_generation_loop(
        reader, session_id=sid, target=2, host=None, lease_state_dir=tmp_path / "sdk-lease"
    )
    assert blocked["new_generations"] == 0
    assert blocked["status"] == "BLOCKED_MODEL_HOST_DISPATCH"
