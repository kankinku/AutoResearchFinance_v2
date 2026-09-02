from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from core.features.catalog import semantic_feature_id
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


def record_feature_proposal(path: Path, proposal: FeatureProposal, *, generation: int) -> None:
    """Append a non-eligible feature proposal to the verification queue."""

    if generation < 0:
        raise FeatureLifecycleError("generation cannot be negative")
    spec = proposal.to_spec()
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "generation": generation,
        "status": "PENDING_VERIFICATION",
        "semantic_id": semantic_feature_id(spec),
        "proposal": proposal.model_dump(mode="json"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
