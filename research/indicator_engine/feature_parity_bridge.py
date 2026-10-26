"""Read-only, exact generic-to-academic semantic parity checks.

This is *not* a register/verify or OOS promotion operation. It compares
independent implementations on bounded completed development-like synthetic
OHLC bars and reports the required unit transforms explicitly.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from core.features.calculators import calculate_feature
from core.features.registry import research_feature_specs
from core.integrity.hashes import content_hash
from research.indicator_engine.models import IndicatorCandidate
from research.indicator_engine.signals import calculate_signal

# Each conversion is mathematically audited, not a name-only rename.
_COMPATIBLE: dict[str, tuple[str, str, str]] = {
    "sma_direction": ("sma", "price_greater_than_sma", "binary"),
    "ema_direction": ("ema", "price_greater_than_ema", "binary"),
    "parkinson_variance": ("parkinson", "square_standard_deviation", "variance"),
    "garman_klass_variance": ("garman_klass", "square_standard_deviation", "variance"),
}


def verify_feature_signal_parity(
    candidate: IndicatorCandidate,
    observations: Mapping[str, tuple[float, ...]],
) -> dict[str, Any]:
    """Prove selected dimensions match; unknown calculators fail closed."""
    if candidate.status != "VERIFIED":
        raise ValueError("academic signal is not VERIFIED")
    if candidate.scope != "single_asset" or candidate.execution_delay_bars != 1:
        raise ValueError("not a causal single-asset next-bar research signal")
    mapping = _COMPATIBLE.get(candidate.calculator)
    if mapping is None:
        raise ValueError("no reviewed unit/semantic transform for calculator")
    generic_name, transform, unit = mapping
    feature = next((f for f in research_feature_specs() if f.name == generic_name), None)
    if feature is None or feature.status != "REGISTERED" or feature.lag_bars != 0:
        raise ValueError("generic feature not registered or lag changed")
    required = set(candidate.required_fields)
    if not required <= observations.keys() or set(feature.inputs) != required:
        raise ValueError("input schema does not match the reviewed transform")
    count = len(observations[candidate.required_fields[0]])
    if not 530 <= count <= 10000:
        raise ValueError("bounded signal equivalence window required")
    if any(len(observations[name]) != count for name in required):
        raise ValueError("input lengths differ")
    spec = feature.model_copy(update={"lookback": candidate.lookback})
    raw = calculate_feature(spec, {name: observations[name] for name in spec.inputs})
    target = calculate_signal(candidate, observations)
    converted: list[float | None] = []
    for idx, value in enumerate(raw):
        if value is None:
            converted.append(None)
        elif transform == "square_standard_deviation":
            converted.append(float(value) ** 2)
        else:
            converted.append(float(observations["close"][idx] > value))
    max_abs = 0.0
    observations_count = 0
    for a, b in zip(converted, target, strict=True):
        if a is None or b is None:
            if a is not None or b is not None:
                raise ValueError("warmup and missing value parity failure")
            continue
        if not math.isfinite(a) or not math.isfinite(b):
            raise ValueError("nonfinite output")
        distance = abs(a - b)
        max_abs = max(max_abs, distance)
        if not math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-11):
            raise ValueError("mathematical parity failure")
        observations_count += 1
    if observations_count < 20:
        raise ValueError("insufficient overlapping samples")
    return {
        "schema": "quant-academic-feature-parity-v1",
        "academic_signal_id": candidate.signal_id,
        "generic_feature": generic_name,
        "conversion": transform,
        "generic_output_unit": "volatility"
        if transform == "square_standard_deviation"
        else "price",
        "academic_output_unit": unit,
        "sample_count": observations_count,
        "max_absolute_difference": max_abs,
        "generic_identity": feature.canonical_id,
        "academic_definition_hash": content_hash(candidate.model_dump(mode="json")),
        "source_observations_hash": content_hash(
            {name: observations[name] for name in sorted(required)}
        ),
        "equivalent_on_tested_development_samples": True,
        "eligible_for_automatic_academic_promotion": False,
        "orders_enabled": False,
        "independent_oos_approved": False,
    }
