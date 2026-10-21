"""Hash-verified developmental risk rejection feedback, not independent GPT inference.

The feedback is an auditable, conservative *hypothesis* about which candidate
family to try next. It never relaxes risk limits or treats rejected strategies
as OOS validation. Rejection rows are tied to the same pinned parent/token.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from core.backtest.p2_policy import ChildRiskBudget
from core.integrity.hashes import content_hash


def summarize_precommit_rejections(
    *,
    rows: Sequence[Mapping[str, Any]],
    dataset_hash: str,
    parent_selection_hash: str,
    parent_strategy_hash: str,
    token_hash: str,
    budget: ChildRiskBudget,
) -> dict[str, Any]:
    """Only verified, same-parent, same-token rejections inform the next attempt."""
    legitimate: list[dict[str, Any]] = []
    for row in rows:
        body = json.loads(row["review_json"])
        if content_hash(body) != row["review_hash"]:
            raise ValueError("P2 signed risk rejection record changed")
        if (
            body.get("schema") != "p2-precommit-child-risk-rejection-v1"
            or body.get("dataset_hash") != dataset_hash
            or body.get("parent_selection_hash") != parent_selection_hash
            or body.get("parent_strategy_hash") != parent_strategy_hash
            or body.get("token_hash") != token_hash
            or body.get("risk_budget") != budget.model_dump(mode="json")
            or body.get("risk_review", {}).get("eligible") is not False
            or not isinstance(body.get("proposal_operations"), list)
        ):
            raise ValueError("P2 rejected proposal does not belong to current checkpoint")
        legitimate.append(body)
    exceeded_mdd = sum(
        item["risk_review"]["child_mdd_pct"] > budget.max_child_mdd_pct for item in legitimate
    )
    relative_mdd = sum(
        item["risk_review"]["child_mdd_pct"]
        > item["risk_review"]["parent_mdd_pct"] + budget.max_mdd_increase_pp
        for item in legitimate
    )
    insufficient_trades = sum(
        item["risk_review"]["closed_trades"] < budget.min_closed_trades for item in legitimate
    )
    rejected_families = Counter(
        operation["path"].split(".")[0]
        for item in legitimate
        for operation in item["proposal_operations"]
        if isinstance(operation, dict) and isinstance(operation.get("path"), str)
    )
    # An empirically observed failure count informs priority only; it does
    # not assert a given change will lower MDD. Rejection history of the same
    # parent is used; the next strategy still must pass full costed replay.
    if exceeded_mdd or relative_mdd:
        order = ["entry", "exit"]
        hypothesis = (
            "Test more selective entry or earlier exits to address "
            "observed excessive child drawdown."
        )
    elif insufficient_trades:
        order = ["exit", "entry"]
        hypothesis = "Test less restrictive entry/exit mechanisms to recover enough closed trades."
    else:
        order = ["entry", "exit"]
        hypothesis = "Prior results are inconclusive; test a different executable strategy."
    digest = content_hash(
        [(b["request_hash"], b["child_strategy_hash"], b["risk_review"]) for b in legitimate]
    )
    return {
        "schema": "p2-risk-feedback-v1",
        "mode": "DETERMINISTIC_SIGNED_EVIDENCE_GUIDANCE_NOT_GPT",
        "rejection_count": len(legitimate),
        "absolute_mdd_failures": exceeded_mdd,
        "relative_mdd_failures": relative_mdd,
        "trade_count_failures": insufficient_trades,
        "rejected_operation_domains": dict(sorted(rejected_families.items())),
        "proposed_domain_order": order,
        "hypothesis": hypothesis,
        "evidence_digest": digest,
        "dataset_hash": dataset_hash,
        "parent_strategy_hash": parent_strategy_hash,
        "budget": budget.model_dump(mode="json"),
        "never_relax_thresholds": True,
    }


def prioritize_untried_operations(
    operations: Sequence[list[dict[str, Any]]],
    feedback: Mapping[str, Any],
) -> list[list[dict[str, Any]]]:
    """Change candidate order from the current *verified* rejection diagnosis.

    Not a trained optimizer or an LLM call. Every candidate is still passed
    through the exact same execution and risk gate; no risk thresholds change.
    """
    allowed = feedback.get("proposed_domain_order")
    if (
        feedback.get("schema") != "p2-risk-feedback-v1"
        or feedback.get("never_relax_thresholds") is not True
        or not isinstance(allowed, list)
        or sorted(allowed) != ["entry", "exit"]
    ):
        raise ValueError("invalid signed-feedback candidate priority")
    domains = {name: i for i, name in enumerate(allowed)}

    def priority(ops: list[dict[str, Any]]) -> tuple[int, int]:
        touched = {
            op["path"].split(".")[0]
            for op in ops
            if isinstance(op, dict) and isinstance(op.get("path"), str)
        }
        score = min((domains[name] for name in touched if name in domains), default=2)
        return (score, len(ops))

    return sorted(operations, key=priority)


def iter_feedback_adjusted_designs(
    designs: Sequence[list[dict[str, Any]]],
    current_feedback: list[dict[str, Any]],
):
    """Re-prioritize pending candidates only when a verified rejection arrives."""
    remaining = list(designs)
    last_digest = None
    while remaining:
        feedback = current_feedback[0]
        if feedback["evidence_digest"] != last_digest:
            if feedback["rejection_count"] > 0:
                remaining = prioritize_untried_operations(remaining, feedback)
            last_digest = feedback["evidence_digest"]
        yield remaining.pop(0)
