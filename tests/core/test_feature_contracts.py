from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.data.contracts import DataContractError, DataZone, SeriesDataSet, SeriesObservation
from core.features.alignment import align_as_of
from core.features.contracts import FeatureSpec, FeatureVerification
from core.features.registry import FeatureRegistrationError, FeatureRegistry


def _time(day: int, hour: int = 0) -> datetime:
    return datetime(2024, 1, day, hour, tzinfo=timezone.utc)


def test_series_contract_allows_negative_rate_values_and_requires_sorted_unique_points() -> None:
    series = SeriesDataSet(
        "macro-v1",
        DataZone.DEVELOPMENT,
        (
            SeriesObservation("US10Y", _time(1), -0.25, _time(1, 18)),
            SeriesObservation("US10Y", _time(2), 0.10, _time(2, 18)),
        ),
    )

    assert series.dataset_hash
    assert series.observations[0].value == -0.25

    with pytest.raises(DataContractError, match="duplicate"):
        SeriesDataSet(
            "macro-v1",
            DataZone.DEVELOPMENT,
            series.observations + (series.observations[1],),
        )


def test_as_of_alignment_respects_observation_and_available_timestamps() -> None:
    observations = (
        SeriesObservation("VIX", _time(1, 16), 18.0, _time(1, 17)),
        SeriesObservation("VIX", _time(2, 16), 22.0, _time(2, 17)),
    )

    aligned = align_as_of(
        (_time(1, 18), _time(2, 16, ), _time(2, 18)),
        observations,
    )

    assert aligned == (18.0, 18.0, 22.0)


def test_registry_rejects_incomplete_verification_and_registers_verified_feature() -> None:
    registry = FeatureRegistry()
    spec = FeatureSpec(
        name="vix_percentile",
        family="macro",
        inputs=("VIX.close",),
        lookback=20,
        formula="rolling_percentile(VIX.close, 20)",
    )

    with pytest.raises(FeatureRegistrationError, match="verification"):
        registry.register_verified(spec, FeatureVerification())

    registered = registry.register_verified(
        spec,
        FeatureVerification(
            schema_valid=True,
            unit=True,
            historical=True,
            no_future_leak=True,
            alignment=True,
            missing_data=True,
            reproducible=True,
            resource_bounded=True,
            safe=True,
        ),
    )

    assert registered.status == "REGISTERED"
    assert registry.get("vix_percentile").version == registered.version
