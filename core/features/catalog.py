from __future__ import annotations

import re
from dataclasses import dataclass

from core.features.contracts import FeatureSpec
from core.integrity.hashes import content_hash


@dataclass(frozen=True)
class FeatureCatalog:
    _features: tuple[FeatureSpec, ...]

    def __post_init__(self) -> None:
        names: set[str] = set()
        aliases: set[str] = set()
        for feature in self._features:
            if feature.name in names or feature.name in aliases:
                raise ValueError(f"duplicate catalog name: {feature.name}")
            names.add(feature.name)
            for alias in feature.aliases:
                if alias in names or alias in aliases:
                    raise ValueError(f"duplicate catalog alias: {alias}")
                aliases.add(alias)

    def resolve(self, name: str) -> FeatureSpec:
        for feature in self._features:
            if name == feature.name or name in feature.aliases or name == feature.canonical_id:
                return feature
        raise KeyError(name)

    def all(self) -> tuple[FeatureSpec, ...]:
        return tuple(sorted(self._features, key=lambda item: item.name))

    def search(self, family: str) -> tuple[FeatureSpec, ...]:
        return tuple(feature for feature in self.all() if feature.family == family)

    def duplicates(self) -> dict[str, tuple[str, ...]]:
        groups: dict[str, list[str]] = {}
        for feature in self._features:
            group = feature.duplicate_group or feature.canonical_id
            groups.setdefault(group, []).append(feature.name)
        return {key: tuple(sorted(value)) for key, value in groups.items() if len(value) > 1}


def semantic_feature_id(spec: FeatureSpec) -> str:
    normalized_formula = re.sub(r"\s+", "", spec.formula.lower())
    payload = {
        "calculator": spec.calculator.lower(),
        "inputs": spec.inputs,
        "parameters": dict(sorted(spec.parameters.items())),
        "timeframe": spec.timeframe,
        "lag_bars": spec.lag_bars,
        "output_name": spec.output_name,
        "data_contract": spec.data_contract,
        "formula": normalized_formula,
    }
    return content_hash(payload)


def rate_series_ids() -> tuple[str, ...]:
    return (
        "US2Y", "US10Y", "US20Y", "JP2Y", "JP10Y", "JP20Y", "KR2Y", "KR10Y", "KR20Y"
    )


def _spec(
    name: str,
    family: str,
    calculator: str,
    inputs: tuple[str, ...] = ("close",),
    lookback: int = 14,
    *,
    aliases: tuple[str, ...] = (),
    parameters: dict[str, int | float | str | bool] | None = None,
    data_contract: str = "scalar",
) -> FeatureSpec:
    spec = FeatureSpec(
        name=name,
        family=family,
        inputs=inputs,
        calculator=calculator,
        lookback=lookback,
        parameters=parameters or {},
        formula=f"{calculator}({', '.join(inputs)}, {lookback})",
        aliases=aliases,
        data_contract=data_contract,  # type: ignore[arg-type]
        duplicate_group=name,
    )
    return spec.model_copy(update={"canonical_id": semantic_feature_id(spec)})


def imported_feature_catalog() -> FeatureCatalog:
    """Return the deduplicated source inventory available to the feature engine."""

    features: list[FeatureSpec] = [
        _spec("rsi", "momentum", "rsi", aliases=("relative_strength_index",)),
        _spec("rsi.wilder", "momentum", "rsi", parameters={"method": "wilder"}),
        _spec("rsi.ema", "momentum", "rsi", parameters={"method": "ema"}),
    ]
    definitions = (
        ("sma", "trend", "sma"), ("ema", "trend", "ema"), ("wma", "trend", "wma"),
        ("hma", "trend", "hma"), ("dema", "trend", "dema"), ("tema", "trend", "tema"),
        ("kama", "trend", "kama"), ("macd", "momentum", "macd"),
        ("stochastic", "momentum", "stochastic"), ("williams_r", "momentum", "williams_r"),
        ("cci", "momentum", "cci"), ("trix", "momentum", "trix"),
        ("tsi", "momentum", "tsi"), ("vortex", "trend", "vortex"),
        ("aroon", "trend", "aroon"), ("supertrend", "trend", "supertrend"),
        ("ichimoku", "trend", "ichimoku"), ("parabolic_sar", "trend", "parabolic_sar"),
        ("atr", "volatility", "atr"), ("true_range", "volatility", "true_range"),
        ("bollinger", "volatility", "bollinger"), ("keltner", "volatility", "keltner"),
        ("donchian", "volatility", "donchian"), ("normalized_atr", "volatility", "normalized_atr"),
        ("ulcer_index", "volatility", "ulcer_index"), ("obv", "volume", "obv"),
        ("vwap", "volume", "vwap"), ("adl", "volume", "adl"),
        ("cmf", "volume", "cmf"), ("mfi", "volume", "mfi"),
        ("force_index", "volume", "force_index"), ("pvt", "volume", "pvt"),
        ("fisher", "cycles", "fisher"), ("dpo", "cycles", "dpo"),
        ("zscore", "statistics", "zscore"), ("hurst", "statistics", "hurst"),
        ("entropy", "statistics", "entropy"), ("log_returns", "statistics", "log_returns"),
        ("cusum", "statistics", "cusum"),
    )
    features.extend(_spec(name, family, calculator) for name, family, calculator in definitions)
    return FeatureCatalog(tuple(features))
