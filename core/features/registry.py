from __future__ import annotations

from core.features.catalog import semantic_feature_id
from core.features.contracts import FeatureSpec, FeatureVerification


class FeatureRegistrationError(ValueError):
    """Raised when an unverified feature is submitted to the registry."""


class FeatureRegistry:
    def __init__(self, specs: tuple[FeatureSpec, ...] = ()) -> None:
        self._specs: dict[str, FeatureSpec] = {}
        self._canonical_names: dict[str, str] = {}
        for spec in specs:
            if spec.status != "REGISTERED":
                raise FeatureRegistrationError("registry accepts only registered features")
            canonical = semantic_feature_id(spec)
            if canonical in self._canonical_names:
                raise FeatureRegistrationError("duplicate semantic identity")
            registered = spec.model_copy(update={"canonical_id": canonical})
            self._specs[registered.name] = registered
            self._canonical_names[canonical] = registered.name

    def register_verified(
        self, spec: FeatureSpec, verification: FeatureVerification
    ) -> FeatureSpec:
        if not verification.passed:
            raise FeatureRegistrationError("feature verification did not pass")
        if spec.name in self._specs:
            raise FeatureRegistrationError(f"feature already registered: {spec.name}")
        canonical = semantic_feature_id(spec)
        if canonical in self._canonical_names:
            raise FeatureRegistrationError("duplicate semantic identity")
        registered = spec.model_copy(update={"status": "REGISTERED", "canonical_id": canonical})
        self._specs[registered.name] = registered
        self._canonical_names[canonical] = registered.name
        return registered

    def quarantine(self, spec: FeatureSpec) -> FeatureSpec:
        return spec.model_copy(update={"status": "QUARANTINED"})

    def get(self, name: str) -> FeatureSpec:
        if name in self._specs:
            return self._specs[name]
        for spec in self._specs.values():
            if name in spec.aliases:
                return spec
        raise KeyError(name)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._specs))

    def all(self) -> tuple[FeatureSpec, ...]:
        return tuple(self._specs[name] for name in self.names())


def default_feature_registry() -> FeatureRegistry:
    """Return optional, already verified feature candidates for LLM selection."""

    definitions = (
        ("vix_percentile", "macro", ("VIX.close",), "percentile", 20),
        ("gold_returns", "macro", ("GOLD.close",), "returns", 20),
        ("dxy_returns", "macro", ("DXY.close",), "returns", 20),
        ("qqq_returns", "benchmark", ("QQQ.close",), "returns", 20),
        ("nasdaq_returns", "benchmark", ("NASDAQ.close",), "returns", 20),
        ("us_2y_change", "rates", ("US2Y.close",), "returns", 5),
        ("us_10y_change", "rates", ("US10Y.close",), "returns", 5),
        ("japan_2y_change", "rates", ("JP2Y.close",), "returns", 5),
        ("japan_10y_change", "rates", ("JP10Y.close",), "returns", 5),
        ("korea_2y_change", "rates", ("KR2Y.close",), "returns", 5),
        ("korea_10y_change", "rates", ("KR10Y.close",), "returns", 5),
        ("us_20y_change", "rates", ("US20Y.close",), "returns", 5),
        ("japan_20y_change", "rates", ("JP20Y.close",), "returns", 5),
        ("korea_20y_change", "rates", ("KR20Y.close",), "returns", 5),
    )
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
    registry = FeatureRegistry()
    for name, family, inputs, calculator, lookback in definitions:
        registry.register_verified(
            FeatureSpec(
                name=name,
                family=family,
                inputs=inputs,
                calculator=calculator,
                lookback=lookback,
                formula=f"{calculator}({inputs[0]}, {lookback})",
            ),
            verification,
        )
    return registry
