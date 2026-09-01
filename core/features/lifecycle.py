from __future__ import annotations

from core.features.contracts import FeatureProposal, FeatureSpec, FeatureVerification
from core.features.registry import FeatureRegistrationError, FeatureRegistry


class FeatureLifecycleError(ValueError):
    """Raised when a proposed feature is not ready for registration."""


def register_feature_proposal(
    registry: FeatureRegistry,
    proposal: FeatureProposal,
    verification: FeatureVerification,
    *,
    implementation_hash: str,
) -> FeatureSpec:
    if not implementation_hash:
        raise FeatureLifecycleError("implementation hash is required")
    spec = proposal.to_spec().model_copy(
        update={"implementation_hash": implementation_hash}
    )
    try:
        return registry.register_verified(spec, verification)
    except FeatureRegistrationError as exc:
        raise FeatureLifecycleError(str(exc)) from exc
