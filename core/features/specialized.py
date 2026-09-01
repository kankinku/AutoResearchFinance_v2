from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from core.features.contracts import FeatureSpec


@dataclass(frozen=True)
class ProfileObservation:
    price: float
    volume: float


@dataclass(frozen=True)
class OrderFlowObservation:
    buy_volume: float
    sell_volume: float


@dataclass(frozen=True)
class SessionObservation:
    session: str
    hour: int
    minute: int


SpecializedInput: TypeAlias = (
    tuple[ProfileObservation, ...]
    | tuple[OrderFlowObservation, ...]
    | tuple[SessionObservation, ...]
)


def calculate_specialized(
    spec: FeatureSpec, inputs: dict[str, SpecializedInput]
) -> tuple[float, ...]:
    """Calculate features requiring non-OHLCV observations."""

    calculator = spec.calculator.lower()
    supported = {
        "volume_profile",
        "tpo_profile",
        "order_flow_delta",
        "order_flow_imbalance",
        "weis_wyckoff",
        "session_flag",
        "time_of_day",
        "day_of_week",
    }
    if calculator not in supported:
        raise ValueError(f"unsupported specialized calculator {spec.calculator!r}")
    raw = inputs.get(spec.data_contract)
    if raw is None:
        raise ValueError(f"{spec.data_contract} input required")
    if calculator == "volume_profile":
        profile = _profile(raw)
        return (max(profile, key=lambda item: item.volume).price,)
    if calculator == "tpo_profile":
        profile = _profile(raw)
        return (sum(item.price for item in profile) / len(profile),) if profile else ()
    if calculator in {"order_flow_delta", "order_flow_imbalance"}:
        flow = _order_flow(raw)
        if calculator == "order_flow_delta":
            return tuple(item.buy_volume - item.sell_volume for item in flow)
        return tuple(
            0.0
            if item.buy_volume + item.sell_volume == 0
            else (item.buy_volume - item.sell_volume) / (item.buy_volume + item.sell_volume)
            for item in flow
        )
    if calculator == "weis_wyckoff":
        flow = _order_flow(raw)
        return tuple(item.buy_volume - item.sell_volume for item in flow)
    if calculator == "session_flag":
        sessions = _sessions(raw)
        requested = str(spec.parameters.get("session", "regular"))
        return tuple(1.0 if item.session == requested else 0.0 for item in sessions)
    if calculator == "time_of_day":
        sessions = _sessions(raw)
        return tuple(item.hour + item.minute / 60.0 for item in sessions)
    if calculator == "day_of_week":
        sessions = _sessions(raw)
        return tuple(float(index % 7) for index, _ in enumerate(sessions))
    raise ValueError(f"unsupported specialized calculator {spec.calculator!r}")


def _profile(raw: SpecializedInput) -> tuple[ProfileObservation, ...]:
    if not all(isinstance(item, ProfileObservation) for item in raw):
        raise ValueError("profile input required")
    return tuple(item for item in raw if isinstance(item, ProfileObservation))


def _order_flow(raw: SpecializedInput) -> tuple[OrderFlowObservation, ...]:
    if not all(isinstance(item, OrderFlowObservation) for item in raw):
        raise ValueError("order_flow input required")
    return tuple(item for item in raw if isinstance(item, OrderFlowObservation))


def _sessions(raw: SpecializedInput) -> tuple[SessionObservation, ...]:
    if not all(isinstance(item, SessionObservation) for item in raw):
        raise ValueError("session input required")
    return tuple(item for item in raw if isinstance(item, SessionObservation))
