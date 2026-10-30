"""Bounded development-only observations from *all* prior Guided outcomes.

Rejections are useful experiments; they are not automatically eligible
production strategies. No test or sealed-OOS period is used for ranking the
research parent pool. Development train-fold results are exploratory, not alpha.
"""
from __future__ import annotations

from collections import Counter
from math import isfinite
from typing import Any, Mapping, Sequence

from core.integrity.hashes import content_hash
from experiments.identity import semantic_strategy_hash
from strategy_ir.schema import StrategyIR


def check_proposal(proposal: Mapping[str, Any], *, expected_hash: str) -> dict[str, Any]:
    if not isinstance(proposal, dict) or content_hash(proposal) != expected_hash:
        raise ValueError("GUIDED_PROPOSAL_HASH_MISMATCH")
    items = proposal.get("candidates")
    if not isinstance(items, list) or not items:
        raise ValueError("GUIDED_PROPOSAL_MISSING_CANDIDATES")
    for c in items:
        ir = c.get("strategy_ir")
        if not isinstance(ir, dict) or content_hash(ir) != c.get("strategy_ir_hash"):
            raise ValueError("GUIDED_PROPOSAL_STRATEGY_IR_UNVERIFIED")
        if semantic_strategy_hash(StrategyIR.model_validate(ir)) != c.get("semantic_strategy_hash"):
            raise ValueError("GUIDED_PROPOSAL_STRATEGY_SEMANTICS_MISMATCH")
    cross=proposal.get("crossover_proof")
    if cross is not None:
        from research.llm.guided_crossover import crossover_exit
        if (not isinstance(cross,dict)
            or cross.get("schema")!="guided-two-parent-exit-crossover-v1"
            or not isinstance(proposal.get("crossover_donor_strategy_ir"),dict)
            or not isinstance(proposal.get("crossover_intermediate_ir"),dict)
            or type(cross.get("primary_generation")) is not int
            or type(cross.get("donor_generation")) is not int
            or cross["primary_generation"]==cross["donor_generation"]
            or cross["primary_generation"]>=proposal.get("generation",0)
            or cross["donor_generation"]>=proposal.get("generation",0)
            or proposal.get("parent_run_id")!=cross.get("primary_run_id")):
            raise ValueError("CROSSOVER_UNVERIFIED_PARENT_RECORDS")
        primary=StrategyIR.model_validate(proposal["parent_strategy_ir"])
        donor=StrategyIR.model_validate(proposal["crossover_donor_strategy_ir"])
        hybrid,proof=crossover_exit(primary,donor)
        for key,value in proof.items():
            if cross.get(key)!=value:
                raise ValueError("CROSSOVER_RECOMPUTED_PROOF_MISMATCH")
        if (hybrid.model_dump(mode="json",by_alias=True)!=proposal["crossover_intermediate_ir"]
            or not isinstance(cross.get("donor_run_id"),str)
            or not isinstance(cross.get("primary_run_id"),str)
            or cross["donor_run_id"]==cross["primary_run_id"]):
            raise ValueError("CROSSOVER_EXACT_INTERMEDIATE_IR_MISMATCH")
    elif proposal.get("crossover_donor_strategy_ir") is not None or proposal.get("crossover_intermediate_ir") is not None:
        raise ValueError("CROSSOVER_UNBOUND_DONOR_IR")
    return dict(proposal)


def training_outcome(attempt: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Training-only observations; never use validation-fold test or full CAGR to rank."""
    selection = attempt.get("train_only_selection", {})
    folds = selection.get("folds", []) if isinstance(selection, dict) else []
    train = [f.get("train_total_return") for f in folds
             if isinstance(f, dict)
             and f.get("selected_candidate_hash") == candidate.get("candidate_hash")
             and f.get("selection_applied") is True
             and isinstance(f.get("train_end_at"), str)
             and isinstance(f.get("test_start_at"), str)
             and f["train_end_at"] < f["test_start_at"]
             and type(f.get("train_total_return")) in (float,int)
             and isfinite(f["train_total_return"])]
    if selection.get("sealed_oos_evaluated") is not False:
        train = []
    return {
        "training_only_return_mean": round(sum(train)/len(train), 8) if train else None,
        "train_folds_observed": len(train),
        "training_selection_provenance_verified": bool(selection.get("upstream_selection_verified")),
        "training_score_excludes_validation_test": True,
    }


def summarize(
    history: Sequence[Mapping[str, Any]],
    *, dataset_hash: str,
    recent_limit: int = 8,
) -> dict[str, Any]:
    """Return bounded actionable feedback including rejected and incomplete cases."""
    if not 1 <= recent_limit <= 20:
        raise ValueError("invalid bounded feedback size")
    gate_count: Counter[str] = Counter()
    family_count: Counter[str] = Counter()
    observations: list[dict[str, Any]] = []
    reusable: list[dict[str, Any]] = []
    rejected = 0
    for gen, entry in enumerate(history, 1):
        attempt = entry["attempt"]
        if (attempt.get("status") != "COMPLETED" or attempt.get("verification") is not None
                or attempt.get("research_run_id") != entry["run_id"]
                or attempt.get("attempt_id") != entry["attempt_id"]):
            raise ValueError("GUIDED_LEARNING_EVIDENCE_UNVERIFIED")
        for cand in attempt.get("candidates", []):
            if cand.get("dataset_hash") != dataset_hash:
                raise ValueError("GUIDED_LEARNING_DATASET_MISMATCH")
            failed = cand.get("failed_gates")
            if not isinstance(failed, list):
                raise ValueError("GUIDED_LEARNING_FAILED_GATES_INVALID")
            gate_count.update(failed)
            family = cand.get("family") or "UNCLASSIFIED"
            family_count[family] += 1
            rejected += bool(failed)
            train = training_outcome(attempt, cand)
            obs = {
                "generation": gen, "run_id": entry["run_id"],
                "strategy_semantic_hash": cand.get("semantic_strategy_hash"),
                "candidate_hash":cand.get("candidate_hash"),
                "family":family, "failed_gates":list(failed),
                "policy_approved":not failed and cand.get("status") != "REJECT",
                "development_cagr_observed_not_parent_rank":cand.get("full_cagr"),
                "development_drawdown_observed":cand.get("max_drawdown"),
                "trade_count":cand.get("trade_count"),
                "qqq_cagr_delta_observed_not_parent_rank":cand.get("qqq_cagr_delta"),
                **train,
                "research_only_not_production_approval":True,
            }
            observations.append(obs)
            if entry.get("proposal_verified") is True and train["train_folds_observed"]:
                reusable.append(obs)
    # This is an advisory routing decision, not a fixed success-only whitelist.
    recent=observations[-recent_limit:]
    if not observations:
        mode,reason="EXPLORE","NO_COMPLETED_GENERATIONS"
    elif len(observations) >= 5 and all(
            "validation" in x["failed_gates"] for x in observations[-5:]):
        mode,reason="TEST_HYPOTHESIS","REPEATED_VALIDATION_FAILURES_REQUIRE_DIAGNOSIS"
    elif sum(bool(x["failed_gates"]) for x in recent) >= 3:
        mode,reason="DIAGNOSE","MULTIPLE_FAILED_OUTCOMES_TO_EXPLAIN"
    else:
        mode,reason="EVOLVE_OR_EXPLORE","MIXED_OUTCOMES_NEED_CONTROLLED_COMPARISON"
    # Multiple score lanes; training only; even failed strategies can inform
    # proposals, but parent reuse requires exact persisted IR and replay proof.
    ranked=sorted(reusable,key=lambda x:(
        -(x["training_only_return_mean"] or -1000),x["generation"]
    ))
    leaders=ranked[:3]
    # These are paired, falsifiable suggestions, not model-produced causal
    # conclusions. Keep the unchanged parent and identical costs as control.
    suggested=[]
    if gate_count["validation"]:
        suggested.append({
          "hypothesis":"TEST_RULE_ABLATION_FOR_VALIDATION_INSTABILITY",
          "design":"Hold the parent/fees fixed; change one entry or exit rule and measure temporal folds, exposure and forgone winning trades.",
          "competing_explanation":"A seemingly improved development return may merely lower exposure or fit a single trend period.",
          "control":"PARENT_UNCHANGED_COSTED", "causal_status":"UNTESTED",
        })
    if gate_count["fast"] or gate_count["annual_trade_count"]:
        suggested.append({
          "hypothesis":"TEST_SIGNAL_FREQUENCY_WITHOUT_ARTIFICIAL_TRADING",
          "design":"Ablate one restrictive entry condition while preserving transaction costs and examine whether real completed trades change.",
          "competing_explanation":"Higher turnover can increase costs and worsen net risk-adjusted return.",
          "control":"PARENT_UNCHANGED_COSTED", "causal_status":"UNTESTED",
        })
    if gate_count["qqq_cagr_delta"]:
        suggested.append({
          "hypothesis":"SEPARATE_MARKET_EXPOSURE_FROM_ENTRY_EDGE",
          "design":"Compare a single entry-timing variant against unchanged parent and costed QQQ buy-and-hold on development data; evaluate exposure-adjusted results.",
          "competing_explanation":"Higher return may be caused by greater QQQ exposure, not a predictive signal.",
          "control":"PARENT_UNCHANGED_COSTED", "causal_status":"UNTESTED",
        })
    if gate_count["robustness"]:
        suggested.append({
          "hypothesis":"TEST_REGIME_TRANSFER_OF_THE_SAME_SIGNAL",
          "design":"Compare one explicitly specified trend/volatility regime filter against the unmodified parent across train-only regimes.",
          "competing_explanation":"Filtering out losing regimes retrospectively can introduce selection bias.",
          "control":"PARENT_UNCHANGED_COSTED", "causal_status":"UNTESTED",
        })
    failures=sorted((x for x in observations if x["failed_gates"]),
                    key=lambda x:(x["development_drawdown_observed"] if
                                  type(x["development_drawdown_observed"]) in (float,int) else 999,
                                  x["generation"]))[:3]
    return {
        "schema":"guided-cross-generation-feedback-v1",
        "mode":"EVIDENCE_ADVISORY_NOT_AUTONOMOUS_LLM",
        "completed_generations":len(history),
        "evaluated_candidates":len(observations),
        "failed_candidates_included":rejected,
        "failure_gate_counts":dict(sorted(gate_count.items())),
        "family_counts":dict(sorted(family_count.items())),
        "next_research_mode":mode, "direction_reason":reason,
        "recent_observations":recent,
        "development_research_parent_shortlist":[
            {"generation":x["generation"],"strategy_semantic_hash":x["strategy_semantic_hash"],
             "train_only_return":x["training_only_return_mean"],
             "failed_final_gates":x["failed_gates"],
             "reusable_only_with_exact_ir_and_replay":True}
            for x in leaders
        ],
        "suggested_controlled_hypotheses":suggested[:4],
        "research_loop":"GPT chooses next EXPLORATION / DIAGNOSIS / RESEARCH PARENT after reading all signed failures; no fixed generation mutation grid.",
        "diagnostic_failure_cases":[
            {"generation":x["generation"],"failed_gates":x["failed_gates"],
             "development_drawdown":x["development_drawdown_observed"],
             "requires_control_experiment":True} for x in failures
        ],
        "production_promotions":0,
        "parent_pool_is_development_only":True,
        "independent_oos_approved":False,
        "orders_enabled":False,
        "never_use_validation_or_oos_for_parent_ranking":True,
        "evidence_digest":content_hash([{
            "run_id":e["run_id"],"attempt_id":e["attempt_id"],
            "proposal_hash":e.get("proposal_hash"),
            "candidate_hashes":[c.get("candidate_hash") for c in e["attempt"].get("candidates",[])],
        } for e in history]),
    }
