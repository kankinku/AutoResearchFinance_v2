from __future__ import annotations

import math

import pytest

from core.features.calculators import calculate_feature
from core.features.catalog import imported_feature_catalog, rate_series_ids
from core.features.contracts import FeatureSpec, FeatureVerification
from core.features.registry import FeatureRegistrationError, FeatureRegistry


def test_rsi_aliases_share_one_canonical_feature() -> None:
    catalog = imported_feature_catalog()
    rsi = catalog.resolve("rsi")

    assert "relative_strength_index" in rsi.aliases
    assert catalog.resolve("relative_strength_index").canonical_id == rsi.canonical_id


def test_different_rsi_smoothing_is_not_false_deduplicated() -> None:
    catalog = imported_feature_catalog()

    assert catalog.resolve("rsi.wilder").canonical_id != catalog.resolve("rsi.ema").canonical_id


def test_source_function_aliases_resolve_to_existing_canonical_indicators() -> None:
    catalog = imported_feature_catalog()

    for alias, canonical in (
        ("williams_percent_r", "williams_r"),
        ("simple_returns", "returns"),
        ("klinger_oscillator", "klinger"),
        ("volume_flow_indicator", "vfi"),
        ("garman_klass_volatility", "garman_klass"),
    ):
        assert catalog.resolve(alias).canonical_id == catalog.resolve(canonical).canonical_id


def test_catalog_contains_nine_optional_rate_series() -> None:
    assert set(rate_series_ids()) == {
        "US2Y",
        "US10Y",
        "US20Y",
        "JP2Y",
        "JP10Y",
        "JP20Y",
        "KR2Y",
        "KR10Y",
        "KR20Y",
    }


def test_catalog_retains_the_full_audited_inventory_without_silent_omissions() -> None:
    catalog = imported_feature_catalog()
    names = {feature.name for feature in catalog.all()}

    assert len(names) >= 100
    assert {"stoch_rsi", "garman_klass", "heikin_ashi", "volume_profile"} <= names
    assert all(feature.status == "REGISTERED" for feature in catalog.all())


def test_registered_scalar_catalog_specs_execute_with_their_declared_inputs() -> None:
    values = tuple(float(10 + index % 4) for index in range(32))
    inputs = {
        "close": values,
        "open": tuple(value - 0.2 for value in values),
        "high": tuple(value + 1.0 for value in values),
        "low": tuple(value - 1.0 for value in values),
        "volume": tuple(float(100 + index * 10) for index in range(32)),
    }

    for spec in imported_feature_catalog().all():
        if spec.data_contract != "scalar":
            continue
        result = calculate_feature(spec, {name: inputs[name] for name in spec.inputs})
        assert len(result) == len(values), spec.name
        assert all(value is None or math.isfinite(value) for value in result), spec.name


def test_registry_rejects_duplicate_semantic_identity() -> None:
    registry = FeatureRegistry()
    first = FeatureSpec(
        name="rsi_a",
        family="momentum",
        inputs=("close",),
        calculator="rsi",
        lookback=14,
        formula="RSI(close,14)",
        status="PROPOSED",
    )
    second = first.model_copy(update={"name": "rsi_b"})
    verification = FeatureVerification(
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

    registry.register_verified(first, verification)
    with pytest.raises(FeatureRegistrationError, match="semantic identity"):
        registry.register_verified(second, verification)
