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
    return ("US2Y", "US10Y", "US20Y", "JP2Y", "JP10Y", "JP20Y", "KR2Y", "KR10Y", "KR20Y")


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
    status: str = "PROPOSED",
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
        status=status,  # type: ignore[arg-type]
    )
    return spec.model_copy(update={"canonical_id": semantic_feature_id(spec)})


def imported_feature_catalog() -> FeatureCatalog:
    """Return the deduplicated source inventory available to the feature engine."""

    features: list[FeatureSpec] = [
        _spec("rsi", "momentum", "rsi", aliases=("relative_strength_index",), status="REGISTERED"),
        _spec(
            "rsi.wilder", "momentum", "rsi", parameters={"method": "wilder"}, status="REGISTERED"
        ),
        _spec("rsi.ema", "momentum", "rsi", parameters={"method": "ema"}, status="REGISTERED"),
    ]
    definitions = (
        ("sma", "trend", "sma"),
        ("ema", "trend", "ema"),
        ("wma", "trend", "wma"),
        ("hma", "trend", "hma"),
        ("dema", "trend", "dema"),
        ("tema", "trend", "tema"),
        ("kama", "trend", "kama"),
        ("macd", "momentum", "macd"),
        ("stochastic", "momentum", "stochastic"),
        ("williams_r", "momentum", "williams_r"),
        ("cci", "momentum", "cci"),
        ("trix", "momentum", "trix"),
        ("tsi", "momentum", "tsi"),
        ("vortex", "trend", "vortex"),
        ("aroon", "trend", "aroon"),
        ("supertrend", "trend", "supertrend"),
        ("ichimoku", "trend", "ichimoku"),
        ("parabolic_sar", "trend", "parabolic_sar"),
        ("atr", "volatility", "atr"),
        ("true_range", "volatility", "true_range"),
        ("bollinger", "volatility", "bollinger"),
        ("keltner", "volatility", "keltner"),
        ("donchian", "volatility", "donchian"),
        ("normalized_atr", "volatility", "normalized_atr"),
        ("ulcer_index", "volatility", "ulcer_index"),
        ("obv", "volume", "obv"),
        ("vwap", "volume", "vwap"),
        ("adl", "volume", "adl"),
        ("cmf", "volume", "cmf"),
        ("mfi", "volume", "mfi"),
        ("force_index", "volume", "force_index"),
        ("pvt", "volume", "pvt"),
        ("fisher", "cycles", "fisher"),
        ("dpo", "cycles", "dpo"),
        ("zscore", "statistics", "zscore"),
        ("hurst", "statistics", "hurst"),
        ("entropy", "statistics", "entropy"),
        ("log_returns", "statistics", "log_returns"),
        ("cusum", "statistics", "cusum"),
    )
    features.extend(
        _spec(name, family, calculator, status="REGISTERED")
        for name, family, calculator in definitions
    )
    proposed = (
        ("tma", "trend", "tma"),
        ("vidya", "trend", "vidya"),
        ("cmo", "momentum", "cmo"),
        ("vwma", "trend", "vwma"),
        ("mcginley", "trend", "mcginley"),
        ("zero_lag_ema", "trend", "zero_lag_ema"),
        ("fama", "trend", "fama"),
        ("guppy_mma", "trend", "guppy_mma"),
        ("moving_average_envelope", "trend", "moving_average_envelope"),
        ("stoch_rsi", "momentum", "stoch_rsi"),
        ("rvi", "momentum", "rvi"),
        ("rsx", "momentum", "rsx"),
        ("ultimate_oscillator", "momentum", "ultimate_oscillator"),
        ("connors_rsi", "momentum", "connors_rsi"),
        ("schaff_trend_cycle", "momentum", "schaff_trend_cycle"),
        ("dti", "momentum", "dti"),
        ("laguerre_rsi", "momentum", "laguerre_rsi"),
        ("smi", "momentum", "smi"),
        ("qstick", "momentum", "qstick"),
        ("macd_signal", "momentum", "macd_signal"),
        ("macd_histogram", "momentum", "macd_histogram"),
        ("normalized_atr_percent", "volatility", "normalized_atr_percent"),
        ("historical_volatility", "volatility", "historical_volatility"),
        ("chaikin_volatility", "volatility", "chaikin_volatility"),
        ("volatility_ratio", "volatility", "volatility_ratio"),
        ("atr_percent", "volatility", "atr_percent"),
        ("mass_index", "volatility", "mass_index"),
        ("garman_klass", "volatility", "garman_klass"),
        ("parkinson", "volatility", "parkinson"),
        ("range_volatility", "volatility", "range_volatility"),
        ("volume_oscillator", "volume", "volume_oscillator"),
        ("volume_roc", "volume", "volume_roc"),
        ("volume_delta", "volume", "volume_delta"),
        ("intraday_intensity", "volume", "intraday_intensity"),
        ("vw_macd", "volume", "vw_macd"),
        ("smoothed_obv", "volume", "smoothed_obv"),
        ("klinger", "volume", "klinger"),
        ("vfi", "volume", "vfi"),
        ("pvi", "volume", "pvi"),
        ("nvi", "volume", "nvi"),
        ("pivot_points", "price_action", "pivot_points"),
        ("zigzag", "price_action", "zigzag"),
        ("heikin_ashi", "price_action", "heikin_ashi"),
        ("renko", "price_action", "renko"),
        ("engulfing", "price_action", "engulfing"),
        ("doji", "price_action", "doji"),
        ("pin_bar", "price_action", "pin_bar"),
        ("hammer", "price_action", "hammer"),
        ("shooting_star", "price_action", "shooting_star"),
        ("morning_star", "price_action", "morning_star"),
        ("evening_star", "price_action", "evening_star"),
        ("inside_bar", "price_action", "inside_bar"),
        ("outside_bar", "price_action", "outside_bar"),
        ("support_resistance", "price_action", "support_resistance"),
        ("higher_high_lower_low", "price_action", "higher_high_lower_low"),
        ("fractal", "price_action", "fractal"),
        ("hilbert_sine", "cycles", "hilbert_sine"),
        ("hilbert_phase", "cycles", "hilbert_phase"),
        ("hilbert_trendline", "cycles", "hilbert_trendline"),
        ("dominant_cycle", "cycles", "dominant_cycle"),
        ("itrend", "cycles", "itrend"),
        ("laguerre", "cycles", "laguerre"),
        ("adaptive_cycle_divergence", "cycles", "adaptive_cycle_divergence"),
        ("fractal_dimension", "statistics", "fractal_dimension"),
        ("kalman_slope", "statistics", "kalman_slope"),
        ("shannon_entropy", "statistics", "shannon_entropy"),
        ("kl_divergence", "statistics", "kl_divergence"),
        ("minmax_scale", "statistics", "minmax_scale"),
        ("robust_scale", "statistics", "robust_scale"),
        ("fractional_difference", "statistics", "fractional_difference"),
        ("rolling_skewness", "statistics", "rolling_skewness"),
        ("rolling_kurtosis", "statistics", "rolling_kurtosis"),
        ("mad", "statistics", "mad"),
        ("percentile_rank", "statistics", "percentile_rank"),
        ("normalized_time_of_day", "session", "normalized_time_of_day"),
        ("session_high", "session", "session_high"),
        ("session_low", "session", "session_low"),
        ("time_since_extreme", "session", "time_since_extreme"),
        ("volume_profile", "profile", "volume_profile"),
        ("tpo_profile", "profile", "tpo_profile"),
        ("order_flow_delta", "order_flow", "order_flow_delta"),
        ("order_flow_imbalance", "order_flow", "order_flow_imbalance"),
        ("weis_wyckoff", "order_flow", "weis_wyckoff"),
    )
    features.extend(
        _spec(
            name,
            family,
            calculator,
            data_contract=family if family in {"profile", "order_flow", "session"} else "scalar",
        )
        for name, family, calculator in proposed
        if name not in {feature.name for feature in features}
    )
    return FeatureCatalog(tuple(features))
