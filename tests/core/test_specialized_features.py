from __future__ import annotations

import pytest

from core.features.contracts import FeatureSpec
from core.features.specialized import (
    OrderFlowObservation,
    ProfileObservation,
    SessionObservation,
    calculate_specialized,
)


def _spec(calculator: str, data_contract: str) -> FeatureSpec:
    return FeatureSpec(
        name=calculator,
        family="specialized",
        inputs=(data_contract,),
        calculator=calculator,
        lookback=3,
        formula=f"{calculator}({data_contract})",
        data_contract=data_contract,  # type: ignore[arg-type]
    )


def test_profile_indicator_requires_profile_input() -> None:
    with pytest.raises(ValueError, match="profile input required"):
        calculate_specialized(_spec("volume_profile", "profile"), {})


def test_profile_and_order_flow_features_use_their_declared_contracts() -> None:
    profile = (
        ProfileObservation(100.0, 10.0),
        ProfileObservation(101.0, 30.0),
    )
    order_flow = (
        OrderFlowObservation(5.0, 2.0),
        OrderFlowObservation(4.0, 6.0),
    )

    point_of_control = calculate_specialized(
        _spec("volume_profile", "profile"), {"profile": profile}
    )
    delta = calculate_specialized(
        _spec("order_flow_delta", "order_flow"), {"order_flow": order_flow}
    )

    assert point_of_control == (101.0,)
    assert delta == (3.0, -2.0)


def test_session_features_require_session_metadata_and_orders_are_not_calculators() -> None:
    session = (
        SessionObservation("regular", 4, 30, high=105.0, low=95.0),
        SessionObservation("regular", 5, 0, high=107.0, low=96.0),
    )
    flags = calculate_specialized(_spec("session_flag", "session"), {"session": session})

    assert flags == (1.0, 1.0)
    assert calculate_specialized(
        _spec("normalized_time_of_day", "session"), {"session": session}
    ) == (4.5 / 24.0, 5.0 / 24.0)
    assert calculate_specialized(_spec("session_high", "session"), {"session": session}) == (107.0,)
    assert calculate_specialized(_spec("session_low", "session"), {"session": session}) == (95.0,)
    assert calculate_specialized(
        _spec("session_overlay_flags", "session"), {"session": session}
    ) == (1.0, 1.0)
    with pytest.raises(ValueError, match="unsupported specialized calculator"):
        calculate_specialized(_spec("place_order", "scalar"), {})
