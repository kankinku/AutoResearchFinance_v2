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
        ("returns", "statistics", "returns"),
    )
    definition_input_map = {
        "stochastic": ("high", "low", "close"),
        "williams_r": ("high", "low", "close"),
        "cci": ("high", "low", "close"),
        "vortex": ("high", "low", "close"),
        "aroon": ("high", "low"),
        "supertrend": ("high", "low", "close"),
        "ichimoku": ("high", "low", "close"),
        "parabolic_sar": ("high", "low"),
        "atr": ("high", "low", "close"),
        "true_range": ("high", "low", "close"),
        "keltner": ("high", "low", "close"),
        "donchian": ("high", "low"),
        "normalized_atr": ("high", "low", "close"),
        "obv": ("close", "volume"),
        "vwap": ("high", "low", "close", "volume"),
        "adl": ("high", "low", "close", "volume"),
        "cmf": ("high", "low", "close", "volume"),
        "mfi": ("high", "low", "close", "volume"),
        "force_index": ("close", "volume"),
        "pvt": ("close", "volume"),
        "fisher": ("high", "low"),
    }
    features.extend(
        _spec(
            name,
            family,
            calculator,
            inputs=definition_input_map.get(name, ("close",)),
            status="REGISTERED",
        )
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
        ("session_flag", "session", "session_flag"),
        ("time_of_day", "session", "time_of_day"),
        ("day_of_week", "session", "day_of_week"),
        ("session_overlay_flags", "session", "session_overlay_flags"),
        ("time_since_extreme", "session", "time_since_extreme"),
        ("volume_profile", "profile", "volume_profile"),
        ("tpo_profile", "profile", "tpo_profile"),
        ("order_flow_delta", "order_flow", "order_flow_delta"),
        ("order_flow_imbalance", "order_flow", "order_flow_imbalance"),
        ("weis_wyckoff", "order_flow", "weis_wyckoff"),
        ("roc", "momentum", "roc"),
        ("momentum", "momentum", "momentum"),
        ("dmi_adx", "trend", "dmi_adx"),
        ("slope_of_ema", "trend", "slope_of_ema"),
        ("linear_regression", "trend", "linear_regression"),
        ("median_price", "trend", "median_price"),
        ("typical_price", "trend", "typical_price"),
        ("donchian_channel_width", "volatility", "donchian_channel_width"),
        ("standard_deviation", "volatility", "standard_deviation"),
        ("relative_volatility_index", "volatility", "relative_volatility_index"),
        ("ease_of_movement", "volume", "ease_of_movement"),
        ("price_roc", "price_action", "price_roc"),
        ("bar_range_ratio", "price_action", "bar_range_ratio"),
        ("wick_ratio", "price_action", "wick_ratio"),
        ("high_low_breakout", "price_action", "high_low_breakout"),
        ("trend_candle_strength", "price_action", "trend_candle_strength"),
        ("price_action_score", "price_action", "price_action_score"),
        ("detect_marubozu", "price_action", "detect_marubozu"),
        ("detect_three_bar_reversal", "price_action", "detect_three_bar_reversal"),
        ("phase_accumulation_cycle", "cycles", "phase_accumulation_cycle"),
        ("inverse_fisher_transform", "cycles", "inverse_fisher_transform"),
        ("super_smoother", "cycles", "super_smoother"),
        ("roofing_filter", "cycles", "roofing_filter"),
        ("center_of_gravity", "cycles", "center_of_gravity"),
        ("bandpass_filter", "cycles", "bandpass_filter"),
        ("dc_based_rsi", "cycles", "dc_based_rsi"),
        ("cyber_cycle", "cycles", "cyber_cycle"),
        ("hilbert_transform", "cycles", "hilbert_transform"),
        ("tsf", "trend", "tsf"),
    )
    input_map = {
        "qstick": ("open", "close"),
        "normalized_atr_percent": ("high", "low", "close"),
        "vwma": ("close", "volume"),
        "ultimate_oscillator": ("high", "low", "close"),
        "smi": ("high", "low", "close"),
        "chaikin_volatility": ("high", "low"),
        "atr_percent": ("high", "low", "close"),
        "mass_index": ("high", "low"),
        "garman_klass": ("open", "high", "low", "close"),
        "parkinson": ("high", "low"),
        "range_volatility": ("high", "low"),
        "volume_oscillator": ("volume",),
        "volume_roc": ("volume",),
        "volume_delta": ("close", "volume"),
        "intraday_intensity": ("close", "high", "low", "volume"),
        "vw_macd": ("high", "low", "close", "volume"),
        "smoothed_obv": ("close", "volume"),
        "klinger": ("high", "low", "close", "volume"),
        "vfi": ("high", "low", "close", "volume"),
        "pvi": ("close", "volume"),
        "nvi": ("close", "volume"),
        "pivot_points": ("high", "low", "close"),
        "heikin_ashi": ("open", "high", "low", "close"),
        "engulfing": ("open", "high", "low", "close"),
        "doji": ("open", "high", "low", "close"),
        "pin_bar": ("open", "high", "low", "close"),
        "hammer": ("open", "high", "low", "close"),
        "shooting_star": ("open", "high", "low", "close"),
        "morning_star": ("open", "high", "low", "close"),
        "evening_star": ("open", "high", "low", "close"),
        "inside_bar": ("high", "low"),
        "outside_bar": ("high", "low"),
        "support_resistance": ("high", "low"),
        "higher_high_lower_low": ("high", "low"),
        "fractal": ("high", "low"),
        "normalized_time_of_day": ("session",),
        "session_high": ("session",),
        "session_low": ("session",),
        "session_flag": ("session",),
        "time_of_day": ("session",),
        "day_of_week": ("session",),
        "session_overlay_flags": ("session",),
        "dmi_adx": ("high", "low", "close"),
        "median_price": ("high", "low"),
        "typical_price": ("high", "low", "close"),
        "donchian_channel_width": ("high", "low"),
        "ease_of_movement": ("high", "low", "volume"),
        "bar_range_ratio": ("open", "close", "high", "low"),
        "wick_ratio": ("open", "close", "high", "low"),
        "trend_candle_strength": ("open", "close"),
        "detect_marubozu": ("open", "close", "high", "low"),
        "detect_three_bar_reversal": ("close",),
    }
    contract_map = {
        "normalized_time_of_day": "session",
        "session_high": "session",
        "session_low": "session",
        "session_flag": "session",
        "time_of_day": "session",
        "day_of_week": "session",
        "session_overlay_flags": "session",
        "time_since_extreme": "scalar",
    }
    features.extend(
        _spec(
            name,
            family,
            calculator,
            inputs=input_map.get(name, ("close",)),
            data_contract=contract_map.get(
                name, family if family in {"profile", "order_flow", "session"} else "scalar"
            ),
            status="REGISTERED" if calculator in _IMPLEMENTED_CALCULATORS else "PROPOSED",
        )
        for name, family, calculator in proposed
        if name not in {feature.name for feature in features}
    )
    aliases_by_name = {
        "stochastic": ("stochastic_oscillator",),
        "williams_r": ("williams_percent_r",),
        "fisher": ("fisher_transform",),
        "dpo": ("detrended_price_oscillator",),
        "dti": ("directional_trend_index",),
        "rvi": ("relative_vigor_index",),
        "tsi": ("true_strength_index",),
        "cmo": ("chande_momentum_oscillator",),
        "vortex": ("vortex_indicator",),
        "returns": ("simple_returns",),
        "fractional_difference": ("fractional_diff",),
        "cusum": ("cusum_filter",),
        "kalman_slope": ("kalman_filter_slope",),
        "hurst": ("hurst_exponent",),
        "renko": ("renko_boxes",),
        "engulfing": ("detect_engulfing",),
        "pin_bar": ("detect_pin_bar",),
        "fractal": ("detect_fractals",),
        "higher_high_lower_low": ("higher_highs_lower_lows",),
        "klinger": ("klinger_oscillator",),
        "vfi": ("volume_flow_indicator",),
        "pvt": ("price_volume_trend",),
        "mcginley": ("mcginley_dynamic",),
        "garman_klass": ("garman_klass_volatility",),
        "parkinson": ("parkinson_volatility",),
        "range_volatility": ("range_based_volatility",),
        "standard_deviation": ("std_dev",),
        "bollinger": ("bollinger_bands",),
        "keltner": ("keltner_channel",),
        "donchian": ("donchian_channel",),
    }
    features = [
        feature.model_copy(
            update={
                "aliases": tuple(
                    dict.fromkeys(feature.aliases + aliases_by_name.get(feature.name, ()))
                )
            }
        )
        for feature in features
    ]
    return FeatureCatalog(tuple(features))


_IMPLEMENTED_CALCULATORS = frozenset(
    {
        "tma",
        "vidya",
        "cmo",
        "vwma",
        "mcginley",
        "zero_lag_ema",
        "fama",
        "stoch_rsi",
        "rvi",
        "rsx",
        "ultimate_oscillator",
        "dti",
        "laguerre_rsi",
        "smi",
        "macd_signal",
        "macd_histogram",
        "historical_volatility",
        "volatility_ratio",
        "atr_percent",
        "mass_index",
        "garman_klass",
        "parkinson",
        "range_volatility",
        "volume_oscillator",
        "volume_roc",
        "volume_delta",
        "smoothed_obv",
        "pvi",
        "nvi",
        "normalized_atr_percent",
        "intraday_intensity",
        "support_resistance",
        "time_since_extreme",
        "adaptive_cycle_divergence",
        "chaikin_volatility",
        "connors_rsi",
        "dominant_cycle",
        "evening_star",
        "fractional_difference",
        "guppy_mma",
        "hilbert_phase",
        "hilbert_sine",
        "hilbert_trendline",
        "itrend",
        "kl_divergence",
        "klinger",
        "laguerre",
        "morning_star",
        "moving_average_envelope",
        "pin_bar",
        "qstick",
        "schaff_trend_cycle",
        "shannon_entropy",
        "shooting_star",
        "vfi",
        "vw_macd",
        "normalized_time_of_day",
        "session_high",
        "session_low",
        "session_flag",
        "time_of_day",
        "day_of_week",
        "session_overlay_flags",
        "roc",
        "momentum",
        "dmi_adx",
        "slope_of_ema",
        "linear_regression",
        "median_price",
        "typical_price",
        "donchian_channel_width",
        "standard_deviation",
        "relative_volatility_index",
        "ease_of_movement",
        "price_roc",
        "bar_range_ratio",
        "wick_ratio",
        "high_low_breakout",
        "trend_candle_strength",
        "price_action_score",
        "detect_marubozu",
        "detect_three_bar_reversal",
        "phase_accumulation_cycle",
        "inverse_fisher_transform",
        "super_smoother",
        "roofing_filter",
        "center_of_gravity",
        "bandpass_filter",
        "dc_based_rsi",
        "cyber_cycle",
        "hilbert_transform",
        "tsf",
        "pivot_points",
        "zigzag",
        "heikin_ashi",
        "renko",
        "engulfing",
        "doji",
        "hammer",
        "inside_bar",
        "outside_bar",
        "higher_high_lower_low",
        "fractal",
        "fractal_dimension",
        "kalman_slope",
        "minmax_scale",
        "robust_scale",
        "rolling_skewness",
        "rolling_kurtosis",
        "mad",
        "percentile_rank",
        "returns",
        "volume_profile",
        "tpo_profile",
        "order_flow_delta",
        "order_flow_imbalance",
        "weis_wyckoff",
    }
)
