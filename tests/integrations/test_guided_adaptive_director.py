"""GPT research-direction evidence binding; failures and diverse parents stay eligible."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from application.gpt_guided_research_service import GPTGuidedResearchService
from core.integrity.hashes import content_hash
from integrations.chatgpt_mcp_sdk import chatgpt_tools
from research.llm.guided_director_brief import build_director_brief, validate_director_decision
from tests.integrations.test_guided_learning_loop_restore import _intent


def _history(gen, train, family, failed):
    candidate_hash = f"candidate{gen}"
    return {
        "proposal_verified": True,
        "run_id": f"run{gen}", "attempt_id":f"attempt{gen}",
        "attempt":{
            "train_only_selection":{
                "sealed_oos_evaluated":False,
                "folds":[{"selected_candidate_hash":candidate_hash,
                          "train_total_return":train,
                          "test_total_return":100 if gen==1 else -100,
                          "train_end_at":"2022-01-01T00:00:00+00:00",
                          "test_start_at":"2022-02-01T00:00:00+00:00",
                          "selection_applied":True}],
            },
            "candidates":[{
                "candidate_hash":candidate_hash,
                "semantic_strategy_hash":f"{gen:064x}",
                "family":family,"failed_gates":failed,
            }],
        },
    }


def _decision(brief,*, mode="EXPLORE", parent=None, contrast=None):
    return {
        "schema":"guided-research-director-decision-v1",
        "context_digest":brief["context_digest"],
        "research_mode":mode,
        "hypothesis":"Changing one rule changes costed development training fills.",
        "competing_explanation":"Returns may change merely because exposure changes.",
        "research_parent_generation":parent,
        "contrast_parent_generation":contrast,
    }


def test_failed_parents_are_eligible_and_training_only_scores_choose_lanes():
    history=[_history(1,.1,"momentum",["qqq_cagr_delta"]),
             _history(2,.3,"mean_reversion",["validation"]),
             _history(3,-.2,"momentum",["robustness"])]
    brief=build_director_brief(
        session_id="a"*32,generation=4,checkpoint_token="b"*32,
        history=history,
        learning={"failed_candidates_included":3,"evidence_digest":"c"*64},
        controlled={"next_experiment_priority":"TEST_SINGLE_FACTOR"},
    )
    assert brief["failed_candidates_considered"]==3
    assert brief["parent_lanes"]["TRAIN_ONLY_PERFORMANCE"][0]["generation"]==2
    assert brief["parent_lanes"]["FAILED_HYPOTHESIS_REPAIR"][0]["generation"]==3
    assert {x["family"] for x in brief["parent_lanes"]["DISTINCT_FAMILY_EXPLORATION"]}=={"momentum","mean_reversion"}
    assert brief["multiple_parent_guide_only"] and not brief["production_parent_promotion"]
    assert all(not x["crossed_strategy_constructed"] for x in brief["contrast_parent_pairs"])
    accepted=validate_director_decision(
        decision=_decision(brief,mode="CONTRAST_PARENTS",parent=2,contrast=3),
        brief=brief,requested_parent_generation=2,
    )
    assert accepted["contrast_parent_generation"]==3


def test_stale_context_and_claimed_parent_or_contrast_fail_closed():
    h=[_history(1,-.1,"trend",["validation"]),_history(2,.2,"mean",["qqq_cagr_delta"])]
    brief=build_director_brief(session_id="a"*32,generation=3,checkpoint_token="1"*32,
       history=h,learning={"evidence_digest":"a"*64},controlled={})
    good=_decision(brief,mode="REFINE_PARENT",parent=1)
    assert validate_director_decision(decision=good,brief=brief,requested_parent_generation=1)
    for changes,match in [({"context_digest":"f"*64},"STALE_FEEDBACK"),
                          ({"research_parent_generation":2},"DISAGREES"),
                          ({"contrast_parent_generation":2},"INVALID_CONTRAST")]:
        with pytest.raises(ValueError,match=match):
            validate_director_decision(decision={**good,**changes},brief=brief,
                                       requested_parent_generation=1)
    modified=build_director_brief(session_id="a"*32,generation=3,checkpoint_token="2"*32,
       history=h,learning={"evidence_digest":"a"*64},controlled={})
    assert brief["context_digest"] != modified["context_digest"]


def test_optin_adaptive_session_requires_new_gpt_decision_and_keeps_failed_parent(tmp_path):
    root=Path(__file__).resolve().parents[2]
    service=GPTGuidedResearchService(project_root=root,state_dir=tmp_path/"autonomous-director")
    args={"data_path":"data/market/public_yahoo_qqq/QQQ_2020-01-02_2025-12-31_raw.parquet",
          "generations":2,"count":1,"seed":42567,"require_execution_change":True,
          "allow_research_parent_inheritance":True,"adaptive_research_controller":True,
          "benchmark_mode":"QQQ_COSTED_NEXT_OPEN_DEV_V1"}
    point=service.start(args)
    assert point["adaptive_research_controller"] is True
    assert point["research_director_brief"]["next_generation"]==1
    source="strategies/normalized/0a805e67c88e16da-4.json"
    step={"session_id":point["session_id"],"checkpoint_token":point["checkpoint_token"],
          "generation":1,"source_path":source,"intent":_intent(90)}
    with pytest.raises(ValueError,match="DIRECTOR_RESEARCH_DECISION_REQUIRED"):
        service.submit(step)
    brief=point["research_director_brief"]
    first=service.submit({**step,"research_decision":_decision(brief)})
    assert first["completed_generations"]==1
    assert first["learning_feedback"]["failed_candidates_included"]==1
    assert first["research_director_brief"]["context_digest"]!=brief["context_digest"]
    assert first["research_director_brief"]["parent_lanes"]["FAILED_HYPOTHESIS_REPAIR"]
    new_step={"session_id":first["session_id"],"checkpoint_token":first["checkpoint_token"],
              "generation":2,"source_path":source,"intent":_intent(75),
              "research_parent_generation":1}
    with pytest.raises(ValueError,match="DIRECTOR_STALE_FEEDBACK_CONTEXT"):
        service.submit({**new_step,"research_decision":_decision(brief,mode="REFINE_PARENT",parent=1)})
    second=service.submit({**new_step,"research_decision":_decision(
        first["research_director_brief"],mode="REFINE_PARENT",parent=1)})
    assert second["status"]=="COMPLETED" and second["completed_generations"]==2
    assert second["controlled_training_memory"]["verified_generations"]==2
    assert second["orders_enabled"] is False and second["sealed_oos_evaluated"] is False
    with sqlite3.connect(service.db_path) as db:
        rows=db.execute("SELECT proposal_json,proposal_hash,status FROM guided_research_proposals WHERE session_id=? ORDER BY generation",
                        (second["session_id"],)).fetchall()
    assert len(rows)==2
    for raw,digest,status in rows:
        proposal=json.loads(raw)
        assert content_hash(proposal)==digest
        assert proposal["research_director_decision"]["context_digest"]
        assert status=="COMMITTED"


def test_adaptive_requires_explicit_optin_and_public_schema_remains_same():
    tools={x["name"]:x for x in chatgpt_tools()}
    assert len(tools)==33
    assert "adaptive_research_controller" in tools["start_guided_research"]["inputSchema"]["properties"]
    assert "research_decision" in tools["submit_guided_generation"]["inputSchema"]["properties"]
