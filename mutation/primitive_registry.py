from __future__ import annotations

from dataclasses import dataclass


class UnknownPrimitiveError(KeyError):
    """Raised when a strategy refers to a primitive that is not registered."""


@dataclass(frozen=True)
class PrimitiveDefinition:
    name: str
    input_names: tuple[str, ...]
    output_type: str
    registry_version: str = "primitive-registry-v1"


class PrimitiveRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, PrimitiveDefinition] = {}

    def register(
        self,
        name: str,
        *,
        input_names: tuple[str, ...],
        output_type: str,
    ) -> PrimitiveDefinition:
        if name in self._definitions:
            raise ValueError(f"primitive already registered: {name}")
        definition = PrimitiveDefinition(name, input_names, output_type)
        self._definitions[name] = definition
        return definition

    def get(self, name: str) -> PrimitiveDefinition:
        try:
            return self._definitions[name]
        except KeyError as exc:
            raise UnknownPrimitiveError(f"unknown primitive: {name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._definitions))


def default_registry() -> PrimitiveRegistry:
    registry = PrimitiveRegistry()
    indicator_names = (
        "sma_cross",
        "ema_cross",
        "rsi",
        "macd",
        "atr",
        "adx",
        "bollinger",
        "volume_breakout",
        "52_week_high",
        "volatility_filter",
        "regime_filter",
    )
    for name in indicator_names:
        registry.register(name, input_names=("period",), output_type="indicator")
    registry.register("stop_logic", input_names=("stop_loss_pct",), output_type="risk")
    registry.register("take_profit", input_names=("take_profit_pct",), output_type="risk")
    registry.register("trailing_stop", input_names=("trailing_stop_pct",), output_type="risk")
    registry.register("position_sizing", input_names=("position_size_pct",), output_type="risk")
    return registry
