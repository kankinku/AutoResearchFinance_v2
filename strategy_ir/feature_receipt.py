"""Development-only evidence binding for the policy switch feature vectors.

A receipt proves consistency with a trusted verifier's prior review, not PIT approval.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from core.data.contracts import MarketDataSet
from core.integrity.hashes import content_hash
from strategy_ir.policy_decision import PolicyDecision
from strategy_ir.policy_program import PolicySwitch, compile_policy_switch


@dataclass(frozen=True)
class FeatureAuditReceipt:
    feature_id: str
    dataset_hash: str
    values_hash: str
    verification_id: str
    verification_status: str


def compile_reviewed_policy_switch(
    dataset: MarketDataSet,
    program: PolicySwitch,
    features: Mapping[str, Sequence[float | None]],
    *,
    trusted_receipts: Mapping[str, FeatureAuditReceipt],
) -> tuple[PolicyDecision, ...]:
    """Require independently supplied audit receipts bound to exact input vectors."""
    identifiers = {predicate.feature for predicate in program.predicates}
    for feature_id in identifiers:
        receipt = trusted_receipts.get(feature_id)
        values = features.get(feature_id)
        if receipt is None or values is None:
            raise ValueError("trusted feature receipt required")
        if (
            receipt.feature_id != feature_id
            or receipt.dataset_hash != dataset.dataset_hash
            or receipt.verification_status != "AUDITED"
            or not receipt.verification_id.strip()
            or receipt.values_hash != content_hash(tuple(values))
        ):
            raise ValueError("feature receipt mismatch or not audited")
    return compile_policy_switch(
        dataset, program, features, audited_features=frozenset(identifiers)
    )
