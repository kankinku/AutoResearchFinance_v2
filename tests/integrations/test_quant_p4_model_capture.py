"""P4-2 signed caller-capture and checkpoint chain in a real isolated session."""
import base64
from datetime import datetime, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from core.data.parquet import ParquetDataProvider
from foundation.hashes import canonical_bytes, content_hash
from research.llm.model_provenance_v1 import SCOPE, ModelCaptureError
from tests.research.test_academic_algorithm_plan import _market
from tests.research.test_autonomous_academic_cycle import ScriptedResearcher


def _signed(secret, checkpoint, phase, response):
    body = {
        "schema": "p4-external-model-capture-v1",
        "session_id": checkpoint["session_id"],
        "generation": checkpoint["completed_generations"] + 1,
        "phase": phase,
        "provider": "fixture-provider-unverified",
        "model": "fixture-model",
        "collector_id": "fixture-external-signer",
        "invocation_id": f"fixture-{phase}-{checkpoint['completed_generations'] + 1}",
        "prompt_hash": "a"*64,
        "response_hash": content_hash(response),
        "checkpoint_context_hash": checkpoint["model_capture_context_hash"],
        "checkpoint_token_hash": content_hash(checkpoint["checkpoint_token"]),
        "prior_receipt_hash": checkpoint["model_capture_audit"]["chain_head"],
        "decision_log_hash": "b"*64,
        "decision_summary": "Fixture-only: change the technical entry confirmation.",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "claim_scope": SCOPE,
    }
    return {**body, "signature_b64": base64.b64encode(
        secret.sign(canonical_bytes(body))
    ).decode()}


def _service(tmp_path):
    root = tmp_path / "project"
    (root / "data").mkdir(parents=True)
    ParquetDataProvider.write(root / "data" / "study.parquet", _market())
    secret = Ed25519PrivateKey.generate()
    public = secret.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )
    service = AcademicMCPCheckpointService(
        project_root=root, state_dir=tmp_path / "isolated_state",
        parent_portfolio_v2=True, generalization_parent_v1=True,
        p4_quality_gate_v1=True, p4_model_capture_v1=True,
        p4_capture_public_key_hex=public.hex(),
    )
    return service, secret, public


def test_p4_2_real_plan_diagnosis_capture_and_replay(tmp_path: Path):
    svc, secret, public = _service(tmp_path)
    first = svc.start({"data_path": "data/study.parquet", "generations": 1})
    assert first["model_capture_audit"]["captured_steps"] == 0
    # Disabling the scoped provenance flag after enrollment must NOT let
    # a caller bypass the signed-plan/diagnosis contract.
    downgraded = AcademicMCPCheckpointService(
        project_root=svc.root, state_dir=tmp_path / "isolated_state",
        parent_portfolio_v2=True, generalization_parent_v1=True,
        p4_quality_gate_v1=True,
    )
    with pytest.raises(ModelCaptureError, match="requires pinned"):
        downgraded.get({"session_id": first["session_id"]})
    plan = ScriptedResearcher().propose(first["model_context"])
    unsigned = {"session_id": first["session_id"],
                "checkpoint_token": first["checkpoint_token"], "plan": plan}
    with pytest.raises(ModelCaptureError):
        svc.submit_plan(unsigned)
    assert svc.get({"session_id": first["session_id"]})["checkpoint_phase"] == "AWAITING_PLAN"
    receipt = _signed(secret, first, "plan", plan)
    staged = svc.submit_plan({**unsigned, "model_capture": receipt})
    assert staged["model_capture_audit"]["captured_steps"] == 1
    assert staged["checkpoint_phase"] == "AWAITING_DIAGNOSIS"
    assert staged["model_capture_audit"]["provider_signed_receipt_verified"] is False
    assert svc.submit_plan({**unsigned, "model_capture": receipt}) == staged
    with pytest.raises(ModelCaptureError):
        svc.submit_plan({**unsigned, "model_capture": {**receipt, "decision_summary": "bad"}})
    diagnosis = ScriptedResearcher()
    diagnosis.seen = 1
    response = diagnosis.propose(staged["model_context"])
    diagnosis_args = {
        "session_id": first["session_id"],
        "checkpoint_token": staged["checkpoint_token"], "diagnosis": response,
    }
    with pytest.raises(ModelCaptureError):
        svc.submit_diagnosis(diagnosis_args)
    second_receipt = _signed(secret, staged, "diagnosis", response)
    completed = svc.submit_diagnosis({**diagnosis_args, "model_capture": second_receipt})
    assert completed["completed_generations"] == 1
    assert completed["checkpoint_phase"] == "COMPLETED"
    assert completed["model_capture_audit"]["captured_steps"] == 2
    assert completed["model_capture_audit"]["independent_model_invocation_verified"] is False
    assert not completed["orders_enabled"]
    assert completed["model_capture_audit"] == svc.get({"session_id": first["session_id"]})[
        "model_capture_audit"]
    assert svc.submit_diagnosis({**diagnosis_args, "model_capture": second_receipt}) == completed
    with svc._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM model_capture_receipts").fetchone()[0] == 2
        db.execute("UPDATE model_capture_receipts SET record_json='{}' WHERE phase_order=0")
    with pytest.raises(ModelCaptureError):
        svc.get({"session_id": first["session_id"]})
    with pytest.raises(ModelCaptureError):
        svc2 = AcademicMCPCheckpointService(
            project_root=svc.root, state_dir=tmp_path / "isolated_state",
            parent_portfolio_v2=True, generalization_parent_v1=True,
            p4_quality_gate_v1=True, p4_model_capture_v1=True,
            p4_capture_public_key_hex=("f"*64),
        )
        svc2.get({"session_id": first["session_id"]})


def test_unenrolled_legacy_session_cannot_gain_posthoc_capture(tmp_path: Path):
    service, _, public = _service(tmp_path)
    legacy = AcademicMCPCheckpointService(
        project_root=service.root, state_dir=tmp_path / "isolated_state",
    )
    started = legacy.start({"data_path": "data/study.parquet", "generations": 1})
    with pytest.raises(ModelCaptureError, match="lacks original"):
        service.get({"session_id": started["session_id"]})
    with pytest.raises(ModelCaptureError, match="require explicit"):
        legacy.submit_plan({"session_id": started["session_id"],
                            "checkpoint_token": started["checkpoint_token"],
                            "plan": {}, "model_capture": {}})
    with pytest.raises(ValueError, match="requires P4-1"):
        AcademicMCPCheckpointService(
            project_root=service.root, state_dir=tmp_path / "isolated_state",
            p4_model_capture_v1=True, p4_capture_public_key_hex=public.hex(),
        )


def test_chatgpt_mcp_schema_exposes_optional_capture_without_changing_legacy_requirements():
    from integrations.chatgpt_mcp_sdk import chatgpt_tools
    tools = {item["name"]: item["inputSchema"] for item in chatgpt_tools()}
    for name in ("submit_algorithm_plan", "submit_algorithm_diagnosis"):
        item = tools[name]
        assert "model_capture" in item["properties"]
        assert "model_capture" not in item["required"]
        assert "signature_b64" in item["properties"]["model_capture"]["required"]
        assert item["additionalProperties"] is False


def test_p42_mcp_env_enrollment_is_strictly_scoped(tmp_path: Path, monkeypatch):
    from integrations.codex_mcp_core import CodexMCPServer

    monkeypatch.setenv("QUANT_MCP_GENERALIZATION_PARENT_V1_NEW_SESSION", "1")
    monkeypatch.setenv("QUANT_MCP_P4_QUALITY_NEW_SESSION", "1")
    monkeypatch.setenv("QUANT_MCP_P4_MODEL_CAPTURE_NEW_SESSION", "1")
    monkeypatch.setenv("QUANT_MCP_P4_CAPTURE_PUBLIC_KEY_HEX", "a"*64)
    seen = []

    class Stub:
        def __init__(self, **kwargs):
            seen.append(kwargs)

        def start(self, args):
            return {"started": args["generations"]}

        def get(self, args):
            return {"session_id": args["session_id"]}

    monkeypatch.setattr("integrations.codex_mcp_core.AcademicMCPCheckpointService", Stub)
    srv = CodexMCPServer(state_dir=tmp_path / "state", project_root=tmp_path)
    srv._dispatch("start_algorithm_research", {"generations": 1})
    assert seen[-1]["p4_model_capture_v1"] is True
    monkeypatch.setenv("QUANT_MCP_GENERALIZATION_PARENT_V1_NEW_SESSION", "0")
    monkeypatch.setenv("QUANT_MCP_P4_QUALITY_NEW_SESSION", "0")
    monkeypatch.setenv("QUANT_MCP_P4_MODEL_CAPTURE_NEW_SESSION", "0")
    monkeypatch.setenv("QUANT_MCP_P4_MODEL_CAPTURE_SESSION_ID", "b"*32)
    monkeypatch.setenv("QUANT_MCP_P4_QUALITY_SESSION_ID", "b"*32)
    srv = CodexMCPServer(state_dir=tmp_path / "state", project_root=tmp_path)
    srv._dispatch("get_algorithm_research", {"session_id": "b"*32})
    assert seen[-1]["p4_model_capture_v1"] is True
    srv._dispatch("get_algorithm_research", {"session_id": "c"*32})
    assert seen[-1]["p4_model_capture_v1"] is False
    monkeypatch.setenv("QUANT_MCP_P4_MODEL_CAPTURE_SESSION_ID", "c"*32)
    with pytest.raises(ValueError, match="sessions must match"):
        CodexMCPServer(state_dir=tmp_path / "state", project_root=tmp_path)
    monkeypatch.setenv("QUANT_MCP_P4_QUALITY_SESSION_ID", "")
    monkeypatch.setenv("QUANT_MCP_P4_CAPTURE_PUBLIC_KEY_HEX", "invalid")
    with pytest.raises(ValueError, match="public key"):
        CodexMCPServer(state_dir=tmp_path / "state", project_root=tmp_path)


def test_reconcile_crashed_counted_generation_without_capture_cannot_advance(tmp_path: Path):
    service, secret, _ = _service(tmp_path)
    first = service.start({"data_path": "data/study.parquet", "generations": 1})
    plan = ScriptedResearcher().propose(first["model_context"])
    staged = service.submit_plan({
        "session_id": first["session_id"], "checkpoint_token": first["checkpoint_token"],
        "plan": plan, "model_capture": _signed(secret, first, "plan", plan),
    })
    diagnosed = ScriptedResearcher()
    diagnosed.seen = 1
    diagnosis = diagnosed.propose(staged["model_context"])
    completed = service.submit_diagnosis({
        "session_id": first["session_id"], "checkpoint_token": staged["checkpoint_token"],
        "diagnosis": diagnosis, "model_capture": _signed(secret, staged, "diagnosis", diagnosis),
    })
    assert completed["completed_generations"] == 1
    # Reproduce the dangerous boundary: counted cycle committed but collector
    # receipt absent while gateway still looks RUNNING after a crash.
    with service._connect() as db:
        db.execute(
            "DELETE FROM model_capture_receipts WHERE session_id=? AND phase_order=1",
            (first["session_id"],),
        )
        db.execute(
            "UPDATE stages SET phase='RUNNING' WHERE session_id=?",
            (first["session_id"],),
        )
    with pytest.raises(ModelCaptureError, match="incomplete"):
        service.reconcile({"session_id": first["session_id"]})
    with service._connect() as db:
        checkpoint = db.execute(
            "SELECT phase FROM stages WHERE session_id=?", (first["session_id"],),
        ).fetchone()
        assert checkpoint["phase"] == "RUNNING"
    # No post-hoc reconstruction of a fake collector proof occurred.
