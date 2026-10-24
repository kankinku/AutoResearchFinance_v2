"""P4-3: rejection is explainable, immutable and does not count a generation."""
from pathlib import Path

import pytest

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from core.data.parquet import ParquetDataProvider
from research.llm.s7_quality_gate_p4_3 import P4S7Rejected
from tests.research.test_academic_algorithm_plan import _market
from tests.research.test_autonomous_academic_cycle import ScriptedResearcher


def _svc(tmp_path: Path):
    root = tmp_path / "project"
    (root / "data").mkdir(parents=True)
    ParquetDataProvider.write(root / "data" / "study.parquet", _market())
    return AcademicMCPCheckpointService(
        project_root=root, state_dir=tmp_path / "isolated_state",
        parent_portfolio_v2=True, generalization_parent_v1=True,
        p4_quality_gate_v1=True, p4_s7_quality_v1=True,
    )


def test_actual_noop_rejected_without_spending_generation_and_revisable(tmp_path: Path):
    service = _svc(tmp_path)
    first = service.start({"data_path": "data/study.parquet", "generations": 1})
    plan = ScriptedResearcher().propose(first["model_context"])
    staged = service.submit_plan({
        "session_id": first["session_id"], "checkpoint_token": first["checkpoint_token"],
        "plan": plan,
    })
    trial = ScriptedResearcher()
    trial.seen = 1
    diagnosis = trial.propose(staged["model_context"])
    payload = {
        "session_id": first["session_id"], "checkpoint_token": staged["checkpoint_token"],
        "diagnosis": diagnosis,
    }
    with pytest.raises(P4S7Rejected, match="NO_OBSERVED_EFFECT"):
        service.submit_diagnosis(payload)
    state = service.get({"session_id": first["session_id"]})
    assert state["completed_generations"] == 0
    assert state["checkpoint_token"] == staged["checkpoint_token"]
    assert state["checkpoint_phase"] == "AWAITING_DIAGNOSIS"
    feedback = state["model_context"]["p4_s7_rejection_feedback"]
    assert feedback["rejection_count"] == 1
    assert feedback["recent_rejections"][0]["reasons"][0]["reason"] == "NO_OBSERVED_EFFECT"
    with pytest.raises(P4S7Rejected):
        service.submit_diagnosis(payload)
    assert service.get({"session_id": first["session_id"]})["model_context"][
        "p4_s7_rejection_feedback"]["rejection_count"] == 1

    repaired = dict(diagnosis)
    hypothesis = dict(repaired["hypotheses"][0])
    hypothesis["hypothesis_id"] = "s7_sizing_accepted"
    hypothesis["expected_metric"] = "max_drawdown"
    hypothesis["predicted_direction"] = "DECREASE"
    hypothesis["test_design"] = "PARAMETER"
    hypothesis["next_intent"] = {
        **hypothesis["next_intent"], "mode": "parameter",
        "operations": [{"op": "CHANGE_POSITION_SIZE", "path": "risk.position_size_pct",
                        "value": 70.0}],
    }
    repaired["hypotheses"] = [hypothesis]
    completed = service.submit_diagnosis({**payload, "diagnosis": repaired})
    assert completed["completed_generations"] == 1
    assert completed["checkpoint_phase"] == "COMPLETED"
    assert completed["p4_s7_quality_audit"]["approved_count"] == 1
    assert completed["p4_s7_quality_audit"]["rejection_count"] == 1
    assert completed["orders_enabled"] is False


def test_legacy_session_cannot_be_retroactively_enrolled(tmp_path: Path):
    service = _svc(tmp_path)
    legacy = AcademicMCPCheckpointService(
        project_root=service.root, state_dir=tmp_path / "isolated_state",
    )
    started = legacy.start({"data_path": "data/study.parquet", "generations": 1})
    with pytest.raises(ValueError, match="original P4-3 enrollment"):
        service.get({"session_id": started["session_id"]})
    with pytest.raises(ValueError, match="P4-1"):
        AcademicMCPCheckpointService(
            project_root=service.root, state_dir=tmp_path / "isolated_state",
            p4_s7_quality_v1=True,
        )


def test_quality_sidecar_tamper_and_opt_out_are_fail_closed(tmp_path: Path):
    service = _svc(tmp_path)
    started = service.start({"data_path": "data/study.parquet", "generations": 1})
    downgraded = AcademicMCPCheckpointService(
        project_root=service.root, state_dir=tmp_path / "isolated_state",
        parent_portfolio_v2=True, generalization_parent_v1=True,
        p4_quality_gate_v1=True,
    )
    with pytest.raises(ValueError, match="cannot disable"):
        downgraded.get({"session_id": started["session_id"]})
    with service._connect() as db:
        db.execute(
            "UPDATE p4_s7_enrollments SET policy='FAKE' WHERE session_id=?",
            (started["session_id"],),
        )
    with pytest.raises(ValueError, match="original P4-3 enrollment"):
        service.get({"session_id": started["session_id"]})


def test_p43_gateway_explicit_enrollment_is_scoped(tmp_path: Path, monkeypatch):
    from integrations.codex_mcp_core import CodexMCPServer

    monkeypatch.setenv("QUANT_MCP_GENERALIZATION_PARENT_V1_NEW_SESSION", "1")
    monkeypatch.setenv("QUANT_MCP_P4_QUALITY_NEW_SESSION", "1")
    monkeypatch.setenv("QUANT_MCP_P4_S7_QUALITY_NEW_SESSION", "1")
    seen = []

    class Stub:
        def __init__(self, **kwargs):
            seen.append(kwargs)

        def start(self, args):
            return {"session_id": "a"*32}

        def get(self, args):
            return args

    monkeypatch.setattr("integrations.codex_mcp_core.AcademicMCPCheckpointService", Stub)
    server = CodexMCPServer(state_dir=tmp_path / "state", project_root=tmp_path)
    server._dispatch("start_algorithm_research", {"generations": 1})
    assert seen[-1]["p4_s7_quality_v1"] is True
    monkeypatch.setenv("QUANT_MCP_GENERALIZATION_PARENT_V1_NEW_SESSION", "0")
    monkeypatch.setenv("QUANT_MCP_P4_QUALITY_NEW_SESSION", "0")
    monkeypatch.setenv("QUANT_MCP_P4_S7_QUALITY_NEW_SESSION", "0")
    monkeypatch.setenv("QUANT_MCP_P4_S7_QUALITY_SESSION_ID", "b"*32)
    monkeypatch.setenv("QUANT_MCP_P4_QUALITY_SESSION_ID", "b"*32)
    server = CodexMCPServer(state_dir=tmp_path / "state", project_root=tmp_path)
    server._dispatch("get_algorithm_research", {"session_id": "b"*32})
    assert seen[-1]["p4_s7_quality_v1"] is True
    server._dispatch("get_algorithm_research", {"session_id": "c"*32})
    assert seen[-1]["p4_s7_quality_v1"] is False
    monkeypatch.setenv("QUANT_MCP_P4_QUALITY_SESSION_ID", "c"*32)
    with pytest.raises(ValueError, match="must match"):
        CodexMCPServer(state_dir=tmp_path / "state", project_root=tmp_path)
