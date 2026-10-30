"""Fail-closed parent recovery from immutable train-only selected Evidence.

A development successor is not a production champion and never authorizes OOS
or broker orders. There is deliberately NO fallback to the largest test CAGR.
"""
from __future__ import annotations

from core.integrity.hashes import content_hash
from experiments.identity import semantic_strategy_hash
from strategy_ir.schema import StrategyIR


def inherited_parent_from_evidence(
    *,
    attempt: dict,
    dataset_hash: str,
) -> tuple[StrategyIR,str]:
    if attempt.get("status") != "COMPLETED" or attempt.get("verification") is not None:
        raise ValueError("INHERITED_PARENT_EVIDENCE_UNVERIFIED")
    selected = attempt.get("train_only_selection")
    if not isinstance(selected,dict) or selected.get("status") != "EVALUATED" or not selected.get("upstream_selection_verified"):
        raise ValueError("INHERITED_PARENT_TRAIN_ONLY_SELECTION_UNVERIFIED")
    if selected.get("sealed_oos_evaluated") is not False:
        raise ValueError("INHERITED_PARENT_OOS_ACCESS_FORBIDDEN")
    folds = selected.get("folds")
    if not isinstance(folds,list) or not folds:
        raise ValueError("INHERITED_PARENT_TRAIN_ONLY_FOLDS_MISSING")
    latest=folds[-1]
    candidate_hash=latest.get("selected_candidate_hash")
    if (latest.get("selection_applied") is not True
            or not isinstance(candidate_hash,str)
            or candidate_hash not in latest.get("generated_candidate_hashes",[])
            or not latest.get("train_end_at") or not latest.get("test_start_at")
            or latest["train_end_at"] >= latest["test_start_at"]):
        raise ValueError("INHERITED_PARENT_TRAIN_CUTOFF_INVALID")
    matches=[c for c in attempt.get("candidates",[]) if c.get("candidate_hash")==candidate_hash]
    if len(matches)!=1:
        raise ValueError("INHERITED_PARENT_SELECTED_CANDIDATE_MISSING")
    candidate=matches[0]
    if (candidate.get("status") not in {"SURVIVOR","FRONTIER","CHAMPION_CANDIDATE","CHAMPION"}
            or candidate.get("failed_gates")
            or candidate.get("dataset_hash") != dataset_hash):
        raise ValueError("INHERITED_PARENT_POLICY_GATES_FAILED")
    ir=candidate.get("strategy_ir")
    if not isinstance(ir,dict) or content_hash(ir)!=candidate.get("strategy_ir_hash"):
        raise ValueError("INHERITED_PARENT_STRATEGY_IR_UNVERIFIED")
    strategy=StrategyIR.model_validate(ir)
    identity=semantic_strategy_hash(strategy)
    if identity != candidate.get("semantic_strategy_hash"):
        raise ValueError("INHERITED_PARENT_SEMANTIC_IDENTITY_MISMATCH")
    return strategy,identity
