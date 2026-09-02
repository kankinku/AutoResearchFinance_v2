from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.features.contracts import FeatureProposal, FeatureVerification
from core.features.lifecycle import (
    FeatureLifecycleError,
    record_feature_proposal,
    register_feature_proposal,
)
from core.features.registry import FeatureRegistry


def _verification() -> FeatureVerification:
    return FeatureVerification(
        schema_valid=True,
        unit=True,
        historical=True,
        no_future_leak=True,
        alignment=True,
        missing_data=True,
        reproducible=True,
        resource_bounded=True,
        safe=True,
    )


def test_successful_implementation_is_registered_with_hash() -> None:
    proposal = FeatureProposal(
        name="rate_spread_change",
        family="rates",
        inputs=("US10Y.close", "US2Y.close"),
        calculator="spread",
        lookback=1,
        formula="US10Y.close - US2Y.close",
        justification="measure curve change",
    )

    registered = register_feature_proposal(
        FeatureRegistry(), proposal, _verification(), implementation_hash="impl-123"
    )

    assert registered.status == "REGISTERED"
    assert registered.implementation_hash == "impl-123"


def test_feature_registration_rejects_missing_implementation_hash() -> None:
    proposal = FeatureProposal(
        name="unbuilt",
        family="macro",
        inputs=("VIX.close",),
        calculator="percentile",
        lookback=20,
        formula="percentile(VIX.close, 20)",
        justification="volatility regime",
    )

    with pytest.raises(FeatureLifecycleError, match="implementation hash"):
        register_feature_proposal(
            FeatureRegistry(), proposal, _verification(), implementation_hash=""
        )


def test_feature_proposal_rejects_executable_formula() -> None:
    with pytest.raises(ValueError, match="unsafe"):
        FeatureProposal(
            name="unsafe",
            family="macro",
            inputs=("VIX.close",),
            lookback=1,
            formula="import requests",
            justification="not allowed",
        )


def test_feature_proposal_is_persisted_as_pending_verification(tmp_path: Path) -> None:
    proposal = FeatureProposal(
        name="pending_macro",
        family="macro",
        inputs=("VIX.close",),
        calculator="percentile",
        lookback=20,
        formula="percentile(VIX.close, 20)",
        justification="regime filter",
    )

    record_feature_proposal(tmp_path / "feature-proposals.jsonl", proposal, generation=4)

    record = json.loads(
        (tmp_path / "feature-proposals.jsonl").read_text(encoding="utf-8")
    )
    assert record["status"] == "PENDING_VERIFICATION"
    assert record["generation"] == 4
    assert record["proposal"]["name"] == "pending_macro"
