"""P0-3: tie research-decision claims to real S7/audit, not model identity."""

from __future__ import annotations

from copy import deepcopy

import pytest

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from integrations.chatgpt_mcp_sdk import chatgpt_tools
from research.llm.decision_provenance import DecisionProvenanceError
from tests.integrations.test_academic_mcp_sessions import _setup
from tests.research.test_autonomous_academic_cycle import ScriptedResearcher


def _claim(*, refs: list | None = None, current: list | None = None, origin="SCRIPTED") -> dict:
    return {
        "declared_origin": origin,
        "decision_summary": (
            "The measured prior S7 experiment contradicted the tested hypothesis, "
            "so test a different confidence gate and compare the identical development bars."
        ),
        "rejected_alternative": (
            "Merely shrinking allocation lowers loss magnitude and cannot prove "
            "that timing signals or predictor quality improved."
        ),
        "referenced_s7": refs or [],
        "current_observation_ids": current or [],
    }


def test_cited_s7_plan_and_trade_diagnosis_preserved_without_model_authentication(tmp_path) -> None:
    server, started = _setup(tmp_path)
    sid = started["session_id"]
    provider = ScriptedResearcher()
    # Prior legacy research is accepted, but must NOT gain retroactive model provenance.
    first = server._dispatch(
        "submit_algorithm_plan",
        {
            "session_id": sid,
            "checkpoint_token": started["checkpoint_token"],
            "plan": provider.propose(started["model_context"]),
        },
    )
    first_done = server._dispatch(
        "submit_algorithm_diagnosis",
        {
            "session_id": sid,
            "checkpoint_token": first["checkpoint_token"],
            "diagnosis": provider.propose(first["model_context"]),
        },
    )
    assert first_done["completed_generations"] == 1
    assert first_done["decision_provenance"]["recorded_claims"] == 0
    report = first_done["latest_controlled_experiments"]
    trial = report["report"]["experiments"][0]
    ref = [
        {
            "generation": 1,
            "hypothesis_id": trial["hypothesis_id"],
            "s7_record_hash": report["record_hash"],
            "observed_status": trial["status"],
        }
    ]
    plan = provider.propose(first_done["model_context"])
    arg = {
        "session_id": sid,
        "checkpoint_token": first_done["checkpoint_token"],
        "plan": plan,
        "decision_evidence": _claim(refs=ref, origin="CHATGPT_CLIENT"),
        "require_decision_evidence": True,
    }
    forged = deepcopy(arg)
    forged["decision_evidence"]["referenced_s7"][0]["observed_status"] = "FAKE_GOOD_RESULT"
    with pytest.raises(DecisionProvenanceError, match="observed outcome"):
        server._dispatch("submit_algorithm_plan", forged)
    assert (
        server._dispatch("get_algorithm_research", {"session_id": sid})["checkpoint_phase"]
        == "AWAITING_PLAN"
    )
    staged = server._dispatch("submit_algorithm_plan", arg)
    assert server._dispatch("submit_algorithm_plan", arg) == staged
    assert staged["decision_provenance"]["recorded_claims"] == 1
    assert staged["decision_provenance"]["real_model_connection_verified"] is False
    assert staged["decision_provenance"]["recent_decisions"][0]["declared_origin"] == (
        "CHATGPT_CLIENT"
    )
    summary = staged["decision_provenance"]["recent_decisions"][0]
    assert summary["source_origin_verified"] is False
    assert summary["evidence_links_verified"] is True
    assert staged["checkpoint_phase"] == "AWAITING_DIAGNOSIS"
    first_loss = staged["model_context"]["observations"]["loss_cases"][0]["trade_id"]
    diag = provider.propose(staged["model_context"])
    diagnosed = {
        "session_id": sid,
        "checkpoint_token": staged["checkpoint_token"],
        "diagnosis": diag,
        "decision_evidence": _claim(refs=ref, current=[first_loss], origin="SCRIPTED"),
        "require_decision_evidence": True,
    }
    false_trace = deepcopy(diagnosed)
    false_trace["decision_evidence"]["current_observation_ids"] = ["INVENTED_T-123"]
    with pytest.raises(DecisionProvenanceError, match="exact audited"):
        server._dispatch("submit_algorithm_diagnosis", false_trace)
    assert (
        server._dispatch("get_algorithm_research", {"session_id": sid})["checkpoint_phase"]
        == "AWAITING_DIAGNOSIS"
    )
    last = server._dispatch("submit_algorithm_diagnosis", diagnosed)
    assert last["completed_generations"] == 2
    assert server._dispatch("submit_algorithm_diagnosis", diagnosed) == last
    assert last["decision_provenance"]["recorded_claims"] == 2
    assert last["decision_provenance"]["model_autonomy_verified"] is False
    assert last["history"][1]["previous_evidence_hash"] == last["history"][0]["evidence_hash"]
    svc = AcademicMCPCheckpointService(
        project_root=server.project_root,
        state_dir=server.state_dir,
    )
    with svc._connect() as db:
        rows = db.execute(
            "SELECT phase,generation,receipt_json FROM research_decision_receipts "
            "WHERE session_id=? ORDER BY phase",
            (sid,),
        ).fetchall()
        assert len(rows) == 2
        db.execute(
            "UPDATE research_decision_receipts SET receipt_hash='deadbeef' "
            "WHERE session_id=? AND phase='PLAN'",
            (sid,),
        )
    with pytest.raises(DecisionProvenanceError, match="identity mismatch"):
        svc.get({"session_id": sid})


def test_strict_opt_in_rejects_missing_claim_and_legacy_is_unchanged(tmp_path) -> None:
    server, start = _setup(tmp_path)
    plan = ScriptedResearcher().propose(start["model_context"])
    with pytest.raises(DecisionProvenanceError, match="required"):
        server._dispatch(
            "submit_algorithm_plan",
            {
                "session_id": start["session_id"],
                "checkpoint_token": start["checkpoint_token"],
                "plan": plan,
                "require_decision_evidence": True,
            },
        )
    assert (
        server._dispatch(
            "get_algorithm_research",
            {
                "session_id": start["session_id"],
            },
        )["completed_generations"]
        == 0
    )
    outcome = server._dispatch(
        "submit_algorithm_plan",
        {
            "session_id": start["session_id"],
            "checkpoint_token": start["checkpoint_token"],
            "plan": plan,
        },
    )
    assert outcome["checkpoint_phase"] == "AWAITING_DIAGNOSIS"
    assert outcome["decision_provenance"]["recorded_claims"] == 0


def test_original_mcp_tool_names_retained_and_citation_fields_advertised() -> None:
    tools = {t["name"]: t for t in chatgpt_tools()}
    assert len(tools) == 32
    for name in ("submit_algorithm_plan", "submit_algorithm_diagnosis"):
        props = tools[name]["inputSchema"]["properties"]
        assert "decision_evidence" in props
        assert "require_decision_evidence" in props
        assert props["decision_evidence"]["properties"]["declared_origin"]["description"] == (
            "Self-declared only; never model-authenticated."
        )
        assert tools[name]["inputSchema"]["additionalProperties"] is False
