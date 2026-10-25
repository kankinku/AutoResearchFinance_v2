"""D3: signed externally authored MCP submission, never a GPT simulator.

Offline signatures below are FIXTURE ONLY and do not establish model use.
"""

import asyncio
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from integrations.python_mcp_academic_handoff import (
    AcademicSubmissionRejected,
    SignedAcademicHandoff,
)
from integrations.python_mcp_direct import QuantMCPDirectClient, QuantMCPSettings
from research.llm.model_provenance_v1 import ModelCaptureError
from tests.integrations.test_quant_p4_model_capture import _service, _signed
from tests.research.test_autonomous_academic_cycle import ScriptedResearcher


def _pub(secret: Ed25519PrivateKey) -> str:
    return secret.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ).hex()


def _client(root: Path, sid: str, key: str | None) -> QuantMCPDirectClient:
    return QuantMCPDirectClient(
        QuantMCPSettings(
            project_root=root,
            state_dir=root / "state" / "python-mcp",
            scope_session=sid,
            surface="chatgpt_academic",
            capture_public_key_hex=key,
        )
    )


def test_d3_fails_closed_without_explicit_capture_public_key(tmp_path: Path):
    root = tmp_path / "fork"
    root.mkdir()
    client = _client(root, "f" * 32, None)
    with pytest.raises(AcademicSubmissionRejected, match="trusted.*capture"):
        SignedAcademicHandoff(client)
    assert not (root / "state").exists()


@pytest.mark.parametrize("bad_key", ["", "0" * 32, "gg" * 32, "a" * 65])
def test_d3_rejects_invalid_collector_key(tmp_path: Path, bad_key: str):
    root = tmp_path / "fork"
    root.mkdir()
    with pytest.raises(ValueError, match="capture public key"):
        _client(root, "f" * 32, bad_key)


def test_d3_rejects_wrong_mcp_surface_and_session(tmp_path: Path):
    root = tmp_path / "fork"
    root.mkdir()
    secret = Ed25519PrivateKey.generate()
    with pytest.raises(AcademicSubmissionRejected, match="academic"):
        SignedAcademicHandoff(
            QuantMCPDirectClient(
                QuantMCPSettings(
                    project_root=root, state_dir=root / "state" / "python-mcp",
                    surface="codex", scope_session="f" * 32,
                    capture_public_key_hex=None,
                )
            )
        )
    h = SignedAcademicHandoff(_client(root, "f" * 32, _pub(secret)))
    with pytest.raises(ValueError, match="session mismatch"):
        asyncio.run(h.submit("e" * 32, {}, {}, checkpoint_token="f" * 32))
    assert not (root / "state").exists()


def test_d3_rejects_unsigned_before_any_mcp_process(tmp_path: Path):
    root = tmp_path / "fork"
    root.mkdir()
    secret = Ed25519PrivateKey.generate()
    h = SignedAcademicHandoff(_client(root, "a" * 32, _pub(secret)))
    with pytest.raises(AcademicSubmissionRejected, match="signed capture"):
        asyncio.run(
            h.submit(
                "a" * 32, {"algorithm": "fixture"},
                {}, checkpoint_token="f" * 32,
            )
        )
    assert not (root / "state").exists()


def test_d3_real_fork_local_mcp_rejects_tampered_capture_without_counting(
    tmp_path: Path,
):
    service, secret, _ = _service(tmp_path)
    # Service fixture uses a different state path; wrap it in a fork-local
    # scope for a real executable MCP process without touching original P5.
    root = service.root
    scoped_state = root / "state" / "python-mcp"
    from application.academic_checkpoint_service import AcademicMCPCheckpointService
    svc = AcademicMCPCheckpointService(
        project_root=root, state_dir=scoped_state,
        parent_portfolio_v2=True, generalization_parent_v1=True,
        p4_quality_gate_v1=True, p4_model_capture_v1=True,
        p4_s7_quality_v1=True, p4_capture_public_key_hex=_pub(secret),
    )
    started = svc.start({"data_path": "data/study.parquet", "generations": 1})
    h = SignedAcademicHandoff(_client(root, started["session_id"], _pub(secret)))
    plan = ScriptedResearcher().propose(started["model_context"])
    receipt = _signed(secret, started, "plan", plan)
    receipt["decision_summary"] = "TAMPERED"
    with pytest.raises((AcademicSubmissionRejected, ModelCaptureError)):
        asyncio.run(
            h.submit(
                started["session_id"], plan, receipt,
                checkpoint_token=started["checkpoint_token"],
            )
        )
    after = svc.get({"session_id": started["session_id"]})
    assert after["completed_generations"] == 0
    assert after["checkpoint_token"] == started["checkpoint_token"]
    assert after["checkpoint_phase"] == "AWAITING_PLAN"
    assert not after["orders_enabled"] and not after["independent_oos_approved"]



def test_d3_real_signed_fixture_plan_and_diagnosis_through_stdio(tmp_path: Path):
    """A *scripted fixture*, not GPT: one complete signed MCP generation."""
    service, secret, _ = _service(tmp_path)
    root = service.root
    scoped = root / "state" / "python-mcp"
    from application.academic_checkpoint_service import AcademicMCPCheckpointService

    svc = AcademicMCPCheckpointService(
        project_root=root, state_dir=scoped,
        parent_portfolio_v2=True, generalization_parent_v1=True,
        p4_quality_gate_v1=True, p4_s7_quality_v1=True,
        p4_model_capture_v1=True,
        p4_capture_public_key_hex=_pub(secret),
    )
    started = svc.start({"data_path": "data/study.parquet", "generations": 1})
    handoff = SignedAcademicHandoff(
        _client(root, started["session_id"], _pub(secret))
    )
    scripted = ScriptedResearcher()
    plan = scripted.propose(started["model_context"])
    signed = _signed(secret, started, "plan", plan)
    stage = asyncio.run(
        handoff.submit(
            started["session_id"], plan, signed,
            checkpoint_token=started["checkpoint_token"],
            require_execution_change=False,
            require_trade_activity=True,
        )
    )
    assert stage["checkpoint_phase"] == "AWAITING_DIAGNOSIS"
    assert stage["completed_generations"] == 0
    pending = svc.get({"session_id": started["session_id"]})
    assert pending["model_capture_audit"]["captured_steps"] == 1
    diagnosis = scripted.propose(pending["model_context"])
    # The default deterministic fixture is a known S7 no-op. Use the
    # previously validated S7 position-sizing control, still FIXTURE ONLY.
    h = dict(diagnosis["hypotheses"][0])
    h["hypothesis_id"] = "d3_fixture_position_size_70"
    h["expected_metric"] = "max_drawdown"
    h["predicted_direction"] = "DECREASE"
    h["test_design"] = "PARAMETER"
    h["next_intent"] = {
        **h["next_intent"],
        "mode": "parameter",
        "operations": [{
            "op": "CHANGE_POSITION_SIZE",
            "path": "risk.position_size_pct",
            "value": 70.0,
        }],
    }
    diagnosis["hypotheses"] = [h]
    signed_diag = _signed(secret, pending, "diagnosis", diagnosis)
    completed = asyncio.run(
        handoff.submit(
            started["session_id"], diagnosis, signed_diag,
            checkpoint_token=pending["checkpoint_token"],
        )
    )
    assert completed["completed_generations"] == 1
    assert completed["checkpoint_phase"] == "COMPLETED"
    assert completed["provider_invocation_verified"] is False
    assert svc.get({"session_id": started["session_id"]})[
        "model_capture_audit"
    ]["captured_steps"] == 2
    assert not completed["orders_enabled"] and not completed["independent_oos_approved"]
